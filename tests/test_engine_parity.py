"""
Parity test: the Python strategy port vs the reference JS in grid_bot_calculator.html.

The HTML is the calibrated source of truth (validated <0.3% against a real closed
bot). This test feeds *identical* synthetic candle series to both the Python
``backtest`` and the original JS ``backtest`` (run via Node through
``tools/reference_engine.mjs``) and asserts every numeric output agrees to a tiny
tolerance. It also checks the RNG and the Monte Carlo path generator match
bit-for-bit-equivalently. Requires Node (``node``) on PATH.

Run directly:  python tests/test_engine_parity.py
Or via pytest:  pytest tests/test_engine_parity.py
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.strategy.engine import backtest  # noqa: E402
from backend.strategy.paths import gen_one_path  # noqa: E402
from backend.strategy.rng import mulberry32  # noqa: E402

HTML = os.path.join(ROOT, "grid_bot_calculator.html")
REF = os.path.join(ROOT, "tools", "reference_engine.mjs")

# JS field name -> Python BacktestResult attribute.
FIELD_MAP = {
    "gridProfit": "grid_profit",
    "floating": "floating",
    "total": "total",
    "totalFees": "total_fees",
    "buyTrades": "buy_trades",
    "sellTrades": "sell_trades",
    "matched": "matched",
    "qtyPerOrder": "qty_per_order",
    "initialBuyQty": "initial_buy_qty",
    "entryPrice": "entry_price",
    "days": "days",
    "apr": "apr",
    "inRange": "in_range",
    "atrPct": "atr_pct",
    "rangeCov": "range_cov",
    "feeImpact": "fee_impact",
    "maxDD": "max_dd",
    "finalPrice": "final_price",
    "gridEff": "grid_eff",
    "riskRatio": "risk_ratio",
    "cashEnd": "cash_end",
    "invQtyEnd": "inv_qty_end",
    "profitPerGridPct": "profit_per_grid_pct",
}


def _node() -> str:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node not found on PATH; parity test requires Node")
    return node


def run_ref(req: dict) -> object:
    proc = subprocess.run(
        [_node(), REF, HTML],
        input=json.dumps(req),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"reference engine failed: {proc.stderr}")
    return json.loads(proc.stdout)


def make_candles(seed: int, n: int, base: float, drift: float, vol: float) -> list[dict]:
    """Deterministic OHLC series (shared by both engines). Uses the ported RNG so
    the series is identical run-to-run; the engines never see the RNG, only these
    candles."""
    rnd = mulberry32(seed)
    out = []
    p = base
    t = 1_700_000_000
    step = 3600
    for _ in range(n):
        o = p
        r = (rnd() - 0.5) * 2 * vol + drift
        c = o * (1 + r)
        hi = max(o, c) * (1 + rnd() * vol)
        lo = min(o, c) * (1 - rnd() * vol)
        out.append({"t": t, "o": o, "h": hi, "l": lo, "c": c})
        p = c
        t += step
    return out


def approx(a: float, b: float, rel: float = 1e-9, ab: float = 1e-6) -> bool:
    if a is None or b is None:
        return a == b
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    return math.isclose(a, b, rel_tol=rel, abs_tol=ab)


# (label, candle params, backtest params)
SCENARIOS = [
    ("choppy-geo", dict(seed=1, n=200, base=150.0, drift=0.0, vol=0.01),
     dict(lower=120, upper=180, grids=20, mode="geometric", invest=1000, fee=0.1, slip_bps=0)),
    ("uptrend-arith", dict(seed=2, n=300, base=100.0, drift=0.0008, vol=0.012),
     dict(lower=80, upper=160, grids=30, mode="arithmetic", invest=5000, fee=0.075, slip_bps=2)),
    ("downtrend-geo", dict(seed=3, n=250, base=200.0, drift=-0.0009, vol=0.015),
     dict(lower=120, upper=260, grids=12, mode="geometric", invest=2500, fee=0.1, slip_bps=5)),
    ("manual-entry", dict(seed=4, n=180, base=70.0, drift=0.0002, vol=0.02),
     dict(lower=55, upper=95, grids=40, mode="geometric", invest=3000, fee=0.02, slip_bps=1, entry=72.5)),
    ("wide-fewgrids", dict(seed=5, n=400, base=50.0, drift=0.0, vol=0.008),
     dict(lower=30, upper=70, grids=5, mode="arithmetic", invest=800, fee=0.1, slip_bps=0)),
    ("tight-manygrids", dict(seed=6, n=350, base=300.0, drift=0.0003, vol=0.006),
     dict(lower=280, upper=320, grids=120, mode="geometric", invest=10000, fee=0.04, slip_bps=3)),
    ("no-slip-sellall-off", dict(seed=7, n=220, base=42.0, drift=-0.0004, vol=0.018),
     dict(lower=30, upper=60, grids=15, mode="geometric", invest=1500, fee=0.1, slip_bps=0, sell_all_on_stop=False)),
]


def test_backtest_parity():
    for label, cargs, pargs in SCENARIOS:
        candles = make_candles(**cargs)
        s, e = 0, len(candles) - 1
        py = backtest(candles, s, e, {**pargs, "record_trades": False})
        # JS expects camelCase param keys; translate the snake_case ones.
        js_p = dict(pargs)
        if "slip_bps" in js_p:
            js_p["slipBps"] = js_p.pop("slip_bps")
        if "sell_all_on_stop" in js_p:
            js_p["sellAllOnStop"] = js_p.pop("sell_all_on_stop")
        ref = run_ref({"cmd": "backtest", "candles": candles, "s": s, "e": e, "p": js_p})
        for js_key, py_attr in FIELD_MAP.items():
            jv = ref[js_key]
            pv = getattr(py, py_attr)
            assert approx(pv, jv, rel=1e-7, ab=1e-5), (
                f"[{label}] field {js_key}: python={pv!r} js={jv!r}"
            )
    print("backtest parity: OK across", len(SCENARIOS), "scenarios")


def test_rng_parity():
    for seed in (1, 42, 123456789, 2654435761):
        ref = run_ref({"cmd": "rng", "seed": seed, "n": 50})
        rnd = mulberry32(seed)
        for i, jv in enumerate(ref):
            pv = rnd()
            assert approx(pv, jv, rel=0, ab=1e-12), f"rng seed={seed} i={i}: {pv} vs {jv}"
    print("rng parity: OK")


def test_path_parity():
    cases = [
        # lastClose, lastTs, count, stepSec, vol, drift, seed, trend
        [150.0, 1_700_000_000, 60, 3600, 0.01, 0.0, 12345, 0.5],
        [100.0, 1_700_000_000, 120, 900, 0.02, 0.05, 999999, 0.7],
        [72.0, 1_700_000_000, 40, 60, 0.005, -0.03, 2654435761, 0.0],
    ]
    for args in cases:
        ref = run_ref({"cmd": "path", "args": args})
        py = gen_one_path(*args)
        assert len(ref) == len(py), "path length mismatch"
        for i, (rc, pc) in enumerate(zip(ref, py)):
            for k in ("o", "h", "l", "c"):
                assert approx(pc[k], rc[k], rel=1e-9, ab=1e-9), (
                    f"path i={i} {k}: {pc[k]} vs {rc[k]}"
                )
    print("path parity: OK")


if __name__ == "__main__":
    test_rng_parity()
    test_path_parity()
    test_backtest_parity()
    print("\nALL PARITY TESTS PASSED")
