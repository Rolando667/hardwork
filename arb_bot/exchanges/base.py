"""ExchangeClient — a thin, normalized ccxt wrapper for one exchange.

Responsibilities (P0, read-only):
* init ccxt with ``defaultType=swap`` and rate limiting,
* ``load_markets()`` first, then expose linear USDT-margined swaps as
  :class:`NormalizedMarket` keyed by coin,
* fetch top-of-book (best bid/ask, never ``last``) and funding in batch.

Per-exchange quirks (contractSize-as-string #11123, non-unified funding fields)
are handled here and in :mod:`funding` so the rest of the bot sees clean data.
"""

from __future__ import annotations

import os

import ccxt

from ..core.config import FeesConfig, MarketConfig
from ..core.logging_setup import get_logger
from ..core.models import FundingSnapshot, NormalizedMarket, QuoteSnapshot
from ..core.timeutils import ms_to_utc, utcnow
from .funding import normalize_funding, zero_funding

log = get_logger(__name__)


class ExchangeLoadError(Exception):
    """Raised when an exchange cannot be initialized or load its markets."""


class ExchangeClient:
    def __init__(
        self,
        name: str,
        market_cfg: MarketConfig,
        fees_cfg: FeesConfig,
        request_timeout_ms: int = 15000,
    ) -> None:
        self.name = name
        self.market_cfg = market_cfg
        self.fees_cfg = fees_cfg
        self._timeout = request_timeout_ms
        self._exchange: ccxt.Exchange | None = None
        # coin -> NormalizedMarket (linear USDT swaps only)
        self.markets: dict[str, NormalizedMarket] = {}

    # ---- lifecycle -------------------------------------------------------

    def load(self) -> None:
        """Create the ccxt client and load markets. Raises ExchangeLoadError."""
        try:
            klass = getattr(ccxt, self.name)
        except AttributeError as exc:
            raise ExchangeLoadError(f"unknown ccxt exchange '{self.name}'") from exc

        try:
            self._exchange = klass(
                {
                    "enableRateLimit": True,
                    "timeout": self._timeout,
                    "options": {"defaultType": self.market_cfg.type},
                }
            )
            _configure_session(self._exchange)
            self._exchange.load_markets()
        except Exception as exc:  # noqa: BLE001 - ccxt raises a wide variety
            raise ExchangeLoadError(f"{self.name}: {type(exc).__name__}: {exc}") from exc

        self.markets = self._build_markets()
        log.info(
            "%s loaded: %d linear %s/%s markets",
            self.name,
            len(self.markets),
            self.market_cfg.contract,
            self.market_cfg.settle,
        )

    # ---- market normalization -------------------------------------------

    def _build_markets(self) -> dict[str, NormalizedMarket]:
        assert self._exchange is not None
        out: dict[str, NormalizedMarket] = {}
        for m in self._exchange.markets.values():
            nm = self._normalize_market(m)
            if nm is not None:
                # If a coin somehow maps twice, keep the first (deterministic).
                out.setdefault(nm.coin, nm)
        return out

    def _normalize_market(self, m: dict) -> NormalizedMarket | None:
        """Keep only active linear USDT-margined swaps; normalize fields."""
        if not m.get("swap"):
            return None
        if not m.get("linear"):
            return None
        if m.get("settle") != self.market_cfg.settle:
            return None
        if m.get("active") is False:
            return None

        limits = m.get("limits") or {}
        amount = limits.get("amount") or {}
        cost = limits.get("cost") or {}
        precision = m.get("precision") or {}

        # ccxt #11123: contractSize is sometimes a string — cast explicitly.
        try:
            contract_size = float(m.get("contractSize") or 1.0)
        except (TypeError, ValueError):
            contract_size = 1.0

        maker, taker = self._resolve_fees(m)

        return NormalizedMarket(
            exchange=self.name,
            coin=str(m.get("base")),
            symbol=str(m.get("symbol")),
            base=str(m.get("base")),
            quote=str(m.get("quote")),
            settle=str(m.get("settle")),
            linear=True,
            contract_size=contract_size,
            amount_min=_as_float(amount.get("min")),
            amount_max=_as_float(amount.get("max")),
            cost_min=_as_float(cost.get("min")),
            cost_max=_as_float(cost.get("max")),
            amount_step=_precision_step(precision.get("amount")),
            maker_fee=maker,
            taker_fee=taker,
        )

    def _resolve_fees(self, m: dict) -> tuple[float, float]:
        """Config override (your real VIP/discount tier) beats ccxt defaults."""
        override = self.fees_cfg.fee_override(self.name)
        if override:
            maker = float(override.get("maker", m.get("maker") or 0.0))
            taker = float(override.get("taker", m.get("taker") or 0.0))
            return maker, taker
        return float(m.get("maker") or 0.0), float(m.get("taker") or 0.0)

    # ---- live data -------------------------------------------------------

    def fetch_tickers(self) -> dict[str, QuoteSnapshot]:
        """One batched call -> best bid/ask per coin for our markets.

        Also the source of 24h quote volume (returned separately via
        :meth:`fetch_volumes` from the same payload would double the call, so we
        expose both from one fetch here through :attr:`_last_raw_tickers`).
        """
        assert self._exchange is not None
        symbols = [nm.symbol for nm in self.markets.values()]
        raw = self._safe_fetch_tickers(symbols)
        self._last_raw_tickers = raw

        out: dict[str, QuoteSnapshot] = {}
        for nm in self.markets.values():
            t = raw.get(nm.symbol)
            if not t:
                continue
            bid = _as_float(t.get("bid"))
            ask = _as_float(t.get("ask"))
            if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
                continue  # skip crossed/empty books (never fall back to 'last')
            out[nm.coin] = QuoteSnapshot(
                exchange=self.name,
                symbol=nm.symbol,
                bid=bid,
                ask=ask,
                ts=ms_to_utc(t.get("timestamp")) or utcnow(),
            )
        return out

    def volumes(self) -> dict[str, float]:
        """24h quote volume per coin, from the last :meth:`fetch_tickers` call."""
        raw = getattr(self, "_last_raw_tickers", {})
        out: dict[str, float] = {}
        for nm in self.markets.values():
            t = raw.get(nm.symbol)
            if not t:
                continue
            qv = _as_float(t.get("quoteVolume"))
            if qv is None:
                base_v = _as_float(t.get("baseVolume"))
                last = _as_float(t.get("last")) or _as_float(t.get("close"))
                qv = base_v * last if (base_v is not None and last is not None) else 0.0
            out[nm.coin] = qv or 0.0
        return out

    def fetch_funding(self, coins: list[str]) -> dict[str, FundingSnapshot]:
        """Funding per coin, batched where the exchange supports it."""
        assert self._exchange is not None
        symbols = [self.markets[c].symbol for c in coins if c in self.markets]
        default_h = self.fees_cfg.default_funding_interval_hours
        out: dict[str, FundingSnapshot] = {}

        if self._exchange.has.get("fetchFundingRates"):
            try:
                raw = self._exchange.fetch_funding_rates(symbols)
                for coin in coins:
                    nm = self.markets.get(coin)
                    if nm and nm.symbol in raw:
                        out[coin] = normalize_funding(self.name, nm.symbol, raw[nm.symbol], default_h)
                if out:
                    return self._fill_missing_funding(coins, out, default_h)
            except Exception as exc:  # noqa: BLE001
                log.warning("%s fetch_funding_rates failed (%s); trying per-symbol", self.name, exc)

        # Per-symbol fallback.
        if self._exchange.has.get("fetchFundingRate"):
            for coin in coins:
                nm = self.markets.get(coin)
                if not nm:
                    continue
                try:
                    raw = self._exchange.fetch_funding_rate(nm.symbol)
                    out[coin] = normalize_funding(self.name, nm.symbol, raw, default_h)
                except Exception as exc:  # noqa: BLE001
                    log.debug("%s funding fetch failed for %s: %s", self.name, coin, exc)

        return self._fill_missing_funding(coins, out, default_h)

    def _fill_missing_funding(
        self, coins: list[str], out: dict[str, FundingSnapshot], default_h: float
    ) -> dict[str, FundingSnapshot]:
        for coin in coins:
            nm = self.markets.get(coin)
            if nm and coin not in out:
                out[coin] = zero_funding(self.name, nm.symbol, default_h)
        return out

    def _safe_fetch_tickers(self, symbols: list[str]) -> dict:
        assert self._exchange is not None
        try:
            if self._exchange.has.get("fetchTickers"):
                return self._exchange.fetch_tickers(symbols)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s fetch_tickers(symbols) failed (%s); fetching all", self.name, exc)
        try:
            return self._exchange.fetch_tickers()
        except Exception as exc:  # noqa: BLE001
            log.warning("%s fetch_tickers() failed: %s", self.name, exc)
            return {}


def _configure_session(exchange: ccxt.Exchange) -> None:
    """Make ccxt's HTTP session honor the environment's proxy / CA bundle.

    ccxt sets ``session.trust_env = False`` by default, so it ignores
    ``REQUESTS_CA_BUNDLE``/``HTTPS_PROXY`` and verifies against certifi only. In
    networks behind a TLS-intercepting egress proxy (corporate / sandboxed), that
    yields a self-signed-cert failure. We re-enable env trust and point ``verify``
    at the env CA bundle when present — keeping verification ON, just against the
    correct chain. A no-op on an open network.
    """
    session = getattr(exchange, "session", None)
    if session is None:
        return
    session.trust_env = True
    ca = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if ca and os.path.exists(ca):
        session.verify = ca


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _precision_step(value: object) -> float | None:
    """ccxt precision may be a step size (e.g. 0.001) or a digit count (e.g. 3).

    Heuristic: integers >= 1 are digit counts -> 10**-n; otherwise it is already
    a step size. None stays None (no rounding constraint known).
    """
    f = _as_float(value)
    if f is None:
        return None
    if f >= 1 and float(f).is_integer():
        return 10.0 ** (-int(f))
    return f
