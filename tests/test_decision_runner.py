"""
End-to-end decision-loop test with a fake (offline) exchange.

Drives the real :class:`BotRunner` in dry-run through a synthetic adapter so we
exercise reconcile -> metrics -> decision -> validation -> apply -> safety without
touching the network. Covers: first deploy, hold-within-band, a price breakout
that triggers a reposition, the daily-loss limit, and the panic kill-switch.

Run:  python tests/test_decision_runner.py   (or pytest)
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend import config as cfgmod  # noqa: E402
from backend.bot import runner as runner_mod  # noqa: E402
from backend.bot.runner import BotRunner  # noqa: E402
from backend.bot.safety import Safety  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.db import Store  # noqa: E402
from backend.exchange.adapter import Order  # noqa: E402
from backend.strategy.rng import mulberry32  # noqa: E402


class FakeAdapter:
    """Offline adapter: scripted price + generated candles, paper order book."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.symbol = settings.symbol
        self.price = 150.0
        self.center = 150.0
        self.vol = 0.01
        self._orders: list[Order] = []
        self.seeded = 0.0

    # market data
    def market_price(self) -> float:
        return self.price

    def fetch_ohlcv(self, timeframe: str, limit: int) -> list[dict]:
        rnd = mulberry32(int(self.center * 100))
        out = []
        p = self.center
        t = 1_700_000_000
        for _ in range(min(limit, 120)):
            o = p
            c = o * (1 + (rnd() - 0.5) * 2 * self.vol)
            hi = max(o, c) * (1 + rnd() * self.vol)
            lo = min(o, c) * (1 - rnd() * self.vol)
            out.append({"t": t, "o": o, "h": hi, "l": lo, "c": c})
            p = c
            t += 3600
        return out

    # account
    def fetch_balances(self):
        return {"free": {self.settings.base_asset: 0.0, self.settings.quote_asset: self.settings.invest},
                "total": {self.settings.base_asset: 0.0, self.settings.quote_asset: self.settings.invest}}

    def fetch_open_orders(self):
        return list(self._orders)

    def fetch_my_trades(self, since):
        return []

    # trading (paper)
    def place_limit(self, side, price, amount, client_id):
        o = Order(id=f"f-{client_id}", client_id=client_id, side=side, price=price, amount=amount, status="open")
        self._orders.append(o)
        return o

    def cancel(self, order_id):
        self._orders = [o for o in self._orders if o.id != order_id]

    def cancel_all(self):
        n = len(self._orders)
        self._orders = []
        return n

    def seed_inventory(self, amount):
        self.seeded += amount
        return amount

    def amount_to_precision(self, a):
        return a

    def price_to_precision(self, p):
        return p

    def min_notional(self):
        return 0.0

    def startup_checks(self):
        return None


def _make_runner(tmpdir, **overrides):
    db = os.path.join(tmpdir, "t.db")
    settings = Settings(
        mode="dry_run", db_path=db, invest=1000.0, grids=8, grid_mode="geometric",
        cycle_seconds=60, cooldown_seconds=0, max_repositions_per_day=20,
        reject_overfit=False, history_candles=120, band_pct=0.5, vol_pct=0.5,
        fee_pct=0.1, slip_bps=2, **overrides,
    )
    store = Store(db)
    fake = FakeAdapter(settings)
    runner_mod.build_adapter = lambda s: fake  # inject offline adapter
    r = BotRunner(settings, store)
    r._running = True  # allow placement without spinning the scheduler thread
    return r, fake, store


def test_full_loop():
    with tempfile.TemporaryDirectory() as tmp:
        r, fake, store = _make_runner(tmp)

        # 1. first cycle -> deploy a grid
        fake.price = 150.0
        fake.center = 150.0
        r.run_cycle()
        assert r.active is not None, "expected a grid to be deployed on first cycle"
        snap = r.get_snapshot()
        assert snap["last_decision"]["action"] in ("deploy", "reposition"), snap["last_decision"]
        deployed_epoch = r.active.epoch
        assert len(fake.fetch_open_orders()) > 0, "ladder orders should be placed"
        set_lower, set_upper = r.active.config.lower, r.active.config.upper

        # 2. price stays inside the band -> hold (no churn)
        fake.price = (set_lower + set_upper) / 2
        r.run_cycle()
        dec = r.get_snapshot()["last_decision"]
        assert dec["action"] == "hold", f"expected hold within band, got {dec}"
        assert "within band" in dec["reason"] or "no trigger" in dec["reason"]
        assert r.active.epoch == deployed_epoch, "grid should not have moved on a hold"

        # 3. price breaks far above the band -> reposition
        grid_step = (set_upper - set_lower) / r.active.config.grids
        fake.price = set_upper + 5 * grid_step
        fake.center = fake.price
        r.run_cycle()
        dec = r.get_snapshot()["last_decision"]
        assert dec["action"] == "reposition", f"expected reposition on breakout, got {dec}"
        assert "price_above_band" in dec["triggers"]
        assert r.active.epoch == deployed_epoch + 1, "epoch should bump on reposition"

        # 4. panic -> cancel all + halt
        res = r.panic("test panic")
        assert res["halted"] is True
        assert len(fake.fetch_open_orders()) == 0
        assert r.safety.is_halted()

        # 5. while halted, a cycle holds and places nothing new
        r._running = True
        before = len(fake.fetch_open_orders())
        r.run_cycle()
        assert r.get_snapshot()["last_decision"]["action"] == "hold"
        assert len(fake.fetch_open_orders()) == before
        store.close()
    print("full loop: deploy -> hold -> reposition -> panic -> halted-hold  OK")


def test_daily_loss_limit():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "s.db")
        settings = Settings(mode="dry_run", db_path=db, max_daily_loss=50.0)
        store = Store(db)
        safety = Safety(settings, store)
        # baseline set on first observation; then a large negative move breaches
        breached, _ = safety.check_daily_loss(100.0)
        assert not breached
        breached, intraday = safety.check_daily_loss(40.0)
        assert breached, f"expected breach, intraday={intraday}"
        assert intraday <= -50.0
        store.close()
    print("daily loss limit: OK")


def test_throttle_blocks_reposition():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "th.db")
        settings = Settings(mode="dry_run", db_path=db, cooldown_seconds=3600, max_repositions_per_day=5)
        store = Store(db)
        safety = Safety(settings, store)
        ok, _ = safety.can_reposition()
        assert ok
        safety.record_reposition()
        ok, reason = safety.can_reposition()
        assert not ok and "cooldown" in reason, reason
        # now the daily cap path: exhaust it and check the cap reason
        s2 = Settings(mode="dry_run", db_path=db, cooldown_seconds=0, max_repositions_per_day=1)
        safety2 = Safety(s2, store)
        # already 1 reposition recorded today -> cap of 1 reached
        ok2, reason2 = safety2.can_reposition()
        assert not ok2 and "cap" in reason2, reason2
        store.close()
    print("throttle: OK")


if __name__ == "__main__":
    test_throttle_blocks_reposition()
    test_daily_loss_limit()
    test_full_loop()
    print("\nALL DECISION/RUNNER TESTS PASSED")
