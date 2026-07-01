# arb_bot — delta-neutral crypto perp arbitrage bot

Cross-exchange spread arbitrage on crypto **perpetual futures**, built strictly
phase by phase: **scanner (read-only) → simulator (paper) → guarded live**.

> **Status: Phase 1 (P0) + Phase 2 (P0).** The repository contains the read-only
> scanner (Phase 1) and the paper simulator (Phase 2). There are still **no API
> keys, no orders, and no real trading** — the simulator trades virtually. Phase 3
> (guarded live execution) is deliberately not built yet.

The bot supports (by design) three pluggable strategies on shared
infrastructure — cross-exchange perp-perp spread (the main one), funding-rate
arbitrage, and spot-perp basis — but **Phase 1 implements only the cross-exchange
perp-perp price-spread scanner**. A strategy is "is it worth entering?" logic; the
data, cost accounting, sizing and (later) execution are shared.

Out of scope for the whole project (mentioned here so it is explicit): triangular,
latency, statistical, and DEX/MEV arbitrage. Those are different problems with
different infrastructure and are not pursued.

---

## What Phase 1 (P0) does

On every scan loop it:

1. **Loads markets** from each configured exchange (`load_markets()` first). Any
   exchange that fails to load (geo-block, downtime, rate-limit) is **logged and
   skipped** — the scan runs on whatever loaded, as long as ≥ 2 venues are up.
2. **Forms the universe automatically** (no hardcoded coin list): the intersection
   of coins listed and live-quoted on ≥ 2 venues, filtered by a 24h quote-volume
   floor, then the **top-N by volume**.
3. For each universe coin and each exchange pair, fetches **best bid/ask** (never
   `last`) and **funding rate**, validates the pair, sizes both legs symmetrically,
   and runs the shared cost engine.
4. Prints a **ranked table** of opportunities (signal or not) plus a yes/no signal
   against the configured net-spread threshold.

It deliberately surfaces the honest result: on liquid coins, clean spreads are
almost always eaten by the cost stack. Seeing "best net −3 bps, break-even 30 bps"
is the point — it tells you the edge is thin, not that the bot is broken.

### Why a scanner first (and REST, not WebSocket, in P0)

This phase is reconnaissance: confirm on real public data whether workable spreads
exist before writing any execution code. P0 uses **synchronous REST** for
simplicity — one batched `fetch_tickers` call per exchange per loop is plenty for a
periodic scan and stays within rate limits. The real-time path
(`watchOrderBook`/`watchTicker` over WebSocket) is **P1**, where latency and book
freshness start to matter.

### What is intentionally NOT in P0 (it is P1+)

WebSocket feeds; L2-depth slippage (P0 uses a flat estimate); the richer universe
filters (order-book depth, max coin spread, blacklist, new-listing age, symmetric
capacity); periodic universe recalculation on its own clock; JSONL/CSV trade
journaling; CLI flags; and unit tests. **Inverse (coin-margined) contracts are
excluded** — linear (USDT-margined) only — because linear and inverse have
mismatched (convex) payoffs and cannot be hedged 1:1.

---

## The cost / profit model (shared `fees/` engine)

`arb_bot/fees/engine.py` is the **single source of truth** for P&L — every later
phase computes profit through it so a paper simulation can never drift from live.

```
income  = gross_spread + net_funding (signed, two-sided)
costs   = 4 leg commissions (open+close, long+short)
        + half-spread crossing on each taker leg
        + slippage beyond top-of-book
        + cost of frozen capital (delta-neutral 1x/1x ties up ~2x notional)

net_spread = gross + net_funding − other_costs
breakeven  = other_costs − net_funding
```

Key correctness points, all handled in code:

- **Commissions are read at runtime** from `market['maker']`/`market['taker']`,
  with per-exchange **overrides in config** for your real VIP tier / native-token
  discount / referral. CCXT does not know your actual tier — never hardcode fees.
- **Net funding is two-sided and normalized.** Funding paid on the long leg vs
  received on the short leg, each divided by its own (per-exchange, possibly 4h /
  1h, **not assumed 8h**) interval before comparison. The inferred interval per
  exchange is logged each scan so it can be eyeball-verified — a wrong interval is
  the single biggest way to corrupt the funding number.
- **`contractSize` is cast to float** (ccxt sometimes returns it as a string,
  issue #11123) and all sizing is done in coin-denominated terms.

### Realistic expectations

On liquid tier-1 coins, full-cycle break-even is ≈ **25–30 bps** (4 taker legs ×
~0.05% ≈ 20 bps, plus a few bps of crossing/slippage). The entry threshold must sit
**well above** that. Fat spreads live on **less liquid** coins — which carry their
own delisting/liquidity/counterparty risk. Funding-arb realistically yields
~8–20% APY over a full cycle, dropping to 0–5% (or negative) in chop/bear markets;
"100%+ annualized" headlines are short spikes, not the norm.

---

## Project layout

```
config.yaml             # all thresholds — nothing is hardcoded
.env.example            # placeholder; P0 needs no keys
requirements.txt        # pinned deps
main.py                 # entry point
arb_bot/
  core/      models.py, config.py, timeutils.py, logging_setup.py
  exchanges/ base.py (ccxt wrapper), factory.py (graceful skip), funding.py (interval normalization)
  fees/      engine.py            # the cost/profit source of truth
  risk/      sizing.py            # symmetric delta-neutral sizing
  pairs/     validate.py          # same-asset, linear-only, sane book
  scanner/   universe.py, scanner.py (collect_market_data/build_opportunities/scan), report.py
  web/       server.py (stdlib dashboard), serialize.py, static/index.html
  simulator/ paper.py (loop), legging.py, pnl.py, journal.py, models.py   # Phase 2
logs/                   # paper_trades.jsonl journal lands here
tests/                  # unit tests land here in P1
```

---

## Configuration (`config.yaml`)

Every threshold is tunable here. Defaults shipped:

| Section | Key | Default | Meaning |
|---|---|---|---|
| `exchanges` | — | binance, bybit, okx, mexc, gate | venues to attempt; failures are skipped |
| `market` | `contract` | `linear` | linear (USDT-margined) only in P0 |
| `universe` | `top_n` | 20 | monitor the N most-liquid eligible coins |
| `universe` | `min_quote_volume_24h` | 1,000,000 | drop coins thinner than this on every venue |
| `thresholds` | `entry_net_spread_bps` | 35 | net spread (after costs) to flag a signal |
| `sizing` | `target_notional_quote` | 100 | USDT notional per leg we size toward |
| `sizing` | `residual_tolerance_frac` | 0.01 | max leg imbalance from rounding before flagging |
| `fees` | `taker_only` | true | cross the book on all legs |
| `fees` | `slippage_bps` | 2 | extra slippage **per crossing leg** (×4 round-trip) |
| `fees` | `count_exit_crossing` | true | model the full round-trip, not just entry |
| `fees` | `capital_cost_annual_bps` | 1000 | opportunity cost of frozen capital (10%/yr) |
| `fees` | `expected_hold_hours` | 8 | assumed hold, used for capital + funding accrual |
| `fees` | `funding_horizon_hours` | 8 | window net funding is accrued over for the estimate |
| `fees` | `overrides` | per-exchange | your real maker/taker fractions (VIP/discount) |
| `runtime` | `loop` / `loop_interval_seconds` | true / 30 | repeat scans every N seconds |

---

## Running it

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py            # console scanner; uses ./config.yaml; Ctrl-C to stop
python main.py web        # read-only web dashboard at http://127.0.0.1:8000
```

You should see, per loop:

- which exchanges loaded and which were **skipped** (with the reason);
- the **inferred funding interval** per exchange (e.g. `4h x6, 8h x14`);
- a **universe summary** (coins seen, on ≥2 venues, passed volume, selected, and
  how many were dropped for being single-venue or low-volume);
- a **ranked table**: achievable size, gross spread, each cost line (commission,
  half-spread, slippage, funding, capital), **net spread**, break-even, return on
  capital, and a `SIG` yes/no against the threshold.

On liquid coins expect **0 signals** and best net spread near/below break-even —
that is the honest, expected outcome. Coins where a symmetric $100 position cannot
fit both venues' lot minimums are skipped (visible at `DEBUG` log level).

### Web dashboard

`python main.py web` starts a **read-only** dashboard (stdlib `http.server`, no
extra dependencies) on `web.host:web.port` (default `127.0.0.1:8000`). A background
thread runs the same `scan()` loop the console uses and stores the latest result;
the page polls `/api/scan` and renders:

- exchange status chips (loaded vs skipped, with the skip reason on hover);
- inferred funding interval per exchange (with a ⚠ count if any fell back);
- the universe summary (seen / on ≥2 venues / passed volume / selected);
- a **sortable, filterable** opportunities table (click a column to sort; "only
  signals" and "min net" filters), color-coded, refreshing on the scan interval.

It shows the exact same numbers as the console — both go through the shared
`fees/` engine. There are **no controls that place orders or change anything**; it
is a viewer. Endpoints: `/` (page), `/api/scan` (JSON), `/health`. Set
`web.host: 0.0.0.0` to reach it from your LAN (still read-only). Note that in an
ephemeral container there is no stable public port — the dashboard is most useful
when you run the bot on your own machine or a VPS.

### Network note (proxied / sandboxed environments)

Some networks sit behind a **TLS-intercepting egress proxy** with a self-signed
CA. ccxt's HTTP session ignores environment trust settings by default, which causes
`certificate verify failed`. The client re-enables `trust_env` and points
verification at the env CA bundle (`REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE`) when
present — verification stays **on**, just against the correct chain. Separately,
**Binance and Bybit block some hosting regions** (HTTP 451 / CloudFront 403); when
unreachable they are skipped and the scan proceeds on the remaining venues.

---

## Phase 2 — paper simulator

`python main.py sim` runs a **paper (virtual) trader** over the same read-only
feed. Each pass it first checks exits for open positions, then opens new ones:

1. **Entry** on a wide gross spread (`simulator.entry_gross_bps`, default 15). This
   is the real dislocation to bet on converging — whether it is *profitable* after
   costs is exactly what the sim measures. On liquid coins at $100 most trades net
   negative (no free edge); raise the threshold to bet only on larger gaps, or add
   a `min_expected_net_bps` gate.
2. **Legging model** on open: with `one_leg_fill_prob` the second leg never fills →
   the entry is aborted and the first leg is unwound at a full one-leg round-trip
   loss (journaled as `one_leg_fail`). Otherwise both fill, but the spread decays
   during `delay_ms` (`adverse_bps_per_100ms`), so the effective entry is worse.
3. **Hold**, then **exit** on the first of: convergence (spread ≤ `convergence_bps`,
   take profit), stop (spread widened ≥ entry + `stop_adverse_bps`), or timeout
   (`max_hold_seconds`). All three are modeled.
4. **P&L** through the shared `fees/` engine: `capture = effective_entry − exit`,
   minus commission / half-spread / slippage / capital (scaled to the *actual*
   hold), plus **event-based net funding** — you only pay/receive at a settlement
   you were actually holding through (two-sided, per each leg's own interval).

Every close is appended to a **JSONL journal** (`simulator.journal_path`,
default `logs/paper_trades.jsonl`) with the full breakdown: entry/exit times and
spreads, size, residual delta, each cost line separately, realized net funding,
net P&L, return on capital, hold duration, and exit reason. The console prints a
running status line (open/closed counts, win %, realized P&L, exit-reason
breakdown, and how much of the gross capture the costs ate).

Runs are reproducible via `simulator.legging.seed`. Because real spreads converge
over minutes–hours, a short run mostly shows opens and timeouts; lower
`max_hold_seconds` / `loop_interval_seconds` to exercise the full cycle quickly.

**Phase 2 scope note:** this is the P0 slice — full virtual cycle + journal +
legging/one-leg/funding-timing risk models, reusing the flat-slippage cost model
from Phase 1. Real L2-depth slippage, the full statistics summary + equity curve,
and unit tests are the Phase 2 P1 follow-ups.

## Limitations & risks (read this)

Arbitrage is not free money — the edge is thin and it is primarily an **execution
and cost-accounting** problem. Delta-neutral removes price direction but **not**:
basis risk, funding flips, single-leg liquidation (possible even at 1× if one
leg's margin is drawn down before the other realizes), counterparty risk (remember
FTX), transfer/settlement risk, and operational risk. Capital is frozen at ~2×.

Phase-1-specific caveats:

- **Funding-interval inference is the biggest correctness risk.** It is read
  per-exchange from non-unified ccxt fields; verify the logged intervals.
- **Slippage is a flat estimate** in P0, not computed from real L2 depth (P1).
  `capital_cost_annual_bps` is a judgment knob. Exit costs are modeled flatly.
- **Cross-exchange 24h volume is reported inconsistently** (base vs quote); the
  universe takes the max across venues as a representative figure.
- **Same-underlying matching is by ccxt `base` symbol.** Venue-specific naming
  (e.g. OKX `1000X` / numbered contracts, MEXC quirks) can mis-match or drop a
  legitimate pair; an alias map is a P1 improvement.
- At **$100 notional**, many high-priced coins won't satisfy symmetric lot
  minimums on both venues and are skipped — expect a modest hit rate.

This scanner tells you whether opportunities *plausibly* exist after costs. It does
**not** account for execution latency between legs, queue position, partial fills,
or withdrawal/transfer constraints — those are modeled in Phase 2 (simulator) and
guarded against in Phase 3 (live).
