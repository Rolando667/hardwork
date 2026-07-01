"""
FastAPI application: the UI server + control API for the bot.

Two tiers (non-negotiable): this Python backend holds all secrets and does all
trading; the browser is UI only and never receives or stores API keys. The
dashboard talks to the REST endpoints here and receives live snapshots over a
WebSocket.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .bot.runner import BotRunner
from .config import Mode, get_settings, reload_settings
from .db import Store
from .env_writer import update_env

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
ENV_PATH = os.path.join(os.getcwd(), ".env")


class WSManager:
    """Pushes snapshots to connected dashboards. Bridges the scheduler thread
    (which produces snapshots) to the asyncio loop (which owns the sockets)."""

    def __init__(self) -> None:
        self.active: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def _send_all(self, data: dict[str, Any]) -> None:
        for ws in list(self.active):
            try:
                await ws.send_json(data)
            except Exception:  # noqa: BLE001
                self.disconnect(ws)

    def broadcast_threadsafe(self, data: dict[str, Any]) -> None:
        if self.loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(self._send_all(data), self.loop)
            except RuntimeError:
                pass


class App:
    """Mutable holder so the runner can be rebuilt when keys/config change."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.store = Store(self.settings.db_path)
        self.ws = WSManager()
        self.runner = BotRunner(self.settings, self.store, on_update=self.ws.broadcast_threadsafe)

    def rebuild(self) -> None:
        try:
            self.runner.stop()
        except Exception:  # noqa: BLE001
            pass
        self.settings = reload_settings()
        self.runner = BotRunner(self.settings, self.store, on_update=self.ws.broadcast_threadsafe)


state: App | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global state
    state = App()
    state.ws.loop = asyncio.get_event_loop()
    # Fire-and-forget initial reconcile so the dashboard gets data shortly after
    # boot — NOT awaited, so a slow/blocked exchange never delays server bind.
    state.ws.loop.run_in_executor(None, _safe_initial_cycle)
    yield
    if state:
        try:
            state.runner.stop()
        except Exception:  # noqa: BLE001
            pass
        state.store.close()


def _safe_initial_cycle() -> None:
    try:
        state.runner.run_cycle()  # type: ignore[union-attr]
    except Exception as e:  # noqa: BLE001
        print(f"[startup] initial reconcile failed (will retry on Start): {e}")


app = FastAPI(title="Self-Regulating Spot Grid Bot", lifespan=lifespan)


# ----------------------------------------------------------------- API models
class KeysIn(BaseModel):
    mode: str | None = None
    exchange: str | None = None
    symbol: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    api_password: str | None = None
    invest: float | None = None
    grids: int | None = None
    grid_mode: str | None = None
    lower: float | None = None
    upper: float | None = None
    fee_pct: float | None = None
    slip_bps: float | None = None
    cycle_seconds: int | None = None
    band_pct: float | None = None
    vol_pct: float | None = None
    min_fill_rate_per_day: float | None = None
    cooldown_seconds: int | None = None
    max_repositions_per_day: int | None = None
    max_daily_loss: float | None = None
    max_capital: float | None = None
    allow_live: bool | None = None
    use_ai: bool | None = None
    ai_model: str | None = None
    anthropic_api_key: str | None = None
    kline_interval: str | None = None


# ----------------------------------------------------------------- REST
@app.get("/api/status")
def status() -> dict[str, Any]:
    return state.runner.get_snapshot()  # type: ignore[union-attr]


@app.get("/api/config")
def config() -> dict[str, Any]:
    return state.settings.public_dict()  # type: ignore[union-attr]


@app.get("/api/log")
def log(limit: int = 100) -> dict[str, Any]:
    return {"actions": state.store.recent_actions(limit=min(500, max(1, limit)))}  # type: ignore[union-attr]


@app.post("/api/start")
def start() -> dict[str, Any]:
    if state.settings.is_live and not state.settings.allow_live:  # type: ignore[union-attr]
        return JSONResponse({"error": "live mode requires ALLOW_LIVE"}, status_code=400)
    state.runner.start()  # type: ignore[union-attr]
    return {"running": True}


@app.post("/api/stop")
def stop() -> dict[str, Any]:
    state.runner.stop()  # type: ignore[union-attr]
    return {"running": False}


@app.post("/api/panic")
def panic() -> dict[str, Any]:
    return state.runner.panic("manual panic (UI)")  # type: ignore[union-attr]


@app.post("/api/resume")
def resume() -> dict[str, Any]:
    state.runner.resume()  # type: ignore[union-attr]
    return {"halted": False}


@app.post("/api/config/keys")
def set_keys(body: KeysIn) -> dict[str, Any]:
    """Persist config + keys to the server-side .env, then rebuild the runner.

    The browser sends keys here exactly once; they are written to .env (0600) and
    never returned, logged, or stored client-side. Rejects invalid live config
    before applying.
    """
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    # Validate the would-be settings BEFORE writing anything. Settings() reads the
    # current .env for everything not overridden here, so the live gate (allow_live
    # + max_capital) is enforced against the merged result.
    try:
        from .config import Settings
        Settings(**updates)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"invalid config: {e}"}, status_code=400)

    changed = update_env(ENV_PATH, updates)
    state.rebuild()  # type: ignore[union-attr]
    # record which env vars changed — names only, never values
    state.store.log("info", "config", "config updated via setup", {"changed_vars": changed})  # type: ignore[union-attr]
    return {"ok": True, "changed": changed, "config": state.settings.public_dict()}  # type: ignore[union-attr]


# ----------------------------------------------------------------- WebSocket
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await state.ws.connect(ws)  # type: ignore[union-attr]
    try:
        await ws.send_json(state.runner.get_snapshot())  # type: ignore[union-attr]
        while True:
            # keep the socket open; client doesn't need to send anything
            await ws.receive_text()
    except WebSocketDisconnect:
        state.ws.disconnect(ws)  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        state.ws.disconnect(ws)  # type: ignore[union-attr]


# static dashboard (mounted last so /api/* and /ws take precedence)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
