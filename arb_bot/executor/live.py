"""Live executor orchestration — DRY_RUN by default, deterministic, no LLM.

Real trading requires BOTH live.live_trading=true AND passing the interactive
confirmation at startup; otherwise everything runs through the DRY_RUN broker,
which logs intended orders and simulates fills. The loop reuses the read-only
scanner feed for signals and prices, and drives every open/close through the
atomic executor + state machine so the safety guarantees hold identically in
DRY_RUN and live.

Recommended rollout (per the spec): prove out spot-perp on a single exchange
first, then cross-exchange perp-perp. This module implements the cross-exchange
perp-perp path we have scanners/sim for.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

from ..core.config import Config
from ..core.logging_setup import get_logger
from ..core.timeutils import utcnow
from ..exchanges.factory import build_exchanges
from ..scanner.scanner import build_opportunities, collect_market_data
from .broker import Broker, DryRunBroker, OrderResult
from .execution import AtomicExecutor, LegPlan, TradePlan
from .kill_switch import kill_all
from .reconciliation import ExpectedLeg, reconcile
from .state_machine import State, StateMachine

log = get_logger(__name__)

_BPS = 10_000.0


@dataclass
class LivePosition:
    plan: TradePlan
    sm: StateMachine
    entry_ts: datetime
    entry_gross_bps: float
    long_res: OrderResult
    short_res: OrderResult


def confirm_live() -> bool:
    """Interactive gate. Only the exact word LIVE proceeds; EOF/anything else aborts."""
    try:
        answer = input("LIVE TRADING requested. Type LIVE (all caps) to place REAL orders: ")
    except EOFError:
        answer = ""
    return answer.strip() == "LIVE"


class LiveExecutor:
    def __init__(self, clients: dict, broker: Broker, cfg: Config) -> None:
        self.clients = clients
        self.broker = broker
        self.cfg = cfg
        self.exec = AtomicExecutor(broker, cfg.live)
        self.positions: dict[tuple[str, str, str], LivePosition] = {}
        self._trade_seq = 0

    # ---- held-leg helpers (for reconcile / kill) -------------------------

    def held_legs(self) -> list[ExpectedLeg]:
        legs: list[ExpectedLeg] = []
        for p in self.positions.values():
            legs.append(ExpectedLeg(p.plan.long_leg.exchange, p.plan.long_leg.symbol,
                                    "long", p.plan.long_leg.amount))
            legs.append(ExpectedLeg(p.plan.short_leg.exchange, p.plan.short_leg.symbol,
                                    "short", p.plan.short_leg.amount))
        return legs

    # ---- one pass --------------------------------------------------------

    def step(self, md, opportunities) -> None:
        if isinstance(self.broker, DryRunBroker):
            for ex, quotes in md.quotes_by_ex.items():
                for q in quotes.values():
                    self.broker.set_quote(ex, q.symbol, q.bid, q.ask)

        self._manage_exits(md)
        self._maybe_open(md, opportunities)

    def _manage_exits(self, md) -> None:
        now = utcnow()
        ex_cfg = self.cfg.live.exit
        for key, pos in list(self.positions.items()):
            lq = md.quotes_by_ex.get(pos.plan.long_leg.exchange, {}).get(pos.plan.coin)
            sq = md.quotes_by_ex.get(pos.plan.short_leg.exchange, {}).get(pos.plan.coin)
            if lq is None or sq is None:
                continue
            gross = (sq.mid - lq.mid) / lq.mid * _BPS
            hold_s = (now - pos.entry_ts).total_seconds()
            reason = None
            if gross <= ex_cfg.convergence_bps:
                reason = "convergence"
            elif gross >= pos.entry_gross_bps + ex_cfg.stop_adverse_bps:
                reason = "stop"
            elif hold_s >= self.cfg.live.max_hold_seconds:
                reason = "timeout"
            if reason is None:
                continue
            log.info("closing trade %s (%s): gross %.1f bps, held %.0fs",
                     pos.plan.trade_id, reason, gross, hold_s)
            self.exec.close_trade(pos.plan, pos.sm)
            del self.positions[key]

    def _maybe_open(self, md, opportunities) -> None:
        live = self.cfg.live
        for opp in opportunities:
            if opp.cost.net_spread_bps < live.entry_net_spread_bps:
                continue  # opportunities are sorted by net desc; safe to keep scanning
            key = (opp.coin, opp.long_exchange, opp.short_exchange)
            if key in self.positions:
                continue
            self._open(opp)

    def _open(self, opp) -> None:
        self._trade_seq += 1
        long_market = self.clients[opp.long_exchange].markets[opp.coin]
        short_market = self.clients[opp.short_exchange].markets[opp.coin]
        plan = TradePlan(
            trade_id=f"T{self._trade_seq}",
            coin=opp.coin,
            long_leg=LegPlan(opp.long_exchange, long_market.symbol, "buy",
                             opp.sizing.contracts_long, "long"),
            short_leg=LegPlan(opp.short_exchange, short_market.symbol, "sell",
                              opp.sizing.contracts_short, "short"),
            size_coin=opp.sizing.coin_qty,
            notional_quote=opp.cost.notional_per_leg_quote,
        )
        outcome = self.exec.open_trade(plan)
        if outcome.ok:
            self.positions[(opp.coin, opp.long_exchange, opp.short_exchange)] = LivePosition(
                plan=plan, sm=outcome.sm, entry_ts=utcnow(),
                entry_gross_bps=opp.cost.gross_spread_bps,
                long_res=outcome.long_res, short_res=outcome.short_res,
            )
        # aborted opens are already flattened by the atomic executor.

    def status_line(self) -> str:
        return f"LIVE[{'DRY_RUN' if self.broker.is_dry_run else 'REAL'}] open={len(self.positions)}"

    def flatten_all(self) -> None:
        legs = self.held_legs()
        if legs:
            kill_all(self.broker, legs, self.cfg.live.position_mode)
        self.positions.clear()


def run_live(cfg: Config) -> int:
    """Entry point for `python main.py live`. DRY_RUN unless explicitly confirmed."""
    live = cfg.live
    dry_run = not live.live_trading
    if live.live_trading:
        if live.require_confirmation and not confirm_live():
            log.error("live trading NOT confirmed -> aborting (no orders placed)")
            return 3
        log.warning("LIVE TRADING CONFIRMED — real orders will be placed")

    log.info("Phase 3 executor starting: mode=%s position_mode=%s margin_mode=%s",
             "DRY_RUN" if dry_run else "REAL", live.position_mode, live.margin_mode)

    # Read-only clients drive market data and (in DRY_RUN) simulated fills.
    clients = build_exchanges(cfg)
    if len(clients) < 2:
        log.error("need at least 2 loaded exchanges; exiting")
        return 1

    if dry_run:
        broker: Broker = DryRunBroker(
            slippage_bps=live.dry_run_slippage_bps,
            one_leg_fail_prob=live.dry_run_one_leg_fail_prob,
        )
    else:
        # Live path: real orders require authenticated ccxt clients (keys in .env).
        # Building/authenticating those is gated here so DRY_RUN never needs keys.
        from .broker import CcxtBroker
        broker = CcxtBroker({name: c._exchange for name, c in clients.items()})  # noqa: SLF001

    ex = LiveExecutor(clients, broker, cfg)

    # Reconcile before doing anything: never trust process memory on start.
    recon = reconcile(broker, ex.held_legs())
    if not recon.ok:
        log.error("startup reconciliation found discrepancies — halting (resolve manually)")
        return 4

    try:
        while True:
            try:
                md = collect_market_data(clients, cfg)
                opportunities, _ = build_opportunities(clients, cfg, md)
                ex.step(md, opportunities)
                print(ex.status_line())
            except Exception as exc:  # noqa: BLE001
                log.exception("live step failed -> entering RECOVERY: %s", exc)
                reconcile(broker, ex.held_legs())  # re-verify before continuing
            if not cfg.runtime.loop:
                break
            time.sleep(live.poll_interval_seconds)
    except KeyboardInterrupt:
        log.warning("interrupted — %d open position(s). Use kill switch to flatten if needed.",
                    len(ex.positions))
    return 0
