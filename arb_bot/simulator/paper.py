"""Paper trader: open on wide spreads, hold, close on convergence/stop/timeout.

Drives the same read-only market feed the scanner uses. On each pass it first
checks exits for open virtual positions, then opens new ones on qualifying
opportunities (with the legging model applied). Every close is accounted through
the shared pnl/ + fees/ code and written to the JSONL journal. No real orders.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from random import Random

from ..core.config import Config
from ..core.logging_setup import get_logger
from ..core.models import Opportunity
from ..core.timeutils import utcnow
from ..exchanges.base import ExchangeClient
from ..exchanges.factory import build_exchanges
from ..scanner.scanner import MarketData, build_opportunities, collect_market_data
from .journal import TradeJournal
from .legging import apply_legging
from .models import (
    CONVERGENCE,
    ONE_LEG_FAIL,
    STOP,
    TIMEOUT,
    ClosedTrade,
    OpenPosition,
)
from .pnl import aborted_pnl, compute_trade_pnl

log = get_logger(__name__)

_BPS = 10_000.0


@dataclass
class Stats:
    opened: int = 0
    closed: int = 0
    wins: int = 0
    one_leg_fails: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)
    realized_pnl_quote: float = 0.0
    gross_capture_quote: float = 0.0   # capture before costs, for "how much costs ate"
    costs_quote: float = 0.0

    def record(self, trade: ClosedTrade) -> None:
        self.closed += 1
        self.by_reason[trade.exit_reason] = self.by_reason.get(trade.exit_reason, 0) + 1
        self.realized_pnl_quote += trade.pnl.net_pnl_quote
        if trade.pnl.net_pnl_quote > 0:
            self.wins += 1
        if trade.exit_reason == ONE_LEG_FAIL:
            self.one_leg_fails += 1
        n = trade.notional_quote
        self.gross_capture_quote += trade.pnl.capture_bps / _BPS * n
        self.costs_quote += (
            trade.pnl.commission_bps + trade.pnl.half_spread_bps
            + trade.pnl.slippage_bps + trade.pnl.capital_bps
        ) / _BPS * n


class PaperTrader:
    def __init__(self, clients: dict[str, ExchangeClient], cfg: Config) -> None:
        self.clients = clients
        self.cfg = cfg
        self.rng = Random(cfg.simulator.legging.seed)
        self.journal = TradeJournal(cfg.simulator.journal_path)
        self.open: dict[tuple[str, str, str], OpenPosition] = {}
        self.stats = Stats()
        self._next_id = 1

    # ---- one pass --------------------------------------------------------

    def step(self, md: MarketData, opportunities: list[Opportunity]) -> None:
        self._process_exits(md)
        self._process_entries(md, opportunities)

    def _process_exits(self, md: MarketData) -> None:
        now = utcnow()
        ex_cfg = self.cfg.simulator.exit
        for key, pos in list(self.open.items()):
            lq = md.quotes_by_ex.get(pos.long_exchange, {}).get(pos.coin)
            sq = md.quotes_by_ex.get(pos.short_exchange, {}).get(pos.coin)
            if lq is None or sq is None:
                continue  # cannot price this round; re-check next pass
            current_gross = (sq.mid - lq.mid) / lq.mid * _BPS
            hold_s = (now - pos.entry_ts).total_seconds()

            reason: str | None = None
            if current_gross <= ex_cfg.convergence_bps:
                reason = CONVERGENCE
            elif current_gross >= pos.entry_gross_bps + ex_cfg.stop_adverse_bps:
                reason = STOP
            elif hold_s >= ex_cfg.max_hold_seconds:
                reason = TIMEOUT
            if reason is None:
                continue

            pnl = compute_trade_pnl(pos, current_gross, now, self.cfg.fees)
            trade = ClosedTrade(
                id=pos.id, coin=pos.coin,
                long_exchange=pos.long_exchange, short_exchange=pos.short_exchange,
                filled=True, exit_reason=reason,
                entry_ts=pos.entry_ts, exit_ts=now, hold_seconds=hold_s,
                size_coin=pos.size_coin, notional_quote=pos.notional_quote,
                residual_delta_coin=pos.residual_delta_coin,
                entry_gross_bps=pos.entry_gross_bps,
                effective_entry_gross_bps=pos.effective_entry_gross_bps,
                exit_gross_bps=current_gross,
                legging_penalty_bps=pos.legging_penalty_bps,
                pnl=pnl,
            )
            self.journal.write(trade)
            self.stats.record(trade)
            del self.open[key]
            log.info(
                "CLOSE #%d %s %s->%s %s: entry %.1f -> exit %.1f bps, net %+.2f USDT (%.1fs)",
                pos.id, pos.coin, pos.long_exchange, pos.short_exchange, reason,
                pos.entry_gross_bps, current_gross, pnl.net_pnl_quote, hold_s,
            )

    def _process_entries(self, md: MarketData, opportunities: list[Opportunity]) -> None:
        sim = self.cfg.simulator
        # Widest gross first — those are the real dislocations to bet on.
        for opp in sorted(opportunities, key=lambda o: o.cost.gross_spread_bps, reverse=True):
            if opp.cost.gross_spread_bps < sim.entry_gross_bps:
                break  # sorted desc; nothing wider remains
            if len(self.open) >= sim.max_open_positions:
                break
            key = (opp.coin, opp.long_exchange, opp.short_exchange)
            if key in self.open:
                continue
            # Optional gate: expected net assuming we exit at the convergence target.
            expected_net = opp.cost.net_spread_bps - sim.exit.convergence_bps
            if expected_net < sim.min_expected_net_bps:
                continue
            self._open_position(md, opp)

    def _open_position(self, md: MarketData, opp: Opportunity) -> None:
        long_market = self.clients[opp.long_exchange].markets[opp.coin]
        outcome = apply_legging(
            self.rng, self.cfg.simulator.legging, self.cfg.fees,
            opp.cost.gross_spread_bps, long_market, opp.long_quote,
        )
        now = utcnow()
        notional = opp.cost.notional_per_leg_quote

        if not outcome.filled:
            # Leg-2 never filled -> abort the entry, unwind leg-1 at a loss.
            pnl = aborted_pnl(outcome.emergency_cost_bps, notional)
            trade = ClosedTrade(
                id=self._next_id, coin=opp.coin,
                long_exchange=opp.long_exchange, short_exchange=opp.short_exchange,
                filled=False, exit_reason=ONE_LEG_FAIL,
                entry_ts=now, exit_ts=now, hold_seconds=0.0,
                size_coin=opp.sizing.coin_qty, notional_quote=notional,
                residual_delta_coin=opp.sizing.residual_delta_coin,
                entry_gross_bps=opp.cost.gross_spread_bps,
                effective_entry_gross_bps=opp.cost.gross_spread_bps,
                exit_gross_bps=opp.cost.gross_spread_bps,
                legging_penalty_bps=0.0, pnl=pnl,
            )
            self.journal.write(trade)
            self.stats.record(trade)
            self._next_id += 1
            log.warning(
                "ONE-LEG-FAIL #%d %s %s->%s: unwind cost %+.2f USDT",
                trade.id, opp.coin, opp.long_exchange, opp.short_exchange, pnl.net_pnl_quote,
            )
            return

        effective_entry = opp.cost.gross_spread_bps - outcome.entry_penalty_bps
        pos = OpenPosition(
            id=self._next_id, coin=opp.coin,
            long_exchange=opp.long_exchange, short_exchange=opp.short_exchange,
            size_coin=opp.sizing.coin_qty, notional_quote=notional,
            entry_ts=now,
            entry_gross_bps=opp.cost.gross_spread_bps,
            effective_entry_gross_bps=effective_entry,
            legging_penalty_bps=outcome.entry_penalty_bps,
            entry_long_ask=opp.long_quote.ask, entry_short_bid=opp.short_quote.bid,
            cost=opp.cost,
            long_funding=md.funding_by_ex[opp.long_exchange][opp.coin],
            short_funding=md.funding_by_ex[opp.short_exchange][opp.coin],
            residual_delta_coin=opp.sizing.residual_delta_coin,
            within_tolerance=opp.sizing.within_tolerance,
        )
        self.open[(opp.coin, opp.long_exchange, opp.short_exchange)] = pos
        self.stats.opened += 1
        self._next_id += 1
        log.info(
            "OPEN  #%d %s %s->%s: gross %.1f bps (eff %.1f after %.1f legging), size %.6g ($%.0f)",
            pos.id, pos.coin, pos.long_exchange, pos.short_exchange,
            pos.entry_gross_bps, effective_entry, outcome.entry_penalty_bps,
            pos.size_coin, notional,
        )

    # ---- reporting -------------------------------------------------------

    def status_line(self) -> str:
        s = self.stats
        wr = (s.wins / s.closed * 100.0) if s.closed else 0.0
        reasons = ", ".join(f"{k}={v}" for k, v in sorted(s.by_reason.items())) or "-"
        eaten = ""
        if s.gross_capture_quote > 0:
            eaten = f" | costs ate {s.costs_quote / s.gross_capture_quote * 100:.0f}% of gross capture"
        return (
            f"PAPER open={len(self.open)} opened={s.opened} closed={s.closed} "
            f"win%={wr:.0f} realized={s.realized_pnl_quote:+.2f} USDT "
            f"[{reasons}]{eaten}"
        )

    def close(self) -> None:
        self.journal.close()


def run_paper(cfg: Config) -> int:
    """Build exchanges and run the paper-trading loop until interrupted."""
    log.info("Phase 2 paper simulator — virtual trades only, no keys/orders.")
    clients = build_exchanges(cfg)
    if len(clients) < 2:
        log.error("need at least 2 loaded exchanges to simulate; exiting")
        return 1

    trader = PaperTrader(clients, cfg)
    log.info("journal: %s", cfg.simulator.journal_path)
    try:
        while True:
            try:
                md = collect_market_data(clients, cfg)
                opportunities, _ = build_opportunities(clients, cfg, md)
                trader.step(md, opportunities)
                print(trader.status_line())
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                log.exception("paper step failed: %s", exc)
            if not cfg.runtime.loop:
                break
            time.sleep(cfg.runtime.loop_interval_seconds)
    except KeyboardInterrupt:
        log.info("interrupted; %s", trader.status_line())
    finally:
        trader.close()
    return 0
