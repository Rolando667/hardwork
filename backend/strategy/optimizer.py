"""
Walk-forward optimizer.

Port of ``runOptimization`` from ``grid_bot_calculator.html``: scan a grid of
candidate configs (lower/upper bounds x grid counts x geometric/arithmetic),
backtest each on the SAME real data, and — with walk-forward enabled — rank on
the in-sample slice (first 70%) while re-testing on the held-out out-of-sample
slice (last 30%). A candidate that looks great in-sample but collapses
out-of-sample fit past noise, not a real edge, and must be rejected before deploy.
"""
from __future__ import annotations

from typing import Any

from .engine import backtest, clamp

GRID_SET = [5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 65, 80, 100, 120, 150]
MODES = ["geometric", "arithmetic"]


def wf_split(s0: int, e0: int) -> tuple[int, int, int, int] | None:
    """Return ``(is_s, is_e, oos_s, oos_e)`` for a 70/30 split, or None if the
    window is too short to hold out a meaningful out-of-sample slice.

    Mirrors the split logic in ``runOptimization``: need at least 24 candles and
    at least 4 out-of-sample candles.
    """
    if (e0 - s0 + 1) < 24:
        return None
    split = s0 + max(8, int((e0 - s0 + 1) * 0.70))
    is_e = min(split, e0 - 4)
    oos_s = is_e + 1
    oos_e = e0
    if oos_e - oos_s < 4:
        return None
    return s0, is_e, oos_s, oos_e


def evaluate_candidate(
    candles: list[dict[str, Any]],
    s0: int,
    e0: int,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Walk-forward-evaluate a single candidate config.

    Returns a dict with the in-sample and out-of-sample backtests plus an
    ``overfit`` flag. ``overfit`` is True when the OOS APR drops far below the IS
    APR — the same threshold the calculator paints red:
    ``oos_apr - is_apr < -max(20, |is_apr| * 0.5)``.

    When the window is too short to split, ``oos`` is None and ``overfit`` is
    False (we cannot prove overfit, so we don't block on it — the caller decides).
    """
    split = wf_split(s0, e0)
    is_r = backtest(candles, s0, e0, cfg)
    if split is None:
        return {"is": is_r, "oos": None, "overfit": False, "wf": False}
    is_s, is_e, oos_s, oos_e = split
    is_r = backtest(candles, is_s, is_e, cfg)
    oos_r = backtest(candles, oos_s, oos_e, cfg)
    d = oos_r.apr - is_r.apr
    bad = d < -max(20.0, abs(is_r.apr) * 0.5)
    return {"is": is_r, "oos": oos_r, "overfit": bad, "wf": True}


def _downsample(candles: list[dict[str, Any]], s0: int, e0: int) -> tuple[list[dict[str, Any]], int, int]:
    """Downsample a very dense segment to <=1600 candles for the scan (port)."""
    seg_len = e0 - s0 + 1
    if seg_len <= 1600:
        return candles, s0, e0
    step_n = -(-seg_len // 1600)  # ceil
    ds: list[dict[str, Any]] = []
    i = s0
    while i <= e0:
        ds.append(candles[i])
        i += step_n
    if ds[-1]["t"] != candles[e0]["t"]:
        ds.append(candles[e0])
    return ds, 0, len(ds) - 1


def optimize(
    candles: list[dict[str, Any]],
    s0: int,
    e0: int,
    base: dict[str, Any],
    ref_price: float,
    wf: bool = True,
    sort: str = "total",
    top: int = 12,
) -> list[dict[str, Any]]:
    """Scan candidate grids and return the top ranked configs.

    ``base`` carries the fixed params (invest, fee, slip_bps, entry,
    sell_all_on_stop). ``ref_price`` anchors the candidate bounds. ``sort`` is one
    of ``total`` / ``apr`` / ``risk``. Each returned item:
    ``{lo, up, grids, mode, is, oos, overfit, wf}``.
    """
    cs, s0, e0 = _downsample(candles, s0, e0)
    seg = cs[s0 : e0 + 1]
    if len(seg) < 5:
        return []
    mn = min(c["l"] for c in seg)
    mx = max(c["h"] for c in seg)
    mid = (mn + mx) / 2.0
    span = (mx - mn) or (mid * 0.01)

    split = wf_split(s0, e0) if wf else None
    use_wf = split is not None

    ref = (base.get("entry") if base.get("entry", 0) and base["entry"] > 0 else ref_price) or mid
    floor = max(mn * 0.6, ref * 0.3, 1e-6)
    cap = max(mx, ref * 3)

    def cu(v: float) -> float:
        return min(max(v, floor * 1.01), cap)

    lowers = [
        max(mn, floor),
        max(mn + span * 0.1, floor),
        max(mn - span * 0.15, floor),
        max(mid - span * 0.6, floor),
    ]
    uppers = [
        min(mx, cap),
        cu(mx - span * 0.1),
        cu(mx + span * 0.15),
        cu(mid + span * 0.6),
    ]

    base_cfg = {
        "invest": base["invest"],
        "fee": base["fee"],
        "entry": base.get("entry", 0),
        "sell_all_on_stop": base.get("sell_all_on_stop", True),
        "slip_bps": base.get("slip_bps", 0),
        "record_trades": False,
    }

    results: list[dict[str, Any]] = []
    for lo in lowers:
        for up in uppers:
            if up <= lo or lo <= 0:
                continue
            for g_n in GRID_SET:
                for m in MODES:
                    cfg = {**base_cfg, "lower": lo, "upper": up, "grids": g_n, "mode": m}
                    if use_wf:
                        is_s, is_e, oos_s, oos_e = split  # type: ignore[misc]
                        rank_r = backtest(cs, is_s, is_e, cfg)
                        oos_r = backtest(cs, oos_s, oos_e, cfg)
                    else:
                        rank_r = backtest(cs, s0, e0, cfg)
                        oos_r = None
                    results.append({
                        "lo": lo, "up": up, "grids": g_n, "mode": m,
                        "is": rank_r, "oos": oos_r, "wf": use_wf,
                    })

    key_attr = {"total": "total", "apr": "apr", "risk": "risk_ratio"}.get(sort, "total")
    results.sort(key=lambda x: getattr(x["is"], key_attr), reverse=True)
    out = results[:top]
    for x in out:
        if x["oos"] is not None:
            d = x["oos"].apr - x["is"].apr
            x["overfit"] = d < -max(20.0, abs(x["is"].apr) * 0.5)
        else:
            x["overfit"] = False
    return out
