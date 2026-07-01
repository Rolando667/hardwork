"""Reconcile in-memory state against the exchange's real positions.

Run at startup and after any disconnect BEFORE continuing: process memory is not
to be trusted after a crash/reconnect. We fetch the real position for each leg we
believe we hold and flag any mismatch (missing, unexpected side, size drift).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.logging_setup import get_logger
from .broker import Broker

log = get_logger(__name__)


@dataclass(frozen=True)
class ExpectedLeg:
    exchange: str
    symbol: str
    position_side: str   # 'long' | 'short'
    contracts: float


@dataclass(frozen=True)
class Discrepancy:
    exchange: str
    symbol: str
    kind: str            # 'missing' | 'side_mismatch' | 'size_mismatch'
    expected: str
    actual: str


@dataclass
class ReconResult:
    ok: bool
    discrepancies: list[Discrepancy] = field(default_factory=list)


def reconcile(broker: Broker, expected: list[ExpectedLeg], size_tol: float = 1e-6) -> ReconResult:
    """Compare each expected leg to the real position. ok=True if all match."""
    discrepancies: list[Discrepancy] = []
    for leg in expected:
        pos = broker.fetch_position(leg.exchange, leg.symbol)
        if pos.side is None or pos.contracts == 0.0:
            discrepancies.append(Discrepancy(
                leg.exchange, leg.symbol, "missing",
                f"{leg.position_side} {leg.contracts:.6g}", "flat"))
            continue
        if pos.side != leg.position_side:
            discrepancies.append(Discrepancy(
                leg.exchange, leg.symbol, "side_mismatch", leg.position_side, pos.side))
        elif abs(pos.contracts - leg.contracts) > size_tol:
            discrepancies.append(Discrepancy(
                leg.exchange, leg.symbol, "size_mismatch",
                f"{leg.contracts:.6g}", f"{pos.contracts:.6g}"))

    ok = not discrepancies
    if ok:
        log.info("reconciliation clean: %d leg(s) match exchange state", len(expected))
    else:
        for d in discrepancies:
            log.error("RECON mismatch %s %s: %s (expected %s, actual %s)",
                      d.exchange, d.symbol, d.kind, d.expected, d.actual)
    return ReconResult(ok=ok, discrepancies=discrepancies)
