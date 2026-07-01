"""
Spot grid backtest engine.

This is a faithful Python port of the calibrated grid backtester whose reference
implementation lives in ``grid_bot_calculator.html`` (the ``backtest`` and
``buildLevels`` functions in its inline ``<script>``). That HTML file was
validated to within <0.3% of a real closed Binance SOL/USDT bot, so the math
here is *ported, not reinvented*. ``tests/test_engine_parity.py`` runs both this
module and the original JS (via Node) over identical candle series and asserts
the numbers agree to a tiny tolerance.

The engine is pure and deterministic: given the same candles and parameters it
always returns the same result. It performs no I/O and knows nothing about
exchanges — it is the shared strategy core used by the calculator, the live
metrics, the walk-forward optimizer, and the Monte Carlo simulator.

Candles are dicts: ``{"t": int_seconds, "o": float, "h": float, "l": float, "c": float}``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def clamp(v: float, a: float, b: float) -> float:
    return max(a, min(b, v))


def build_levels(lower: float, upper: float, n: int, mode: str) -> list[float]:
    """Grid price ladder of ``n + 1`` levels.

    Geometric: constant ratio between adjacent lines (equal % spacing).
    Arithmetic: constant absolute spacing. Mirrors ``buildLevels`` in the HTML.
    """
    levels: list[float] = []
    if mode == "geometric":
        r = (upper / lower) ** (1.0 / n)
        for i in range(n + 1):
            levels.append(lower * (r ** i))
    else:
        s = (upper - lower) / n
        for i in range(n + 1):
            levels.append(lower + s * i)
    return levels


@dataclass
class BacktestResult:
    """Full output of :func:`backtest`. Field names match the HTML's ``out`` object."""

    levels: list[float] = field(default_factory=list)
    grid_profit: float = 0.0          # realised matched-pair profit (Binance "Grid Profit")
    floating: float = 0.0             # Total - Grid Profit (Binance "Floating")
    total: float = 0.0                # cash + inventory value - investment
    total_fees: float = 0.0
    buy_trades: int = 0
    sell_trades: int = 0
    matched: int = 0
    qty_per_order: float = 0.0
    initial_buy_qty: float = 0.0
    start_price: float = 0.0
    entry_price: float = 0.0
    days: float = 0.0
    apr: float = 0.0
    profit_per_grid_pct: float = 0.0
    in_range: float = 0.0             # % of time price spent inside the grid
    out_range: float = 0.0
    atr_pct: float = 0.0              # average true range as % of final price
    range_cov: float = 0.0
    fee_impact: float = 0.0
    max_dd: float = 0.0               # max drawdown (absolute, in quote currency)
    final_price: float = 0.0
    grid_eff: float = 0.0
    risk_ratio: float = 0.0
    buy_time_sec: float = 0.0
    sell_time_sec: float = 0.0
    oor_time_sec: float = 0.0
    period_sec: float = 0.0
    stop_price: float = 0.0
    sell_qty_stop: float = 0.0
    avg_sell_stop: float = 0.0
    cash_end: float = 0.0
    inv_qty_end: float = 0.0
    inv_value_end: float = 0.0
    balance_stop_usdt: float = 0.0
    balance_stop_base: float = 0.0
    sell_all: bool = True
    equity: list[float] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        # equity/trades are large; callers that want them ask explicitly
        return d


def backtest(
    candles: list[dict[str, Any]],
    s_idx: int,
    e_idx: int,
    p: dict[str, Any],
) -> BacktestResult:
    """Run the grid strategy over ``candles[s_idx .. e_idx]``.

    ``p`` keys (matching the HTML's params):
      lower, upper: grid bounds (quote price)
      grids: number of grids (>= 2)
      mode: "geometric" | "arithmetic"
      invest: total quote investment
      fee: per-fill fee in percent (e.g. 0.1 == 0.1%)
      entry: optional manual entry price (0/None = use first candle close)
      slip_bps: per-fill slippage/spread in basis points (buys fill higher, sells lower)
      sell_all_on_stop: if True, market-liquidate inventory at stop (default True)
      stop_price: optional tick-accurate price to revalue at on stop
      record_trades: if True, record the (capped) trade list
      base: base asset symbol for trade records (display only)

    Returns a :class:`BacktestResult`. This is a line-for-line port of the
    calibrated ``backtest`` function; see the module docstring.
    """
    lower = float(p["lower"])
    upper = float(p["upper"])
    grids = int(p["grids"])
    mode = p["mode"]
    invest = float(p["invest"])
    fee = float(p["fee"])
    fee_r = fee / 100.0
    slip = max(0.0, float(p.get("slip_bps", 0) or 0)) / 1e4
    sell_all = p.get("sell_all_on_stop", True) is not False
    entry = float(p.get("entry", 0) or 0)
    stop_price = float(p.get("stop_price", 0) or 0)
    record_trades = p.get("record_trades", False) is True
    base = p.get("base", "BASE")

    out = BacktestResult()
    out.sell_all = sell_all

    n = len(candles)
    # Guard degenerate inputs up front: a zero/negative lower bound would divide by
    # zero in build_levels (geometric) and profit_per_grid_pct; invest<=0 would
    # divide by zero in apr. All produce an empty (zeroed) result rather than crash.
    if e_idx <= s_idx or n == 0 or upper <= lower or grids < 2 or lower <= 0 or invest <= 0:
        return out
    s_idx = int(clamp(s_idx, 0, n - 1))
    e_idx = int(clamp(e_idx, 0, n - 1))
    seg = candles[s_idx : e_idx + 1]
    if len(seg) < 2:
        return out

    levels = build_levels(lower, upper, grids, mode)
    out.levels = levels
    start_price = entry if entry > 0 else seg[0]["c"]
    out.start_price = start_price
    mid = (lower + upper) / 2.0
    cells = grids

    # Binance uses an EQUAL BASE quantity per grid (Order History shows a constant
    # Executed qty). Calibrated against a real closed bot: q = investment / sum of
    # the buy lines of all cells except the topmost. Reproduces Binance's per-order
    # quantity to <0.3%.
    sum_buy_lines = 0.0
    for i in range(cells - 1):
        sum_buy_lines += levels[i]
    q_base = invest / sum_buy_lines if sum_buy_lines > 0 else 0.0
    out.qty_per_order = q_base

    cash = invest
    holding = [False] * cells
    buy_t = [0] * cells
    buy_p = [0.0] * cells

    # Seed inventory only for cells fully ABOVE the start price (buy line >= start).
    # The straddle cell (start between its buy & sell line) stays a pending BUY.
    init_qty = 0.0
    init_cost = 0.0
    seed_px = start_price * (1.0 + slip)
    for i in range(cells):
        if levels[i] >= start_price:
            holding[i] = True
            init_qty += q_base
            init_cost += q_base * seed_px
            buy_t[i] = seg[0]["t"]
            buy_p[i] = levels[i]
            f = q_base * seed_px * fee_r
            cash -= q_base * seed_px + f
            out.total_fees += f
    out.initial_buy_qty = init_qty
    out.entry_price = (init_cost / init_qty) if init_qty > 0 else start_price

    TCAP = 4000
    trades: list[dict[str, Any]] = []

    def hold_value(c: float) -> float:
        v = 0.0
        for i in range(cells):
            if holding[i]:
                v += q_base * c
        return v

    prev = start_price
    equity: list[float] = []
    peak = -1e9
    dd = 0.0

    def do_leg(a: float, b: float, t_a: float, t_span: float) -> None:
        """Process one MONOTONIC price move a->b, filling every grid line crossed."""
        nonlocal cash
        if b > a:  # rising -> sells
            d = (b - a) or 1e-9
            for i in range(cells):
                if holding[i] and levels[i + 1] > a and levels[i + 1] <= b:
                    ex_sell = levels[i + 1] * (1.0 - slip)
                    ex_buy = levels[i] * (1.0 + slip)
                    sell_fee = q_base * ex_sell * fee_r
                    buy_fee = q_base * ex_buy * fee_r
                    net = q_base * (ex_sell - ex_buy) - sell_fee - buy_fee
                    cash += q_base * ex_sell - sell_fee
                    out.total_fees += sell_fee
                    out.grid_profit += net
                    holding[i] = False
                    out.sell_trades += 1
                    out.matched += 1
                    if record_trades and len(trades) < TCAP:
                        st = round(t_a + ((levels[i + 1] - a) / d) * t_span)
                        trades.append({
                            "t": st, "side": "Sell", "price": ex_sell,
                            "qty": q_base, "fee": sell_fee, "feeAsset": "USDT",
                            "profit": net,
                        })
        elif b < a:  # falling -> buys
            d = (a - b) or 1e-9
            for i in range(cells - 1, -1, -1):
                if (not holding[i]) and levels[i] < a and levels[i] >= b:
                    ex_buy = levels[i] * (1.0 + slip)
                    buy_fee = q_base * ex_buy * fee_r
                    cash -= q_base * ex_buy + buy_fee
                    out.total_fees += buy_fee
                    holding[i] = True
                    out.buy_trades += 1
                    buy_t[i] = round(t_a + ((a - levels[i]) / d) * t_span)
                    buy_p[i] = levels[i]
                    if record_trades and len(trades) < TCAP:
                        trades.append({
                            "t": buy_t[i], "side": "Buy", "price": ex_buy,
                            "qty": q_base, "fee": q_base * fee_r, "feeAsset": base,
                            "profit": 0.0,
                        })

    for k in range(1, len(seg)):
        cd = seg[k]
        t0 = seg[k - 1]["t"]
        t1 = seg[k]["t"]
        dt = max(1, t1 - t0)
        c = cd["c"]
        hi = max(cd["h"] if cd.get("h") is not None else c, prev, c)
        lo = min(cd["l"] if cd.get("l") is not None else c, prev, c)
        # time-in-range: count by where the candle traded relative to mid
        if lower <= c <= upper:
            if c < mid:
                out.buy_time_sec += dt
            else:
                out.sell_time_sec += dt
        else:
            out.oor_time_sec += dt
        # Walk the candle's intra-bar path so we capture round-trips a close-to-close
        # walk would miss. Heuristic: a bullish candle dips to low first then rallies
        # to high; a bearish candle does the reverse.
        low_first = c >= prev
        wps = [prev, lo, hi, c] if low_first else [prev, hi, lo, c]
        big_d = 0.0
        for j in range(len(wps) - 1):
            big_d += abs(wps[j + 1] - wps[j])
        if big_d <= 0:
            big_d = 1e-9
        cum = 0.0
        for j in range(len(wps) - 1):
            a = wps[j]
            b = wps[j + 1]
            leg_d = abs(b - a)
            if leg_d > 0:
                do_leg(a, b, t0 + (cum / big_d) * (t1 - t0), (leg_d / big_d) * (t1 - t0))
            cum += leg_d
        prev = c
        eq = cash + hold_value(c) - invest
        equity.append(eq)
        if eq > peak:
            peak = eq
        if peak - eq > dd:
            dd = peak - eq

    # final price = tick-accurate stop price when pinned (else last candle close).
    end_p = stop_price if stop_price > 0 else seg[-1]["c"]
    out.final_price = end_p
    inv_qty = 0.0
    for i in range(cells):
        if holding[i]:
            inv_qty += q_base
    inv_value = inv_qty * end_p
    out.cash_end = cash
    out.inv_qty_end = inv_qty
    out.inv_value_end = inv_value
    out.total = cash + inv_value - invest               # Total = Current Value - Investment
    out.floating = out.total - out.grid_profit          # Floating = Total - Grid Profit

    out.stop_price = end_p
    out.sell_qty_stop = inv_qty
    out.avg_sell_stop = end_p
    if sell_all:
        out.balance_stop_usdt = cash + inv_qty * end_p * (1.0 - slip) * (1.0 - fee_r)
        out.balance_stop_base = 0.0
    else:
        out.balance_stop_usdt = cash
        out.balance_stop_base = inv_qty

    out.period_sec = seg[-1]["t"] - seg[0]["t"]
    in_sec = out.buy_time_sec + out.sell_time_sec
    out.in_range = (in_sec / out.period_sec * 100.0) if out.period_sec > 0 else 0.0
    out.out_range = 100.0 - out.in_range
    out.equity = equity
    out.max_dd = dd
    if record_trades:
        out.trades = list(reversed(trades))
    out.days = out.period_sec / 86400.0
    out.apr = ((out.total / invest) / out.days * 365.0 * 100.0) if out.days > 0 else 0.0

    avg_space_pct = 0.0
    for i in range(cells):
        avg_space_pct += (levels[i + 1] - levels[i]) / levels[i]
    avg_space_pct = avg_space_pct / cells * 100.0
    out.profit_per_grid_pct = avg_space_pct - 2 * fee - 2 * (float(p.get("slip_bps", 0) or 0)) / 100.0

    tr = 0.0
    for k in range(1, len(seg)):
        h = seg[k]["h"]
        low = seg[k]["l"]
        pc = seg[k - 1]["c"]
        tr += max(h - low, abs(h - pc), abs(low - pc))
    out.atr_pct = (tr / (len(seg) - 1)) / end_p * 100.0

    mn = float("inf")
    mx = float("-inf")
    for cd in seg:
        if cd["l"] < mn:
            mn = cd["l"]
        if cd["h"] > mx:
            mx = cd["h"]
    span = upper - lower
    out.range_cov = clamp((min(mx, upper) - max(mn, lower)) / span * 100.0, 0.0, 100.0)
    if out.grid_profit > 0:
        out.fee_impact = clamp(out.total_fees / (out.grid_profit + out.total_fees) * 100.0, 0.0, 100.0)
    else:
        out.fee_impact = 100.0 if out.total_fees > 0 else 0.0
    out.grid_eff = out.matched / max(1, len(seg)) * 100.0
    out.risk_ratio = (out.total / out.max_dd) if out.max_dd > 0.01 else (out.total if out.total > 0 else 0.0)
    return out
