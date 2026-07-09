"""Завантаження QSS-теми з підстановкою кольорових токенів (темна/світла)."""
from __future__ import annotations

import os
import sys

DARK = {
    "@BG@": "#1a1d23",
    "@PANEL@": "#22262e",
    "@INPUT@": "#2b3038",
    "@BORDER@": "#363c47",
    "@SELECT@": "#2f3b52",
    "@BTN@": "#2b3038",
    "@BTN_HOVER@": "#333a44",
    "@TEXT@": "#e6e9ef",
    "@TEXT_DIM@": "#8b94a3",
    "@ACCENT@": "#4c8bf5",
    "@ACCENT_HOVER@": "#3d78dd",
    "@DANGER@": "#e5534b",
}

LIGHT = {
    "@BG@": "#f2f4f8",
    "@PANEL@": "#ffffff",
    "@INPUT@": "#f7f9fc",
    "@BORDER@": "#d8dde6",
    "@SELECT@": "#dbe7fb",
    "@BTN@": "#f0f2f6",
    "@BTN_HOVER@": "#e4e8ef",
    "@TEXT@": "#1a1d23",
    "@TEXT_DIM@": "#6b7280",
    "@ACCENT@": "#2f6fe0",
    "@ACCENT_HOVER@": "#255bc0",
    "@DANGER@": "#d63c34",
}


def _styles_path() -> str:
    """Шлях до styles.qss, з урахуванням запуску всередині PyInstaller (.exe)."""
    if hasattr(sys, "_MEIPASS"):  # PyInstaller розпаковує сюди
        return os.path.join(sys._MEIPASS, "ui", "styles.qss")
    return os.path.join(os.path.dirname(__file__), "styles.qss")


def load_stylesheet(theme: str = "dark") -> str:
    """Повертає готовий QSS для заданої теми ('dark' або 'light')."""
    colors = LIGHT if theme == "light" else DARK
    with open(_styles_path(), "r", encoding="utf-8") as f:
        qss = f.read()
    for token, value in colors.items():
        qss = qss.replace(token, value)
    return qss
