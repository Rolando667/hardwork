"""
Safety & throttling.

Three independent guards, all backed by persisted state so they survive restarts:

* **Throttle** — a cooldown between repositions and a per-UTC-day reposition cap,
  so the bot can't churn the grid even if triggers keep firing.
* **Daily loss limit** — if intraday realized+floating PnL breaches
  ``-max_daily_loss``, halt and alert.
* **Kill switch** — a sticky "halted" flag (set by the panic button/endpoint or a
  breached loss limit) that blocks all order placement until explicitly cleared.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from ..config import Settings
from ..db import Store


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Safety:
    def __init__(self, settings: Settings, store: Store) -> None:
        self.settings = settings
        self.store = store

    # ---- kill switch ----
    def is_halted(self) -> bool:
        return bool(self.store.get_state("halted", {}).get("halted", False))

    def halt(self, reason: str) -> None:
        self.store.set_state("halted", {"halted": True, "reason": reason, "ts": time.time()})
        self.store.log("safety", "halt", reason)

    def resume(self) -> None:
        self.store.set_state("halted", {"halted": False, "reason": "", "ts": time.time()})
        self.store.log("safety", "resume", "kill-switch cleared")

    def halt_reason(self) -> str:
        return str(self.store.get_state("halted", {}).get("reason", ""))

    # ---- throttle ----
    def _throttle(self) -> dict:
        t = self.store.get_state("throttle", {})
        if t.get("day") != _utc_day():
            t = {"day": _utc_day(), "count": 0, "last_reposition_ts": t.get("last_reposition_ts", 0)}
        return t

    def can_reposition(self, now: float | None = None) -> tuple[bool, str]:
        now = now if now is not None else time.time()
        t = self._throttle()
        if t["count"] >= self.settings.max_repositions_per_day:
            return False, f"daily reposition cap reached ({self.settings.max_repositions_per_day})"
        elapsed = now - float(t.get("last_reposition_ts", 0) or 0)
        if elapsed < self.settings.cooldown_seconds:
            remain = int(self.settings.cooldown_seconds - elapsed)
            return False, f"cooldown active ({remain}s remaining)"
        return True, ""

    def record_reposition(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        t = self._throttle()
        t["count"] = int(t.get("count", 0)) + 1
        t["last_reposition_ts"] = now
        self.store.set_state("throttle", t)

    def repositions_today(self) -> int:
        return int(self._throttle().get("count", 0))

    # ---- daily loss limit ----
    def check_daily_loss(self, total_pnl: float) -> tuple[bool, float]:
        """Update intraday baseline and return ``(breached, intraday_pnl)``.

        On a UTC day rollover the baseline is anchored to the **last observed
        total** (the end of the prior day), not the current one — otherwise a loss
        that lands on the very first cycle of a new day would be masked (baseline
        re-anchored to the already-depressed total => intraday 0). ``last_total``
        is persisted every call so the reference survives restarts.
        """
        d = self.store.get_state("daily_pnl", {})
        if d.get("day") != _utc_day():
            prev_last = d.get("last_total")
            baseline = float(prev_last) if prev_last is not None else total_pnl
            d = {"day": _utc_day(), "baseline_total": baseline, "last_total": total_pnl}
        else:
            d["last_total"] = total_pnl
        self.store.set_state("daily_pnl", d)
        intraday = total_pnl - float(d.get("baseline_total", total_pnl))
        breached = intraday <= -abs(self.settings.max_daily_loss)
        return breached, intraday
