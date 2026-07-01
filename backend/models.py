"""Shared data structures for the bot layer and the API."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GridConfig:
    """A concrete grid the bot deploys or evaluates."""

    lower: float
    upper: float
    grids: int
    mode: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActiveGrid:
    """The grid currently believed to be live, plus the conditions when it was set."""

    config: GridConfig
    epoch: int                       # bumped each reposition; used for client order IDs
    set_price: float                 # price when the grid was deployed
    set_atr_pct: float               # ATR% when the grid was deployed
    set_time: float                  # unix seconds
    levels: list[float] = field(default_factory=list)
    fills_at_set: int = 0            # FillTracker.count when the grid was deployed

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "epoch": self.epoch,
            "set_price": self.set_price,
            "set_atr_pct": self.set_atr_pct,
            "set_time": self.set_time,
            "levels": self.levels,
            "fills_at_set": self.fills_at_set,
        }


@dataclass
class Decision:
    """The outcome of one decision-engine evaluation."""

    action: str                      # "hold" | "reposition" | "deploy"
    reason: str
    triggers: list[str] = field(default_factory=list)
    candidate: GridConfig | None = None
    validated: bool = False
    rejected_reason: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    walk_forward: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "triggers": self.triggers,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "validated": self.validated,
            "rejected_reason": self.rejected_reason,
            "metrics": self.metrics,
            "walk_forward": self.walk_forward,
        }


@dataclass
class PnL:
    realized: float = 0.0            # matched grid profit (Binance "Grid Profit")
    floating: float = 0.0           # unrealised mark-to-market of held inventory
    total: float = 0.0
    inventory_qty: float = 0.0
    inventory_cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
