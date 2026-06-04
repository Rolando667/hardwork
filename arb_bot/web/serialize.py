"""Convert a ScanResult into a JSON-friendly dict for the dashboard API.

Kept separate from the scanner so the data layer has no web dependency and the
exact same numbers the console prints are what the dashboard shows.
"""

from __future__ import annotations

from ..core.models import Opportunity
from ..scanner.scanner import ScanResult


def opportunity_to_dict(opp: Opportunity) -> dict:
    c = opp.cost
    s = opp.sizing
    return {
        "coin": opp.coin,
        "long_exchange": opp.long_exchange,
        "short_exchange": opp.short_exchange,
        "long_bid": opp.long_quote.bid,
        "long_ask": opp.long_quote.ask,
        "short_bid": opp.short_quote.bid,
        "short_ask": opp.short_quote.ask,
        "size_coin": s.coin_qty,
        "notional_quote": c.notional_per_leg_quote,
        "residual_delta": s.residual_delta_coin,
        "within_tolerance": s.within_tolerance,
        "gross_bps": c.gross_spread_bps,
        "commission_bps": c.commission_bps,
        "half_spread_bps": c.half_spread_cost_bps,
        "slippage_bps": c.slippage_bps,
        "net_funding_bps": c.net_funding_bps,
        "capital_bps": c.capital_cost_bps,
        "net_bps": c.net_spread_bps,
        "breakeven_bps": c.breakeven_spread_bps,
        "return_on_capital": c.return_on_capital,
        "signal": opp.signal,
    }


def scan_to_dict(result: ScanResult, threshold_bps: float) -> dict:
    """Full dashboard payload for one scan."""
    opps = [opportunity_to_dict(o) for o in result.opportunities]
    return {
        "threshold_bps": threshold_bps,
        "exchanges_loaded": result.exchanges_loaded,
        "funding_intervals": result.funding_intervals,
        "universe": [
            {"coin": e.coin, "exchanges": e.exchanges, "volume": e.volume}
            for e in result.universe
        ],
        "stats": {
            "total_coins_seen": result.stats.total_coins_seen,
            "on_multiple_exchanges": result.stats.on_multiple_exchanges,
            "passed_volume": result.stats.passed_volume,
            "selected": result.stats.selected,
            "dropped_single_exchange": result.stats.dropped_single_exchange,
            "dropped_low_volume": result.stats.dropped_low_volume,
        },
        "pairs_evaluated": len(opps),
        "pairs_skipped": result.skipped_pairs,
        "signals": sum(1 for o in opps if o["signal"]),
        "opportunities": opps,
    }
