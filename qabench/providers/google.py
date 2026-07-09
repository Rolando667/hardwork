"""Провайдер Google Gemini (generateContent).

POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=...
systemInstruction = промт; contents = транскрипт.
generationConfig.responseMimeType = "application/json" + responseSchema для чистого JSON.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

from core import reasoning
from core.models import ModelConfig, RunCell
from core.parsing import ParseError, parse_response

from .base import ApiError, compute_cost, post_with_retries, status_enum

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _response_schema() -> Dict[str, Any]:
    return {
        "type": "OBJECT",
        "properties": {
            "status": {"type": "STRING", "enum": status_enum()},
            "comment": {"type": "STRING"},
        },
        "required": ["status", "comment"],
    }


def _build_body(
    model: ModelConfig,
    prompt_text: str,
    transcript: str,
    level: str,
    reasoning_map: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    generation_config: Dict[str, Any] = {
        "responseMimeType": "application/json",
        "responseSchema": _response_schema(),
        "maxOutputTokens": int(model.max_tokens or 4096),
    }
    if model.temperature is not None:
        generation_config["temperature"] = model.temperature

    label = f"{level} → без роздумів"
    value = reasoning.resolve(model.reasoning_type, level, reasoning_map)

    if model.reasoning_type == "gemini_thinking_budget":
        # Gemini 2.5: thinkingBudget. thinkingLevel на 2.5 не передавати.
        budget = 0 if value is None else int(value)
        generation_config["thinkingConfig"] = {"thinkingBudget": budget}
        label = f"{level} → thinkingBudget {budget}"
    elif model.reasoning_type == "gemini_thinking_level":
        # Gemini 3+: thinkingLevel. НІКОЛИ не передавати разом із thinkingBudget.
        if value:
            generation_config["thinkingConfig"] = {"thinkingLevel": str(value)}
            label = f"{level} → thinkingLevel {value}"
        else:
            label = f"{level} → thinkingConfig не передавати"

    body: Dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": prompt_text or ""}]},
        "contents": [{"role": "user", "parts": [{"text": transcript}]}],
        "generationConfig": generation_config,
    }
    return body, label


def _extract_text(data: Dict[str, Any]) -> str:
    candidates: List[Dict[str, Any]] = data.get("candidates", []) or []
    if not candidates:
        return ""
    content = candidates[0].get("content", {}) or {}
    parts = content.get("parts", []) or []
    out: List[str] = []
    for part in parts:
        if isinstance(part, dict) and "text" in part:
            out.append(part.get("text", ""))
    return "".join(out)


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

    url = f"{BASE_URL}/{model.model_id}:generateContent"
    headers = {"content-type": "application/json"}
    params = {"key": model.api_key}

    started = time.monotonic()
    try:
        resp = await post_with_retries(
            client, url, headers=headers, params=params, json_body=body
        )
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

    usage = data.get("usageMetadata", {}) or {}
    cell.tokens_in = usage.get("promptTokenCount")
    candidates_tokens = usage.get("candidatesTokenCount") or 0
    # У Gemini thoughtsTokenCount додається до output при розрахунку.
    thoughts_tokens = usage.get("thoughtsTokenCount") or 0
    if usage.get("candidatesTokenCount") is None and not thoughts_tokens:
        cell.tokens_out = None
    else:
        cell.tokens_out = candidates_tokens + thoughts_tokens
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
