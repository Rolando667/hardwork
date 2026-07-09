"""Точка входу QABench — десктопний стенд тестування LLM-промтів для QA-аудиту."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from core import config
from ui.main_window import MainWindow
from ui.state import AppState
from ui.theme import DARK_QSS


def main() -> int:
    config.ensure_dirs()
    app = QApplication(sys.argv)
    app.setApplicationName("QABench")
    app.setStyleSheet(DARK_QSS)

    state = AppState()
    window = MainWindow(state)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
