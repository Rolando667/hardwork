"""Legging risk — the gap between filling leg 1 and leg 2.

Two failure modes the spec insists on modeling:

* **Adverse decay:** in the ``delay_ms`` between the two fills the spread partly
  collapses, so the second leg fills worse and we capture less than the observed
  spread. Modeled as a bps penalty proportional to the delay.
* **One-leg fill:** with some probability leg 2 never fills; we are left
  directionally exposed and must immediately unwind leg 1 (reduce-only), eating a
  full one-leg round-trip cost. The entry is aborted at that loss.

Pure and deterministic given the seeded RNG, so paper runs reproduce.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random

from ..core.config import FeesConfig, SimLeggingConfig
from ..core.models import NormalizedMarket, QuoteSnapshot

_BPS = 10_000.0


@dataclass(frozen=True)
class LeggingOutcome:
    filled: bool
    entry_penalty_bps: float     # adverse spread decay during the leg gap (>= 0)
    emergency_cost_bps: float    # if not filled: cost to unwind the one filled leg (>= 0)


def apply_legging(
    rng: Random,
    leg_cfg: SimLeggingConfig,
    fees_cfg: FeesConfig,
    entry_gross_bps: float,
    first_leg_market: NormalizedMarket,
    first_leg_quote: QuoteSnapshot,
) -> LeggingOutcome:
    """Decide whether both legs fill and how much the spread decayed meanwhile.

    ``first_leg_*`` describe the leg that fills first (assumed the long/buy leg);
    it is the one we must emergency-close if the second leg fails.
    """
    # One-leg-fill failure -> abort, unwind the first leg at a full round-trip cost.
    if rng.random() < leg_cfg.one_leg_fill_prob:
        taker = first_leg_market.taker_fee
        half = abs(first_leg_quote.ask - first_leg_quote.mid) / first_leg_quote.mid * _BPS
        emergency = 2.0 * taker * _BPS + 2.0 * half + 2.0 * fees_cfg.slippage_bps
        return LeggingOutcome(filled=False, entry_penalty_bps=0.0, emergency_cost_bps=emergency)

    # Both legs fill, but the spread decayed during the gap -> worse effective entry.
    penalty = (leg_cfg.delay_ms / 100.0) * leg_cfg.adverse_bps_per_100ms
    penalty = min(penalty, max(entry_gross_bps, 0.0))  # cannot lose more than the spread on entry
    return LeggingOutcome(filled=True, entry_penalty_bps=penalty, emergency_cost_bps=0.0)
