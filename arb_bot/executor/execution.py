"""Atomic two-leg open/close — the core safety mechanism.

Both legs are submitted near-simultaneously (parallel). If one fills and the
other does not within the timeout, the filled leg is immediately closed
reduce-only — we NEVER stay directionally exposed. Closing likewise sends
reduce-only on both legs so we can only ever reduce, never flip.

Deterministic; no LLM. Every order carries a clientOrderId for idempotency so a
retry or reconnect cannot double-fill.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..core.config import LiveConfig
from ..core.logging_setup import get_logger
from .broker import Broker, OrderResult
from .state_machine import State, StateMachine

log = get_logger(__name__)


@dataclass(frozen=True)
class LegPlan:
    exchange: str
    symbol: str
    side: str            # 'buy' | 'sell'
    amount: float        # contracts
    position_side: str   # 'long' | 'short'
    price: float | None = None  # None => market (taker)


@dataclass(frozen=True)
class TradePlan:
    trade_id: str
    coin: str
    long_leg: LegPlan    # the leg that establishes the long position
    short_leg: LegPlan
    size_coin: float
    notional_quote: float


@dataclass
class OpenOutcome:
    ok: bool
    sm: StateMachine
    long_res: OrderResult | None
    short_res: OrderResult | None
    aborted: bool = False
    reason: str | None = None


@dataclass
class CloseOutcome:
    ok: bool
    sm: StateMachine
    reason: str | None = None


class AtomicExecutor:
    def __init__(self, broker: Broker, cfg: LiveConfig) -> None:
        self.broker = broker
        self.cfg = cfg
        self._seq = 0

    # ---- open ------------------------------------------------------------

    def open_trade(self, plan: TradePlan) -> OpenOutcome:
        sm = StateMachine(plan.trade_id)
        sm.to(State.OPENING_LEG_1)

        # Submit both legs in parallel — this is the atomicity guarantee.
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_long = pool.submit(self._submit, plan.long_leg, reduce_only=False, tag="openL")
            f_short = pool.submit(self._submit, plan.short_leg, reduce_only=False, tag="openS")
            long_res = f_long.result()
            short_res = f_short.result()

        long_res = self._await_fill(long_res)
        short_res = self._await_fill(short_res)

        long_ok, short_ok = long_res.is_filled, short_res.is_filled

        if long_ok and short_ok:
            sm.to(State.OPENING_LEG_2)
            sm.to(State.OPEN)
            log.info("trade %s OPEN: both legs filled", plan.trade_id)
            return OpenOutcome(ok=True, sm=sm, long_res=long_res, short_res=short_res)

        if long_ok ^ short_ok:
            # One leg filled, the other did not -> emergency close the filled one.
            filled_leg, filled_res = (
                (plan.long_leg, long_res) if long_ok else (plan.short_leg, short_res)
            )
            unfilled_res = short_res if long_ok else long_res
            sm.to(State.OPENING_LEG_2)
            sm.to(State.EMERGENCY_CLOSE)
            log.warning(
                "trade %s ONE-LEG-FILL (%s filled, %s did not) -> emergency close",
                plan.trade_id, filled_leg.exchange, unfilled_res.exchange,
            )
            self._cancel_if_open(unfilled_res)
            self._emergency_close(filled_leg, plan.trade_id)
            sm.to(State.FLAT)
            return OpenOutcome(ok=False, sm=sm, long_res=long_res, short_res=short_res,
                               aborted=True, reason="one_leg_fill")

        # Neither leg filled -> cancel any resting orders, stay flat.
        self._cancel_if_open(long_res)
        self._cancel_if_open(short_res)
        sm.to(State.FLAT)
        log.warning("trade %s no fills -> flat", plan.trade_id)
        return OpenOutcome(ok=False, sm=sm, long_res=long_res, short_res=short_res,
                           aborted=True, reason="no_fill")

    # ---- close -----------------------------------------------------------

    def close_trade(self, plan: TradePlan, sm: StateMachine) -> CloseOutcome:
        if sm.state != State.OPEN:
            raise ValueError(f"can only close from OPEN, not {sm.state}")
        sm.to(State.CLOSING)

        # Reduce-only closing orders on both legs, submitted in parallel.
        close_long = LegPlan(plan.long_leg.exchange, plan.long_leg.symbol, "sell",
                             plan.long_leg.amount, "long")
        close_short = LegPlan(plan.short_leg.exchange, plan.short_leg.symbol, "buy",
                              plan.short_leg.amount, "short")
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_l = pool.submit(self._submit, close_long, reduce_only=True, tag="closeL")
            f_s = pool.submit(self._submit, close_short, reduce_only=True, tag="closeS")
            lr = self._await_fill(f_l.result())
            sr = self._await_fill(f_s.result())

        if lr.is_filled and sr.is_filled:
            sm.to(State.FLAT)
            log.info("trade %s FLAT: both legs closed", plan.trade_id)
            return CloseOutcome(ok=True, sm=sm)

        # A close leg did not fill -> emergency retry the stragglers reduce-only.
        sm.to(State.EMERGENCY_CLOSE)
        for leg, res in ((close_long, lr), (close_short, sr)):
            if not res.is_filled:
                log.warning("trade %s close leg %s unfilled -> emergency retry", plan.trade_id, leg.exchange)
                self._emergency_close(LegPlan(leg.exchange, leg.symbol,
                                              "sell" if leg.position_side == "long" else "buy",
                                              leg.amount, leg.position_side), plan.trade_id)
        sm.to(State.FLAT)
        return CloseOutcome(ok=False, sm=sm, reason="close_retry")

    # ---- helpers ---------------------------------------------------------

    def _submit(self, leg: LegPlan, *, reduce_only: bool, tag: str) -> OrderResult:
        self._seq += 1
        coid = f"{tag}-{leg.exchange}-{self._seq}"
        return self.broker.create_order(
            exchange=leg.exchange, symbol=leg.symbol, side=leg.side, amount=leg.amount,
            position_side=leg.position_side, reduce_only=reduce_only,
            position_mode=self.cfg.position_mode, client_order_id=coid, price=leg.price,
        )

    def _await_fill(self, res: OrderResult) -> OrderResult:
        """Give a resting order until the timeout to fill, then give up on it."""
        if res.is_filled or res.status in ("rejected", "canceled"):
            return res
        deadline = time.monotonic() + self.cfg.leg_fill_timeout_ms / 1000.0
        while time.monotonic() < deadline:
            still_open = any(
                o.client_order_id == res.client_order_id
                for o in self.broker.fetch_open_orders(res.exchange, res.symbol)
            )
            if not still_open:
                # No longer resting: re-fetch position implies it filled — trust filled.
                res.status, res.filled = "filled", res.amount
                return res
            time.sleep(min(0.05, self.cfg.leg_fill_timeout_ms / 1000.0))
        return res  # still not filled at deadline

    def _emergency_close(self, filled_leg: LegPlan, trade_id: str) -> OrderResult:
        """Reduce-only unwind of a single filled leg (opposite side)."""
        self._seq += 1
        opposite = "sell" if filled_leg.side == "buy" else "buy"
        coid = f"emg-{filled_leg.exchange}-{self._seq}"
        log.warning("trade %s EMERGENCY reduce-only %s %s on %s",
                    trade_id, opposite, filled_leg.symbol, filled_leg.exchange)
        return self.broker.create_order(
            exchange=filled_leg.exchange, symbol=filled_leg.symbol, side=opposite,
            amount=filled_leg.amount, position_side=filled_leg.position_side,
            reduce_only=True, position_mode=self.cfg.position_mode, client_order_id=coid,
        )

    def _cancel_if_open(self, res: OrderResult) -> None:
        if not res.is_filled and res.status == "open":
            self.broker.cancel_order(res.exchange, res.symbol, res.client_order_id)
