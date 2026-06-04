"""Plain-text console report for a scan.

Shows the ranked opportunities (signal or not) so the spread distribution and how
far it sits from break-even are always visible — the honest, expected result on
liquid coins is "nothing clears threshold after costs", and that should be plain
to see. P2 will add a colorized live table.
"""

from __future__ import annotations

from .scanner import ScanResult

_COLS = (
    f"{'#':>2}  {'COIN':<10} {'BUY→SELL':<16} {'SIZE(coin)':>11} {'$/leg':>8} "
    f"{'gross':>7} {'comm':>6} {'half':>6} {'slip':>6} {'fund':>7} {'cap':>5} "
    f"{'NET':>7} {'brkeven':>7} {'ROC%':>7}  SIG"
)


def format_scan(result: ScanResult, threshold_bps: float, top: int = 30) -> str:
    lines: list[str] = []
    lines.append("=" * len(_COLS))
    lines.append(
        f"SCAN  threshold={threshold_bps:g}bps  "
        f"universe={result.stats.selected}  "
        f"pairs_evaluated={len(result.opportunities)}  "
        f"pairs_skipped={result.skipped_pairs}"
    )
    if result.universe:
        coins = ", ".join(e.coin for e in result.universe[:15])
        more = "" if len(result.universe) <= 15 else f" (+{len(result.universe) - 15} more)"
        lines.append(f"universe: {coins}{more}")
    lines.append("-" * len(_COLS))

    if not result.opportunities:
        lines.append("no evaluable exchange pairs this scan (see logs for skip reasons)")
        lines.append("=" * len(_COLS))
        return "\n".join(lines)

    lines.append(_COLS)
    lines.append("-" * len(_COLS))

    signals = 0
    for i, opp in enumerate(result.opportunities[:top], start=1):
        c = opp.cost
        if opp.signal:
            signals += 1
        lines.append(
            f"{i:>2}  {opp.coin:<10} "
            f"{opp.long_exchange + '→' + opp.short_exchange:<16} "
            f"{opp.sizing.coin_qty:>11.6g} {c.notional_per_leg_quote:>8.2f} "
            f"{c.gross_spread_bps:>7.1f} {c.commission_bps:>6.1f} "
            f"{c.half_spread_cost_bps:>6.1f} {c.slippage_bps:>6.1f} "
            f"{c.net_funding_bps:>+7.2f} {c.capital_cost_bps:>5.2f} "
            f"{c.net_spread_bps:>+7.1f} {c.breakeven_spread_bps:>7.1f} "
            f"{c.return_on_capital * 100:>+7.3f}  {'YES' if opp.signal else '-'}"
        )

    lines.append("-" * len(_COLS))
    total_signals = sum(1 for o in result.opportunities if o.signal)
    lines.append(
        f"signals (net_spread >= {threshold_bps:g}bps): {total_signals} "
        f"of {len(result.opportunities)} pairs"
    )
    if result.opportunities:
        best = result.opportunities[0]
        lines.append(
            f"best net_spread: {best.cost.net_spread_bps:+.1f}bps on {best.coin} "
            f"{best.long_exchange}→{best.short_exchange} "
            f"(gross {best.cost.gross_spread_bps:.1f}bps, breakeven {best.cost.breakeven_spread_bps:.1f}bps)"
        )
    lines.append("all values in bps of one leg's notional unless noted. fund/cap signed.")
    lines.append("=" * len(_COLS))
    return "\n".join(lines)
