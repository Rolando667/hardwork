"""Per-exchange funding-rate normalization.

The single biggest correctness risk in the whole cost model: ``fetchFundingRate``
fields are NOT unified across exchanges. The raw ``fundingRate`` is comparable
only once divided by its (exchange- and coin-specific) interval. Intervals are
dynamic — Binance/Bybit switch some coins to 1h, others run 4h/8h — so we must
NEVER assume 8h. This module extracts the interval per-exchange, normalizes to a
per-hour rate, and flags when it had to fall back to the configured default.
"""

from __future__ import annotations

import re

from ..core.logging_setup import get_logger
from ..core.models import FundingSnapshot
from ..core.timeutils import ms_to_utc, normalize_rate_per_hour, utcnow

log = get_logger(__name__)

# Parses ccxt's unified interval strings like "8h", "4h", "1h", "480m".
_INTERVAL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([hmd])\s*$", re.IGNORECASE)


def _parse_interval_string(value: object) -> float | None:
    """Parse an interval like '8h' / '480m' / '1d' into hours, or None."""
    if value is None:
        return None
    m = _INTERVAL_RE.match(str(value))
    if not m:
        return None
    qty = float(m.group(1))
    unit = m.group(2).lower()
    return {"h": qty, "m": qty / 60.0, "d": qty * 24.0}[unit]


def _interval_from_timestamps(fr: dict) -> float | None:
    """Derive interval (hours) from successive funding timestamps when present.

    For exchanges where ``fundingTimestamp`` is the *current* settlement and
    ``nextFundingTimestamp`` is the next one (e.g. OKX), their delta is the
    interval. Where the two fields mean the same instant, this returns None and
    we fall through to other sources.
    """
    cur = fr.get("fundingTimestamp")
    nxt = fr.get("nextFundingTimestamp")
    if cur is None or nxt is None:
        return None
    try:
        delta_h = (float(nxt) - float(cur)) / 3_600_000.0
    except (TypeError, ValueError):
        return None
    # Accept only plausible perp intervals; reject 0 or absurd values.
    if 0.5 <= delta_h <= 24.0:
        return round(delta_h, 4)
    return None


def _interval_from_info(exchange: str, info: dict) -> float | None:
    """Exchange-specific interval extraction from the raw ``info`` payload."""
    if not isinstance(info, dict):
        return None

    if exchange == "bybit":
        # Bybit reports fundingInterval in MINUTES (e.g. 480).
        raw = info.get("fundingInterval") or info.get("funding_interval")
        if raw is not None:
            try:
                return float(raw) / 60.0
            except (TypeError, ValueError):
                return None

    if exchange == "gate":
        # Gate (gateio) reports funding_interval in SECONDS (e.g. 28800).
        raw = info.get("funding_interval")
        if raw is not None:
            try:
                return float(raw) / 3600.0
            except (TypeError, ValueError):
                return None

    if exchange == "binance":
        # Binance premiumIndex sometimes carries fundingIntervalHours.
        raw = info.get("fundingIntervalHours")
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None

    return None


def normalize_funding(
    exchange: str,
    symbol: str,
    raw: dict,
    default_interval_hours: float,
) -> FundingSnapshot:
    """Turn a ccxt funding-rate dict into a normalized FundingSnapshot.

    Resolution order for the interval: unified ``interval`` string ->
    exchange-specific ``info`` field -> successive timestamps -> configured
    default (flagged as inferred).
    """
    rate = raw.get("fundingRate")
    try:
        rate = float(rate) if rate is not None else 0.0
    except (TypeError, ValueError):
        rate = 0.0

    interval = _parse_interval_string(raw.get("interval"))
    inferred = False
    if interval is None:
        interval = _interval_from_info(exchange, raw.get("info") or {})
    if interval is None:
        interval = _interval_from_timestamps(raw)
    if interval is None or interval <= 0:
        interval = float(default_interval_hours)
        inferred = True

    next_ts = ms_to_utc(raw.get("nextFundingTimestamp") or raw.get("fundingTimestamp"))

    return FundingSnapshot(
        exchange=exchange,
        symbol=symbol,
        funding_rate=rate,
        interval_hours=interval,
        rate_per_hour=normalize_rate_per_hour(rate, interval),
        next_funding_ts=next_ts,
        ts=utcnow(),
        interval_inferred=inferred,
    )


def zero_funding(exchange: str, symbol: str, default_interval_hours: float) -> FundingSnapshot:
    """A neutral funding snapshot used when the exchange has no funding data."""
    return FundingSnapshot(
        exchange=exchange,
        symbol=symbol,
        funding_rate=0.0,
        interval_hours=float(default_interval_hours),
        rate_per_hour=0.0,
        next_funding_ts=None,
        ts=utcnow(),
        interval_inferred=True,
    )
