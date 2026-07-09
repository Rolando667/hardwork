"""Вкладка «Промти»: список збережених промтів + редактор."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core import storage


class PromptsTab(QWidget):
    prompts_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Текст системного промта (інструкція QA-аудиту)…")
        self.editor.textChanged.connect(self._update_counter)

        self.counter = QLabel("Символів: 0 • ≈ токенів: 0")
        self.counter.setObjectName("hint")

        new_btn = QPushButton("Новий")
        save_btn = QPushButton("Зберегти")
        dup_btn = QPushButton("Дублювати")
        dup_btn.setObjectName("secondary")
        del_btn = QPushButton("Видалити")
        del_btn.setObjectName("danger")
        new_btn.clicked.connect(self._new)
        save_btn.clicked.connect(self._save)
        dup_btn.clicked.connect(self._duplicate)
        del_btn.clicked.connect(self._delete)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Збережені промти:"))
        left_layout.addWidget(self.list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Редактор:"))
        right_layout.addWidget(self.editor)
        right_layout.addWidget(self.counter)
        btn_row = QHBoxLayout()
        btn_row.addWidget(new_btn)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(dup_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        right_layout.addLayout(btn_row)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self._current_name: str | None = None
        self.refresh()

    def refresh(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for prompt in storage.list_prompts():
            item = QListWidgetItem(prompt.name)
            item.setData(Qt.UserRole, prompt.text)
            self.list.addItem(item)
        self.list.blockSignals(False)

    def _update_counter(self) -> None:
        text = self.editor.toPlainText()
        chars = len(text)
        approx_tokens = int(chars / 2.7)
        self.counter.setText(f"Символів: {chars} • ≈ токенів: {approx_tokens}")

    def _on_select(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            return
        self._current_name = current.text()
        self.editor.setPlainText(current.data(Qt.UserRole) or "")

    def _new(self) -> None:
        self.list.clearSelection()
        self._current_name = None
        self.editor.clear()
        self.editor.setFocus()

    def _save(self) -> None:
        text = self.editor.toPlainText()
        name = self._current_name
        if not name:
            name, ok = QInputDialog.getText(self, "Зберегти промт", "Назва промта:")
            if not ok or not name.strip():
                return
            name = name.strip()
        stem = storage.save_prompt(name, text)
        self._current_name = stem
        self.refresh()
        self._select_by_name(stem)
        self.prompts_changed.emit()

    def _duplicate(self) -> None:
        text = self.editor.toPlainText()
        base = (self._current_name or "промт") + "_копія"
        name, ok = QInputDialog.getText(
            self, "Дублювати промт", "Назва копії:", text=base
        )
        if not ok or not name.strip():
            return
        stem = storage.save_prompt(name.strip(), text)
        self._current_name = stem
        self.refresh()
        self._select_by_name(stem)
        self.prompts_changed.emit()

    def _delete(self) -> None:
        if not self._current_name:
            QMessageBox.information(self, "Промти", "Оберіть промт для видалення.")
            return
        if (
            QMessageBox.question(
                self, "Видалити промт", f"Видалити промт «{self._current_name}»?"
            )
            != QMessageBox.Yes
        ):
            return
        storage.delete_prompt(self._current_name)
        self._current_name = None
        self.editor.clear()
        self.refresh()
        self.prompts_changed.emit()

    def _select_by_name(self, name: str) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).text() == name:
                self.list.setCurrentRow(i)
                return
