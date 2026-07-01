"""
Stochastic price-path generator for Monte Carlo.

Port of ``genOnePath`` from ``grid_bot_calculator.html``: a single future price
path under one drift assumption, with the same dynamics the calculator uses —
Gaussian shocks, volatility clustering (vol mean-reverts to its base with its own
noise), AR(1) momentum (trend persistence), and rare fat-tail jumps.
"""
from __future__ import annotations

from typing import Any

from .engine import clamp
from .rng import gauss_rand, mulberry32

_MASK = 0xFFFFFFFF


def gen_one_path(
    last_close: float,
    last_ts: int,
    count: int,
    step_sec: int,
    vol_per_step: float,
    drift_total: float,
    seed: int,
    trend: float,
) -> list[dict[str, Any]]:
    """Generate ``count`` synthetic candles of ``step_sec`` each.

    ``trend`` is the AR(1) momentum coefficient (0 = pure random walk,
    1 = strong trend persistence), clamped to [0, 0.96] as in the reference.
    """
    rnd = mulberry32(seed & _MASK)
    mom = clamp(trend if trend is not None else 0.5, 0.0, 0.96)
    drift_per = drift_total / count
    arr: list[dict[str, Any]] = []
    p = last_close
    t = last_ts
    ret = 0.0
    vol = vol_per_step
    for _i in range(count):
        t += step_sec
        o = p
        # volatility clustering: vol mean-reverts to base with its own noise
        vol += (vol_per_step - vol) * 0.05 + (rnd() - 0.5) * vol_per_step * 0.15
        vol = clamp(vol, vol_per_step * 0.3, vol_per_step * 3.2)
        shock = gauss_rand(rnd) * vol
        if rnd() < 0.012:  # rare fat-tail jump
            shock += (rnd() - 0.5) * 2 * vol * 5
        # AR(1) momentum: blend previous move with the new shock
        ret = mom * ret + (1 - mom) * shock
        c = o * (1 + ret + drift_per)
        wig = vol * 0.6
        h = max(o, c) * (1 + abs(gauss_rand(rnd)) * wig)
        low = min(o, c) * (1 - abs(gauss_rand(rnd)) * wig)
        arr.append({"t": t, "o": o, "h": h, "l": low, "c": c})
        p = c
    return arr
