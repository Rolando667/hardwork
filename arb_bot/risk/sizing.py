"""Symmetric leg sizing — both legs equal in COIN quantity (delta-neutral).

Unequal legs are a directional bet on the difference, exactly the tilt we must
avoid. The achievable size is the intersection of both venues' limits, rounded
down to a step both can represent. If even the intersection minimum cannot be
met, the coin is skipped (never "almost symmetric"). Any tiny leftover from
independent precision rounding is reported as ``residual_delta``.

All math is in COIN units, reached from ccxt's contract units via contractSize.
"""

from __future__ import annotations

import math

from ..core.config import SizingConfig
from ..core.models import NormalizedMarket, SizingResult

_EPS = 1e-12


def _floor_to_step(value: float, step: float | None) -> float:
    """Round ``value`` down to a multiple of ``step`` (no-op if step is falsy)."""
    if not step or step <= 0:
        return value
    return math.floor(value / step + _EPS) * step


def _coin_limits(m: NormalizedMarket, reference_price: float) -> tuple[float, float, float | None]:
    """Return (min_coin, max_coin, step_coin) for one market.

    Folds both the contract-amount limits and the quote-cost limits into coin
    terms; the effective min is the larger of the two, the max the smaller.
    """
    cs = m.contract_size

    amount_min_coin = (m.amount_min * cs) if m.amount_min is not None else 0.0
    cost_min_coin = (m.cost_min / reference_price) if m.cost_min is not None else 0.0
    min_coin = max(amount_min_coin, cost_min_coin)

    maxes = []
    if m.amount_max is not None:
        maxes.append(m.amount_max * cs)
    if m.cost_max is not None:
        maxes.append(m.cost_max / reference_price)
    max_coin = min(maxes) if maxes else math.inf

    step_coin = (m.amount_step * cs) if m.amount_step else None
    return min_coin, max_coin, step_coin


def symmetric_size(
    *,
    long_market: NormalizedMarket,
    short_market: NormalizedMarket,
    target_notional_quote: float,
    reference_price: float,
    cfg: SizingConfig,
) -> SizingResult:
    """Compute the achievable equal-leg size across both venues."""
    if reference_price <= 0:
        return _skip("invalid reference price", target_coin=0.0, lower=0.0, upper=0.0)

    min_l, max_l, step_l = _coin_limits(long_market, reference_price)
    min_s, max_s, step_s = _coin_limits(short_market, reference_price)

    lower = max(min_l, min_s)
    upper = min(max_l, max_s)

    if upper < lower:
        return _skip(
            f"no overlapping size range (lower={lower:.6g} > upper={upper:.6g})",
            target_coin=0.0,
            lower=lower,
            upper=upper,
        )

    target_coin = min(target_notional_quote / reference_price, upper)

    # Round the common target down to the coarser of the two steps, then floor
    # each leg independently to its own step (what the venue will actually accept).
    coarse_step = max((s for s in (step_l, step_s) if s), default=None)
    common = _floor_to_step(target_coin, coarse_step)

    long_leg = _floor_to_step(common, step_l)
    short_leg = _floor_to_step(common, step_s)
    achievable = min(long_leg, short_leg)

    if achievable < lower - _EPS or achievable <= 0:
        return _skip(
            f"achievable {achievable:.6g} below intersection min {lower:.6g} "
            f"(target ${target_notional_quote:g} too small for lot sizes)",
            target_coin=target_coin,
            lower=lower,
            upper=upper,
        )

    residual_delta = abs(long_leg - short_leg)
    within_tol = residual_delta <= cfg.residual_tolerance_frac * achievable + _EPS

    contracts_long = long_leg / long_market.contract_size
    contracts_short = short_leg / short_market.contract_size

    return SizingResult(
        ok=True,
        skip_reason=None,
        coin_qty=achievable,
        contracts_long=contracts_long,
        contracts_short=contracts_short,
        lower_bound=lower,
        upper_bound=upper,
        target_coin_qty=target_coin,
        residual_delta_coin=residual_delta,
        within_tolerance=within_tol,
    )


def _skip(reason: str, *, target_coin: float, lower: float, upper: float) -> SizingResult:
    return SizingResult(
        ok=False,
        skip_reason=reason,
        coin_qty=0.0,
        contracts_long=0.0,
        contracts_short=0.0,
        lower_bound=lower,
        upper_bound=upper,
        target_coin_qty=target_coin,
        residual_delta_coin=0.0,
        within_tolerance=False,
    )
