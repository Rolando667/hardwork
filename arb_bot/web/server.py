"""Read-only web dashboard for the Phase 1 scanner.

Architecture: a background thread builds the exchange clients once and then runs
the same ``scan()`` loop the console uses, storing the latest result in a shared,
lock-protected state. A tiny stdlib HTTP server serves a single static page that
polls a JSON endpoint. No third-party web framework, no build step, no trading —
purely a viewer over the read-only scanner.

Endpoints:
    GET /            -> the dashboard page
    GET /api/scan    -> latest scan as JSON (+ status meta)
    GET /health      -> liveness probe
"""

from __future__ import annotations

import json
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..core.config import Config
from ..core.logging_setup import get_logger
from ..core.timeutils import utcnow
from ..exchanges.factory import build_exchanges_verbose
from ..scanner.scanner import scan
from .serialize import scan_to_dict

log = get_logger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


class DashboardState:
    """Latest scan + status, shared between the worker thread and HTTP handlers."""

    def __init__(self, cfg: Config) -> None:
        self._lock = threading.Lock()
        self._cfg = cfg
        self.scan_payload: dict | None = None
        self.skipped_exchanges: dict[str, str] = {}
        self.error: str | None = None
        self.last_update = None
        self.scans_done = 0

    def set_scan(self, payload: dict) -> None:
        with self._lock:
            self.scan_payload = payload
            self.last_update = utcnow()
            self.error = None
            self.scans_done += 1

    def set_error(self, message: str) -> None:
        with self._lock:
            self.error = message

    def set_skipped(self, skipped: dict[str, str]) -> None:
        with self._lock:
            self.skipped_exchanges = skipped

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "ok": self.error is None and self.scan_payload is not None,
                "error": self.error,
                "last_update": self.last_update.isoformat() if self.last_update else None,
                "scans_done": self.scans_done,
                "refresh_seconds": self._cfg.runtime.loop_interval_seconds,
                "skipped_exchanges": dict(self.skipped_exchanges),
                "scan": self.scan_payload,
            }


def _worker(state: DashboardState, cfg: Config, stop: threading.Event) -> None:
    """Build exchanges once, then scan on a loop until ``stop`` is set."""
    log.info("dashboard worker: building exchanges...")
    clients, skipped = build_exchanges_verbose(cfg)
    state.set_skipped(skipped)
    if len(clients) < 2:
        state.set_error(
            f"only {len(clients)} exchange(s) loaded; need >= 2. skipped: "
            + ", ".join(f"{k} ({v})" for k, v in skipped.items())
        )
        log.error("dashboard worker: not enough exchanges; worker idle")
        return

    threshold = cfg.thresholds.entry_net_spread_bps
    while not stop.is_set():
        try:
            result = scan(clients, cfg)
            state.set_scan(scan_to_dict(result, threshold))
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            log.exception("dashboard scan failed: %s", exc)
            state.set_error(f"scan failed: {exc}")
        if not cfg.runtime.loop:
            break
        stop.wait(cfg.runtime.loop_interval_seconds)


class _Handler(BaseHTTPRequestHandler):
    server_version = "arb_bot-dashboard"

    def __init__(self, *args, state: DashboardState, **kwargs) -> None:
        self._state = state
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/index.html":
            self._send_file("index.html", "text/html; charset=utf-8")
        elif path == "/api/scan":
            self._send_json(self._state.snapshot())
        elif path == "/health":
            self._send_json({"status": "ok"})
        else:
            self._send_bytes(404, b"not found", "text/plain")

    def _send_file(self, name: str, content_type: str) -> None:
        target = (_STATIC_DIR / name).resolve()
        if not str(target).startswith(str(_STATIC_DIR.resolve())) or not target.exists():
            self._send_bytes(404, b"not found", "text/plain")
            return
        self._send_bytes(200, target.read_bytes(), content_type)

    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload, default=_json_default).encode("utf-8")
        self._send_bytes(200, body, "application/json")

    def _send_bytes(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # quiet; route to our logger
        log.debug("http %s", fmt % args)


def _json_default(obj: object) -> object:
    # Floats/ints/strs/bools/None serialize natively; this catches stragglers.
    return str(obj)


def run_dashboard(cfg: Config, host: str = "127.0.0.1", port: int = 8000) -> int:
    """Start the background scan worker and serve the dashboard until interrupted."""
    state = DashboardState(cfg)
    stop = threading.Event()
    worker = threading.Thread(target=_worker, args=(state, cfg, stop), daemon=True)
    worker.start()

    handler = partial(_Handler, state=state)
    httpd = ThreadingHTTPServer((host, port), handler)
    log.info("dashboard serving at http://%s:%d  (Ctrl-C to stop)", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("dashboard interrupted; shutting down")
    finally:
        stop.set()
        httpd.shutdown()
        httpd.server_close()
    return 0
