"""Централізований стан застосунку: конфіг, моделі, мапінг роздумів."""
from __future__ import annotations

from typing import Any, Dict, List

from core import config
from core.models import ModelConfig


class AppState:
    def __init__(self) -> None:
        config.ensure_dirs()
        self.config: Dict[str, Any] = config.load_config()
        self.models: List[ModelConfig] = [
            ModelConfig.from_dict(m) for m in self.config.get("models", [])
        ]
        self.reasoning_map: Dict[str, Any] = config.load_reasoning_map()

    # --- Збереження ---
    def save(self) -> None:
        self.config["models"] = [m.to_dict() for m in self.models]
        config.save_config(self.config)

    # --- Проксі ---
    @property
    def proxy(self) -> str:
        return self.config.get("proxy", "") or ""

    @proxy.setter
    def proxy(self, value: str) -> None:
        self.config["proxy"] = value or ""

    # --- Останні вибори ---
    @property
    def last_selection(self) -> Dict[str, Any]:
        return self.config.setdefault("last_selection", {})

    def model_by_id(self, model_id: str) -> ModelConfig | None:
        for m in self.models:
            if m.id == model_id:
                return m
        return None
