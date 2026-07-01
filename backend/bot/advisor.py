"""
Optional AI advisor (flag ``USE_AI``, OFF by default).

The advisor **never** places, cancels, or moves orders, and never touches
withdrawals. On a slower cadence it receives a compact metrics snapshot plus the
engine's proposed action and returns:

  (a) a plain-language explanation,
  (b) a sanity flag ("reasonable" / "risky" with a why),
  (c) optionally a parameter tweak — which the runner clamps to allowed ranges
      and re-validates before anything is applied.

Any timeout / error / malformed output is treated as **no action**. It is kept
cheap: a small JSON summary in, a small JSON object out — never raw ticks. The
``anthropic`` package is imported lazily so the app runs fine without it when the
advisor is off.
"""
from __future__ import annotations

from typing import Any

from ..config import Settings

_SCHEMA = {
    "type": "object",
    "properties": {
        "explanation": {"type": "string"},
        "sanity": {"type": "string", "enum": ["reasonable", "risky"]},
        "why": {"type": "string"},
        "suggest_grids": {"type": ["integer", "null"]},
        "suggest_range_mult": {"type": ["number", "null"]},
    },
    "required": ["explanation", "sanity", "why"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a risk-aware advisor for a spot grid trading bot. You do NOT control "
    "the bot — a deterministic engine already decided the action and applies hard "
    "guardrails. Given a metrics snapshot and the engine's proposed action, give a "
    "one or two sentence plain-language explanation, a sanity flag (reasonable or "
    "risky) with a brief why, and OPTIONALLY a small parameter tweak. Any tweak you "
    "suggest will be clamped to a narrow allowed range and re-validated; never "
    "suggest extreme changes. Be concise. Respond only with the JSON object."
)


def get_advice(settings: Settings, summary: dict[str, Any]) -> dict[str, Any] | None:
    """Return advisor output, or None on any error/timeout/malformed result."""
    key = settings.anthropic_api_key.get_secret_value()
    if not key:
        return None
    try:
        import anthropic  # lazy import
        import json

        client = anthropic.Anthropic(api_key=key)
        resp = client.with_options(timeout=20.0).messages.create(
            model=settings.ai_model,
            max_tokens=512,
            system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": json.dumps(summary)}],
        )
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
        data = json.loads(text)
        if not isinstance(data, dict) or "sanity" not in data:
            return None
        return data
    except Exception as e:  # noqa: BLE001 - advisor failure must never break the cycle
        return {"error": str(e)[:200]}


def clamp_nudge(
    settings: Settings,
    candidate_grids: int,
    candidate_lower: float,
    candidate_upper: float,
    advice: dict[str, Any],
) -> tuple[int, float, float, str] | None:
    """Apply a clamped version of the advisor's tweak to a candidate.

    Returns ``(grids, lower, upper, note)`` if a within-bounds tweak was applied,
    else None. The clamp keeps any change within ``ai_max_param_nudge_pct`` of the
    engine's own candidate, so the advisor can nudge but never override.
    """
    if not advice or advice.get("sanity") != "reasonable":
        return None
    pct = settings.ai_max_param_nudge_pct
    notes = []
    grids = candidate_grids
    lower = candidate_lower
    upper = candidate_upper

    sg = advice.get("suggest_grids")
    if isinstance(sg, int) and sg >= 2:
        lo = max(2, int(candidate_grids * (1 - pct)))
        hi = int(candidate_grids * (1 + pct))
        clamped = max(lo, min(hi, sg))
        if clamped != grids:
            grids = clamped
            notes.append(f"grids {candidate_grids}->{grids}")

    rm = advice.get("suggest_range_mult")
    if isinstance(rm, (int, float)) and rm > 0:
        rm = max(1 - pct, min(1 + pct, float(rm)))
        mid = (candidate_lower + candidate_upper) / 2
        half = (candidate_upper - candidate_lower) / 2 * rm
        if half > 0:
            lower = mid - half
            upper = mid + half
            notes.append(f"range x{rm:.3f}")

    if not notes:
        return None
    return grids, lower, upper, "AI nudge: " + ", ".join(notes)
