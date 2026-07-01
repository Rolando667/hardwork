"""
SQLite persistence: the structured action log and bot key/value state.

Every decision the engine makes — reposition or hold — is recorded here with its
trigger reason, so the dashboard and any post-mortem can answer "why did it do
that?". State (current grid epoch, last reposition time, daily counters, running
flag) survives restarts so a startup reconcile has something to compare against.

Stdlib ``sqlite3`` only (no extra dependency). A single connection guarded by a
lock — the scheduler thread and the API event loop both touch it.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    cycle INTEGER,
    kind TEXT NOT NULL,            -- decision | reposition | safety | order | ai | error | info
    action TEXT NOT NULL,          -- hold | reposition | panic | start | stop | ...
    reason TEXT,                   -- human-readable trigger reason
    detail TEXT                    -- JSON blob with structured context
);
CREATE INDEX IF NOT EXISTS idx_action_ts ON action_log(ts);

CREATE TABLE IF NOT EXISTS kv_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: str) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ---- action log ----
    def log(
        self,
        kind: str,
        action: str,
        reason: str = "",
        detail: dict[str, Any] | None = None,
        cycle: int | None = None,
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO action_log (ts, cycle, kind, action, reason, detail) "
                "VALUES (?,?,?,?,?,?)",
                (time.time(), cycle, kind, action, reason, json.dumps(detail or {})),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def recent_actions(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["detail"] = json.loads(d["detail"]) if d["detail"] else {}
            except (json.JSONDecodeError, TypeError):
                d["detail"] = {}
            out.append(d)
        return out

    # ---- key/value state ----
    def set_state(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO kv_state (key, value, updated) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
                (key, json.dumps(value), time.time()),
            )
            self._conn.commit()

    def get_state(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM kv_state WHERE key=?", (key,)
            ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return default

    def close(self) -> None:
        with self._lock:
            self._conn.close()
