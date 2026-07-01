"""Per-exchange order params for reduce-only / position side — the concrete quirks.

CCXT does NOT unify these, and getting them wrong silently opens the wrong side or
gets the order rejected. Encoded here from the spec's hard-won specifics and kept
pure so it can be unit-tested exactly:

* camelCase ``reduceOnly`` (snake_case is silently ignored, ccxt #19082).
* **Binance:** one-way -> ``{'reduceOnly': True}``; hedge -> ``{'positionSide':
  'LONG'|'SHORT'}`` (UPPERCASE) and DO NOT send reduceOnly (else -2022).
* **Bybit:** integer ``positionIdx`` (0 one-way, 1 hedge-long, 2 hedge-short);
  reduceOnly on a zero position -> 110017, so only send it when closing.
* **OKX:** ``{'posSide': 'long'|'short'|'net'}`` (lowercase); reduceOnly is
  emulated (mapped to the opposite posSide), so in hedge we drive it by posSide.
"""

from __future__ import annotations


def build_order_params(
    exchange: str,
    *,
    position_side: str,   # the position this order concerns: 'long' or 'short'
    reduce_only: bool,    # True when closing/reducing, False when opening
    position_mode: str,   # 'one-way' or 'hedge'
) -> dict:
    """Return the ccxt ``params`` dict for one order on ``exchange``."""
    if position_side not in ("long", "short"):
        raise ValueError(f"position_side must be 'long'|'short', got {position_side!r}")
    if position_mode not in ("one-way", "hedge"):
        raise ValueError(f"position_mode must be 'one-way'|'hedge', got {position_mode!r}")

    ex = exchange.lower()
    if ex == "binance":
        return _binance(position_side, reduce_only, position_mode)
    if ex == "bybit":
        return _bybit(position_side, reduce_only, position_mode)
    if ex in ("okx", "okex"):
        return _okx(position_side, reduce_only, position_mode)
    # Generic default: camelCase reduceOnly, only when closing.
    return {"reduceOnly": True} if reduce_only else {}


def _binance(position_side: str, reduce_only: bool, position_mode: str) -> dict:
    if position_mode == "hedge":
        # In hedge mode positionSide selects the book; reduceOnly must NOT be sent.
        return {"positionSide": position_side.upper()}
    # one-way: reduceOnly closes; opening sends nothing special.
    return {"reduceOnly": True} if reduce_only else {}


def _bybit(position_side: str, reduce_only: bool, position_mode: str) -> dict:
    if position_mode == "hedge":
        params: dict = {"positionIdx": 1 if position_side == "long" else 2}
        if reduce_only:
            params["reduceOnly"] = True
        return params
    # one-way uses positionIdx 0; reduceOnly only when closing (else 110017 on flat).
    params = {"positionIdx": 0}
    if reduce_only:
        params["reduceOnly"] = True
    return params


def _okx(position_side: str, reduce_only: bool, position_mode: str) -> dict:
    if position_mode == "hedge":
        # posSide drives open/close in hedge; reduceOnly is emulated, so omit it.
        return {"posSide": position_side}
    # one-way is posSide 'net'; reduceOnly (emulated) only when closing.
    params = {"posSide": "net"}
    if reduce_only:
        params["reduceOnly"] = True
    return params
