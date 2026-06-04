"""UTC time helpers and funding-interval normalization.

Everything internal is UTC and timezone-aware. ccxt returns epoch milliseconds;
convert through here so the rest of the code never touches naive datetimes.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current time, timezone-aware UTC."""
    return datetime.now(timezone.utc)


def ms_to_utc(ms: float | int | None) -> datetime | None:
    """Convert epoch milliseconds to a UTC datetime, or None if no timestamp."""
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def normalize_rate_per_hour(raw_rate: float, interval_hours: float) -> float:
    """Convert a raw funding rate over its interval into a per-hour rate.

    Guards against a zero/None interval (would otherwise divide by zero); falls
    back to treating the rate as already per-interval=1h, which is then visibly
    wrong in logs rather than crashing.
    """
    if not interval_hours or interval_hours <= 0:
        return raw_rate
    return raw_rate / interval_hours
