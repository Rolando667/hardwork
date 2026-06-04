"""Universe auto-discovery — the first step of every scan.

The bot does not work off a hardcoded coin list. Each scan it forms the universe:
take coins listed (and live-quoted) on >= 2 exchanges, drop those below a volume
floor, and keep the top-N by 24h quote volume. This keeps us off illiquid junk
while staying off a fixed list whose liquidity drifts over time.

P0 implements the volume floor + top-N. The richer filters (L2 depth, max coin
spread, blacklist, new-listing age, symmetric capacity) are P1.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.config import UniverseConfig
from ..core.logging_setup import get_logger
from ..core.models import NormalizedMarket, QuoteSnapshot

log = get_logger(__name__)


@dataclass(frozen=True)
class UniverseEntry:
    coin: str
    exchanges: list[str]   # venues with both a market and a live quote
    volume: float          # representative 24h quote volume (max across venues)


@dataclass(frozen=True)
class UniverseStats:
    total_coins_seen: int
    on_multiple_exchanges: int
    passed_volume: int
    selected: int
    dropped_single_exchange: int
    dropped_low_volume: int


def build_universe(
    markets_by_ex: dict[str, dict[str, NormalizedMarket]],
    quotes_by_ex: dict[str, dict[str, QuoteSnapshot]],
    volumes_by_ex: dict[str, dict[str, float]],
    cfg: UniverseConfig,
) -> tuple[list[UniverseEntry], UniverseStats]:
    """Return (selected entries sorted by volume desc, stats for logging)."""
    # coin -> exchanges where it is both listed and currently quoted.
    presence: dict[str, list[str]] = {}
    for ex, markets in markets_by_ex.items():
        quotes = quotes_by_ex.get(ex, {})
        for coin in markets:
            if coin in quotes:
                presence.setdefault(coin, []).append(ex)

    total_seen = len(presence)
    multi = {c: exs for c, exs in presence.items() if len(exs) >= 2}
    dropped_single = total_seen - len(multi)

    entries: list[UniverseEntry] = []
    dropped_low_vol = 0
    for coin, exs in multi.items():
        # Cross-exchange volume reporting is inconsistent (base vs quote); take the
        # max across venues as the representative figure. Documented limitation.
        vol = max((volumes_by_ex.get(ex, {}).get(coin, 0.0) for ex in exs), default=0.0)
        if vol < cfg.min_quote_volume_24h:
            dropped_low_vol += 1
            continue
        entries.append(UniverseEntry(coin=coin, exchanges=sorted(exs), volume=vol))

    passed_volume = len(entries)
    entries.sort(key=lambda e: e.volume, reverse=True)
    selected = entries[: cfg.top_n]

    stats = UniverseStats(
        total_coins_seen=total_seen,
        on_multiple_exchanges=len(multi),
        passed_volume=passed_volume,
        selected=len(selected),
        dropped_single_exchange=dropped_single,
        dropped_low_volume=dropped_low_vol,
    )
    return selected, stats
