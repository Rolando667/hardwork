"""Calibrated spot-grid strategy core (ported from grid_bot_calculator.html).

Pure, deterministic, I/O-free. Shared by the live metrics, the walk-forward
optimizer, and the Monte Carlo simulator.
"""
from .engine import BacktestResult, backtest, build_levels, clamp
from .metrics import LiveMetrics, compute_live_metrics, realized_vol_daily
from .montecarlo import mc_model_params, monte_carlo, percentile, steps_for_horizon
from .optimizer import evaluate_candidate, optimize, wf_split
from .paths import gen_one_path
from .rng import gauss_rand, mulberry32

__all__ = [
    "BacktestResult",
    "backtest",
    "build_levels",
    "clamp",
    "LiveMetrics",
    "compute_live_metrics",
    "realized_vol_daily",
    "mc_model_params",
    "monte_carlo",
    "percentile",
    "steps_for_horizon",
    "evaluate_candidate",
    "optimize",
    "wf_split",
    "gen_one_path",
    "gauss_rand",
    "mulberry32",
]
