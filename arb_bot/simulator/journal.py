"""Machine-readable trade journal (JSONL) — one line per closed paper trade.

Each line carries the full accounting: entry/exit times and spreads, size,
residual delta, every cost line separately, realized net funding, net P&L,
return on capital and duration. This is the raw material for the equity curve
and statistics (P1).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ..core.logging_setup import get_logger
from .models import ClosedTrade

log = get_logger(__name__)


class TradeJournal:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def write(self, trade: ClosedTrade) -> None:
        self._fh.write(json.dumps(_flatten(trade), default=_default) + "\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:  # noqa: BLE001
            pass


def _flatten(trade: ClosedTrade) -> dict:
    """ClosedTrade -> flat dict with the nested pnl fields lifted to top level."""
    d = asdict(trade)
    pnl = d.pop("pnl")
    d.update({k: v for k, v in pnl.items()})
    return d


def _default(obj: object) -> object:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)
