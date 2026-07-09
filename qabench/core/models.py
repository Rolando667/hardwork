"""Моделі даних: конфігурація моделі, діалог, промт, клітинка результату."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# --- Універсальні рівні роздумів (вибираються користувачем) ---
LEVELS: List[str] = ["none", "minimal", "low", "medium", "high"]

# --- Провайдери ---
PROVIDERS: List[str] = ["Anthropic", "Google", "OpenAI"]

# --- Типи параметра роздумів ---
REASONING_TYPES: List[str] = [
    "none",
    "anthropic_thinking_budget",
    "anthropic_adaptive_effort",
    "gemini_thinking_budget",
    "gemini_thinking_level",
    "openai_reasoning_effort",
]

# --- Значення вердиктів ---
V_OK = "Відповідає стандарту"
V_FAIL = "Не відповідає стандарту"
V_NA = "Неможливо оцінити"
V_DASH = "—"

VERDICTS: List[str] = [V_OK, V_FAIL, V_NA]
ETALON_OPTIONS: List[str] = [V_OK, V_FAIL, V_NA, V_DASH]

VERDICT_ICON = {
    V_OK: "✅",
    V_FAIL: "❌",
    V_NA: "❓",
}
ERROR_ICON = "⚠️"


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class ModelConfig:
    """Опис однієї моделі провайдера."""

    name: str = ""
    provider: str = "Anthropic"
    model_id: str = ""
    api_key: str = ""
    price_in: float = 0.0          # $/1M вхідних токенів
    price_out: float = 0.0         # $/1M вихідних токенів
    reasoning_type: str = "none"
    max_tokens: int = 4096
    temperature: Optional[float] = None   # None = не передавати параметр
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "model_id": self.model_id,
            "api_key": self.api_key,
            "price_in": self.price_in,
            "price_out": self.price_out,
            "reasoning_type": self.reasoning_type,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ModelConfig":
        return ModelConfig(
            id=d.get("id") or _new_id(),
            name=d.get("name", ""),
            provider=d.get("provider", "Anthropic"),
            model_id=d.get("model_id", ""),
            api_key=d.get("api_key", ""),
            price_in=float(d.get("price_in", 0.0) or 0.0),
            price_out=float(d.get("price_out", 0.0) or 0.0),
            reasoning_type=d.get("reasoning_type", "none"),
            max_tokens=int(d.get("max_tokens", 4096) or 4096),
            temperature=(
                None
                if d.get("temperature") in (None, "")
                else float(d.get("temperature"))
            ),
        )


@dataclass
class Dialog:
    """Транскрипт діалогу колцентру з необов'язковим еталоном."""

    name: str = ""
    text: str = ""
    etalon: str = V_DASH
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "text": self.text,
            "etalon": self.etalon,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Dialog":
        return Dialog(
            id=d.get("id") or _new_id(),
            name=d.get("name", ""),
            text=d.get("text", ""),
            etalon=d.get("etalon", V_DASH) or V_DASH,
        )


@dataclass
class Prompt:
    """Системний промт (зберігається як .txt файл; name = ім'я файлу без розширення)."""

    name: str = ""
    text: str = ""


@dataclass
class RunCell:
    """Результат одного виклику API (одна комбінація модель×рівень×діалог×повтор)."""

    dialog_id: str
    model_id: str          # id ModelConfig, не рядок API
    level: str
    repeat_index: int
    status: Optional[str] = None       # один з VERDICTS або None
    comment: str = ""
    raw: str = ""                      # сира відповідь повністю
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None   # повний вихід (з thinking-токенами)
    cost: Optional[float] = None
    seconds: float = 0.0
    error: Optional[str] = None        # текст помилки запиту чи парсингу
    translation: str = ""              # у що транслювався рівень роздумів
