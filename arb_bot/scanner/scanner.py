"""Scan orchestration: fetch -> universe -> evaluate every exchange-pair.

For each universe coin and each ordered exchange pair, we buy on the cheaper
venue and sell on the dearer one, validate the pair, size symmetrically, and
run the shared fees engine. Output is a ranked list of opportunities (signal or
not) so the spread *distribution* is visible even when nothing clears threshold.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from ..core.config import Config
from ..core.logging_setup import get_logger
from ..core.models import FundingSnapshot, Opportunity, QuoteSnapshot
from ..core.timeutils import utcnow
from ..exchanges.base import ExchangeClient
from ..fees.engine import compute_cost_breakdown
from ..pairs.validate import validate_pair
from ..risk.sizing import symmetric_size
from .universe import UniverseEntry, UniverseStats, build_universe

log = get_logger(__name__)


@dataclass
class ScanResult:
    opportunities: list[Opportunity]
    universe: list[UniverseEntry]
    stats: UniverseStats
    skipped_pairs: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)
    exchanges_loaded: list[str] = field(default_factory=list)
    # exchange -> {"summary": "4h x6, 8h x14", "by_interval": {"4h": 6}, "inferred": 0}
    funding_intervals: dict[str, dict] = field(default_factory=dict)


def scan(clients: dict[str, ExchangeClient], cfg: Config) -> ScanResult:
    """Run one full scan pass across all loaded exchanges."""
    # 1) One batched ticker fetch per exchange -> quotes + volumes.
    quotes_by_ex: dict[str, dict[str, QuoteSnapshot]] = {}
    volumes_by_ex: dict[str, dict[str, float]] = {}
    markets_by_ex = {name: c.markets for name, c in clients.items()}
    for name, client in clients.items():
        quotes_by_ex[name] = client.fetch_tickers()
        volumes_by_ex[name] = client.volumes()

    # 2) Form the universe (intersection >=2 venues, volume floor, top-N).
    universe, stats = build_universe(markets_by_ex, quotes_by_ex, volumes_by_ex, cfg.universe)
    log.info(
        "universe: %d coins seen, %d on >=2 venues, %d passed volume, %d selected "
        "(dropped: %d single-venue, %d low-volume)",
        stats.total_coins_seen,
        stats.on_multiple_exchanges,
        stats.passed_volume,
        stats.selected,
        stats.dropped_single_exchange,
        stats.dropped_low_volume,
    )

    # 3) Funding for universe coins only (limit request volume), per exchange.
    funding_by_ex: dict[str, dict[str, FundingSnapshot]] = {}
    coins_per_ex: dict[str, list[str]] = {}
    for entry in universe:
        for ex in entry.exchanges:
            coins_per_ex.setdefault(ex, []).append(entry.coin)
    for name, coins in coins_per_ex.items():
        funding_by_ex[name] = clients[name].fetch_funding(coins)
    funding_intervals = _summarize_funding_intervals(funding_by_ex)

    # 4) Evaluate every exchange pair for every universe coin.
    opportunities: list[Opportunity] = []
    skip_reasons: dict[str, int] = {}
    skipped = 0

    for entry in universe:
        for ex_a, ex_b in itertools.combinations(entry.exchanges, 2):
            q_a = quotes_by_ex[ex_a].get(entry.coin)
            q_b = quotes_by_ex[ex_b].get(entry.coin)
            if q_a is None or q_b is None:
                continue

            # Buy where it is cheaper (lower mid), sell where dearer.
            if q_a.mid <= q_b.mid:
                long_ex, short_ex, long_q, short_q = ex_a, ex_b, q_a, q_b
            else:
                long_ex, short_ex, long_q, short_q = ex_b, ex_a, q_b, q_a

            opp = _evaluate(
                clients, cfg, entry.coin, long_ex, short_ex, long_q, short_q, funding_by_ex
            )
            if opp is None:
                skipped += 1
                continue
            opportunities.append(opp)

    # Sort best-first by net spread.
    opportunities.sort(key=lambda o: o.cost.net_spread_bps, reverse=True)
    return ScanResult(
        opportunities=opportunities,
        universe=universe,
        stats=stats,
        skipped_pairs=skipped,
        skip_reasons=skip_reasons,
        exchanges_loaded=list(clients),
        funding_intervals=funding_intervals,
    )


def _evaluate(
    clients: dict[str, ExchangeClient],
    cfg: Config,
    coin: str,
    long_ex: str,
    short_ex: str,
    long_q: QuoteSnapshot,
    short_q: QuoteSnapshot,
    funding_by_ex: dict[str, dict[str, FundingSnapshot]],
) -> Opportunity | None:
    long_market = clients[long_ex].markets[coin]
    short_market = clients[short_ex].markets[coin]

    ok, reason = validate_pair(long_market, short_market, long_q, short_q)
    if not ok:
        log.debug("skip %s %s/%s: %s", coin, long_ex, short_ex, reason)
        return None

    sizing = symmetric_size(
        long_market=long_market,
        short_market=short_market,
        target_notional_quote=cfg.sizing.target_notional_quote,
        reference_price=long_q.mid,
        cfg=cfg.sizing,
    )
    if not sizing.ok:
        log.debug("skip %s %s/%s sizing: %s", coin, long_ex, short_ex, sizing.skip_reason)
        return None

    long_funding = funding_by_ex.get(long_ex, {}).get(coin)
    short_funding = funding_by_ex.get(short_ex, {}).get(coin)
    if long_funding is None or short_funding is None:
        log.debug("skip %s %s/%s: missing funding", coin, long_ex, short_ex)
        return None

    cost = compute_cost_breakdown(
        long_market=long_market,
        short_market=short_market,
        long_quote=long_q,
        short_quote=short_q,
        long_funding=long_funding,
        short_funding=short_funding,
        sizing=sizing,
        cfg=cfg.fees,
    )

    return Opportunity(
        coin=coin,
        long_exchange=long_ex,
        short_exchange=short_ex,
        long_quote=long_q,
        short_quote=short_q,
        sizing=sizing,
        cost=cost,
        signal=cost.net_spread_bps >= cfg.thresholds.entry_net_spread_bps,
        ts=utcnow(),
    )


def _summarize_funding_intervals(
    funding_by_ex: dict[str, dict[str, FundingSnapshot]],
) -> dict[str, dict]:
    """Summarize the inferred funding interval per exchange, log it, and return it.

    A wrong interval silently corrupts net_funding — the biggest correctness
    risk — so we surface what was inferred and flag fallbacks both in the log and
    in the returned structure (consumed by the console report and web dashboard).
    """
    out: dict[str, dict] = {}
    for ex, fundings in funding_by_ex.items():
        if not fundings:
            continue
        intervals: dict[float, int] = {}
        inferred = 0
        for f in fundings.values():
            intervals[f.interval_hours] = intervals.get(f.interval_hours, 0) + 1
            if f.interval_inferred:
                inferred += 1
        by_interval = {f"{h:g}h": n for h, n in sorted(intervals.items())}
        summary = ", ".join(f"{k} x{n}" for k, n in by_interval.items())
        note = f" ({inferred} fell back to default)" if inferred else ""
        log.info("funding interval [%s]: %s%s", ex, summary, note)
        out[ex] = {"summary": summary, "by_interval": by_interval, "inferred": inferred}
    return out
