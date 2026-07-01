"""
The bot runner — orchestrates one cycle and the scheduler around it.

Each cycle (APScheduler, every ``cycle_seconds``):
  1. **Reconcile first** — the exchange is the source of truth. Pull price,
     balances, open orders, and (live/testnet) new fills.
  2. **Recompute live metrics** on fresh klines (ATR%, vol, fill-rate, TIR).
  3. **Daily loss check** — breach => panic (cancel all + halt).
  4. **Decide** hold vs reposition via the deterministic engine (hysteresis +
     walk-forward validation), honouring the kill-switch and throttle.
  5. **Optional AI advisor** (slow cadence) — advisory only, clamped + re-validated.
  6. **Apply** a validated reposition idempotently (cancel stale -> seed -> place).
  7. Update the snapshot + action log; broadcast to the dashboard.

All exchange mutation happens here or via :meth:`panic`; both are guarded by a
lock so the API thread and the scheduler never race.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from ..config import Mode, Settings
from ..db import Store
from ..exchange import Adapter, build_adapter
from ..models import ActiveGrid, Decision, GridConfig, PnL
from ..strategy.engine import backtest, build_levels
from ..strategy.metrics import compute_live_metrics
from ..strategy.montecarlo import mc_model_params, monte_carlo, steps_for_horizon
from . import advisor, decision
from .safety import Safety
from .state import FillTracker

_TF_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "12h": 43200, "1d": 86400,
}
_MC_HORIZON_SEC = 7 * 86400
_MC_PATHS = 150


class BotRunner:
    def __init__(self, settings: Settings, store: Store,
                 on_update: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.settings = settings
        self.store = store
        self.safety = Safety(settings, store)
        self.on_update = on_update
        self._cycle_lock = threading.RLock()   # serialises cycles + all trading
        self._snap_lock = threading.RLock()    # brief; keeps status reads responsive
        self._scheduler = None
        self._running = False
        self._cycle = int(store.get_state("cycle", 0))
        self._last_error: str | None = None
        self._ai_advice: dict[str, Any] | None = None

        self.adapter: Adapter = build_adapter(settings)
        # refuse to run if the key can withdraw (live/testnet); dry-run is a no-op
        self.adapter.startup_checks()

        self.active: ActiveGrid | None = self._load_active()
        self.fills = FillTracker.from_state(store.get_state("fills"))
        self.snapshot: dict[str, Any] = self._empty_snapshot()

    # ---------------------------------------------------------------- state
    def _load_active(self) -> ActiveGrid | None:
        s = self.store.get_state("active_grid")
        if not s:
            return None
        c = s["config"]
        return ActiveGrid(
            config=GridConfig(c["lower"], c["upper"], c["grids"], c["mode"]),
            epoch=int(s["epoch"]),
            set_price=float(s["set_price"]),
            set_atr_pct=float(s["set_atr_pct"]),
            set_time=float(s["set_time"]),
            levels=list(s.get("levels", [])),
        )

    def _persist_active(self) -> None:
        self.store.set_state("active_grid", self.active.to_dict() if self.active else None)

    def _empty_snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.settings.mode.value,
            "running": self._running,
            "halted": self.safety.is_halted(),
            "halt_reason": self.safety.halt_reason(),
            "symbol": self.settings.symbol,
            "price": None,
            "balances": None,
            "open_orders": [],
            "active_grid": self.active.to_dict() if self.active else None,
            "metrics": None,
            "pnl": None,
            "last_decision": None,
            "monte_carlo": None,
            "ai_advice": None,
            "daily": {
                "intraday_pnl": 0.0,
                "repositions_today": self.safety.repositions_today(),
                "max_repositions": self.settings.max_repositions_per_day,
                "max_daily_loss": self.settings.max_daily_loss,
            },
            "cycle": self._cycle,
            "last_cycle_ts": None,
            "last_error": None,
        }

    def get_snapshot(self) -> dict[str, Any]:
        # uses only the brief snapshot lock, never the cycle lock, so reads stay
        # responsive even while a cycle is mid-network.
        with self._snap_lock:
            snap = dict(self.snapshot)
        snap["running"] = self._running
        snap["halted"] = self.safety.is_halted()
        snap["halt_reason"] = self.safety.halt_reason()
        return snap

    def _broadcast(self) -> None:
        if self.on_update:
            try:
                self.on_update(self.get_snapshot())
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> None:
        with self._cycle_lock:
            if self._running:
                return
            self._running = True
            self.store.set_state("running", True)
            from apscheduler.schedulers.background import BackgroundScheduler
            self._scheduler = BackgroundScheduler(daemon=True)
            self._scheduler.add_job(
                self.run_cycle, "interval", seconds=self.settings.cycle_seconds,
                id="cycle", max_instances=1, coalesce=True,
            )
            self._scheduler.start()
            self.store.log("info", "start", f"bot started in {self.settings.mode.value} mode")
        # run one cycle immediately (outside the lock so it can take the lock itself)
        self.run_cycle()

    def stop(self) -> None:
        with self._cycle_lock:
            self._running = False
            self.store.set_state("running", False)
            if self._scheduler:
                try:
                    self._scheduler.shutdown(wait=False)
                except Exception:  # noqa: BLE001
                    pass
                self._scheduler = None
            self.store.log("info", "stop", "bot stopped (grid left in place)")
        self._broadcast()

    def panic(self, reason: str = "manual panic") -> dict[str, Any]:
        """Kill-switch: halt immediately, then cancel all open orders. Idempotent.

        The halt flag is set first (before taking the trading lock) so that even a
        cycle running concurrently will see ``is_halted()`` and skip placing new
        orders at its pre-apply re-check.
        """
        self.safety.halt(reason)
        self._running = False
        self.store.set_state("running", False)
        with self._cycle_lock:
            cancelled = 0
            try:
                cancelled = self.adapter.cancel_all()
            except Exception as e:  # noqa: BLE001
                self.store.log("error", "panic", f"cancel_all failed: {e}")
            if self._scheduler:
                try:
                    self._scheduler.shutdown(wait=False)
                except Exception:  # noqa: BLE001
                    pass
                self._scheduler = None
            self.store.log("safety", "panic", reason, {"cancelled": cancelled})
        with self._snap_lock:
            self.snapshot["open_orders"] = []
        self._broadcast()
        return {"cancelled": cancelled, "halted": True, "reason": reason}

    def resume(self) -> None:
        self.safety.resume()
        self._broadcast()

    # ---------------------------------------------------------------- cycle
    def run_cycle(self) -> None:
        with self._cycle_lock:
            self._cycle += 1
            self.store.set_state("cycle", self._cycle)
            try:
                self._cycle_body()
                self._last_error = None
            except Exception as e:  # noqa: BLE001 - a cycle must never kill the scheduler
                self._last_error = f"{type(e).__name__}: {e}"
                self.snapshot["last_error"] = self._last_error
                self.store.log("error", "cycle", self._last_error, {"cycle": self._cycle})
        self._broadcast()

    def _cycle_body(self) -> None:
        s = self.settings
        cyc = self._cycle

        # 1. reconcile — exchange is the source of truth
        price = self.adapter.market_price()
        balances = self.adapter.fetch_balances()
        open_orders = [o.to_dict() for o in self.adapter.fetch_open_orders()]
        if s.mode in (Mode.TESTNET, Mode.LIVE):
            since = (self.fills.last_trade_ts or None)
            new_trades = self.adapter.fetch_my_trades(since)
            applied = self.fills.ingest(new_trades, s.base_asset, s.quote_asset)
            if applied:
                self.store.set_state("fills", self.fills.to_state())

        # 2. fresh klines + live metrics for the CURRENT (or default) config
        candles = self.adapter.fetch_ohlcv(s.kline_interval, s.history_candles)
        cur_cfg = self.active.config if self.active else GridConfig(
            price * (1 - s.auto_range_pct), price * (1 + s.auto_range_pct), s.grids, s.grid_mode
        )
        params = {
            "lower": cur_cfg.lower, "upper": cur_cfg.upper, "grids": cur_cfg.grids,
            "mode": cur_cfg.mode, "invest": s.invest, "fee": s.fee_pct,
            "slip_bps": s.slip_bps, "entry": 0, "sell_all_on_stop": True,
        }
        metrics = compute_live_metrics(candles, params)

        # 3. PnL
        if s.mode == Mode.DRY_RUN:
            r = metrics.result
            pnl = PnL(realized=r.grid_profit, floating=r.floating, total=r.total,
                      inventory_qty=r.inv_qty_end, inventory_cost=r.inv_value_end)
        else:
            pnl = self.fills.pnl(price)

        # 4. daily loss limit
        breached, intraday = self.safety.check_daily_loss(pnl.total)
        if breached and not self.safety.is_halted():
            self.store.log("safety", "daily_loss", f"intraday PnL {intraday:.2f} breached "
                           f"-{s.max_daily_loss}", {"intraday": intraday})
            self.panic(f"daily loss limit breached ({intraday:.2f})")
            self._update_snapshot(price, balances, [], metrics, pnl, None, None, intraday, cyc)
            return

        # 5. decision (skip if halted)
        if self.safety.is_halted():
            dec = Decision(action="hold", reason="halted (kill-switch active)", metrics=metrics.to_dict())
            self._update_snapshot(price, balances, open_orders, metrics, pnl, dec, None, intraday, cyc)
            self.store.log("decision", "hold", dec.reason, {}, cyc)
            return

        can_repo, throttle_reason = self.safety.can_reposition()
        dec = decision.evaluate(s, price, self.active, metrics, candles, can_repo, throttle_reason)

        # 6. optional AI advisor (slow cadence; advisory only)
        if s.use_ai and dec.candidate is not None and (cyc % max(1, s.ai_cadence_cycles) == 0):
            self._consult_advisor(dec, price, metrics, candles)

        # 7. apply (only when running; a stopped bot decides but never trades)
        mc = None
        if dec.action in ("deploy", "reposition") and dec.candidate is not None:
            if s.reject_overfit and not dec.validated and dec.action == "reposition":
                # a reposition (not the first deploy) must be validated out-of-sample
                self.store.log("decision", "hold",
                               "candidate not out-of-sample validated; holding",
                               {"candidate": dec.candidate.to_dict(), "wf": dec.walk_forward}, cyc)
                dec = Decision(action="hold",
                               reason="candidate not out-of-sample validated; holding",
                               triggers=dec.triggers, metrics=metrics.to_dict(),
                               walk_forward=dec.walk_forward, rejected_reason="overfit")
            elif not self._running or self.safety.is_halted():
                # bot stopped, or panic fired mid-cycle: decide but don't trade
                self.store.log("decision", "would_" + dec.action,
                               f"would {dec.action} but bot is not actively trading",
                               {"candidate": dec.candidate.to_dict()}, cyc)
            else:
                self._apply_reposition(dec, price, metrics, cyc)
                open_orders = [o.to_dict() for o in self.adapter.fetch_open_orders()]

        # Monte Carlo distribution for the dashboard (current/active grid)
        mc = self._run_mc(candles, cur_cfg, metrics.atr_pct, price)

        self._update_snapshot(price, balances, open_orders, metrics, pnl, dec, mc, intraday, cyc)
        if dec.action == "hold":
            self.store.log("decision", "hold", dec.reason, {"triggers": dec.triggers}, cyc)

    # ---------------------------------------------------------------- advisor
    def _consult_advisor(self, dec: Decision, price: float, metrics, candles) -> None:
        summary = {
            "symbol": self.settings.symbol,
            "mode": self.settings.mode.value,
            "price": round(price, 6),
            "metrics": metrics.to_dict(),
            "proposed_action": dec.action,
            "proposed_candidate": dec.candidate.to_dict() if dec.candidate else None,
            "triggers": dec.triggers,
        }
        advice = advisor.get_advice(self.settings, summary)
        self._ai_advice = advice
        if not advice or advice.get("error"):
            self.store.log("ai", "advice", "advisor unavailable/no-action",
                           {"detail": (advice or {}).get("error")})
            return
        self.store.log("ai", "advice", advice.get("explanation", ""),
                       {"sanity": advice.get("sanity"), "why": advice.get("why")})
        # apply a clamped, re-validated tweak — never in live without confirmation
        if self.settings.mode == Mode.LIVE:
            return
        if dec.candidate is None:
            return
        nudged = advisor.clamp_nudge(
            self.settings, dec.candidate.grids, dec.candidate.lower, dec.candidate.upper, advice
        )
        if not nudged:
            return
        grids, lower, upper, note = nudged
        new_cand = GridConfig(lower=lower, upper=upper, grids=grids, mode=dec.candidate.mode)
        from ..strategy.optimizer import evaluate_candidate  # re-validate the nudged grid
        res = evaluate_candidate(
            candles, 0, len(candles) - 1,
            {"lower": lower, "upper": upper, "grids": grids, "mode": dec.candidate.mode,
             "invest": self.settings.invest, "fee": self.settings.fee_pct,
             "slip_bps": self.settings.slip_bps, "entry": 0, "sell_all_on_stop": True,
             "record_trades": False},
        )
        if res.get("overfit") and self.settings.reject_overfit:
            self.store.log("ai", "advice", f"{note} rejected (failed re-validation)", {})
            return
        dec.candidate = new_cand
        dec.reason = f"{dec.reason} [{note}]"
        self.store.log("ai", "advice", f"{note} applied (re-validated)", {})

    # ---------------------------------------------------------------- reposition
    def _apply_reposition(self, dec: Decision, price: float, metrics, cyc: int) -> None:
        cand = dec.candidate
        assert cand is not None
        s = self.settings
        new_epoch = (self.active.epoch + 1) if self.active else 1

        levels = build_levels(cand.lower, cand.upper, cand.grids, cand.mode)
        cells = cand.grids
        sum_buy_lines = sum(levels[i] for i in range(cells - 1)) or 1.0
        q = s.invest / sum_buy_lines

        seeded = [i for i in range(cells) if levels[i] >= price]
        seed_qty = len(seeded) * q

        # cancel stale orders (any epoch) — cancel-then-place
        cancelled = 0
        try:
            cancelled = self.adapter.cancel_all()
        except Exception as e:  # noqa: BLE001
            self.store.log("error", "reposition", f"cancel_all failed: {e}", {}, cyc)

        placed = 0
        skipped = 0
        # seed inventory for the sell side (no-op in dry-run)
        try:
            if seed_qty > 0:
                self.adapter.seed_inventory(seed_qty)
        except Exception as e:  # noqa: BLE001
            self.store.log("error", "reposition", f"seed_inventory failed: {e}", {}, cyc)

        for i in range(cells):
            try:
                if levels[i] >= price:
                    o = self.adapter.place_limit("sell", levels[i + 1], q, f"gb-{new_epoch}-s-{i}")
                else:
                    o = self.adapter.place_limit("buy", levels[i], q, f"gb-{new_epoch}-b-{i}")
                if o is None:
                    skipped += 1
                else:
                    placed += 1
            except Exception as e:  # noqa: BLE001
                skipped += 1
                self.store.log("error", "reposition", f"place failed at level {i}: {e}", {}, cyc)

        self.active = ActiveGrid(
            config=cand, epoch=new_epoch, set_price=price,
            set_atr_pct=metrics.atr_pct, set_time=time.time(), levels=levels,
        )
        self._persist_active()
        self.safety.record_reposition()
        self.store.log("reposition", dec.action, dec.reason, {
            "epoch": new_epoch,
            "config": cand.to_dict(),
            "qty_per_order": q,
            "seed_qty": seed_qty,
            "placed": placed,
            "skipped": skipped,
            "cancelled": cancelled,
            "validated": dec.validated,
            "walk_forward": dec.walk_forward,
            "dry_run": s.mode == Mode.DRY_RUN,
        }, cyc)

    # ---------------------------------------------------------------- monte carlo
    def _run_mc(self, candles, cfg: GridConfig, atr_pct: float, price: float):
        try:
            ref_sec = _TF_SECONDS.get(self.settings.kline_interval, 3600)
            steps, step_sec = steps_for_horizon(_MC_HORIZON_SEC)
            vol_per_step, drift = mc_model_params(atr_pct, step_sec, ref_sec)
            real = candles[-400:]
            bt_cfg = {
                "lower": cfg.lower, "upper": cfg.upper, "grids": cfg.grids, "mode": cfg.mode,
                "invest": self.settings.invest, "fee": self.settings.fee_pct,
                "slip_bps": self.settings.slip_bps, "entry": 0,
                "sell_all_on_stop": True, "record_trades": False,
            }
            last_ts = real[-1]["t"] if real else int(time.time())
            res = monte_carlo(real, bt_cfg, price, last_ts, _MC_HORIZON_SEC,
                              _MC_PATHS, vol_per_step, drift, base_seed=12345, trend=0.5)
            res.pop("totals", None)  # don't ship the raw array every cycle
            res["horizon_days"] = _MC_HORIZON_SEC / 86400
            return res
        except Exception:  # noqa: BLE001 - MC is decorative; never break the cycle
            return None

    # ---------------------------------------------------------------- snapshot
    def _update_snapshot(self, price, balances, open_orders, metrics, pnl: PnL,
                         dec: Decision | None, mc, intraday: float, cyc: int) -> None:
        with self._snap_lock:
            self._snapshot_update(price, balances, open_orders, metrics, pnl, dec, mc, intraday, cyc)

    def _snapshot_update(self, price, balances, open_orders, metrics, pnl, dec, mc, intraday, cyc) -> None:
        self.snapshot.update({
            "mode": self.settings.mode.value,
            "running": self._running,
            "halted": self.safety.is_halted(),
            "halt_reason": self.safety.halt_reason(),
            "symbol": self.settings.symbol,
            "price": price,
            "balances": balances,
            "open_orders": open_orders,
            "active_grid": self.active.to_dict() if self.active else None,
            "metrics": metrics.to_dict() if metrics else None,
            "pnl": pnl.to_dict() if pnl else None,
            "last_decision": dec.to_dict() if dec else self.snapshot.get("last_decision"),
            "monte_carlo": mc if mc is not None else self.snapshot.get("monte_carlo"),
            "ai_advice": self._ai_advice,
            "daily": {
                "intraday_pnl": intraday,
                "repositions_today": self.safety.repositions_today(),
                "max_repositions": self.settings.max_repositions_per_day,
                "max_daily_loss": self.settings.max_daily_loss,
            },
            "cycle": cyc,
            "last_cycle_ts": time.time(),
            "last_error": self._last_error,
        })
