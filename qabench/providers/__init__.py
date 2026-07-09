"""Провайдери LLM API: Anthropic, Google Gemini, OpenAI.

Кожен провайдер надає async-функцію call(...), що повертає RunCell.
"""
from __future__ import annotations

from typing import Awaitable, Callable

import httpx

from core.models import ModelConfig, RunCell

from . import anthropic as _anthropic
from . import google as _google
from . import openai as _openai

# Тип функції провайдера.
ProviderCall = Callable[..., Awaitable[RunCell]]

_DISPATCH = {
    "Anthropic": _anthropic.call,
    "Google": _google.call,
    "OpenAI": _openai.call,
}


def get_provider(name: str) -> ProviderCall:
    if name not in _DISPATCH:
        raise ValueError(f"Невідомий провайдер: {name}")
    return _DISPATCH[name]
