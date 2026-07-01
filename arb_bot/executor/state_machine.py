"""Explicit trade state machine with validated transitions.

    IDLE -> OPENING_LEG_1 -> OPENING_LEG_2 -> OPEN -> CLOSING -> FLAT
                       \\             \\                    \\
                        -> EMERGENCY_CLOSE <----------------/
    (any) -> RECOVERY  (unexpected error / reconnect -> reconcile before continuing)

Every transition is checked against the allowed set; an illegal transition raises
rather than silently leaving the trade in an ambiguous state. Each trade carries
its own machine so failures are handled per trade, not globally.
"""

from __future__ import annotations

from enum import Enum

from ..core.logging_setup import get_logger

log = get_logger(__name__)


class State(str, Enum):
    IDLE = "IDLE"
    OPENING_LEG_1 = "OPENING_LEG_1"
    OPENING_LEG_2 = "OPENING_LEG_2"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    FLAT = "FLAT"
    RECOVERY = "RECOVERY"
    EMERGENCY_CLOSE = "EMERGENCY_CLOSE"


# Allowed forward transitions. RECOVERY is reachable from anywhere (added below).
_ALLOWED: dict[State, set[State]] = {
    State.IDLE: {State.OPENING_LEG_1, State.FLAT},
    State.OPENING_LEG_1: {State.OPENING_LEG_2, State.EMERGENCY_CLOSE, State.FLAT},
    State.OPENING_LEG_2: {State.OPEN, State.EMERGENCY_CLOSE},
    State.OPEN: {State.CLOSING, State.EMERGENCY_CLOSE},
    State.CLOSING: {State.FLAT, State.EMERGENCY_CLOSE},
    State.EMERGENCY_CLOSE: {State.FLAT, State.RECOVERY},
    State.RECOVERY: {State.FLAT, State.OPEN, State.IDLE},
    State.FLAT: {State.IDLE},
}


class IllegalTransition(Exception):
    pass


class StateMachine:
    def __init__(self, trade_id: str, state: State = State.IDLE) -> None:
        self.trade_id = trade_id
        self.state = state
        self.history: list[State] = [state]

    def can(self, target: State) -> bool:
        if target == State.RECOVERY:
            return True  # always allowed to bail into recovery
        return target in _ALLOWED.get(self.state, set())

    def to(self, target: State) -> None:
        if not self.can(target):
            raise IllegalTransition(f"{self.trade_id}: {self.state.value} -> {target.value} not allowed")
        log.info("trade %s: %s -> %s", self.trade_id, self.state.value, target.value)
        self.state = target
        self.history.append(target)

    @property
    def is_terminal(self) -> bool:
        return self.state == State.FLAT

    @property
    def is_directional(self) -> bool:
        """True while the trade could be holding a one-sided (unhedged) position."""
        return self.state in (State.OPENING_LEG_2, State.OPEN, State.CLOSING, State.EMERGENCY_CLOSE)
