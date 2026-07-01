# Self-Regulating Spot Grid Bot

A self-hosted spot **grid trading bot that regulates itself**. It places a grid
and, on a schedule, re-evaluates the market and **either repositions the grid or
leaves it untouched** — driven by the same metrics as the calibrated backtester
in [`grid_bot_calculator.html`](grid_bot_calculator.html). A rule-driven
deterministic core makes every decision; an **optional** AI advisor can explain
and sanity-check, but never trades.

> **Educational tool. Real funds can be lost. Not financial advice.** Outcomes
> are a *distribution* (see the Monte Carlo P5 / median / P95 on the dashboard),
> not a promise. Start in `dry_run`, graduate to `testnet`, and only go `live`
> deliberately with a small capital cap.

---

## How it works

The strategy math is **ported, not reinvented**, from `grid_bot_calculator.html`
— a single-file backtester validated to within **<0.3%** of a real closed
Binance SOL/USDT bot. The port lives in [`backend/strategy/`](backend/strategy)
and is checked against the original JavaScript, bit-for-bit, by
[`tests/test_engine_parity.py`](tests/test_engine_parity.py):

- the grid backtest engine (equal-base-qty seeding, intra-bar fill walk,
  `Floating = Total − Grid Profit`),
- ATR% / realized-volatility / fill-rate / time-in-range metrics,
- the **walk-forward** optimizer (in-sample 70% / out-of-sample 30%),
- the **Monte Carlo** outcome distribution (P5 / median / P95),
- the per-fill **slippage** model (bps).

### Architecture (two tiers, non-negotiable)

```
 Browser (UI only)            Python backend (holds ALL secrets, does ALL trading)
 ┌──────────────┐   REST/WS   ┌───────────────────────────────────────────────┐
 │  dashboard   │ ──────────▶ │ FastAPI ─ runner ─ decision engine ─ strategy  │
 │  setup form  │ ◀────────── │           │         (ported calibrated math)   │
 └──────────────┘  snapshots  │           ├─ safety (kill-switch, loss limit)  │
   never sees keys            │           ├─ ccxt adapter (Binance/Bybit/OKX)  │
                              │           └─ SQLite action log + state         │
                              └───────────────────────────────────────────────┘
```

The browser **never** receives or stores API keys. Keys are POSTed once to the
backend and written to a server-side `.env` (chmod 600); CORS blocks any
browser→exchange trading anyway.

### Each decision cycle

1. **Reconcile first** — the exchange is the source of truth. Pull price,
   balances, open orders, and (live/testnet) new fills.
2. **Recompute live metrics** on fresh klines.
3. **Decide reposition vs hold** with a **no-trade band / hysteresis**. A
   reposition is proposed only if at least one trigger fires:
   - price left the active range by `> band_pct` of a grid step, **or**
   - ATR% shifted by `> vol_pct` versus when the grid was set, **or**
   - the fill-rate collapsed (grid idle too long).
   Otherwise it **holds** — this is the "sometimes it repositions, sometimes it
   leaves it" behaviour.
4. **Validate before deploying** — the candidate grid is **walk-forward tested**
   on a held-out window and **rejected if it only looks good in-sample**.
5. **Throttle** — a cooldown between repositions and a per-day reposition cap.
6. **Reposition** = cancel stale orders → recompute range around price → place
   new limit orders idempotently (client order IDs, retry with backoff).

---

## Operating modes

| Mode      | What it does                                              | Gating |
|-----------|----------------------------------------------------------|--------|
| `dry_run` | Computes every decision and **logs what it *would* do**; places nothing. Uses real public market data + a paper account. | default |
| `testnet` | Trades on the exchange **sandbox** with fake funds.      | needs API keys |
| `live`    | **Real funds.** | requires `ALLOW_LIVE=true` **and** a positive `MAX_CAPITAL` |

**Get `dry_run` working end-to-end before anything touches real money.**

---

## Quick start (testnet-first)

Requirements: Python 3.11+. (Node is only needed to run the engine parity test.)

```bash
# 1. install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. configure (starts in dry_run; no keys needed)
cp .env.example .env

# 3. run
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000
```

On the dashboard: review the metrics and the "last decision + why", then press
**Start**. In `dry_run` nothing is placed — the action log shows exactly what it
*would* do.

### Going to testnet

1. Create **testnet** API keys on your exchange (e.g. Binance Spot Testnet).
   Grant **trade permission only — no withdrawals** — and set an **IP
   allow-list**.
2. In the dashboard **Setup** panel (or your `.env`): set `MODE=testnet`, paste
   the keys, set the pair and investment. Keys are stored server-side only.
3. Press **Start**. Orders now go to the sandbox. Watch the grid ladder, open
   orders, PnL, and the action log.

The backend **refuses to start** if the API key reports withdrawal scope (where
the exchange exposes it, e.g. Binance), and refuses `live` without `ALLOW_LIVE`
and a capital cap.

---

## Optional AI advisor

Off by default. Set `USE_AI=true` and `ANTHROPIC_API_KEY=...` (and optionally
`AI_MODEL`). On a slow cadence the advisor receives a compact metrics snapshot
plus the engine's proposed action and returns a plain-language explanation, a
sanity flag, and *optionally* a small parameter tweak. That tweak is **clamped to
a narrow range and re-validated** before anything is applied, is **not**
auto-applied in `live` mode, and any timeout/error/malformed output is treated as
**no action**. The AI can never place, move, or cancel orders, and never touches
withdrawals.

---

## Safety & reliability

- **Kill-switch / panic** — one dashboard button and `POST /api/panic` cancel all
  open orders and halt. The halt is sticky until you clear it.
- **Daily loss limit** — if intraday realized+floating PnL breaches
  `-MAX_DAILY_LOSS`, the bot panics and halts.
- **Startup reconcile** — state is synced to the exchange before acting.
- **Structured action log** (SQLite) — every decision with its trigger reason.
- **Throttle + rate-limit aware** — cooldown, daily cap, exponential backoff.

---

## API

| Method | Path                 | Purpose                                  |
|--------|----------------------|------------------------------------------|
| GET    | `/api/status`        | current snapshot (price, grid, PnL, decision, MC) |
| GET    | `/api/config`        | public config (no secrets)               |
| GET    | `/api/log?limit=N`   | recent action log                        |
| POST   | `/api/start`         | start the cycle scheduler                |
| POST   | `/api/stop`          | stop (grid left in place)                |
| POST   | `/api/panic`         | cancel all + halt (kill-switch)          |
| POST   | `/api/resume`        | clear the kill-switch                    |
| POST   | `/api/config/keys`   | persist config/keys to server-side `.env`|
| WS     | `/ws`                | live snapshot push                       |

---

## Tests

```bash
# engine parity vs the reference JS (requires Node)
python tests/test_engine_parity.py
# decision loop end-to-end, offline (deploy -> hold -> reposition -> panic)
python tests/test_decision_runner.py
```

---

## Docker

```bash
cp .env.example .env          # edit as needed
docker compose up --build     # serves on 127.0.0.1:8000, state on a volume
```

---

## Going live (only after dry_run + testnet)

1. Create a **live** key with **trade-only** scope (no withdrawals) and an IP
   allow-list.
2. Start with a **small** `MAX_CAPITAL` and `INVEST`.
3. Set `MODE=live`, `ALLOW_LIVE=true`, `MAX_CAPITAL=<small>`. The backend refuses
   to start otherwise.
4. Keep `MAX_DAILY_LOSS` conservative. Know where the **Panic** button is.

Real funds can be lost. This software is provided for educational purposes with
no warranty.

---

## Do NOT

- hardcode, log, or commit API keys; request withdrawal scope.
- let the AI move funds or trade on raw, unvalidated output.
- promise profit or hide risk.
- store keys in the browser / localStorage / git.
- skip `dry_run` / `testnet` — `live` is opt-in with a capital cap.
