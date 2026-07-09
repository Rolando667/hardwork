"""Шляхи зберігання даних, завантаження та збереження config.json і reasoning_map.json.

Усі дані застосунку зберігаються в %APPDATA%\\QABench\\ на Windows.
На інших ОС (для розробки) використовується домашня тека користувача.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict


APP_NAME = "QABench"


def data_dir() -> Path:
    """Кореневу теку даних застосунку (%APPDATA%\\QABench на Windows)."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / APP_NAME
    else:
        # Резерв для не-Windows середовищ (розробка/тестування).
        base = Path.home() / ".qabench"
    return base


def prompts_dir() -> Path:
    return data_dir() / "prompts"


def dialogs_dir() -> Path:
    return data_dir() / "dialogs"


def results_dir() -> Path:
    return data_dir() / "results"


def config_path() -> Path:
    return data_dir() / "config.json"


def reasoning_map_path() -> Path:
    return data_dir() / "reasoning_map.json"


# Дефолтний мапінг універсальних рівнів роздумів у параметри провайдерів.
# Користувач може редагувати reasoning_map.json вручну без зміни коду.
DEFAULT_REASONING_MAP: Dict[str, Dict[str, Any]] = {
    "anthropic_thinking_budget": {
        "none": None,
        "minimal": 1024,
        "low": 1024,
        "medium": 8192,
        "high": 24576,
    },
    "anthropic_adaptive_effort": {
        "none": None,
        "minimal": "low",
        "low": "low",
        "medium": "medium",
        "high": "high",
    },
    "gemini_thinking_budget": {
        "none": 0,
        "minimal": 1024,
        "low": 1024,
        "medium": 8192,
        "high": 24576,
    },
    "gemini_thinking_level": {
        "none": None,
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
    },
    "openai_reasoning_effort": {
        "none": "minimal",
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
    },
}


DEFAULT_CONFIG: Dict[str, Any] = {
    "models": [],
    "proxy": "",
    "last_selection": {
        "models": [],
        "levels": ["low", "medium"],
        "dialogs": [],
        "prompt": "",
        "repeats": 1,
        "parallel": 2,
    },
}


def ensure_dirs() -> None:
    """Створити всі потрібні теки даних, якщо їх ще немає."""
    for d in (data_dir(), prompts_dir(), dialogs_dir(), results_dir()):
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    ensure_dirs()
    path = config_path()
    if not path.exists():
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Пошкоджений конфіг — робимо резервну копію і повертаємо дефолт.
        try:
            shutil.copy(path, path.with_suffix(".json.bak"))
        except OSError:
            pass
        return json.loads(json.dumps(DEFAULT_CONFIG))
    # Доповнити відсутні ключі дефолтами.
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    merged.update(data)
    ls = json.loads(json.dumps(DEFAULT_CONFIG["last_selection"]))
    ls.update(data.get("last_selection", {}))
    merged["last_selection"] = ls
    return merged


def save_config(config: Dict[str, Any]) -> None:
    ensure_dirs()
    tmp = config_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(config_path())


def load_reasoning_map() -> Dict[str, Any]:
    ensure_dirs()
    path = reasoning_map_path()
    if not path.exists():
        save_reasoning_map(DEFAULT_REASONING_MAP)
        return json.loads(json.dumps(DEFAULT_REASONING_MAP))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_REASONING_MAP))
    # Доповнити відсутні типи дефолтами, щоб уникнути KeyError.
    merged = json.loads(json.dumps(DEFAULT_REASONING_MAP))
    for key, value in data.items():
        merged[key] = value
    return merged


def save_reasoning_map(rmap: Dict[str, Any]) -> None:
    ensure_dirs()
    reasoning_map_path().write_text(
        json.dumps(rmap, ensure_ascii=False, indent=2), encoding="utf-8"
    )
