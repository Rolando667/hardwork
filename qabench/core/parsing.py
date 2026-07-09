"""Парсинг відповіді моделі у структуру {status, comment}.

Очікуваний формат: {"status": "...", "comment": "..."}, де status ∈ VERDICTS.
Алгоритм: зрізати кодові обгортки і префікси → json.loads → валідація enum.
"""
from __future__ import annotations

import json
import re
from typing import Tuple

from .models import VERDICTS


class ParseError(Exception):
    """Не вдалося розпарсити або провалідувати відповідь."""


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _strip_wrappers(text: str) -> str:
    """Зрізати ```json ... ``` обгортки та зайві префікси, залишити JSON-об'єкт."""
    t = text.strip()
    # Прибрати кодові огорожі на початку/кінці.
    t = _FENCE_RE.sub("", t)
    t = t.strip()
    # Якщо навколо JSON є текст — вирізати перший збалансований {...} блок.
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start : end + 1]
    return t.strip()


def parse_response(text: str) -> Tuple[str, str]:
    """Повернути (status, comment) або підняти ParseError.

    status гарантовано входить у VERDICTS.
    """
    if text is None:
        raise ParseError("порожня відповідь")
    candidate = _strip_wrappers(text)
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ParseError(f"не JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError("відповідь не є об'єктом JSON")
    status = data.get("status")
    comment = data.get("comment", "")
    if not isinstance(status, str):
        raise ParseError("відсутнє поле status")
    status = status.strip()
    if status not in VERDICTS:
        raise ParseError(f"невідомий status: {status!r}")
    if not isinstance(comment, str):
        comment = str(comment)
    return status, comment
