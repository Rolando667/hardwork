"""Абстракція рівнів роздумів: трансляція універсального рівня у значення провайдера.

Користувач обирає універсальний рівень (none/minimal/low/medium/high). Перед
викликом рівень транслюється у параметр провайдера згідно з типом, указаним у
моделі, і згідно з мапінгом у reasoning_map.json.
"""
from __future__ import annotations

from typing import Any, Dict


# Сентинел, що означає «ключ відсутній у мапінгу» (на відміну від None = «не передавати»).
_MISSING = object()


def resolve(reasoning_type: str, level: str, reasoning_map: Dict[str, Any]) -> Any:
    """Повернути значення параметра роздумів для типу і рівня.

    Повертає:
        None  — параметр не передавати (thinking вимкнено / рівень «none»);
        int   — числовий бюджет (thinkingBudget / budget_tokens);
        str   — рядковий рівень зусиль (effort / thinkingLevel);
    Якщо тип чи рівень відсутній у мапінгу — трактуємо як None (не передавати).
    """
    if reasoning_type == "none":
        return None
    table = reasoning_map.get(reasoning_type, {})
    value = table.get(level, _MISSING)
    if value is _MISSING:
        return None
    return value
