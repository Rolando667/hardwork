"""Файлове зберігання промтів (.txt), діалогів (.json) та прогонів (results/*.json)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from . import config
from .models import Dialog, Prompt


_SAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str) -> str:
    """Прибрати недопустимі для імені файлу символи."""
    cleaned = _SAFE_RE.sub("_", name).strip().strip(".")
    return cleaned or "untitled"


# ---------------- Промти ----------------

def list_prompts() -> List[Prompt]:
    config.ensure_dirs()
    result: List[Prompt] = []
    for path in sorted(config.prompts_dir().glob("*.txt")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        result.append(Prompt(name=path.stem, text=text))
    return result


def save_prompt(name: str, text: str) -> str:
    """Зберегти промт у prompts/<name>.txt. Повертає фактичне ім'я (stem)."""
    config.ensure_dirs()
    stem = safe_filename(name)
    path = config.prompts_dir() / f"{stem}.txt"
    path.write_text(text, encoding="utf-8")
    return stem


def delete_prompt(name: str) -> None:
    path = config.prompts_dir() / f"{safe_filename(name)}.txt"
    if path.exists():
        path.unlink()


def rename_prompt(old_name: str, new_name: str, text: str) -> str:
    new_stem = save_prompt(new_name, text)
    if safe_filename(old_name) != new_stem:
        delete_prompt(old_name)
    return new_stem


# ---------------- Діалоги ----------------

def list_dialogs() -> List[Dialog]:
    config.ensure_dirs()
    result: List[Dialog] = []
    for path in sorted(config.dialogs_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        result.append(Dialog.from_dict(data))
    return result


def save_dialog(dialog: Dialog) -> None:
    config.ensure_dirs()
    path = config.dialogs_dir() / f"{dialog.id}.json"
    path.write_text(
        json.dumps(dialog.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def delete_dialog(dialog_id: str) -> None:
    path = config.dialogs_dir() / f"{dialog_id}.json"
    if path.exists():
        path.unlink()


# ---------------- Прогони (results) ----------------

def save_run(payload: Dict[str, Any], label: str = "") -> Path:
    """Зберегти повний прогін у results/*.json. Повертає шлях до файлу."""
    config.ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{safe_filename(label)}" if label else ""
    path = config.results_dir() / f"run_{ts}{suffix}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load_run(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
