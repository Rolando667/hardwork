"""Провайдер Anthropic (Messages API).

POST https://api.anthropic.com/v1/messages
Заголовки x-api-key та anthropic-version: 2023-06-01.
system = промт; messages = [{role: user, content: транскрипт}].
Структурований вихід забезпечується інструкцією у промті; парсер зрізає обгортки.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

from core import reasoning
from core.models import ModelConfig, RunCell
from core.parsing import ParseError, parse_response

from .base import ApiError, compute_cost, post_with_retries

URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Інструкція для структурованого JSON-виводу (додається до системного промта).
_JSON_INSTRUCTION = (
    "\n\nВІДПОВІДАЙ ВИКЛЮЧНО валідним JSON без будь-якого додаткового тексту, "
    'у форматі: {"status": "<Відповідає стандарту | Не відповідає стандарту | '
    'Неможливо оцінити>", "comment": "<стислий коментар українською>"}'
)


def _build_body(
    model: ModelConfig,
    prompt_text: str,
    transcript: str,
    level: str,
    reasoning_map: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    """Побудувати тіло запиту і рядок-опис трансляції рівня роздумів."""
    max_tokens = int(model.max_tokens or 4096)
    body: Dict[str, Any] = {
        "model": model.model_id,
        "system": (prompt_text or "") + _JSON_INSTRUCTION,
        "messages": [{"role": "user", "content": transcript}],
    }

    thinking_active = False
    label = f"{level} → без роздумів"

    value = reasoning.resolve(model.reasoning_type, level, reasoning_map)

    if model.reasoning_type == "anthropic_thinking_budget":
        # Claude 4.5 і старіші; на 4.6 застаріло, але працює.
        if value:
            budget = int(value)
            # Обмеження Anthropic: бюджет 1–1023 недопустимий.
            if 0 < budget < 1024:
                budget = 1024
            # max_tokens має бути більшим за budget_tokens.
            if max_tokens <= budget:
                max_tokens = budget + 2048
            body["thinking"] = {"type": "enabled", "budget_tokens": budget}
            thinking_active = True
            label = f"{level} → thinking budget {budget}"
        else:
            label = f"{level} → thinking не передавати"
    elif model.reasoning_type == "anthropic_adaptive_effort":
        # Claude 4.6 і новіші: type:"adaptive" + рівень effort.
        if value:
            body["thinking"] = {"type": "adaptive"}
            body["output_config"] = {"effort": str(value)}
            thinking_active = True
            label = f"{level} → adaptive effort {value}"
        else:
            label = f"{level} → thinking не передавати"

    body["max_tokens"] = max_tokens

    # Температуру не передаємо разом із thinking (на 4.7+ це помилка 400).
    if not thinking_active and model.temperature is not None:
        body["temperature"] = model.temperature

    return body, label


def _extract_text(data: Dict[str, Any]) -> str:
    blocks: List[Dict[str, Any]] = data.get("content", []) or []
    parts: List[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


async def call(
    client: httpx.AsyncClient,
    model: ModelConfig,
    prompt_text: str,
    transcript: str,
    level: str,
    reasoning_map: Dict[str, Any],
    *,
    dialog_id: str,
    repeat_index: int,
) -> RunCell:
    cell = RunCell(
        dialog_id=dialog_id,
        model_id=model.id,
        level=level,
        repeat_index=repeat_index,
    )
    body, label = _build_body(model, prompt_text, transcript, level, reasoning_map)
    cell.translation = label

    headers = {
        "x-api-key": model.api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    started = time.monotonic()
    try:
        resp = await post_with_retries(client, URL, headers=headers, json_body=body)
        data = resp.json()
    except ApiError as exc:
        cell.seconds = time.monotonic() - started
        cell.error = str(exc)
        return cell
    except ValueError as exc:  # невалідний JSON відповіді
        cell.seconds = time.monotonic() - started
        cell.error = f"невалідна відповідь: {exc}"
        return cell

    cell.seconds = time.monotonic() - started

    usage = data.get("usage", {}) or {}
    cell.tokens_in = usage.get("input_tokens")
    # У Anthropic thinking-токени вже входять у output_tokens.
    cell.tokens_out = usage.get("output_tokens")
    cell.cost = compute_cost(
        cell.tokens_in, cell.tokens_out, model.price_in, model.price_out
    )

    raw = _extract_text(data)
    cell.raw = raw
    try:
        status, comment = parse_response(raw)
        cell.status = status
        cell.comment = comment
    except ParseError as exc:
        cell.error = f"парсинг: {exc}"
    return cell
