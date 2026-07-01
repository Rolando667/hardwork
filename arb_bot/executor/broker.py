"""Broker abstraction: one interface, a DRY_RUN implementation and a ccxt one.

The execution logic (state machine, atomic opener, kill switch, reconciliation)
talks only to this interface, so every safety mechanism is exercised identically
in DRY_RUN and live. DRY_RUN places nothing real; it simulates fills (and can
simulate a leg that never fills, to exercise the emergency-close path).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from random import Random

from ..core.logging_setup import get_logger
from .reduce_only import build_order_params

log = get_logger(__name__)

_BPS = 10_000.0


@dataclass
class OrderResult:
    exchange: str
    symbol: str
    client_order_id: str
    side: str                 # 'buy' | 'sell'
    amount: float             # contracts requested
    status: str               # 'filled' | 'open' | 'rejected' | 'canceled'
    filled: float             # contracts filled
    average: float | None     # avg fill price
    reduce_only: bool
    dry_run: bool
    order_id: str | None = None
    error: str | None = None

    @property
    def is_filled(self) -> bool:
        return self.status == "filled" and self.filled > 0


@dataclass
class PositionSnapshot:
    exchange: str
    symbol: str
    side: str | None          # 'long' | 'short' | None (flat)
    contracts: float
    entry_price: float | None


class Broker(abc.ABC):
    is_dry_run: bool = True

    @abc.abstractmethod
    def create_order(
        self,
        *,
        exchange: str,
        symbol: str,
        side: str,
        amount: float,
        position_side: str,
        reduce_only: bool,
        position_mode: str,
        client_order_id: str,
        price: float | None = None,
    ) -> OrderResult: ...

    @abc.abstractmethod
    def fetch_position(self, exchange: str, symbol: str) -> PositionSnapshot: ...

    @abc.abstractmethod
    def fetch_open_orders(self, exchange: str, symbol: str | None = None) -> list[OrderResult]: ...

    @abc.abstractmethod
    def cancel_order(self, exchange: str, symbol: str, client_order_id: str) -> None: ...


# --------------------------------------------------------------------------- #
# DRY_RUN
# --------------------------------------------------------------------------- #
@dataclass
class _VirtualPos:
    contracts: float = 0.0     # signed: + long, - short
    entry_price: float | None = None


class DryRunBroker(Broker):
    """Simulates fills against provided quotes. Never touches a real exchange."""

    is_dry_run = True

    def __init__(self, slippage_bps: float = 1.0, one_leg_fail_prob: float = 0.0, seed: int = 7) -> None:
        self._slip = slippage_bps
        self._fail_prob = one_leg_fail_prob
        self._rng = Random(seed)
        self._quotes: dict[tuple[str, str], tuple[float, float]] = {}  # (ex,sym)->(bid,ask)
        self._pos: dict[tuple[str, str], _VirtualPos] = {}
        self._open_orders: dict[str, OrderResult] = {}
        self._force_fail_next: set[str] = set()  # client_order_ids to force no-fill (tests)
        self.fail_open_exchanges: set[str] = set()  # opens on these venues never fill (tests)

    # test/loop hooks ------------------------------------------------------
    def set_quote(self, exchange: str, symbol: str, bid: float, ask: float) -> None:
        self._quotes[(exchange, symbol)] = (bid, ask)

    def force_fail(self, client_order_id: str) -> None:
        """Make a specific order never fill (used to exercise emergency close)."""
        self._force_fail_next.add(client_order_id)

    # broker interface -----------------------------------------------------
    def create_order(self, *, exchange, symbol, side, amount, position_side,
                      reduce_only, position_mode, client_order_id, price=None) -> OrderResult:
        params = build_order_params(
            exchange, position_side=position_side, reduce_only=reduce_only, position_mode=position_mode
        )
        log.info(
            "DRY_RUN would %s %.6g %s on %s (reduce_only=%s, params=%s, coid=%s)",
            side, amount, symbol, exchange, reduce_only, params, client_order_id,
        )

        no_fill = client_order_id in self._force_fail_next or (
            not reduce_only and exchange in self.fail_open_exchanges
        ) or (
            not reduce_only and self._fail_prob > 0 and self._rng.random() < self._fail_prob
        )
        if no_fill:
            res = OrderResult(exchange, symbol, client_order_id, side, amount,
                              status="open", filled=0.0, average=None,
                              reduce_only=reduce_only, dry_run=True, order_id=f"dry-{client_order_id}")
            self._open_orders[client_order_id] = res
            return res

        bid, ask = self._quotes.get((exchange, symbol), (price or 0.0, price or 0.0))
        fill = ask if side == "buy" else bid
        if fill <= 0:
            fill = price or 0.0
        # taker crossing slippage
        fill *= (1 + self._slip / _BPS) if side == "buy" else (1 - self._slip / _BPS)

        signed = amount if side == "buy" else -amount
        pos = self._pos.setdefault((exchange, symbol), _VirtualPos())
        pos.contracts += signed
        if abs(pos.contracts) < 1e-12:
            pos.contracts = 0.0
            pos.entry_price = None
        elif pos.entry_price is None:
            pos.entry_price = fill

        return OrderResult(exchange, symbol, client_order_id, side, amount,
                           status="filled", filled=amount, average=fill,
                           reduce_only=reduce_only, dry_run=True, order_id=f"dry-{client_order_id}")

    def fetch_position(self, exchange: str, symbol: str) -> PositionSnapshot:
        pos = self._pos.get((exchange, symbol))
        if pos is None or pos.contracts == 0.0:
            return PositionSnapshot(exchange, symbol, None, 0.0, None)
        side = "long" if pos.contracts > 0 else "short"
        return PositionSnapshot(exchange, symbol, side, abs(pos.contracts), pos.entry_price)

    def fetch_open_orders(self, exchange: str, symbol: str | None = None) -> list[OrderResult]:
        return [o for o in self._open_orders.values()
                if o.exchange == exchange and (symbol is None or o.symbol == symbol)]

    def cancel_order(self, exchange: str, symbol: str, client_order_id: str) -> None:
        o = self._open_orders.pop(client_order_id, None)
        if o is not None:
            o.status = "canceled"
            log.info("DRY_RUN cancel %s on %s", client_order_id, exchange)


# --------------------------------------------------------------------------- #
# Live (ccxt) — structural; only used when live_trading is confirmed
# --------------------------------------------------------------------------- #
class CcxtBroker(Broker):
    """Real orders via authenticated ccxt clients. Requires keys; used only live."""

    is_dry_run = False

    def __init__(self, exchanges: dict) -> None:
        # exchanges: name -> authenticated ccxt.Exchange
        self._ex = exchanges

    def create_order(self, *, exchange, symbol, side, amount, position_side,
                      reduce_only, position_mode, client_order_id, price=None) -> OrderResult:
        ex = self._ex[exchange]
        params = build_order_params(
            exchange, position_side=position_side, reduce_only=reduce_only, position_mode=position_mode
        )
        params["clientOrderId"] = client_order_id  # idempotency: retry/reconnect won't double
        otype = "limit" if price is not None else "market"
        try:
            o = ex.create_order(symbol, otype, side, amount, price, params)
            status = "filled" if o.get("status") == "closed" else (o.get("status") or "open")
            return OrderResult(
                exchange, symbol, client_order_id, side, amount,
                status="filled" if status == "closed" else status,
                filled=float(o.get("filled") or 0.0), average=o.get("average"),
                reduce_only=reduce_only, dry_run=False, order_id=str(o.get("id")),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("order failed %s %s %s: %s", exchange, symbol, side, exc)
            return OrderResult(exchange, symbol, client_order_id, side, amount,
                               status="rejected", filled=0.0, average=None,
                               reduce_only=reduce_only, dry_run=False, error=str(exc))

    def fetch_position(self, exchange: str, symbol: str) -> PositionSnapshot:
        ex = self._ex[exchange]
        try:
            positions = ex.fetch_positions([symbol])
        except Exception as exc:  # noqa: BLE001
            log.error("fetch_position failed %s %s: %s", exchange, symbol, exc)
            return PositionSnapshot(exchange, symbol, None, 0.0, None)
        for p in positions or []:
            contracts = float(p.get("contracts") or 0.0)
            if contracts and p.get("symbol") == symbol:
                side = p.get("side") or ("long" if contracts > 0 else "short")
                return PositionSnapshot(exchange, symbol, side, abs(contracts),
                                        p.get("entryPrice"))
        return PositionSnapshot(exchange, symbol, None, 0.0, None)

    def fetch_open_orders(self, exchange: str, symbol: str | None = None) -> list[OrderResult]:
        ex = self._ex[exchange]
        try:
            orders = ex.fetch_open_orders(symbol)
        except Exception as exc:  # noqa: BLE001
            log.error("fetch_open_orders failed %s: %s", exchange, exc)
            return []
        out = []
        for o in orders or []:
            out.append(OrderResult(
                exchange, o.get("symbol"), o.get("clientOrderId") or "", o.get("side"),
                float(o.get("amount") or 0.0), o.get("status") or "open",
                float(o.get("filled") or 0.0), o.get("average"),
                bool((o.get("params") or {}).get("reduceOnly")), dry_run=False,
                order_id=str(o.get("id")),
            ))
        return out

    def cancel_order(self, exchange: str, symbol: str, client_order_id: str) -> None:
        ex = self._ex[exchange]
        try:
            ex.cancel_order(client_order_id, symbol, {"clientOrderId": client_order_id})
        except Exception as exc:  # noqa: BLE001
            log.error("cancel failed %s %s: %s", exchange, client_order_id, exc)
