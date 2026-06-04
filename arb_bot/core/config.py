"""Load and validate config.yaml (+ .env) into typed config dataclasses.

Nothing in the codebase hardcodes a threshold — it all flows from here. The
small, focused config dataclasses are passed into the pure engines (fees,
sizing) so those stay free of YAML/dict access.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class MarketConfig:
    type: str = "swap"
    contract: str = "linear"
    settle: str = "USDT"


@dataclass(frozen=True)
class UniverseConfig:
    top_n: int = 20
    min_quote_volume_24h: float = 1_000_000.0
    recalc_each_loop: bool = True


@dataclass(frozen=True)
class ThresholdsConfig:
    entry_net_spread_bps: float = 35.0


@dataclass(frozen=True)
class SizingConfig:
    target_notional_quote: float = 100.0
    residual_tolerance_frac: float = 0.01


@dataclass(frozen=True)
class FeesConfig:
    taker_only: bool = True
    slippage_bps: float = 5.0
    count_exit_crossing: bool = True
    capital_cost_annual_bps: float = 1000.0
    expected_hold_hours: float = 8.0
    funding_horizon_hours: float = 8.0
    default_funding_interval_hours: float = 8.0
    # exchange -> {"maker": float, "taker": float}
    overrides: dict[str, dict[str, float]] = field(default_factory=dict)

    def fee_override(self, exchange: str) -> dict[str, float] | None:
        return self.overrides.get(exchange)


@dataclass(frozen=True)
class RuntimeConfig:
    loop: bool = True
    loop_interval_seconds: float = 30.0
    request_timeout_ms: int = 15000
    log_level: str = "INFO"


@dataclass(frozen=True)
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8000


@dataclass(frozen=True)
class Config:
    phase: str
    strategy: str
    exchanges: list[str]
    market: MarketConfig
    universe: UniverseConfig
    thresholds: ThresholdsConfig
    sizing: SizingConfig
    fees: FeesConfig
    runtime: RuntimeConfig
    web: WebConfig


def load_config(path: str | Path = "config.yaml") -> Config:
    """Read config.yaml, overlay environment, and validate into a Config."""
    # .env is loaded for later phases; P0 needs no keys but loading is harmless.
    load_dotenv()

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")

    raw = yaml.safe_load(path.read_text()) or {}

    exchanges = [str(e).lower() for e in raw.get("exchanges", [])]
    if len(exchanges) < 2:
        raise ValueError(
            "config 'exchanges' must list at least 2 exchanges (arbitrage needs >=2 venues)"
        )

    market = MarketConfig(**_section(raw, "market"))
    if market.contract != "linear":
        raise ValueError("P0 supports linear contracts only; set market.contract: linear")

    fees_raw = _section(raw, "fees")
    overrides = {str(k).lower(): dict(v) for k, v in (fees_raw.pop("overrides", {}) or {}).items()}
    fees = FeesConfig(overrides=overrides, **fees_raw)

    cfg = Config(
        phase=str(raw.get("phase", "p0")),
        strategy=str(raw.get("strategy", "cross_exchange_spread")),
        exchanges=exchanges,
        market=market,
        universe=UniverseConfig(**_section(raw, "universe")),
        thresholds=ThresholdsConfig(**_section(raw, "thresholds")),
        sizing=SizingConfig(**_section(raw, "sizing")),
        fees=fees,
        runtime=RuntimeConfig(**_section(raw, "runtime")),
        web=WebConfig(**_section(raw, "web")),
    )

    # Allow env to override the log level for quick debugging without editing yaml.
    env_level = os.getenv("LOG_LEVEL")
    if env_level:
        cfg = Config(**{**cfg.__dict__, "runtime": RuntimeConfig(
            **{**cfg.runtime.__dict__, "log_level": env_level})})

    return cfg


def _section(raw: dict, key: str) -> dict:
    """Return a config subsection as a plain dict (empty if absent)."""
    value = raw.get(key) or {}
    if not isinstance(value, dict):
        raise ValueError(f"config section '{key}' must be a mapping")
    return dict(value)
