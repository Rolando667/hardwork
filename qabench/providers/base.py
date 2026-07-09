"""Спільні утиліти провайдерів: ретраї, розрахунок вартості, схеми виводу."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx

from core.models import VERDICTS


REQUEST_TIMEOUT = 120.0     # с на запит
MAX_RETRIES = 2             # до 2 ретраїв на 429/5xx
RETRYABLE_STATUS = {429, 500, 502, 503, 504, 529}


class ApiError(Exception):
    """Помилка виклику API з коротким текстом для клітинки."""


async def post_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> httpx.Response:
    """POST з експоненційними ретраями на 429/5xx. Підіймає ApiError при вичерпанні."""
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await client.post(
                url,
                headers=headers,
                params=params,
                json=json_body,
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.TimeoutException as exc:
            last_exc = ApiError("таймаут запиту")
            # Таймаут ретраїмо як тимчасову помилку.
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
                continue
            raise last_exc from exc
        except httpx.HTTPError as exc:
            raise ApiError(f"мережа: {exc}") from exc

        if resp.status_code in RETRYABLE_STATUS and attempt < MAX_RETRIES:
            await asyncio.sleep(2 ** attempt)
            continue
        if resp.status_code >= 400:
            raise ApiError(_extract_error(resp))
        return resp

    # Недосяжно, але про всяк випадок.
    raise last_exc or ApiError("невідома помилка")


def _extract_error(resp: httpx.Response) -> str:
    """Витягти читабельний текст помилки з відповіді провайдера."""
    try:
        data = resp.json()
    except ValueError:  # включає json.JSONDecodeError
        return f"HTTP {resp.status_code}: {resp.text[:300]}"
    # Anthropic / OpenAI: {"error": {"message": ...}}; Gemini: {"error": {"message": ...}}
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return f"HTTP {resp.status_code}: {err['message']}"
        if isinstance(err, str):
            return f"HTTP {resp.status_code}: {err}"
    return f"HTTP {resp.status_code}: {resp.text[:300]}"


def compute_cost(
    tokens_in: Optional[int],
    tokens_out: Optional[int],
    price_in: float,
    price_out: float,
) -> Optional[float]:
    """Вартість виклику = input×ціна_входу/1e6 + output×ціна_виходу/1e6.

    Якщо usage відсутній (немає обох значень) — повертає None (прочерк).
    """
    if tokens_in is None and tokens_out is None:
        return None
    ti = tokens_in or 0
    to = tokens_out or 0
    return ti * price_in / 1_000_000 + to * price_out / 1_000_000


# JSON-схема статусу для структурованого виводу (OpenAI / Gemini).
def status_enum() -> list:
    return list(VERDICTS)
