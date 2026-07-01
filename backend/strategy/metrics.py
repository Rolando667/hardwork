"""
Live metrics derived from fresh klines.

These are the same quantities the calculator shows and the decision engine acts
on: ATR%, realized volatility, current-range fill-rate, and time-in-range. ATR%
and time-in-range come straight out of :func:`backtest` (so they are identical to
the calculator); realized volatility is the daily log-return sigma from
``refreshHistStats`` in the HTML.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .engine import BacktestResult, backtest


def realized_vol_daily(daily_candles: list[dict[str, Any]]) -> dict[str, float] | None:
    """Daily log-return volatility & drift, port of ``refreshHistStats``.

    Expects ~daily candles. Returns ``{"vol_daily", "drift_daily", "days"}`` or
    None if there isn't enough history.
    """
    if not daily_candles or len(daily_candles) <= 12:
        return None
    rets: list[float] = []
    for i in range(1, len(daily_candles)):
        if daily_candles[i - 1]["c"] > 0:
            rets.append(math.log(daily_candles[i]["c"] / daily_candles[i - 1]["c"]))
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
    return {"vol_daily": math.sqrt(var), "drift_daily": mean, "days": float(len(rets))}


@dataclass
class LiveMetrics:
    """Snapshot of the metrics the decision engine compares against thresholds."""

    atr_pct: float
    in_range_pct: float
    fill_rate_per_day: float
    matched_fills: int
    total_fills: int
    realized_vol_daily: float | None
    days: float
    grid_eff: float
    range_cov: float
    result: BacktestResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "atr_pct": self.atr_pct,
            "in_range_pct": self.in_range_pct,
            "fill_rate_per_day": self.fill_rate_per_day,
            "matched_fills": self.matched_fills,
            "total_fills": self.total_fills,
            "realized_vol_daily": self.realized_vol_daily,
            "days": self.days,
            "grid_eff": self.grid_eff,
            "range_cov": self.range_cov,
        }


def compute_live_metrics(
    candles: list[dict[str, Any]],
    params: dict[str, Any],
    daily_candles: list[dict[str, Any]] | None = None,
) -> LiveMetrics:
    """Backtest the current config over ``candles`` and extract live metrics.

    ``fill_rate_per_day`` is the count of all fills (buys + sells) normalised by
    the window length in days — a low value relative to a config's expectation is
    the "grid idle too long" signal the decision engine uses.
    """
    r = backtest(candles, 0, len(candles) - 1, {**params, "record_trades": False})
    total_fills = r.buy_trades + r.sell_trades
    fill_rate = (total_fills / r.days) if r.days > 0 else 0.0
    rv = realized_vol_daily(daily_candles) if daily_candles else None
    return LiveMetrics(
        atr_pct=r.atr_pct,
        in_range_pct=r.in_range,
        fill_rate_per_day=fill_rate,
        matched_fills=r.matched,
        total_fills=total_fills,
        realized_vol_daily=(rv["vol_daily"] if rv else None),
        days=r.days,
        grid_eff=r.grid_eff,
        range_cov=r.range_cov,
        result=r,
    )
