"""Kill switch — immediately flatten every held leg, reduce-only.

Invoked manually or automatically on an anomaly (bad fill, price sanity failure,
connectivity loss with exposure). Sends reduce-only closes so it can only ever
reduce toward flat, never open a new position.
"""

from __future__ import annotations

from ..core.logging_setup import get_logger
from .broker import Broker, OrderResult
from .reconciliation import ExpectedLeg

log = get_logger(__name__)


def kill_all(broker: Broker, held: list[ExpectedLeg], position_mode: str) -> list[OrderResult]:
    """Reduce-only close every leg in ``held``. Returns the order results."""
    log.warning("KILL SWITCH engaged: flattening %d leg(s)", len(held))
    results: list[OrderResult] = []
    for i, leg in enumerate(held):
        # Close a long by selling, a short by buying.
        side = "sell" if leg.position_side == "long" else "buy"
        res = broker.create_order(
            exchange=leg.exchange, symbol=leg.symbol, side=side, amount=leg.contracts,
            position_side=leg.position_side, reduce_only=True, position_mode=position_mode,
            client_order_id=f"kill-{leg.exchange}-{i}",
        )
        results.append(res)
        if not res.is_filled:
            log.error("KILL leg NOT confirmed flat: %s %s (status=%s)",
                      leg.exchange, leg.symbol, res.status)
    return results
