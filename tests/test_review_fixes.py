"""
Regression tests for the fixes applied after the adversarial review.

Covers: engine div-by-zero guards, realized-vol zero-close handling, .env
injection rejection + temp-file perms, day-rollover loss capture, and
fill-tracker dedup surviving a restart at a boundary timestamp.
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.bot.safety import Safety  # noqa: E402
from backend.bot.state import FillTracker  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.db import Store  # noqa: E402
from backend.env_writer import EnvWriteError, update_env  # noqa: E402
from backend.strategy.engine import backtest  # noqa: E402
from backend.strategy.metrics import realized_vol_daily  # noqa: E402


def _candles(n=60, base=100.0):
    out = []
    t = 1_700_000_000
    p = base
    for i in range(n):
        o = p
        c = o * (1 + (0.01 if i % 2 else -0.008))
        out.append({"t": t, "o": o, "h": max(o, c) * 1.001, "l": min(o, c) * 0.999, "c": c})
        p = c
        t += 3600
    return out


def test_engine_guards_no_crash():
    c = _candles()
    # invest = 0 must not ZeroDivisionError (apr guard)
    r = backtest(c, 0, len(c) - 1, {"lower": 80, "upper": 120, "grids": 10, "mode": "geometric", "invest": 0, "fee": 0.1})
    assert r.total == 0.0 and r.apr == 0.0
    # lower = 0 arithmetic must not ZeroDivisionError (profit_per_grid_pct / build_levels)
    r2 = backtest(c, 0, len(c) - 1, {"lower": 0, "upper": 120, "grids": 10, "mode": "arithmetic", "invest": 1000, "fee": 0.1})
    assert r2.total == 0.0
    print("engine guards: OK")


def test_realized_vol_zero_close():
    daily = [{"t": i, "o": 100, "h": 100, "l": 100, "c": 100.0} for i in range(20)]
    daily[10]["c"] = 0.0  # a bad/gap bar
    rv = realized_vol_daily(daily)  # must not raise math domain error
    assert rv is not None and "vol_daily" in rv
    print("realized_vol zero-close: OK")


def test_env_injection_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, ".env")
        # a newline in a value must be rejected (config-injection guard)
        try:
            update_env(path, {"symbol": "SOL/USDT\nALLOW_LIVE=true\nMODE=live"})
            raise AssertionError("expected EnvWriteError")
        except EnvWriteError:
            pass
        assert not os.path.exists(path), "no file should be written on rejection"
        # a normal write succeeds and is 0600
        changed = update_env(path, {"symbol": "SOL/USDT", "api_secret": "shh"})
        assert "SYMBOL" in changed and "API_SECRET" in changed
        assert (os.stat(path).st_mode & 0o777) == 0o600
        # empty secret does not wipe an existing one
        update_env(path, {"api_secret": ""})
        with open(path) as f:
            assert "API_SECRET=shh" in f.read()
    print("env injection rejected + perms: OK")


def test_day_rollover_captures_loss():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "d.db")
        s = Settings(mode="dry_run", db_path=db, max_daily_loss=50.0)
        store = Store(db)
        safety = Safety(s, store)
        safety.check_daily_loss(100.0)  # first obs today
        # simulate the prior day ending at total=100, then a new-day crash to 40
        d = store.get_state("daily_pnl")
        d["day"] = "2000-01-01"
        d["last_total"] = 100.0
        store.set_state("daily_pnl", d)
        breached, intraday = safety.check_daily_loss(40.0)
        assert breached and intraday <= -50.0, (breached, intraday)
        store.close()
    print("day-rollover loss capture: OK")


def test_fill_dedup_survives_restart():
    ft = FillTracker()
    trades = [{"id": "a", "ts": 1000, "side": "buy", "price": 10, "amount": 1.0, "cost": 10, "fee": 0}]
    ft.ingest(trades, "BASE", "USDT")
    assert ft.count == 1 and abs(ft.inventory_qty - 1.0) < 1e-12
    # restart: persist -> reload -> the same boundary trade is re-fetched (since is
    # inclusive) and must NOT be double-counted
    ft2 = FillTracker.from_state(ft.to_state())
    ft2.ingest(trades, "BASE", "USDT")
    assert ft2.count == 1, f"double-counted: {ft2.count}"
    assert abs(ft2.inventory_qty - 1.0) < 1e-12
    print("fill dedup across restart: OK")


if __name__ == "__main__":
    test_engine_guards_no_crash()
    test_realized_vol_zero_close()
    test_env_injection_rejected()
    test_day_rollover_captures_loss()
    test_fill_dedup_survives_restart()
    print("\nALL REVIEW-FIX TESTS PASSED")
