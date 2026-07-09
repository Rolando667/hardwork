"""Логіка одного агента: aiogram (long polling) + Claude.

Кожен агент — окремий asyncio-таск. Падіння одного не впливає на інших:
всі виключення ловляться всередині таска й переводять агента у стан «помилка».
"""
from __future__ import annotations

import asyncio
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import Message
from PySide6.QtCore import QObject, Signal

from .claude_client import ClaudeClient
from .logger import get_logger, humanize_error
from .storage import Agent, Storage


class BotWorker(QObject):
    """Керує життєвим циклом одного Telegram-бота у фоновому asyncio-таску.

    Сигнали (для GUI):
        status_changed(agent_id, status)   status: running|stopped|error
        count_changed(agent_id, count)      кількість оброблених повідомлень
    """

    status_changed = Signal(str, str)
    count_changed = Signal(str, int)

    def __init__(
        self,
        agent: Agent,
        storage: Storage,
        proxy_telegram: str = "",
        proxy_claude: str = "",
    ) -> None:
        super().__init__()
        self.agent = agent
        self._storage = storage
        self._proxy_telegram = proxy_telegram
        self._proxy_claude = proxy_claude

        self._task: Optional[asyncio.Task] = None
        self._bot: Optional[Bot] = None
        self._dp: Optional[Dispatcher] = None
        self._claude: Optional[ClaudeClient] = None
        self._count = 0
        self._log = get_logger(agent.id, agent.name)
        self._stopping = False

    # ---- Публічний API ----------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running:
            return
        self._stopping = False
        self._count = 0
        self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._dp is not None:
            try:
                await self._dp.stop_polling()
            except Exception:
                pass
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        await self._cleanup()
        self.agent.status = "stopped"
        self.status_changed.emit(self.agent.id, "stopped")
        self._log.info("Агент зупинено.")

    # ---- Внутрішнє --------------------------------------------------------
    def _resolve_claude_key(self) -> str:
        """Ключ агента, або глобальний ключ з налаштувань, якщо порожній."""
        if self.agent.claude_api_key:
            return self.agent.claude_api_key
        return self._storage.get_global_claude_key()

    async def _cleanup(self) -> None:
        if self._bot is not None:
            try:
                await self._bot.session.close()
            except Exception:
                pass
            self._bot = None
        if self._claude is not None:
            await self._claude.aclose()
            self._claude = None
        self._dp = None

    async def _run(self) -> None:
        token = self.agent.telegram_token
        claude_key = self._resolve_claude_key()

        if not token:
            self._fail("Не заданий Telegram-токен.")
            return
        if not claude_key:
            self._fail("Не заданий Claude API Key (ані в агенті, ані глобальний).")
            return

        self._claude = ClaudeClient(claude_key, proxy=self._proxy_claude or None)

        # aiogram-сесія з проксі (за потреби)
        session = AiohttpSession(proxy=self._proxy_telegram) if self._proxy_telegram else None
        try:
            self._bot = Bot(token=token, session=session) if session else Bot(token=token)
        except Exception as exc:
            self._fail(humanize_error(exc))
            return

        self._dp = Dispatcher()
        self._dp.message.register(self._on_message)

        self.agent.status = "running"
        self.status_changed.emit(self.agent.id, "running")
        self._log.info("Агент запущено, слухаю Telegram (long polling).")

        # Автоматичне перепідключення при обривах Telegram
        backoff = 2
        while not self._stopping:
            try:
                await self._dp.start_polling(
                    self._bot,
                    handle_signals=False,  # сигнали ОС обробляє Qt, не aiogram
                )
                break  # start_polling завершився штатно (stop_polling)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if self._stopping:
                    break
                self._log.warning(
                    f"Обрив Telegram: {humanize_error(exc)}. "
                    f"Перепідключення через {backoff}с…"
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def _fail(self, message: str) -> None:
        self.agent.status = "error"
        self._log.error(message)
        self.status_changed.emit(self.agent.id, "error")

    async def _on_message(self, message: Message) -> None:
        """Обробник вхідного повідомлення Telegram."""
        text = message.text or message.caption
        if not text:
            return
        chat_id = message.chat.id

        try:
            # Формуємо контекст з історії
            history = self._storage.get_history(
                self.agent.id, chat_id, self.agent.history_depth * 2
            )
            history.append({"role": "user", "content": text})

            assert self._claude is not None
            reply = await self._claude.complete(
                model=self.agent.model,
                system_prompt=self.agent.system_prompt,
                messages=history,
                temperature=self.agent.temperature,
                max_tokens=self.agent.max_tokens,
            )

            await message.answer(reply)

            # Зберігаємо в історію та обрізаємо за глибиною пам'яті
            self._storage.add_history(self.agent.id, chat_id, "user", text)
            self._storage.add_history(self.agent.id, chat_id, "assistant", reply)
            self._storage.trim_history(
                self.agent.id, chat_id, self.agent.history_depth * 2
            )

            self._count += 1
            self.count_changed.emit(self.agent.id, self._count)
            self._log.info(f"Оброблено повідомлення від chat_id={chat_id}.")

        except Exception as exc:
            human = humanize_error(exc)
            self._log.error(f"Помилка обробки (chat_id={chat_id}): {human}")
            # 401 → переводимо агента у стан «помилка» і зупиняємо
            if type(exc).__name__ == "AuthenticationError":
                self._fail(human)
                self._stopping = True
                if self._dp is not None:
                    try:
                        await self._dp.stop_polling()
                    except Exception:
                        pass
            else:
                try:
                    await message.answer(
                        "Вибачте, сталася помилка під час обробки. Спробуйте ще раз."
                    )
                except Exception:
                    pass
