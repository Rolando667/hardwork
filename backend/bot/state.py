"""
Fill-based PnL tracking for testnet/live.

The exchange is the source of truth. Each cycle we pull new fills (``myTrades``)
and fold them into running inventory + average cost, which yields the same
realized / floating split the calculator uses:

* realized  = matched grid profit booked when inventory is sold above its cost
* floating  = mark-to-market of currently-held inventory vs its cost basis
* total     = realized + floating

In ``dry_run`` there are no fills; the runner sources PnL straight from the
strategy engine over recent klines instead.

Dedup is bounded correctly: we fetch with ``since = last_trade_ts`` (inclusive on
most exchanges), so the only trades ever re-seen are those sharing the newest
millisecond. We therefore persist just the IDs at that boundary timestamp — a
tiny, bounded set that survives restarts without ever dropping a dedup key (the
earlier "keep last N ids" approach could drop boundary keys and double-count).
"""
from __future__ import annotations

from typing import Any

from ..models import PnL


class FillTracker:
    def __init__(self) -> None:
        self.inventory_qty = 0.0
        self.inventory_cost = 0.0     # total quote cost basis of held inventory
        self.realized = 0.0
        self.last_trade_ts = 0        # ms; watermark for incremental fetch
        self.count = 0                # total fills applied (for live fill-rate)
        self.boundary_ids: set[str] = set()  # ids at ts == last_trade_ts (dedup)

    def to_state(self) -> dict[str, Any]:
        return {
            "inventory_qty": self.inventory_qty,
            "inventory_cost": self.inventory_cost,
            "realized": self.realized,
            "last_trade_ts": self.last_trade_ts,
            "count": self.count,
            "boundary_ids": list(self.boundary_ids),
        }

    @classmethod
    def from_state(cls, s: dict[str, Any] | None) -> "FillTracker":
        ft = cls()
        if not s:
            return ft
        ft.inventory_qty = float(s.get("inventory_qty", 0))
        ft.inventory_cost = float(s.get("inventory_cost", 0))
        ft.realized = float(s.get("realized", 0))
        ft.last_trade_ts = int(s.get("last_trade_ts", 0))
        ft.count = int(s.get("count", 0))
        ft.boundary_ids = set(s.get("boundary_ids", []))
        return ft

    def ingest(self, trades: list[dict[str, Any]], base: str, quote: str) -> int:
        """Apply new fills. Returns the number of newly-applied trades."""
        applied = 0
        for tr in sorted(trades, key=lambda x: x.get("ts", 0)):
            tid = str(tr.get("id"))
            ts = int(tr.get("ts", 0))
            if ts < self.last_trade_ts:
                continue  # older than the watermark — already processed
            if ts == self.last_trade_ts and tid in self.boundary_ids:
                continue  # boundary duplicate — already seen this exact fill

            side = tr.get("side")
            price = float(tr.get("price", 0))
            amount = float(tr.get("amount", 0))
            cost = float(tr.get("cost", price * amount))
            fee = float(tr.get("fee", 0) or 0)
            fee_ccy = tr.get("fee_currency")
            if side == "buy":
                self.inventory_qty += amount
                self.inventory_cost += cost
                if fee_ccy == quote:
                    self.inventory_cost += fee
                elif fee_ccy == base:
                    self.inventory_qty -= fee
            elif side == "sell":
                avg = (self.inventory_cost / self.inventory_qty) if self.inventory_qty > 1e-12 else price
                proceeds = cost - (fee if fee_ccy == quote else 0.0)
                self.realized += proceeds - avg * amount
                self.inventory_qty -= amount
                self.inventory_cost -= avg * amount
                if self.inventory_qty < 1e-12:
                    self.inventory_qty = 0.0
                    self.inventory_cost = 0.0

            self.count += 1
            applied += 1
            if ts > self.last_trade_ts:
                self.last_trade_ts = ts
                self.boundary_ids = {tid}
            else:  # ts == last_trade_ts
                self.boundary_ids.add(tid)
        return applied

    def pnl(self, price: float) -> PnL:
        floating = self.inventory_qty * price - self.inventory_cost
        return PnL(
            realized=self.realized,
            floating=floating,
            total=self.realized + floating,
            inventory_qty=self.inventory_qty,
            inventory_cost=self.inventory_cost,
        )
