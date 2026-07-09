"""Головне вікно: вкладки, меню налаштувань, координація оновлень."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, List

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core import config
from core.models import RunCell

from .dialogs_tab import DialogsTab
from .models_tab import ModelsTab
from .prompts_tab import PromptsTab
from .results_tab import ResultsTab
from .run_tab import RunTab
from .state import AppState


class SettingsDialog(QDialog):
    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Налаштування")
        self.setMinimumWidth(460)
        form = QFormLayout()
        self.proxy_edit = QLineEdit(state.proxy)
        self.proxy_edit.setPlaceholderText("напр. http://user:pass@proxy.corp:8080")
        form.addRow("HTTP(S) проксі:", self.proxy_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Зберегти")
        buttons.button(QDialogButtonBox.Cancel).setText("Скасувати")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        self.state.proxy = self.proxy_edit.text().strip()
        self.state.save()
        self.accept()


class ReasoningMapDialog(QDialog):
    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("reasoning_map.json — мапінг рівнів роздумів")
        self.setMinimumSize(560, 480)
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(
            json.dumps(state.reasoning_map, ensure_ascii=False, indent=2)
        )
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Зберегти")
        buttons.button(QDialogButtonBox.Cancel).setText("Скасувати")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        try:
            data = json.loads(self.editor.toPlainText())
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "Помилка", f"Невалідний JSON: {exc}")
            return
        if not isinstance(data, dict):
            QMessageBox.warning(self, "Помилка", "Очікується об'єкт JSON.")
            return
        config.save_reasoning_map(data)
        self.state.reasoning_map = config.load_reasoning_map()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self.setWindowTitle("QABench — стенд тестування LLM-промтів")
        self.resize(1200, 760)

        self.tabs = QTabWidget()
        self.models_tab = ModelsTab(state)
        self.prompts_tab = PromptsTab()
        self.dialogs_tab = DialogsTab()
        self.run_tab = RunTab(state)
        self.results_tab = ResultsTab()

        self.tabs.addTab(self.models_tab, "Моделі")
        self.tabs.addTab(self.prompts_tab, "Промти")
        self.tabs.addTab(self.dialogs_tab, "Діалоги")
        self.tabs.addTab(self.run_tab, "Запуск")
        self.tabs.addTab(self.results_tab, "Результати")
        self.setCentralWidget(self.tabs)

        # Оновлення вкладки «Запуск» при зміні джерел даних.
        self.models_tab.models_changed.connect(self.run_tab.refresh)
        self.prompts_tab.prompts_changed.connect(self.run_tab.refresh)
        self.dialogs_tab.dialogs_changed.connect(self.run_tab.refresh)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Завершення прогону → показати результати.
        self.run_tab.run_finished.connect(self._on_run_finished)

        self._build_menu()

    def _build_menu(self) -> None:
        menu = self.menuBar()

        settings_menu = menu.addMenu("Налаштування")
        proxy_action = QAction("Проксі…", self)
        proxy_action.triggered.connect(self._open_settings)
        settings_menu.addAction(proxy_action)

        reasoning_action = QAction("Мапінг роздумів (reasoning_map.json)…", self)
        reasoning_action.triggered.connect(self._open_reasoning_map)
        settings_menu.addAction(reasoning_action)

        data_menu = menu.addMenu("Дані")
        open_folder_action = QAction("Відкрити папку даних", self)
        open_folder_action.triggered.connect(self._open_data_folder)
        data_menu.addAction(open_folder_action)

    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is self.run_tab:
            self.run_tab.refresh()

    def _on_run_finished(self, results: List[RunCell], context: Dict[str, Any]) -> None:
        self.results_tab.load(results, context, auto_save=True)
        self.tabs.setCurrentWidget(self.results_tab)

    def _open_settings(self) -> None:
        SettingsDialog(self.state, self).exec()

    def _open_reasoning_map(self) -> None:
        ReasoningMapDialog(self.state, self).exec()

    def _open_data_folder(self) -> None:
        path = str(config.data_dir())
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:  # не критично
            QMessageBox.information(self, "Папка даних", f"{path}\n\n{exc}")
