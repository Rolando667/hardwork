"""Realized P&L for a closed paper trade — pure, testable, fees/-consistent.

For a cross-exchange convergence trade we bought the cheaper venue and sold the
dearer one; profit is the spread we captured as it narrowed:

    capture = effective_entry_gross - exit_gross           (bps)
    net_pnl = capture + realized_net_funding - (commission + half_spread
                                                + slippage + capital)

Costs (commission / half-spread / slippage) are taken from the entry
CostBreakdown (the shared fees/ engine); capital and funding are recomputed for
the ACTUAL hold — capital scales with time, funding is event-based (you only
pay/receive at a settlement you were holding through).
"""

from __future__ import annotations

from datetime import datetime

from ..core.config import FeesConfig
from ..core.models import FundingSnapshot
from ..fees.engine import capital_cost_bps
from .models import OpenPosition, TradePnL

_BPS = 10_000.0


def _count_settlements(
    next_ts: datetime | None, interval_hours: float, entry_ts: datetime, exit_ts: datetime
) -> int:
    """How many funding settlements fall in (entry_ts, exit_ts].

    Settlements occur at next_ts, next_ts+interval, next_ts+2*interval, ...
    Returns 0 if the schedule is unknown or the first settlement is after exit.
    """
    if next_ts is None or interval_hours <= 0 or exit_ts <= entry_ts:
        return 0
    if next_ts > exit_ts:
        return 0
    interval_s = interval_hours * 3600.0
    elapsed = (exit_ts - next_ts).total_seconds()
    return int(elapsed // interval_s) + 1


def realized_net_funding(
    long_funding: FundingSnapshot,
    short_funding: FundingSnapshot,
    entry_ts: datetime,
    exit_ts: datetime,
) -> tuple[float, int]:
    """Event-based net funding over the hold. Returns (net_bps, event_count).

    Long leg PAYS its raw rate each of its settlements; short leg RECEIVES its raw
    rate each of its settlements. Net positive = we received.
    """
    long_n = _count_settlements(long_funding.next_funding_ts, long_funding.interval_hours, entry_ts, exit_ts)
    short_n = _count_settlements(short_funding.next_funding_ts, short_funding.interval_hours, entry_ts, exit_ts)
    net_fraction = short_n * short_funding.funding_rate - long_n * long_funding.funding_rate
    return net_fraction * _BPS, long_n + short_n


def compute_trade_pnl(
    position: OpenPosition,
    exit_gross_bps: float,
    exit_ts: datetime,
    fees_cfg: FeesConfig,
) -> TradePnL:
    """Realized P&L for closing ``position`` at ``exit_gross_bps`` / ``exit_ts``."""
    capture_bps = position.effective_entry_gross_bps - exit_gross_bps

    commission_bps = position.cost.commission_bps
    half_spread_bps = position.cost.half_spread_cost_bps
    slippage_bps = position.cost.slippage_bps

    hold_hours = max((exit_ts - position.entry_ts).total_seconds(), 0.0) / 3600.0
    capital_bps = capital_cost_bps(fees_cfg.capital_cost_annual_bps, hold_hours)

    net_funding_bps, events = realized_net_funding(
        position.long_funding, position.short_funding, position.entry_ts, exit_ts
    )

    net_pnl_bps = capture_bps + net_funding_bps - (
        commission_bps + half_spread_bps + slippage_bps + capital_bps
    )
    notional = position.notional_quote
    net_pnl_quote = net_pnl_bps / _BPS * notional
    roc = net_pnl_quote / (2.0 * notional) if notional > 0 else 0.0

    return TradePnL(
        capture_bps=capture_bps,
        commission_bps=commission_bps,
        half_spread_bps=half_spread_bps,
        slippage_bps=slippage_bps,
        capital_bps=capital_bps,
        net_funding_bps=net_funding_bps,
        net_pnl_bps=net_pnl_bps,
        net_pnl_quote=net_pnl_quote,
        return_on_capital=roc,
        funding_events=events,
    )


def aborted_pnl(emergency_cost_bps: float, notional: float) -> TradePnL:
    """P&L for an aborted entry (one-leg-fail): a pure loss of the unwind cost."""
    net_pnl_quote = -emergency_cost_bps / _BPS * notional
    return TradePnL(
        capture_bps=0.0,
        commission_bps=emergency_cost_bps,  # attribute the whole unwind cost to commission-line
        half_spread_bps=0.0,
        slippage_bps=0.0,
        capital_bps=0.0,
        net_funding_bps=0.0,
        net_pnl_bps=-emergency_cost_bps,
        net_pnl_quote=net_pnl_quote,
        return_on_capital=(net_pnl_quote / (2.0 * notional)) if notional > 0 else 0.0,
        funding_events=0,
    )
