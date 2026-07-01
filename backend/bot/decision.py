"""
The deterministic decision engine — the heart of the bot.

Each cycle it answers one question: reposition the grid, or leave it alone?
It does so with a no-trade band / hysteresis so it doesn't churn on noise. A
reposition is proposed only if at least one trigger fires:

  * price left the active range by more than ``band_pct`` of a grid step, or
  * ATR% shifted by more than ``vol_pct`` versus when the grid was set, or
  * the fill-rate collapsed (the grid sat idle too long).

Otherwise it holds. When a reposition *is* warranted, the candidate grid is
walk-forward validated (in-sample / out-of-sample, reusing the calculator's
optimizer) and **rejected if it only looks good in-sample**. Throttling
(cooldown + daily cap) is applied by the runner, which passes ``can_reposition``
in so a throttled-but-warranted cycle is logged honestly as a hold.
"""
from __future__ import annotations

import time
from typing import Any

from ..config import Settings
from ..models import ActiveGrid, Decision, GridConfig
from ..strategy.metrics import LiveMetrics
from ..strategy.optimizer import optimize


def _wf_summary(item: dict[str, Any]) -> dict[str, Any]:
    is_r = item["is"]
    oos_r = item.get("oos")
    return {
        "is_total": round(is_r.total, 4),
        "is_apr": round(is_r.apr, 2),
        "oos_total": round(oos_r.total, 4) if oos_r else None,
        "oos_apr": round(oos_r.apr, 2) if oos_r else None,
        "overfit": bool(item.get("overfit", False)),
        "wf": bool(item.get("wf", False)),
    }


def propose_candidate(
    settings: Settings,
    candles: list[dict[str, Any]],
    price: float,
) -> tuple[GridConfig | None, dict[str, Any] | None, bool, str | None]:
    """Propose a new grid and validate it out-of-sample.

    Returns ``(candidate, walk_forward_summary, validated, reject_reason)``.

    * Uses the optimizer to scan candidate ranges/grid-counts and rank them on the
      in-sample slice with an out-of-sample re-test.
    * Picks the best candidate that is **not** flagged overfit. If every candidate
      is overfit and ``reject_overfit`` is on, returns no candidate (the caller
      holds). If walk-forward couldn't run (too little history), returns the top
      candidate with ``validated=False`` so first-deploy still works.
    """
    base = {
        "invest": settings.invest,
        "fee": settings.fee_pct,
        "slip_bps": settings.slip_bps,
        "entry": 0,
        "sell_all_on_stop": True,
    }
    ranked = optimize(candles, 0, len(candles) - 1, base, price, wf=True, sort="total")

    if not ranked:
        # Not enough data to optimize — fall back to an auto-range grid around price.
        lower = price * (1 - settings.auto_range_pct)
        upper = price * (1 + settings.auto_range_pct)
        cand = GridConfig(lower=lower, upper=upper, grids=settings.grids, mode=settings.grid_mode)
        return cand, None, False, None

    wf_ran = bool(ranked[0].get("wf"))
    if wf_ran:
        good = next((x for x in ranked if not x.get("overfit")), None)
        if good is None:
            if settings.reject_overfit:
                return None, _wf_summary(ranked[0]), False, (
                    "every candidate failed out-of-sample (overfit); holding"
                )
            chosen = ranked[0]
            validated = False
        else:
            chosen = good
            validated = True
    else:
        chosen = ranked[0]
        validated = False  # couldn't hold out a slice; not proven

    cand = GridConfig(
        lower=float(chosen["lo"]),
        upper=float(chosen["up"]),
        grids=int(chosen["grids"]),
        mode=str(chosen["mode"]),
    )
    return cand, _wf_summary(chosen), validated, None


def evaluate(
    settings: Settings,
    price: float,
    active: ActiveGrid | None,
    metrics: LiveMetrics,
    candles: list[dict[str, Any]],
    can_reposition: bool,
    throttle_reason: str = "",
) -> Decision:
    """Decide hold vs reposition for this cycle."""
    m = metrics.to_dict()

    # ---- first deployment: no grid live yet ----
    if active is None:
        cand, wf, validated, reject = propose_candidate(settings, candles, price)
        if cand is None:
            return Decision(action="hold", reason=reject or "no valid initial grid",
                            triggers=[], metrics=m, rejected_reason=reject)
        return Decision(action="deploy", reason="initial deployment", triggers=["initial"],
                        candidate=cand, validated=validated, metrics=m, walk_forward=wf)

    cfg = active.config

    # A geometric grid's cell width varies (small near lower, large near upper), so
    # a single flat average would mis-size the band. Use the actual boundary cell
    # widths from the deployed levels: the top cell for the upper band, the bottom
    # cell for the lower band. Fall back to the flat average if levels are absent.
    avg_step = (cfg.upper - cfg.lower) / cfg.grids if cfg.grids else 0.0
    lv = active.levels
    if lv and len(lv) >= 2:
        top_step = lv[-1] - lv[-2]
        bot_step = lv[1] - lv[0]
    else:
        top_step = bot_step = avg_step

    triggers: list[str] = []
    detail_reasons: list[str] = []

    # trigger 1: price left the active range by > band_pct of a (boundary) grid step
    if avg_step > 0:
        upper_band = cfg.upper + settings.band_pct * top_step
        lower_band = cfg.lower - settings.band_pct * bot_step
        if price > upper_band:
            triggers.append("price_above_band")
            detail_reasons.append(
                f"price {price:.4f} above upper band {upper_band:.4f}"
            )
        elif price < lower_band:
            triggers.append("price_below_band")
            detail_reasons.append(
                f"price {price:.4f} below lower band {lower_band:.4f}"
            )

    # trigger 2: ATR% shifted by > vol_pct vs when grid was set
    if active.set_atr_pct > 1e-9:
        rel = abs(metrics.atr_pct - active.set_atr_pct) / active.set_atr_pct
        if rel > settings.vol_pct:
            triggers.append("vol_shift")
            detail_reasons.append(
                f"ATR% moved {rel * 100:.0f}% (set {active.set_atr_pct:.3f} -> "
                f"now {metrics.atr_pct:.3f})"
            )

    # trigger 3: fill-rate collapsed (grid idle too long)
    age_hours = (time.time() - active.set_time) / 3600.0
    if age_hours >= settings.fill_rate_grace_hours and metrics.fill_rate_per_day < settings.min_fill_rate_per_day:
        triggers.append("fill_rate_low")
        detail_reasons.append(
            f"fill-rate {metrics.fill_rate_per_day:.2f}/day below "
            f"{settings.min_fill_rate_per_day}/day after {age_hours:.1f}h"
        )

    if not triggers:
        return Decision(action="hold",
                        reason="held — within band; no trigger fired",
                        triggers=[], metrics=m)

    # A trigger fired. If throttled, honour it and hold.
    if not can_reposition:
        return Decision(action="hold",
                        reason=f"reposition warranted ({', '.join(triggers)}) but {throttle_reason}",
                        triggers=triggers, metrics=m)

    # Validate a candidate before deploying.
    cand, wf, validated, reject = propose_candidate(settings, candles, price)
    if cand is None:
        return Decision(action="hold",
                        reason=f"trigger fired ({', '.join(triggers)}) but {reject}",
                        triggers=triggers, metrics=m, rejected_reason=reject, walk_forward=wf)

    return Decision(action="reposition",
                    reason="; ".join(detail_reasons),
                    triggers=triggers, candidate=cand, validated=validated,
                    metrics=m, walk_forward=wf)
