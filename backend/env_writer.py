"""
Server-side .env writer for the setup flow.

The UI posts config (and, once, the API keys) to the backend; we persist them to
the local ``.env`` so they load on the next startup and never live in the
browser. Only a curated allow-list of keys is writable, secrets are written with
0600 perms, and nothing here ever logs a secret value.
"""
from __future__ import annotations

import os
from typing import Any

# field name -> .env variable (upper-case). Curated allow-list.
WRITABLE: dict[str, str] = {
    "mode": "MODE",
    "exchange": "EXCHANGE",
    "symbol": "SYMBOL",
    "api_key": "API_KEY",
    "api_secret": "API_SECRET",
    "api_password": "API_PASSWORD",
    "invest": "INVEST",
    "grids": "GRIDS",
    "grid_mode": "GRID_MODE",
    "lower": "LOWER",
    "upper": "UPPER",
    "fee_pct": "FEE_PCT",
    "slip_bps": "SLIP_BPS",
    "cycle_seconds": "CYCLE_SECONDS",
    "band_pct": "BAND_PCT",
    "vol_pct": "VOL_PCT",
    "min_fill_rate_per_day": "MIN_FILL_RATE_PER_DAY",
    "cooldown_seconds": "COOLDOWN_SECONDS",
    "max_repositions_per_day": "MAX_REPOSITIONS_PER_DAY",
    "max_daily_loss": "MAX_DAILY_LOSS",
    "max_capital": "MAX_CAPITAL",
    "allow_live": "ALLOW_LIVE",
    "use_ai": "USE_AI",
    "ai_model": "AI_MODEL",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "kline_interval": "KLINE_INTERVAL",
}

SECRET_FIELDS = {"api_key", "api_secret", "api_password", "anthropic_api_key"}


def _read_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v
    return env


def update_env(path: str, updates: dict[str, Any]) -> list[str]:
    """Merge ``updates`` (field-name keyed) into ``path``. Returns changed env vars
    (secret values are never returned, only the variable names)."""
    env = _read_env(path)
    changed: list[str] = []
    for field, value in updates.items():
        if field not in WRITABLE:
            continue
        if value is None:
            continue
        var = WRITABLE[field]
        if isinstance(value, bool):
            sval = "true" if value else "false"
        else:
            sval = str(value)
        # don't blow away an existing secret with an empty submission
        if field in SECRET_FIELDS and sval == "":
            continue
        env[var] = sval
        changed.append(var)

    lines = [f"{k}={v}" for k, v in env.items()]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return changed
