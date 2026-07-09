"""Картка редагування одного агента + тестовий міні-чат."""
from __future__ import annotations

import asyncio
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.claude_client import ClaudeClient
from core.logger import humanize_error
from core.storage import Agent

MODELS = [
    "claude-sonnet-5",
    "claude-opus-4-8",
    "claude-haiku-4-5-20251001",
    "claude-fable-5",
]


class PasswordEdit(QWidget):
    """Поле пароля з кнопкою-«око» (показати/приховати)."""

    def __init__(self, placeholder: str = "") -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText(placeholder)
        self._btn = QPushButton("👁")
        self._btn.setFixedWidth(40)
        self._btn.setCheckable(True)
        self._btn.setToolTip("Показати / приховати")
        self._btn.toggled.connect(self._toggle)
        lay.addWidget(self.edit)
        lay.addWidget(self._btn)

    def _toggle(self, shown: bool) -> None:
        self.edit.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)

    def text(self) -> str:
        return self.edit.text()

    def setText(self, value: str) -> None:
        self.edit.setText(value)


def _field(label: str, widget: QWidget) -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lbl = QLabel(label)
    lbl.setObjectName("Subtle")
    lay.addWidget(lbl)
    lay.addWidget(widget)
    return box


class BotCard(QWidget):
    """Права панель — редагування конкретного агента."""

    save_clicked = Signal()
    toggle_clicked = Signal()
    duplicate_clicked = Signal()
    delete_clicked = Signal()

    def __init__(self, get_global_key, get_claude_proxy) -> None:
        super().__init__()
        self._agent: Optional[Agent] = None
        self._get_global_key = get_global_key
        self._get_claude_proxy = get_claude_proxy
        self._running = False
        self._build()

    # ---- Побудова UI ------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        container.setObjectName("Card")
        scroll.setWidget(container)

        lay = QVBoxLayout(container)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        title = QLabel("Налаштування агента")
        title.setObjectName("Title")
        lay.addWidget(title)

        # 1. Назва
        self.name_edit = QLineEdit()
        lay.addWidget(_field("Назва бота", self.name_edit))

        # 2. Telegram token
        self.token_edit = PasswordEdit("123456:ABC-DEF…")
        lay.addWidget(_field("Telegram Bot Token", self.token_edit))

        # 3. Claude key
        self.key_edit = PasswordEdit("Порожньо → глобальний ключ з Налаштувань")
        lay.addWidget(
            _field("Claude API Key (перевизначення для цього агента)", self.key_edit)
        )

        # 4. Модель
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(MODELS)
        lay.addWidget(_field("Модель Claude", self.model_combo))

        # 5. Системний промт
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setMinimumHeight(120)
        self.prompt_edit.setPlaceholderText(
            "Опишіть, як бот має себе поводити: стиль, тон, обмеження…"
        )
        lay.addWidget(_field("Системний промт", self.prompt_edit))

        # 6,7,8 — числові поля в рядок
        nums = QHBoxLayout()
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 1.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(0.7)
        nums.addWidget(_field("Температура", self.temp_spin))

        self.tokens_spin = QSpinBox()
        self.tokens_spin.setRange(1, 8192)
        self.tokens_spin.setValue(1024)
        nums.addWidget(_field("Макс. довжина (max_tokens)", self.tokens_spin))

        self.depth_spin = QSpinBox()
        self.depth_spin.setRange(0, 200)
        self.depth_spin.setValue(10)
        nums.addWidget(_field("Глибина пам'яті", self.depth_spin))
        lay.addLayout(nums)

        # 9. Автозапуск
        self.autostart_chk = QCheckBox("Автозапуск разом із програмою")
        lay.addWidget(self.autostart_chk)

        # 10. Кнопки
        btns = QHBoxLayout()
        self.save_btn = QPushButton("💾 Зберегти")
        self.save_btn.setObjectName("Primary")
        self.toggle_btn = QPushButton("▶ Запустити")
        self.test_btn = QPushButton("🧪 Тест")
        self.dup_btn = QPushButton("⧉ Дублювати")
        self.del_btn = QPushButton("🗑 Видалити")
        self.del_btn.setObjectName("Danger")
        for b in (self.save_btn, self.toggle_btn, self.test_btn, self.dup_btn, self.del_btn):
            btns.addWidget(b)
        lay.addLayout(btns)
        lay.addStretch(1)

        self.save_btn.clicked.connect(self.save_clicked.emit)
        self.toggle_btn.clicked.connect(self.toggle_clicked.emit)
        self.dup_btn.clicked.connect(self.duplicate_clicked.emit)
        self.del_btn.clicked.connect(self.delete_clicked.emit)
        self.test_btn.clicked.connect(self._open_test_chat)

    # ---- Дані -------------------------------------------------------------
    def load_agent(self, agent: Agent) -> None:
        self._agent = agent
        self.name_edit.setText(agent.name)
        self.token_edit.setText(agent.telegram_token)
        self.key_edit.setText(agent.claude_api_key)
        self.model_combo.setCurrentText(agent.model)
        self.prompt_edit.setPlainText(agent.system_prompt)
        self.temp_spin.setValue(agent.temperature)
        self.tokens_spin.setValue(agent.max_tokens)
        self.depth_spin.setValue(agent.history_depth)
        self.autostart_chk.setChecked(agent.autostart)
        self.set_running(agent.status == "running")

    def apply_to_agent(self) -> Optional[Agent]:
        """Записує значення форми у поточний агент і повертає його."""
        if self._agent is None:
            return None
        a = self._agent
        a.name = self.name_edit.text().strip() or "Агент"
        a.telegram_token = self.token_edit.text().strip()
        a.claude_api_key = self.key_edit.text().strip()
        a.model = self.model_combo.currentText().strip()
        a.system_prompt = self.prompt_edit.toPlainText()
        a.temperature = self.temp_spin.value()
        a.max_tokens = self.tokens_spin.value()
        a.history_depth = self.depth_spin.value()
        a.autostart = self.autostart_chk.isChecked()
        return a

    @property
    def agent(self) -> Optional[Agent]:
        return self._agent

    def set_running(self, running: bool) -> None:
        self._running = running
        self.toggle_btn.setText("⏹ Зупинити" if running else "▶ Запустити")

    # ---- Тестовий чат -----------------------------------------------------
    def _open_test_chat(self) -> None:
        agent = self.apply_to_agent()
        if agent is None:
            return
        key = agent.claude_api_key or self._get_global_key()
        if not key:
            dlg = QDialog(self)
            dlg.setWindowTitle("Тест")
            l = QVBoxLayout(dlg)
            l.addWidget(QLabel("Не заданий Claude API Key (ані в агенті, ані глобальний)."))
            dlg.exec()
            return
        dialog = TestChatDialog(agent, key, self._get_claude_proxy(), self)
        dialog.exec()


class TestChatDialog(QDialog):
    """Міні-чат для перевірки промта без Telegram."""

    def __init__(self, agent: Agent, api_key: str, proxy: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Тест агента — {agent.name}")
        self.resize(560, 620)
        self._agent = agent
        self._client = ClaudeClient(api_key, proxy=proxy or None)
        self._history: list[dict] = []

        lay = QVBoxLayout(self)
        info = QLabel(
            f"Модель: {agent.model} · темп: {agent.temperature} · "
            f"max_tokens: {agent.max_tokens}"
        )
        info.setObjectName("Subtle")
        lay.addWidget(info)

        self.view = QTextEdit()
        self.view.setReadOnly(True)
        lay.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Напишіть повідомлення боту…")
        self.send_btn = QPushButton("Надіслати")
        self.send_btn.setObjectName("Primary")
        row.addWidget(self.input, 1)
        row.addWidget(self.send_btn)
        lay.addLayout(row)

        self.send_btn.clicked.connect(self._send)
        self.input.returnPressed.connect(self._send)

    def _append(self, who: str, text: str, color: str) -> None:
        self.view.append(f'<b style="color:{color}">{who}:</b> {text}<br>')

    def _send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._append("Ви", text, "#4c8bf5")
        self.send_btn.setEnabled(False)
        asyncio.ensure_future(self._ask(text))

    async def _ask(self, text: str) -> None:
        self._history.append({"role": "user", "content": text})
        try:
            reply = await self._client.complete(
                model=self._agent.model,
                system_prompt=self._agent.system_prompt,
                messages=self._history[-self._agent.history_depth * 2 :]
                if self._agent.history_depth
                else self._history,
                temperature=self._agent.temperature,
                max_tokens=self._agent.max_tokens,
            )
            self._history.append({"role": "assistant", "content": reply})
            self._append("Бот", reply, "#3ac47d")
        except Exception as exc:
            self._append("Помилка", humanize_error(exc), "#e5534b")
        finally:
            self.send_btn.setEnabled(True)

    def closeEvent(self, event) -> None:  # noqa: N802
        asyncio.ensure_future(self._client.aclose())
        super().closeEvent(event)
