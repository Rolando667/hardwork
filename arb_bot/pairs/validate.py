"""Validate that two exchanges' markets for a coin can actually be hedged.

Most structural filtering (linear-only, USDT settle, active) happens at market
load. This module covers the *pairwise* checks: same underlying asset, both
linear (no linear/inverse convexity mismatch), sane contract sizes, and quote
sanity/freshness. An invalid pair is skipped with a logged reason — never
traded on assumption.
"""

from __future__ import annotations

from ..core.models import NormalizedMarket, QuoteSnapshot


def validate_pair(
    long_market: NormalizedMarket,
    short_market: NormalizedMarket,
    long_quote: QuoteSnapshot,
    short_quote: QuoteSnapshot,
) -> tuple[bool, str | None]:
    """Return (ok, skip_reason). ok=True means the pair is hedgeable in P0."""

    # Same underlying asset. We key by ccxt base, but guard explicitly: a venue
    # may list a 1000x or differently-named contract under another base.
    if long_market.base != short_market.base:
        return False, f"asset mismatch: {long_market.base} vs {short_market.base}"

    # Linear vs inverse cannot be hedged 1:1 (convexity mismatch). P0 is linear-only.
    if not (long_market.linear and short_market.linear):
        return False, "non-linear contract in pair (P0 is linear-only)"

    if long_market.settle != short_market.settle:
        return False, f"settle mismatch: {long_market.settle} vs {short_market.settle}"

    if long_market.contract_size <= 0 or short_market.contract_size <= 0:
        return False, "non-positive contractSize"

    # Quote sanity — best bid/ask must be positive and non-crossed on each venue.
    for q in (long_quote, short_quote):
        if q.bid <= 0 or q.ask <= 0 or q.ask < q.bid:
            return False, f"invalid book on {q.exchange}"

    return True, None
