"""
Monte Carlo outcome distribution.

Port of ``runMonteCarlo`` / ``finishMc`` / ``pctl`` / ``mcModelParams`` from
``grid_bot_calculator.html``. Generates many random future price paths from the
same volatility/momentum model (neutral drift by default), backtests the current
grid config over real history + each path, and reports the spread of outcomes.

One forecast line is noise; the *distribution* is the honest answer. We surface
P5 / median / P95 of Total PnL plus the win-rate — never a single promised number.
"""
from __future__ import annotations

import math
from typing import Any

from .engine import backtest, clamp
from .paths import gen_one_path

_MASK = 0xFFFFFFFF
_GOLDEN = 2654435761  # the multiplier used to decorrelate per-path seeds


def percentile(arr: list[float], q: float) -> float:
    """Linear-interpolated percentile, matching the calculator's ``pctl``."""
    if not arr:
        return 0.0
    a = sorted(arr)
    idx = clamp(q * (len(a) - 1), 0, len(a) - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return a[lo]
    return a[lo] + (a[hi] - a[lo]) * (idx - lo)


def mc_model_params(
    atr_pct: float,
    step_sec: int,
    ref_sec: int,
    vol_mul: float = 1.0,
) -> tuple[float, float]:
    """Per-step volatility and (neutral) total drift, from ATR%.

    Mirrors the non-auto branch of ``mcModelParams``:
    ``volPerStep = atrFrac * volMul * sqrt(stepSec / refSec)``, ``driftTotal = 0``.
    """
    import math
    atr_frac = clamp((atr_pct or 0.05) / 100.0, 0.0002, 0.05)
    vol_per_step = atr_frac * vol_mul * math.sqrt(step_sec / max(1, ref_sec))
    return vol_per_step, 0.0


def steps_for_horizon(horizon_sec: int) -> tuple[int, int]:
    """Return ``(steps, step_sec)`` for a horizon, matching the calculator."""
    horizon = max(60, horizon_sec)
    if horizon > 2592000:
        coarse = 86400
    elif horizon > 604800:
        coarse = 3600
    elif horizon > 86400:
        coarse = 900
    else:
        coarse = 60
    steps = int(clamp(round(horizon / coarse), 40, 260))
    step_sec = max(1, round(horizon / steps))
    return steps, step_sec


def monte_carlo(
    real_segment: list[dict[str, Any]],
    bt_cfg: dict[str, Any],
    last_close: float,
    last_ts: int,
    horizon_sec: int,
    n_paths: int,
    vol_per_step: float,
    drift_total: float,
    base_seed: int,
    trend: float = 0.5,
) -> dict[str, Any]:
    """Run ``n_paths`` simulations and summarise the Total-PnL distribution.

    ``real_segment`` is the real history (downsampled by the caller if needed);
    each path is appended to it and the whole series is backtested. Returns
    P5/P50/P95 of Total PnL, median APR & drawdown, win-rate, and the raw totals
    (for histogram rendering).
    """
    steps, step_sec = steps_for_horizon(horizon_sec)
    base_seed = (base_seed or 12345) & _MASK
    totals: list[float] = []
    aprs: list[float] = []
    dds: list[float] = []
    for i in range(n_paths):
        seed = (base_seed + i * _GOLDEN) & _MASK
        path = gen_one_path(last_close, last_ts, steps, step_sec, vol_per_step, drift_total, seed, trend)
        series = real_segment + path
        r = backtest(series, 0, len(series) - 1, bt_cfg)
        totals.append(r.total)
        aprs.append(r.apr)
        dds.append(r.max_dd)

    p5 = percentile(totals, 0.05)
    p50 = percentile(totals, 0.5)
    p95 = percentile(totals, 0.95)
    win = (len([t for t in totals if t > 0]) / len(totals) * 100.0) if totals else 0.0
    return {
        "n": n_paths,
        "p5": p5,
        "p50": p50,
        "p95": p95,
        "win_rate": win,
        "apr_median": percentile(aprs, 0.5),
        "dd_median": percentile(dds, 0.5),
        "totals": totals,
    }
