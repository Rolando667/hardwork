"""Провайдер OpenAI (Chat Completions).

POST https://api.openai.com/v1/chat/completions
response_format типу json_schema з enum статусу (status/comment).
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

from core import reasoning
from core.models import ModelConfig, RunCell
from core.parsing import ParseError, parse_response

from .base import ApiError, compute_cost, post_with_retries, status_enum

URL = "https://api.openai.com/v1/chat/completions"


def _response_format() -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "qa_verdict",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": status_enum()},
                    "comment": {"type": "string"},
                },
                "required": ["status", "comment"],
                "additionalProperties": False,
            },
        },
    }


def _build_body(
    model: ModelConfig,
    prompt_text: str,
    transcript: str,
    level: str,
    reasoning_map: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    body: Dict[str, Any] = {
        "model": model.model_id,
        "messages": [
            {"role": "system", "content": prompt_text or ""},
            {"role": "user", "content": transcript},
        ],
        "response_format": _response_format(),
        # max_completion_tokens підтримується як для reasoning-, так і для
        # звичайних моделей Chat Completions.
        "max_completion_tokens": int(model.max_tokens or 4096),
    }

    label = f"{level} → без роздумів"
    reasoning_active = False
    value = reasoning.resolve(model.reasoning_type, level, reasoning_map)

    if model.reasoning_type == "openai_reasoning_effort":
        effort = str(value) if value else "minimal"  # none → minimal
        body["reasoning_effort"] = effort
        reasoning_active = True
        label = f"{level} → reasoning_effort {effort}"

    # reasoning-моделі не приймають температуру, відмінну від дефолтної.
    if not reasoning_active and model.temperature is not None:
        body["temperature"] = model.temperature

    return body, label


def _extract_text(data: Dict[str, Any]) -> str:
    choices: List[Dict[str, Any]] = data.get("choices", []) or []
    if not choices:
        return ""
    message = choices[0].get("message", {}) or {}
    content = message.get("content", "")
    if isinstance(content, list):
        # Деякі відповіді повертають список частин.
        parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        return "".join(parts)
    return content or ""


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
        "Authorization": f"Bearer {model.api_key}",
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
    except ValueError as exc:
        cell.seconds = time.monotonic() - started
        cell.error = f"невалідна відповідь: {exc}"
        return cell

    cell.seconds = time.monotonic() - started

    usage = data.get("usage", {}) or {}
    cell.tokens_in = usage.get("prompt_tokens")
    # completion_tokens включає reasoning-токени для reasoning-моделей.
    cell.tokens_out = usage.get("completion_tokens")
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
