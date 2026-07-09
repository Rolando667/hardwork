"""Централізоване логування.

- Пише у файл з ротацією в %APPDATA%\\TelegramAgentManager\\logs
- Дублює події в GUI через Qt-сигнал (QtLogBridge)
- Помилки Claude / Telegram форматуються людською мовою, а не сирим traceback
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

from PySide6.QtCore import QObject, Signal

from .paths import logs_dir

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class QtLogBridge(QObject):
    """Міст між модулем logging та Qt.

    Кожен запис лога перетворюється на сигнал ``record``, який головне вікно
    підключає до віджета «Логи». Поля: agent_id, agent_name, level, message.
    """

    record = Signal(str, str, str, str)  # agent_id, agent_name, level, message


# Єдиний екземпляр моста на весь застосунок.
bridge = QtLogBridge()


class _QtHandler(logging.Handler):
    """logging.Handler, який відправляє записи у Qt-сигнал."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            agent_id = getattr(record, "agent_id", "") or ""
            agent_name = getattr(record, "agent_name", "") or "system"
            msg = record.getMessage()
            bridge.record.emit(agent_id, agent_name, record.levelname, msg)
        except Exception:  # логер ніколи не повинен валити застосунок
            pass


_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Ініціалізує кореневий логер один раз."""
    global _configured
    if _configured:
        return

    root = logging.getLogger("tam")
    root.setLevel(level)
    root.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        logs_dir() / "app.log",
        maxBytes=2 * 1024 * 1024,  # 2 МБ на файл
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    qt_handler = _QtHandler()
    qt_handler.setFormatter(formatter)
    root.addHandler(qt_handler)

    _configured = True


def get_logger(agent_id: str = "", agent_name: str = "system") -> logging.LoggerAdapter:
    """Повертає адаптер логера з прив'язаними agent_id/agent_name.

    Це дозволяє віджету логів фільтрувати повідомлення за конкретним ботом.
    """
    base = logging.getLogger("tam")
    return logging.LoggerAdapter(base, {"agent_id": agent_id, "agent_name": agent_name})


def humanize_error(exc: BaseException) -> str:
    """Перетворює виключення у зрозуміле повідомлення українською.

    Розпізнає типові помилки Claude та Telegram.
    """
    name = type(exc).__name__
    text = str(exc)

    # Anthropic / Claude
    if name == "AuthenticationError" or "401" in text:
        return "Невірний ключ Claude API (401). Перевірте ключ у картці агента."
    if name == "PermissionDeniedError" or "403" in text:
        return "Доступ до Claude API заборонено (403). Перевірте права ключа."
    if name == "RateLimitError" or "429" in text:
        return "Перевищено ліміт запитів Claude API (429). Зачекайте трохи."
    if name == "NotFoundError" or "404" in text:
        return "Модель Claude не знайдена (404). Перевірте назву моделі."
    if "529" in text or "overloaded" in text.lower():
        return "Сервери Claude перевантажені (529). Повторюю спробу пізніше."
    if name in ("APIConnectionError", "APITimeoutError"):
        return "Не вдалося з'єднатися з Claude API. Перевірте інтернет/проксі."

    # Telegram
    low = text.lower()
    if "unauthorized" in low or "token" in low and "invalid" in low:
        return "Невірний Telegram-токен. Перевірте токен бота у картці агента."
    if "network" in low or "connection" in low or "timeout" in low:
        return "Проблема з мережею Telegram. Спроба перепідключення…"

    return f"{name}: {text}" if text else name
