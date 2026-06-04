"""Shared data models for the scanner.

Conventions
-----------
* Money amounts are in the quote currency (USDT) as ``float``.
* Spreads and costs are carried canonically in **basis points (bps)**, with
  quote-currency mirrors (``*_quote``) where a concrete amount is useful.
* All timestamps are timezone-aware ``datetime`` in **UTC**.
* Sizes are tracked in two units: *contracts* (what ccxt orders take) and
  *coin* quantity (contracts * contractSize), which is the delta-neutral unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NormalizedMarket:
    """A single exchange's linear-perp market for one coin, after normalization.

    All limits are expressed in *contracts* as ccxt reports them; convert to
    coin quantity via ``contract_size`` (see ``risk.sizing``).
    """

    exchange: str
    coin: str               # base asset, e.g. "BTC"
    symbol: str             # ccxt unified symbol, e.g. "BTC/USDT:USDT"
    base: str
    quote: str
    settle: str
    linear: bool            # must be True in P0
    contract_size: float    # coin per contract (cast from possible str, ccxt #11123)
    amount_min: float | None  # limits.amount.min, in contracts
    amount_max: float | None
    cost_min: float | None    # limits.cost.min, quote notional
    cost_max: float | None
    amount_step: float | None  # precision step, in contracts
    maker_fee: float          # fraction, e.g. 0.0002 (config-overridable)
    taker_fee: float
    # NOTE: 24h volume is not part of the static market dict — it comes from live
    # tickers and is tracked per-coin in the universe step (see scanner.universe).


@dataclass(frozen=True)
class QuoteSnapshot:
    """Top-of-book for one symbol at one instant. Best bid/ask — never ``last``."""

    exchange: str
    symbol: str
    bid: float
    ask: float
    ts: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


@dataclass(frozen=True)
class FundingSnapshot:
    """Funding for one symbol, normalized to a common per-hour rate.

    ``funding_rate`` is the raw rate for this exchange's own interval; divide by
    ``interval_hours`` to get ``rate_per_hour`` (the comparison key). Do NOT
    assume an 8h interval — it is read per-exchange.
    """

    exchange: str
    symbol: str
    funding_rate: float        # raw, per its own interval
    interval_hours: float
    rate_per_hour: float       # funding_rate / interval_hours
    next_funding_ts: datetime | None
    ts: datetime
    interval_inferred: bool = False  # True if interval came from fallback default


@dataclass(frozen=True)
class SizingResult:
    """Outcome of symmetric (delta-neutral) sizing across two exchanges.

    ``coin_qty`` is the *achievable* equal-leg size — what the scanner reports,
    not the requested target.
    """

    ok: bool
    skip_reason: str | None
    coin_qty: float            # achievable, equal on both legs
    contracts_long: float
    contracts_short: float
    lower_bound: float         # max(min_long, min_short), coin
    upper_bound: float         # min(max_long, max_short), coin
    target_coin_qty: float     # min(config target, upper) before rounding
    residual_delta_coin: float  # |long_coin - short_coin| after independent rounding
    within_tolerance: bool


@dataclass(frozen=True)
class CostBreakdown:
    """Full profit/cost stack for one candidate trade, from the fees engine.

    Every ``*_bps`` is in bps of one leg's notional; ``*_quote`` is the concrete
    USDT amount for the achievable size. ``net_funding_*`` is *signed* (positive
    = net received). ``net_funding_normalized_bps`` is the same value exposed for
    display regardless of sign.
    """

    notional_per_leg_quote: float
    gross_spread_bps: float
    gross_spread_quote: float
    commission_bps: float
    commission_quote: float
    half_spread_cost_bps: float
    half_spread_cost_quote: float
    slippage_bps: float
    slippage_quote: float
    net_funding_bps: float          # signed
    net_funding_quote: float
    capital_cost_bps: float
    capital_cost_quote: float
    total_cost_bps: float
    total_cost_quote: float
    net_spread_bps: float
    net_spread_quote: float
    breakeven_spread_bps: float
    return_on_capital: float        # net_spread_quote / (2 * notional)
    net_funding_normalized_bps: float


@dataclass(frozen=True)
class Opportunity:
    """A fully-evaluated coin / exchange-pair candidate."""

    coin: str
    long_exchange: str   # cheaper — we buy here
    short_exchange: str  # dearer — we sell here
    long_quote: QuoteSnapshot
    short_quote: QuoteSnapshot
    sizing: SizingResult
    cost: CostBreakdown
    signal: bool         # net_spread_bps >= threshold AND sizing.ok
    ts: datetime
