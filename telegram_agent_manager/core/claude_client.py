"""Клієнт Claude API (офіційний anthropic SDK) з ретраями та підтримкою проксі.

- 401 → AuthenticationError (піднімається вгору, агент іде у стан «помилка»)
- 429 / 529 / перевантаження → повторна спроба з експоненційною затримкою (макс. 3)
- Підтримка HTTP/SOCKS5 проксі через httpx
"""
from __future__ import annotations

import asyncio
from typing import Optional

import anthropic
import httpx


class ClaudeClient:
    """Асинхронна обгортка над anthropic.AsyncAnthropic."""

    MAX_RETRIES = 3

    def __init__(self, api_key: str, proxy: Optional[str] = None) -> None:
        self._api_key = api_key
        http_client = None
        if proxy:
            # httpx приймає http://, socks5:// тощо
            http_client = httpx.AsyncClient(proxy=proxy, timeout=60.0)
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            http_client=http_client,
            max_retries=0,  # ретраї реалізуємо самі, щоб логувати їх
        )

    async def complete(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Виконує запит до Claude і повертає текст відповіді.

        `messages` — список {"role": "user"/"assistant", "content": "..."}.
        """
        # Anthropic вимагає, щоб перше повідомлення було від "user"
        while messages and messages[0].get("role") != "user":
            messages = messages[1:]
        if not messages:
            return "(порожнє повідомлення)"

        attempt = 0
        last_exc: Optional[BaseException] = None
        while attempt < self.MAX_RETRIES:
            try:
                resp = await self._client.messages.create(
                    model=model,
                    system=system_prompt or "",
                    messages=messages,
                    temperature=max(0.0, min(1.0, temperature)),
                    max_tokens=max_tokens,
                )
                # Збираємо текст з усіх текстових блоків
                parts = [
                    block.text
                    for block in resp.content
                    if getattr(block, "type", "") == "text"
                ]
                return "".join(parts).strip() or "(порожня відповідь)"
            except anthropic.AuthenticationError:
                # Невірний ключ — ретраї не допоможуть
                raise
            except (anthropic.RateLimitError, anthropic.InternalServerError) as exc:
                # 429 або 5xx (включно з 529 overloaded) — ретраїмо
                last_exc = exc
                attempt += 1
                if attempt >= self.MAX_RETRIES:
                    break
                await asyncio.sleep(2 ** attempt)  # 2s, 4s, 8s
            except anthropic.APIStatusError as exc:
                if exc.status_code in (429, 529, 500, 502, 503, 504):
                    last_exc = exc
                    attempt += 1
                    if attempt >= self.MAX_RETRIES:
                        break
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
            except (anthropic.APIConnectionError, httpx.HTTPError) as exc:
                last_exc = exc
                attempt += 1
                if attempt >= self.MAX_RETRIES:
                    break
                await asyncio.sleep(2 ** attempt)

        assert last_exc is not None
        raise last_exc

    async def aclose(self) -> None:
        try:
            await self._client.close()
        except Exception:
            pass
