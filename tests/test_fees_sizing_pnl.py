"""Tests for the shared cost engine, symmetric sizing, and simulator P&L."""

import unittest
from datetime import timedelta

from arb_bot.core.config import FeesConfig, SizingConfig
from arb_bot.core.models import (
    CostBreakdown, FundingSnapshot, NormalizedMarket, QuoteSnapshot,
)
from arb_bot.core.timeutils import utcnow
from arb_bot.fees.engine import capital_cost_bps, net_funding_bps
from arb_bot.risk.sizing import symmetric_size
from arb_bot.simulator.models import OpenPosition
from arb_bot.simulator.pnl import compute_trade_pnl, realized_net_funding


def _mkt(ex, cs=1.0, amin=0.001, amax=None, step=0.001, taker=0.0005):
    return NormalizedMarket(ex, "BTC", "BTC/USDT:USDT", "BTC", "USDT", "USDT", True,
                            cs, amin, amax, None, None, step, 0.0002, taker)


def _fund(ex, rate, interval, next_ts):
    return FundingSnapshot(ex, "BTC/USDT:USDT", rate, interval, rate / interval, next_ts, utcnow())


class TestFees(unittest.TestCase):
    def test_capital_cost_scales_with_hold(self):
        # 10%/yr on 2x base over 8h -> 2 * 0.10 * 8/8760 * 1e4 bps
        self.assertAlmostEqual(capital_cost_bps(1000, 8), 2 * 1000 * 8 / 8760, places=9)
        self.assertAlmostEqual(capital_cost_bps(1000, 0), 0.0, places=12)

    def test_net_funding_sign_two_sided(self):
        t = utcnow()
        lf = _fund("gate", 0.0001, 8, t)   # long pays 0.0001 per 8h
        sf = _fund("mexc", 0.0003, 8, t)   # short receives 0.0003 per 8h
        # over 8h horizon: (0.0003 - 0.0001) * 1e4 = 2 bps received
        self.assertAlmostEqual(net_funding_bps(lf, sf, 8), 2.0, places=9)


class TestSizing(unittest.TestCase):
    def test_common_step_rounds_down_and_equal_legs(self):
        # long step 0.001, short step 0.01 -> common coarser step 0.01
        long_m = _mkt("gate", step=0.001)
        short_m = _mkt("mexc", step=0.01)
        r = symmetric_size(long_market=long_m, short_market=short_m,
                           target_notional_quote=100.0, reference_price=100.0,
                           cfg=SizingConfig(target_notional_quote=100.0))
        self.assertTrue(r.ok)
        # target 1.0 coin, floored to 0.01 step -> both legs representable, equal
        self.assertAlmostEqual(r.coin_qty, 1.0, places=6)
        self.assertLessEqual(r.residual_delta_coin, 1e-9)

    def test_skips_when_below_intersection_min(self):
        # min 5 coin on one venue, target only 1 coin -> cannot fit -> skip
        long_m = _mkt("gate", amin=5.0)
        short_m = _mkt("mexc", amin=0.001)
        r = symmetric_size(long_market=long_m, short_market=short_m,
                           target_notional_quote=100.0, reference_price=100.0,
                           cfg=SizingConfig())
        self.assertFalse(r.ok)
        self.assertIsNotNone(r.skip_reason)


class TestPnl(unittest.TestCase):
    def _cost(self):
        return CostBreakdown(100.0, 25, 0.25, 18, 0.18, 3, 0.03, 8, 0.08, 0, 0,
                             1.83, 0.0183, 30.83, 0.308, -5.83, -0.058, 30.83, 0, 0)

    def test_convergence_capture_and_net(self):
        t = utcnow()
        lf = _fund("gate", 0.0, 8, t + timedelta(hours=20))
        sf = _fund("mexc", 0.0, 8, t + timedelta(hours=20))
        pos = OpenPosition(1, "BTC", "gate", "mexc", 1.0, 100.0, t, 25.0, 24.0, 1.0,
                           100.0, 100.0, self._cost(), lf, sf, 0.0, True)
        pnl = compute_trade_pnl(pos, 3.0, t + timedelta(seconds=60), FeesConfig())
        self.assertAlmostEqual(pnl.capture_bps, 21.0, places=6)   # 24 - 3
        self.assertEqual(pnl.funding_events, 0)

    def test_event_based_funding_counts_settlements(self):
        t = utcnow()
        lf = _fund("gate", 0.0001, 8, t + timedelta(hours=1))
        sf = _fund("mexc", 0.0002, 8, t + timedelta(hours=1))
        nb, ev = realized_net_funding(lf, sf, t, t + timedelta(hours=2))
        self.assertAlmostEqual(nb, 1.0, places=9)  # (0.0002-0.0001)*1e4
        self.assertEqual(ev, 2)


if __name__ == "__main__":
    unittest.main()
