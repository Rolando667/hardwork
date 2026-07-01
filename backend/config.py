"""
Configuration — loaded server-side only from the environment / ``.env``.

Exchange API keys live here and never leave the backend. The frontend never
receives them (see the UI/setup flow). On import we validate the operating mode
and, for ``live``, enforce an explicit opt-in flag plus a capital cap. The
withdrawal-scope refusal is enforced at exchange-connect time (see
``exchange/adapter.py``) because that requires talking to the exchange.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(str, Enum):
    DRY_RUN = "dry_run"   # compute + log decisions, place nothing
    TESTNET = "testnet"   # trade on the exchange sandbox with fake funds
    LIVE = "live"         # real funds — gated behind allow_live + max_capital


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- operating mode ----
    mode: Mode = Mode.DRY_RUN
    allow_live: bool = False               # must be explicitly true to run live
    max_capital: float = 0.0               # hard cap on deployed quote capital (required for live)

    # ---- exchange ----
    exchange: str = "binance"              # any ccxt exchange id
    symbol: str = "SOL/USDT"
    api_key: SecretStr = SecretStr("")
    api_secret: SecretStr = SecretStr("")
    api_password: SecretStr = SecretStr("")  # some exchanges (okx, kucoin) need a passphrase

    # ---- grid strategy defaults (same params as the calculator) ----
    invest: float = 1000.0                 # quote investment for the grid
    grids: int = 20
    grid_mode: str = "geometric"           # geometric | arithmetic
    lower: float = 0.0                     # 0 => auto-range around current price on first deploy
    upper: float = 0.0
    fee_pct: float = 0.1                   # per-fill taker/maker fee in percent
    slip_bps: float = 2.0                  # per-fill slippage/spread in basis points
    auto_range_pct: float = 0.25           # +/- band around price used when lower/upper are auto

    # ---- decision engine cadence + hysteresis (no-trade band) ----
    cycle_seconds: int = 300               # 1..15 min typical
    band_pct: float = 0.5                  # reposition if price leaves range by > this fraction of a grid step
    vol_pct: float = 0.5                   # reposition if ATR% shifts by > this fraction vs when grid was set
    min_fill_rate_per_day: float = 1.0     # reposition if realised fill-rate drops below this (grid idle)
    fill_rate_grace_hours: float = 6.0     # don't judge fill-rate until the grid has been live this long
    reject_overfit: bool = True            # reject candidates whose OOS walk-forward result is poor

    # ---- throttle ----
    cooldown_seconds: int = 3600           # min seconds between repositions
    max_repositions_per_day: int = 6

    # ---- safety ----
    max_daily_loss: float = 50.0           # stop + alert if realised+floating PnL breaches -this (quote)

    # ---- klines / history used for metrics & validation ----
    kline_interval: str = "1h"             # ccxt timeframe for the metrics dataset
    history_candles: int = 500             # how many candles to pull each cycle

    # ---- optional AI advisor (OFF by default) ----
    use_ai: bool = False
    ai_model: str = "claude-haiku-4-5"     # cheap by design; any Claude model id works
    ai_cadence_cycles: int = 4             # consult the advisor every N cycles
    anthropic_api_key: SecretStr = SecretStr("")
    ai_max_param_nudge_pct: float = 0.15   # AI tweaks are clamped to +/- this fraction of a value

    # ---- server / storage ----
    host: str = "127.0.0.1"
    port: int = 8000
    db_path: str = "gridbot.db"
    # Optional shared secret for the control API. When set, state-changing
    # endpoints (start/stop/panic/resume/keys) require an X-Auth-Token header.
    # Strongly recommended if you bind the server to anything but localhost.
    dashboard_token: SecretStr = SecretStr("")

    @field_validator("grid_mode")
    @classmethod
    def _mode_ok(cls, v: str) -> str:
        if v not in ("geometric", "arithmetic"):
            raise ValueError("grid_mode must be 'geometric' or 'arithmetic'")
        return v

    @model_validator(mode="after")
    def _check_live_gate(self) -> "Settings":
        # live must be opt-in AND have a positive capital cap — refuse otherwise.
        if self.mode == Mode.LIVE:
            if not self.allow_live:
                raise ValueError(
                    "Refusing to start in live mode without ALLOW_LIVE=true. "
                    "Live trades real funds — set it explicitly."
                )
            if self.max_capital <= 0:
                raise ValueError(
                    "Refusing to start in live mode without a positive MAX_CAPITAL cap."
                )
            if self.invest > self.max_capital:
                raise ValueError(
                    f"INVEST ({self.invest}) exceeds MAX_CAPITAL ({self.max_capital})."
                )
        return self

    # ---- helpers (never log secret values) ----
    @property
    def is_live(self) -> bool:
        return self.mode == Mode.LIVE

    @property
    def is_dry_run(self) -> bool:
        return self.mode == Mode.DRY_RUN

    @property
    def base_asset(self) -> str:
        return self.symbol.split("/")[0]

    @property
    def quote_asset(self) -> str:
        return self.symbol.split("/")[1]

    def grid_params(self) -> dict[str, Any]:
        """Engine param dict (snake_case keys consumed by backend.strategy)."""
        return {
            "lower": self.lower,
            "upper": self.upper,
            "grids": self.grids,
            "mode": self.grid_mode,
            "invest": self.invest,
            "fee": self.fee_pct,
            "slip_bps": self.slip_bps,
            "entry": 0,
            "sell_all_on_stop": True,
        }

    def public_dict(self) -> dict[str, Any]:
        """Config safe to expose to the UI — NO secrets."""
        return {
            "mode": self.mode.value,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "invest": self.invest,
            "grids": self.grids,
            "grid_mode": self.grid_mode,
            "lower": self.lower,
            "upper": self.upper,
            "fee_pct": self.fee_pct,
            "slip_bps": self.slip_bps,
            "cycle_seconds": self.cycle_seconds,
            "band_pct": self.band_pct,
            "vol_pct": self.vol_pct,
            "min_fill_rate_per_day": self.min_fill_rate_per_day,
            "cooldown_seconds": self.cooldown_seconds,
            "max_repositions_per_day": self.max_repositions_per_day,
            "max_daily_loss": self.max_daily_loss,
            "max_capital": self.max_capital,
            "allow_live": self.allow_live,
            "kline_interval": self.kline_interval,
            "use_ai": self.use_ai,
            "ai_model": self.ai_model if self.use_ai else None,
            "has_keys": bool(self.api_key.get_secret_value() and self.api_secret.get_secret_value()),
            "auth_required": bool(self.dashboard_token.get_secret_value()),
        }


_settings: Settings | None = None


def get_settings() -> Settings:
    """Process-wide singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Re-read the environment / .env (used after the setup form writes keys)."""
    global _settings
    _settings = Settings()
    return _settings
