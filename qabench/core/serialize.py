"""Серіалізація повного прогону (конфігурація + усі сирі відповіді + мітка часу)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from .models import Dialog, ModelConfig, RunCell


def runcell_to_dict(cell: RunCell) -> Dict[str, Any]:
    return {
        "dialog_id": cell.dialog_id,
        "model_id": cell.model_id,
        "level": cell.level,
        "repeat_index": cell.repeat_index,
        "status": cell.status,
        "comment": cell.comment,
        "raw": cell.raw,
        "tokens_in": cell.tokens_in,
        "tokens_out": cell.tokens_out,
        "cost": cell.cost,
        "seconds": cell.seconds,
        "error": cell.error,
        "translation": cell.translation,
    }


def runcell_from_dict(d: Dict[str, Any]) -> RunCell:
    return RunCell(
        dialog_id=d.get("dialog_id", ""),
        model_id=d.get("model_id", ""),
        level=d.get("level", ""),
        repeat_index=int(d.get("repeat_index", 0)),
        status=d.get("status"),
        comment=d.get("comment", ""),
        raw=d.get("raw", ""),
        tokens_in=d.get("tokens_in"),
        tokens_out=d.get("tokens_out"),
        cost=d.get("cost"),
        seconds=float(d.get("seconds", 0.0) or 0.0),
        error=d.get("error"),
        translation=d.get("translation", ""),
    )


def build_run_payload(
    *,
    models: List[ModelConfig],
    prompt_name: str,
    prompt_text: str,
    dialogs: List[Dialog],
    levels: List[str],
    repeats: int,
    parallel: int,
    results: List[RunCell],
) -> Dict[str, Any]:
    """Скласти повний JSON-об'єкт прогону для збереження в results/."""
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "prompt_name": prompt_name,
        "prompt_text": prompt_text,
        "levels": list(levels),
        "repeats": repeats,
        "parallel": parallel,
        "models": [m.to_dict() for m in models],
        "dialogs": [d.to_dict() for d in dialogs],
        "results": [runcell_to_dict(c) for c in results],
    }


def parse_run_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Розібрати збережений прогін у зручні структури."""
    models = [ModelConfig.from_dict(m) for m in payload.get("models", [])]
    dialogs = [Dialog.from_dict(d) for d in payload.get("dialogs", [])]
    results = [runcell_from_dict(r) for r in payload.get("results", [])]
    return {
        "timestamp": payload.get("timestamp", ""),
        "prompt_name": payload.get("prompt_name", ""),
        "prompt_text": payload.get("prompt_text", ""),
        "levels": payload.get("levels", []),
        "repeats": payload.get("repeats", 1),
        "parallel": payload.get("parallel", 2),
        "models": models,
        "dialogs": dialogs,
        "results": results,
    }
