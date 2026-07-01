"""Unit tests for two-leg atomicity — the most safety-critical guarantee.

The bot must NEVER end up holding one leg. These tests drive the atomic executor
with the DRY_RUN broker and assert: both-fill -> OPEN with both positions; one
leg fails -> the filled leg is emergency-closed and we end FLAT with no residual
position; close -> reduce-only flattens both.
"""

import unittest

from arb_bot.core.config import LiveConfig
from arb_bot.executor.broker import DryRunBroker
from arb_bot.executor.execution import AtomicExecutor, LegPlan, TradePlan
from arb_bot.executor.state_machine import IllegalTransition, State, StateMachine

LONG_SYM = "BTC/USDT:USDT"
SHORT_SYM = "BTC/USDT:USDT"


def _cfg():
    return LiveConfig(leg_fill_timeout_ms=50, position_mode="one-way")


def _plan():
    return TradePlan(
        trade_id="T1", coin="BTC",
        long_leg=LegPlan("gate", LONG_SYM, "buy", 1.0, "long"),
        short_leg=LegPlan("mexc", SHORT_SYM, "sell", 1.0, "short"),
        size_coin=1.0, notional_quote=100.0,
    )


def _broker():
    b = DryRunBroker(slippage_bps=0.0)
    b.set_quote("gate", LONG_SYM, 99.9, 100.1)
    b.set_quote("mexc", SHORT_SYM, 99.9, 100.1)
    return b


class TestHappyPath(unittest.TestCase):
    def test_both_legs_fill_reaches_open(self):
        b = _broker()
        ex = AtomicExecutor(b, _cfg())
        out = ex.open_trade(_plan())
        self.assertTrue(out.ok)
        self.assertEqual(out.sm.state, State.OPEN)
        self.assertEqual(b.fetch_position("gate", LONG_SYM).side, "long")
        self.assertEqual(b.fetch_position("mexc", SHORT_SYM).side, "short")


class TestOneLegFail(unittest.TestCase):
    def test_short_leg_fails_emergency_closes_long_and_ends_flat(self):
        b = _broker()
        b.fail_open_exchanges = {"mexc"}  # short leg never fills
        ex = AtomicExecutor(b, _cfg())
        out = ex.open_trade(_plan())

        self.assertFalse(out.ok)
        self.assertTrue(out.aborted)
        self.assertEqual(out.reason, "one_leg_fill")
        self.assertEqual(out.sm.state, State.FLAT)
        # CRITICAL: no residual directional exposure on either venue.
        self.assertIsNone(b.fetch_position("gate", LONG_SYM).side)
        self.assertIsNone(b.fetch_position("mexc", SHORT_SYM).side)
        # And the FSM actually visited EMERGENCY_CLOSE.
        self.assertIn(State.EMERGENCY_CLOSE, out.sm.history)

    def test_long_leg_fails_emergency_closes_short_and_ends_flat(self):
        b = _broker()
        b.fail_open_exchanges = {"gate"}  # long leg never fills
        ex = AtomicExecutor(b, _cfg())
        out = ex.open_trade(_plan())
        self.assertFalse(out.ok)
        self.assertEqual(out.sm.state, State.FLAT)
        self.assertIsNone(b.fetch_position("gate", LONG_SYM).side)
        self.assertIsNone(b.fetch_position("mexc", SHORT_SYM).side)


class TestClose(unittest.TestCase):
    def test_reduce_only_close_flattens_both(self):
        b = _broker()
        ex = AtomicExecutor(b, _cfg())
        out = ex.open_trade(_plan())
        self.assertEqual(out.sm.state, State.OPEN)
        close = ex.close_trade(_plan(), out.sm)
        self.assertTrue(close.ok)
        self.assertEqual(close.sm.state, State.FLAT)
        self.assertIsNone(b.fetch_position("gate", LONG_SYM).side)
        self.assertIsNone(b.fetch_position("mexc", SHORT_SYM).side)


class TestStateMachine(unittest.TestCase):
    def test_illegal_transition_raises(self):
        sm = StateMachine("T", State.IDLE)
        with self.assertRaises(IllegalTransition):
            sm.to(State.OPEN)  # cannot jump IDLE -> OPEN

    def test_recovery_reachable_from_anywhere(self):
        sm = StateMachine("T", State.OPEN)
        sm.to(State.RECOVERY)  # always allowed
        self.assertEqual(sm.state, State.RECOVERY)


if __name__ == "__main__":
    unittest.main()
