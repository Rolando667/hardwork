"""The cost/profit engine — pure, no I/O, the single source of truth.

Income  = gross_spread + net_funding (signed, two-sided)
Costs   = leg commissions (4 legs) + half-spread crossing + slippage
          + cost of frozen capital (2x notional)

All values are returned both in basis points of one leg's notional and in quote
(USDT) for the achievable size. Sign convention:

    net_spread   = gross + net_funding_signed - other_costs
    breakeven    = other_costs - net_funding_signed
    total_cost   = other_costs + max(0, -net_funding)   # funding only counts as a
                                                         # cost when it is negative

These three stay mutually consistent by construction (see net_funding helper).
"""

from __future__ import annotations

from ..core.config import FeesConfig
from ..core.models import (
    CostBreakdown,
    FundingSnapshot,
    NormalizedMarket,
    QuoteSnapshot,
    SizingResult,
)

_HOURS_PER_YEAR = 24.0 * 365.0  # 8760
_BPS = 10_000.0


def capital_cost_bps(annual_bps: float, hold_hours: float) -> float:
    """Cost of the frozen capital (2x notional) over ``hold_hours``, in bps of one leg.

    rate = (annual_bps / 1e4) * (hold_hours / 8760); applied to a 2x base, so in
    bps of one leg's notional it is 2 * rate * 1e4. Shared by the scanner's
    forward estimate and the simulator's realized (actual-hold) accounting.
    """
    rate = (annual_bps / _BPS) * (hold_hours / _HOURS_PER_YEAR)
    return 2.0 * rate * _BPS


def net_funding_bps(
    long_funding: FundingSnapshot,
    short_funding: FundingSnapshot,
    horizon_hours: float,
) -> float:
    """Signed net funding over ``horizon_hours``, in bps. Positive = we receive.

    We are LONG on the long leg (pay funding when its rate > 0) and SHORT on the
    short leg (receive funding when its rate > 0). Each rate is normalized to
    per-hour upstream, so they are directly comparable here regardless of each
    exchange's native funding interval (8h / 4h / 1h ...).
    """
    long_pay = long_funding.rate_per_hour * horizon_hours
    short_receive = short_funding.rate_per_hour * horizon_hours
    return (short_receive - long_pay) * _BPS


def compute_cost_breakdown(
    *,
    long_market: NormalizedMarket,
    short_market: NormalizedMarket,
    long_quote: QuoteSnapshot,
    short_quote: QuoteSnapshot,
    long_funding: FundingSnapshot,
    short_funding: FundingSnapshot,
    sizing: SizingResult,
    cfg: FeesConfig,
) -> CostBreakdown:
    """Full cost stack for buying the long leg and selling the short leg."""
    long_mid = long_quote.mid
    short_mid = short_quote.mid

    # Gross spread: sell-side mid above buy-side mid, relative to buy price.
    gross_spread_bps = (short_mid - long_mid) / long_mid * _BPS

    # Notional per leg and frozen capital (delta-neutral 1x/1x ties up ~2x).
    notional = sizing.coin_qty * long_mid
    frozen_capital = 2.0 * notional

    # 1) Commissions on 4 legs: open+close on each of long & short.
    fee_long = long_market.taker_fee if cfg.taker_only else long_market.maker_fee
    fee_short = short_market.taker_fee if cfg.taker_only else short_market.maker_fee
    commission_bps = 2.0 * (fee_long + fee_short) * _BPS  # open+close => x2 per leg

    # 2) Half-spread crossing on each taker leg (buy at ask, sell at bid).
    cross_multiplier = 2.0 if cfg.count_exit_crossing else 1.0  # round trip vs entry-only
    if cfg.taker_only:
        half_long = (long_quote.ask - long_mid) / long_mid * _BPS
        half_short = (short_mid - short_quote.bid) / short_mid * _BPS
        half_spread_cost_bps = (half_long + half_short) * cross_multiplier
    else:
        half_spread_cost_bps = 0.0  # resting maker legs do not cross

    # 3) Slippage beyond top-of-book: flat per crossing leg (L2 walk is P1).
    if cfg.taker_only:
        crossing_legs = 4.0 if cfg.count_exit_crossing else 2.0
        slippage_bps = cfg.slippage_bps * crossing_legs
    else:
        slippage_bps = 0.0

    # 4) Net funding (signed). Negative = a cost; positive = income offsetting gross.
    nf_bps = net_funding_bps(long_funding, short_funding, cfg.funding_horizon_hours)

    # 5) Cost of frozen capital over the expected hold.
    cap_bps = capital_cost_bps(cfg.capital_cost_annual_bps, cfg.expected_hold_hours)
    capital_cost_quote = cap_bps / _BPS * notional

    other_costs_bps = commission_bps + half_spread_cost_bps + slippage_bps + cap_bps

    net_spread_bps = gross_spread_bps + nf_bps - other_costs_bps
    breakeven_spread_bps = other_costs_bps - nf_bps
    total_cost_bps = other_costs_bps + max(0.0, -nf_bps)
    return_on_capital = (
        (net_spread_bps / _BPS * notional) / frozen_capital if frozen_capital > 0 else 0.0
    )

    def to_quote(bps: float) -> float:
        return bps / _BPS * notional

    return CostBreakdown(
        notional_per_leg_quote=notional,
        gross_spread_bps=gross_spread_bps,
        gross_spread_quote=to_quote(gross_spread_bps),
        commission_bps=commission_bps,
        commission_quote=to_quote(commission_bps),
        half_spread_cost_bps=half_spread_cost_bps,
        half_spread_cost_quote=to_quote(half_spread_cost_bps),
        slippage_bps=slippage_bps,
        slippage_quote=to_quote(slippage_bps),
        net_funding_bps=nf_bps,
        net_funding_quote=to_quote(nf_bps),
        capital_cost_bps=cap_bps,
        capital_cost_quote=capital_cost_quote,
        total_cost_bps=total_cost_bps,
        total_cost_quote=to_quote(total_cost_bps),
        net_spread_bps=net_spread_bps,
        net_spread_quote=to_quote(net_spread_bps),
        breakeven_spread_bps=breakeven_spread_bps,
        return_on_capital=return_on_capital,
        net_funding_normalized_bps=nf_bps,
    )
