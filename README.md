# arb_bot — delta-neutral crypto perp arbitrage bot

Cross-exchange spread arbitrage on crypto **perpetual futures**, built strictly
phase by phase: **scanner (read-only) → simulator (paper) → guarded live**.

> **Status: Phase 1 (P0) only.** This repository currently contains the read-only
> scanner. There are **no API keys, no orders, and no trading**. Later phases are
> deliberately not built yet.

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
  scanner/   universe.py, scanner.py, report.py
logs/                   # JSONL/CSV journal lands here in P1
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
python main.py            # uses ./config.yaml; Ctrl-C to stop
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

### Network note (proxied / sandboxed environments)

Some networks sit behind a **TLS-intercepting egress proxy** with a self-signed
CA. ccxt's HTTP session ignores environment trust settings by default, which causes
`certificate verify failed`. The client re-enables `trust_env` and points
verification at the env CA bundle (`REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE`) when
present — verification stays **on**, just against the correct chain. Separately,
**Binance and Bybit block some hosting regions** (HTTP 451 / CloudFront 403); when
unreachable they are skipped and the scan proceeds on the remaining venues.

---

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
