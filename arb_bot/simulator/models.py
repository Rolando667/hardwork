"""Simulator data models: open positions, realized trades, P&L breakdown."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..core.models import CostBreakdown, FundingSnapshot


# Exit reasons (also the reason a trade lands in the journal).
CONVERGENCE = "convergence"     # spread narrowed to target -> take profit
STOP = "stop"                   # spread widened against us -> stop out
TIMEOUT = "timeout"            # held too long -> force close
ONE_LEG_FAIL = "one_leg_fail"  # leg-2 never filled -> emergency close leg-1


@dataclass
class OpenPosition:
    """A live virtual position being held until an exit condition triggers."""

    id: int
    coin: str
    long_exchange: str
    short_exchange: str
    size_coin: float
    notional_quote: float
    entry_ts: datetime
    entry_gross_bps: float              # raw spread observed at entry
    effective_entry_gross_bps: float    # after legging penalty (what we actually captured entering)
    legging_penalty_bps: float
    entry_long_ask: float
    entry_short_bid: float
    cost: CostBreakdown                 # captured at entry for its cost components
    long_funding: FundingSnapshot       # entry snapshot (interval + next settlement)
    short_funding: FundingSnapshot
    residual_delta_coin: float
    within_tolerance: bool


@dataclass(frozen=True)
class TradePnL:
    """Realized P&L breakdown for a closed trade (from the pure pnl module)."""

    capture_bps: float           # effective_entry_gross - exit_gross
    commission_bps: float
    half_spread_bps: float
    slippage_bps: float
    capital_bps: float           # scaled to the ACTUAL hold time
    net_funding_bps: float       # event-based over the actual hold (signed)
    net_pnl_bps: float
    net_pnl_quote: float
    return_on_capital: float
    funding_events: int


@dataclass(frozen=True)
class ClosedTrade:
    """One row of the machine-readable trade journal."""

    id: int
    coin: str
    long_exchange: str
    short_exchange: str
    filled: bool                 # False = aborted entry (one-leg-fail)
    exit_reason: str
    entry_ts: datetime
    exit_ts: datetime
    hold_seconds: float
    size_coin: float
    notional_quote: float
    residual_delta_coin: float
    entry_gross_bps: float
    effective_entry_gross_bps: float
    exit_gross_bps: float
    legging_penalty_bps: float
    pnl: TradePnL
