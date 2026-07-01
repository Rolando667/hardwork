"""
Deterministic RNG used by the forecast / Monte Carlo path generators.

Direct port of ``mulberry32`` and ``gaussRand`` from ``grid_bot_calculator.html``.
The whole point is bit-for-bit reproducibility: feeding the same seed here and in
the reference JS must produce the same float sequence, so Monte Carlo outcomes
match the calculator. We therefore replicate JS's 32-bit integer semantics
(``Math.imul``, ``>>>``, ``| 0``) exactly via masking — only the low 32 bits
matter for the bit-twiddling, so we keep state as an unsigned 32-bit int.
"""
from __future__ import annotations

import math
from typing import Callable

_MASK = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    """JS ``Math.imul`` low-32-bit result (operands taken mod 2^32)."""
    return ((a & _MASK) * (b & _MASK)) & _MASK


def mulberry32(seed: int) -> Callable[[], float]:
    """Return a callable producing floats in [0, 1) — the mulberry32 PRNG.

    ``seed`` is reduced to unsigned 32 bits, matching ``mulberry32(seed >>> 0)``.
    """
    state = seed & _MASK

    def rnd() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & _MASK
        a = state
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((((t + _imul(t ^ (t >> 7), 61 | t)) & _MASK) ^ t) & _MASK)
        return ((t ^ (t >> 14)) & _MASK) / 4294967296.0

    return rnd


def gauss_rand(rnd: Callable[[], float]) -> float:
    """Standard-normal sample via Box-Muller, drawing uniforms from ``rnd``."""
    u = 0.0
    v = 0.0
    while u == 0.0:
        u = rnd()
    while v == 0.0:
        v = rnd()
    return math.sqrt(-2.0 * math.log(u)) * math.cos(2.0 * math.pi * v)
