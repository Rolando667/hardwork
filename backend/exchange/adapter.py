"""
ccxt-backed exchange adapter.

One interface (:class:`Adapter`), two implementations:

* :class:`LiveAdapter` — talks to a real exchange via ccxt. Used for ``testnet``
  (ccxt sandbox mode) and ``live``. Places/cancels real orders idempotently using
  client order IDs, with exponential backoff on rate limits.
* :class:`DryRunAdapter` — fetches *real* market data (public endpoints, no keys)
  but keeps the account side on a paper book and places nothing. This is the
  default and lets the whole decision loop run end-to-end before any real money
  is involved.

Security: keys are read from server-side config only. On connect for testnet/live
we refuse to run if the exchange reports the API key carries withdrawal scope.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import ccxt

from ..config import Mode, Settings


class ExchangeError(Exception):
    pass


@dataclass
class Order:
    """Normalised open order."""

    id: str
    client_id: str
    side: str          # buy | sell
    price: float
    amount: float
    status: str
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "client_id": self.client_id,
            "side": self.side,
            "price": self.price,
            "amount": self.amount,
            "status": self.status,
        }


def _retry(fn, *, attempts: int = 4, base: float = 0.8, max_delay: float = 10.0):
    """Call ``fn`` with exponential backoff on transient ccxt errors."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except (ccxt.RateLimitExceeded, ccxt.DDoSProtection, ccxt.NetworkError) as e:
            last = e
            delay = min(base * (2 ** i), max_delay)
            time.sleep(delay)
        except ccxt.ExchangeError:
            raise
    raise ExchangeError(f"exchange call failed after {attempts} attempts: {last}")


class Adapter:
    """Interface shared by the live and dry-run adapters."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.symbol = settings.symbol

    # market data
    def market_price(self) -> float:
        raise NotImplementedError

    def fetch_ohlcv(self, timeframe: str, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    # account
    def fetch_balances(self) -> dict[str, dict[str, float]]:
        raise NotImplementedError

    def fetch_open_orders(self) -> list[Order]:
        raise NotImplementedError

    def fetch_my_trades(self, since_ms: int | None) -> list[dict[str, Any]]:
        return []

    # trading
    def place_limit(self, side: str, price: float, amount: float, client_id: str) -> Order | None:
        raise NotImplementedError

    def cancel(self, order_id: str) -> None:
        raise NotImplementedError

    def cancel_all(self) -> int:
        raise NotImplementedError

    def seed_inventory(self, amount: float) -> float:
        """Market-buy ``amount`` of base to seed the grid's sell side.

        Returns the filled base quantity. No-op (returns 0) in dry-run.
        """
        return 0.0

    # introspection
    def amount_to_precision(self, amount: float) -> float:
        return amount

    def price_to_precision(self, price: float) -> float:
        return price

    def min_notional(self) -> float:
        return 0.0

    def startup_checks(self) -> None:
        """Run safety checks before the bot is allowed to act."""
        return None


# ---------------------------------------------------------------------------
# helpers shared by both adapters
# ---------------------------------------------------------------------------
def _build_ccxt(settings: Settings, with_keys: bool) -> ccxt.Exchange:
    if not hasattr(ccxt, settings.exchange):
        raise ExchangeError(f"unknown ccxt exchange: {settings.exchange}")
    klass = getattr(ccxt, settings.exchange)
    cfg: dict[str, Any] = {"enableRateLimit": True, "options": {"defaultType": "spot"}}
    if with_keys:
        key = settings.api_key.get_secret_value()
        secret = settings.api_secret.get_secret_value()
        if not key or not secret:
            raise ExchangeError("API key/secret required for testnet/live mode")
        cfg["apiKey"] = key
        cfg["secret"] = secret
        pw = settings.api_password.get_secret_value()
        if pw:
            cfg["password"] = pw
    ex = klass(cfg)
    return ex


def _ohlcv_to_candles(rows: list[list[float]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        out.append({
            "t": int(r[0] // 1000),
            "o": float(r[1]),
            "h": float(r[2]),
            "l": float(r[3]),
            "c": float(r[4]),
        })
    return out


# ---------------------------------------------------------------------------
# Live / testnet
# ---------------------------------------------------------------------------
class LiveAdapter(Adapter):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.ex = _build_ccxt(settings, with_keys=True)
        if settings.mode == Mode.TESTNET:
            # Use the exchange sandbox whenever mode != live.
            self.ex.set_sandbox_mode(True)
        # markets are lazy-loaded by ccxt on the first unified call (kept off the
        # startup path so a slow/blocked exchange never wedges server boot).

    def startup_checks(self) -> None:
        self._refuse_if_withdrawal_scope()

    def _refuse_if_withdrawal_scope(self) -> None:
        """Refuse to run if the key can withdraw (where the exchange reports it).

        Best-effort and per-exchange: Binance exposes apiRestrictions; for
        exchanges that don't report it we warn and continue (the user is told to
        scope keys to trade-only with an IP allow-list in the README).
        """
        ex = self.ex
        try:
            if self.settings.exchange in ("binance", "binanceus") and hasattr(
                ex, "sapi_get_account_apirestrictions"
            ):
                r = _retry(ex.sapi_get_account_apirestrictions)
                if str(r.get("enableWithdrawals", "")).lower() == "true" or r.get(
                    "enableWithdrawals"
                ) is True:
                    raise ExchangeError(
                        "API key has WITHDRAWAL permission enabled. Refusing to run. "
                        "Create a key with trade permission only (no withdrawals) and "
                        "set an IP allow-list."
                    )
                return
        except ExchangeError:
            raise
        except Exception as e:  # noqa: BLE001 - best-effort probe
            print(f"[adapter] could not verify withdrawal scope ({e}); "
                  "ensure your key is trade-only with an IP allow-list.")

    def market_price(self) -> float:
        t = _retry(lambda: self.ex.fetch_ticker(self.symbol))
        return float(t["last"])

    def fetch_ohlcv(self, timeframe: str, limit: int) -> list[dict[str, Any]]:
        rows = _retry(lambda: self.ex.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=limit))
        return _ohlcv_to_candles(rows)

    def fetch_balances(self) -> dict[str, dict[str, float]]:
        bal = _retry(self.ex.fetch_balance)
        base = self.settings.base_asset
        quote = self.settings.quote_asset
        free = bal.get("free", {})
        total = bal.get("total", {})
        return {
            "free": {base: float(free.get(base, 0) or 0), quote: float(free.get(quote, 0) or 0)},
            "total": {base: float(total.get(base, 0) or 0), quote: float(total.get(quote, 0) or 0)},
        }

    def fetch_open_orders(self) -> list[Order]:
        rows = _retry(lambda: self.ex.fetch_open_orders(self.symbol))
        out = []
        for o in rows:
            out.append(Order(
                id=str(o.get("id")),
                client_id=str(o.get("clientOrderId") or ""),
                side=str(o.get("side")),
                price=float(o.get("price") or 0),
                amount=float(o.get("amount") or 0),
                status=str(o.get("status") or "open"),
                raw=o,
            ))
        return out

    def fetch_my_trades(self, since_ms: int | None) -> list[dict[str, Any]]:
        try:
            rows = _retry(lambda: self.ex.fetch_my_trades(self.symbol, since=since_ms))
        except (ccxt.NotSupported, ExchangeError):
            return []
        out = []
        for tr in rows:
            out.append({
                "id": str(tr.get("id")),
                "ts": int(tr.get("timestamp") or 0),
                "side": str(tr.get("side")),
                "price": float(tr.get("price") or 0),
                "amount": float(tr.get("amount") or 0),
                "cost": float(tr.get("cost") or 0),
                "fee": float((tr.get("fee") or {}).get("cost") or 0),
                "fee_currency": (tr.get("fee") or {}).get("currency"),
            })
        return out

    def amount_to_precision(self, amount: float) -> float:
        return float(self.ex.amount_to_precision(self.symbol, amount))

    def price_to_precision(self, price: float) -> float:
        return float(self.ex.price_to_precision(self.symbol, price))

    def min_notional(self) -> float:
        m = self.ex.market(self.symbol)
        limits = (m.get("limits") or {}).get("cost") or {}
        return float(limits.get("min") or 0)

    def place_limit(self, side: str, price: float, amount: float, client_id: str) -> Order | None:
        price = self.price_to_precision(price)
        amount = self.amount_to_precision(amount)
        if amount <= 0:
            return None
        notional = price * amount
        mn = self.min_notional()
        if mn and notional < mn:
            # too small to place — caller logs it as a skipped level
            return None
        params = {"clientOrderId": client_id}
        o = _retry(lambda: self.ex.create_order(self.symbol, "limit", side, amount, price, params))
        return Order(
            id=str(o.get("id")),
            client_id=str(o.get("clientOrderId") or client_id),
            side=side,
            price=float(o.get("price") or price),
            amount=float(o.get("amount") or amount),
            status=str(o.get("status") or "open"),
            raw=o,
        )

    def cancel(self, order_id: str) -> None:
        try:
            _retry(lambda: self.ex.cancel_order(order_id, self.symbol))
        except ccxt.OrderNotFound:
            pass  # already gone — idempotent

    def cancel_all(self) -> int:
        n = 0
        for o in self.fetch_open_orders():
            self.cancel(o.id)
            n += 1
        return n

    def seed_inventory(self, amount: float) -> float:
        amount = self.amount_to_precision(amount)
        if amount <= 0:
            return 0.0
        o = _retry(lambda: self.ex.create_order(self.symbol, "market", "buy", amount))
        return float(o.get("filled") or o.get("amount") or amount)


# ---------------------------------------------------------------------------
# Dry-run (paper account, real market data)
# ---------------------------------------------------------------------------
class DryRunAdapter(Adapter):
    """Real prices, paper account, no orders sent.

    Decisions and the would-be order ladder are computed and logged; the account
    side is a static paper book seeded from config so PnL/metrics shown on the
    dashboard come from the strategy engine over real klines (clearly labelled
    as simulated).
    """

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        # public market data only — never sends keys. Markets lazy-load on first
        # call so a blocked exchange can't wedge server boot.
        self.ex = _build_ccxt(settings, with_keys=False)
        self._paper_orders: list[Order] = []

    def startup_checks(self) -> None:
        return None

    def market_price(self) -> float:
        t = _retry(lambda: self.ex.fetch_ticker(self.symbol))
        return float(t["last"])

    def fetch_ohlcv(self, timeframe: str, limit: int) -> list[dict[str, Any]]:
        rows = _retry(lambda: self.ex.fetch_ohlcv(self.symbol, timeframe=timeframe, limit=limit))
        return _ohlcv_to_candles(rows)

    def fetch_balances(self) -> dict[str, dict[str, float]]:
        # paper: all invest sits in quote until the (virtual) grid would deploy
        quote = self.settings.quote_asset
        base = self.settings.base_asset
        return {
            "free": {base: 0.0, quote: self.settings.invest},
            "total": {base: 0.0, quote: self.settings.invest},
        }

    def fetch_open_orders(self) -> list[Order]:
        return list(self._paper_orders)

    def amount_to_precision(self, amount: float) -> float:
        try:
            return float(self.ex.amount_to_precision(self.symbol, amount))
        except Exception:  # noqa: BLE001
            return amount

    def price_to_precision(self, price: float) -> float:
        try:
            return float(self.ex.price_to_precision(self.symbol, price))
        except Exception:  # noqa: BLE001
            return price

    def min_notional(self) -> float:
        try:
            m = self.ex.market(self.symbol)
            return float(((m.get("limits") or {}).get("cost") or {}).get("min") or 0)
        except Exception:  # noqa: BLE001
            return 0.0

    def place_limit(self, side: str, price: float, amount: float, client_id: str) -> Order | None:
        # record on the paper book so the dashboard can show the would-be ladder;
        # nothing is sent to the exchange.
        o = Order(id=f"paper-{client_id}", client_id=client_id, side=side,
                  price=self.price_to_precision(price),
                  amount=self.amount_to_precision(amount), status="open")
        self._paper_orders.append(o)
        return o

    def cancel(self, order_id: str) -> None:
        self._paper_orders = [o for o in self._paper_orders if o.id != order_id]

    def cancel_all(self) -> int:
        n = len(self._paper_orders)
        self._paper_orders = []
        return n


def build_adapter(settings: Settings) -> Adapter:
    if settings.mode == Mode.DRY_RUN:
        return DryRunAdapter(settings)
    return LiveAdapter(settings)
