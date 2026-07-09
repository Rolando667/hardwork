"""Спільні шляхи застосунку (крос-платформенно, з пріоритетом на Windows).

Усі дані програми зберігаються в теці:
    Windows:  %APPDATA%\\TelegramAgentManager
    Linux/Mac: ~/.config/TelegramAgentManager  (fallback для розробки)
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "TelegramAgentManager"


def app_data_dir() -> Path:
    """Повертає базову теку для даних застосунку, створюючи її за потреби."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        # Розробка на Linux/Mac — зберігаємо у ~/.config
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config"
        )
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return app_data_dir() / "config.db"


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
