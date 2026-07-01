"""Unit tests for the per-exchange reduce-only / position-side params.

These encode the concrete exchange quirks; getting them wrong opens the wrong
side or gets rejected, so pin the exact dicts.
"""

import unittest

from arb_bot.executor.reduce_only import build_order_params as p


class TestBinance(unittest.TestCase):
    def test_one_way_open_has_no_reduce_only(self):
        self.assertEqual(p("binance", position_side="long", reduce_only=False, position_mode="one-way"), {})

    def test_one_way_close_sets_reduce_only_camel(self):
        self.assertEqual(p("binance", position_side="long", reduce_only=True, position_mode="one-way"),
                         {"reduceOnly": True})

    def test_hedge_uses_uppercase_position_side_and_no_reduce_only(self):
        # In hedge mode Binance rejects reduceOnly (-2022); positionSide drives it.
        self.assertEqual(p("binance", position_side="long", reduce_only=True, position_mode="hedge"),
                         {"positionSide": "LONG"})
        self.assertEqual(p("binance", position_side="short", reduce_only=False, position_mode="hedge"),
                         {"positionSide": "SHORT"})


class TestBybit(unittest.TestCase):
    def test_one_way_position_idx_zero(self):
        self.assertEqual(p("bybit", position_side="long", reduce_only=False, position_mode="one-way"),
                         {"positionIdx": 0})

    def test_one_way_close_adds_reduce_only(self):
        self.assertEqual(p("bybit", position_side="short", reduce_only=True, position_mode="one-way"),
                         {"positionIdx": 0, "reduceOnly": True})

    def test_hedge_position_idx_by_side(self):
        self.assertEqual(p("bybit", position_side="long", reduce_only=False, position_mode="hedge"),
                         {"positionIdx": 1})
        self.assertEqual(p("bybit", position_side="short", reduce_only=False, position_mode="hedge"),
                         {"positionIdx": 2})


class TestOKX(unittest.TestCase):
    def test_one_way_pos_side_net(self):
        self.assertEqual(p("okx", position_side="long", reduce_only=False, position_mode="one-way"),
                         {"posSide": "net"})

    def test_one_way_close_adds_reduce_only(self):
        self.assertEqual(p("okx", position_side="long", reduce_only=True, position_mode="one-way"),
                         {"posSide": "net", "reduceOnly": True})

    def test_hedge_lowercase_pos_side(self):
        self.assertEqual(p("okx", position_side="long", reduce_only=True, position_mode="hedge"),
                         {"posSide": "long"})
        self.assertEqual(p("okx", position_side="short", reduce_only=False, position_mode="hedge"),
                         {"posSide": "short"})


class TestGenericAndValidation(unittest.TestCase):
    def test_generic_exchange_defaults(self):
        self.assertEqual(p("mexc", position_side="long", reduce_only=False, position_mode="one-way"), {})
        self.assertEqual(p("gate", position_side="long", reduce_only=True, position_mode="one-way"),
                         {"reduceOnly": True})

    def test_bad_inputs_raise(self):
        with self.assertRaises(ValueError):
            p("binance", position_side="up", reduce_only=True, position_mode="one-way")
        with self.assertRaises(ValueError):
            p("binance", position_side="long", reduce_only=True, position_mode="both")


if __name__ == "__main__":
    unittest.main()
