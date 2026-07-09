"""Вкладка «Моделі»: таблиця моделей + Додати/Редагувати/Видалити."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import PROVIDERS, REASONING_TYPES, ModelConfig

from .state import AppState


class ModelDialog(QDialog):
    """Діалог редагування однієї моделі."""

    def __init__(self, model: Optional[ModelConfig], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Модель")
        self.setMinimumWidth(460)
        self._model = model or ModelConfig()

        form = QFormLayout()

        self.name_edit = QLineEdit(self._model.name)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(PROVIDERS)
        if self._model.provider in PROVIDERS:
            self.provider_combo.setCurrentText(self._model.provider)

        self.model_id_edit = QLineEdit(self._model.model_id)
        self.model_id_edit.setPlaceholderText("напр. claude-sonnet-4-5, gemini-3-flash, gpt-5.1")

        self.key_edit = QLineEdit(self._model.api_key)
        self.key_edit.setEchoMode(QLineEdit.Password)
        show_key_btn = QPushButton("👁")
        show_key_btn.setObjectName("secondary")
        show_key_btn.setFixedWidth(40)
        show_key_btn.setCheckable(True)
        show_key_btn.toggled.connect(
            lambda checked: self.key_edit.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_edit)
        key_row.addWidget(show_key_btn)
        key_row_w = QWidget()
        key_row_w.setLayout(key_row)

        self.price_in_edit = QDoubleSpinBox()
        self.price_in_edit.setRange(0.0, 100000.0)
        self.price_in_edit.setDecimals(4)
        self.price_in_edit.setValue(self._model.price_in)

        self.price_out_edit = QDoubleSpinBox()
        self.price_out_edit.setRange(0.0, 100000.0)
        self.price_out_edit.setDecimals(4)
        self.price_out_edit.setValue(self._model.price_out)

        self.reasoning_combo = QComboBox()
        self.reasoning_combo.addItems(REASONING_TYPES)
        if self._model.reasoning_type in REASONING_TYPES:
            self.reasoning_combo.setCurrentText(self._model.reasoning_type)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(1, 1_000_000)
        self.max_tokens_spin.setValue(self._model.max_tokens or 4096)

        self.temp_edit = QLineEdit(
            "" if self._model.temperature is None else str(self._model.temperature)
        )
        self.temp_edit.setPlaceholderText("порожнє = дефолт провайдера")

        form.addRow("Назва для відображення:", self.name_edit)
        form.addRow("Провайдер:", self.provider_combo)
        form.addRow("Model ID:", self.model_id_edit)
        form.addRow("API-ключ:", key_row_w)
        form.addRow("Ціна входу $/1M:", self.price_in_edit)
        form.addRow("Ціна виходу $/1M:", self.price_out_edit)
        form.addRow("Тип параметра роздумів:", self.reasoning_combo)
        form.addRow("Max tokens відповіді:", self.max_tokens_spin)
        form.addRow("Температура:", self.temp_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Зберегти")
        buttons.button(QDialogButtonBox.Cancel).setText("Скасувати")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        name = self.name_edit.text().strip()
        model_id = self.model_id_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Помилка", "Вкажіть назву моделі.")
            return
        if not model_id:
            QMessageBox.warning(self, "Помилка", "Вкажіть Model ID.")
            return
        temp_text = self.temp_edit.text().strip()
        temperature: Optional[float]
        if temp_text == "":
            temperature = None
        else:
            try:
                temperature = float(temp_text.replace(",", "."))
            except ValueError:
                QMessageBox.warning(
                    self, "Помилка", "Температура має бути числом або порожньою."
                )
                return
        self._model.name = name
        self._model.provider = self.provider_combo.currentText()
        self._model.model_id = model_id
        self._model.api_key = self.key_edit.text()
        self._model.price_in = self.price_in_edit.value()
        self._model.price_out = self.price_out_edit.value()
        self._model.reasoning_type = self.reasoning_combo.currentText()
        self._model.max_tokens = self.max_tokens_spin.value()
        self._model.temperature = temperature
        self.accept()

    def model(self) -> ModelConfig:
        return self._model


class ModelsTab(QWidget):
    models_changed = Signal()

    _HEADERS = [
        "Назва",
        "Провайдер",
        "Model ID",
        "Тип роздумів",
        "API-ключ",
        "Ціна вх",
        "Ціна вих",
        "Max tokens",
        "Темп.",
    ]

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self.state = state

        self.table = QTableWidget(0, len(self._HEADERS))
        self.table.setHorizontalHeaderLabels(self._HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda *_: self._edit())

        add_btn = QPushButton("Додати")
        edit_btn = QPushButton("Редагувати")
        edit_btn.setObjectName("secondary")
        del_btn = QPushButton("Видалити")
        del_btn.setObjectName("danger")
        add_btn.clicked.connect(self._add)
        edit_btn.clicked.connect(self._edit)
        del_btn.clicked.connect(self._delete)

        btn_row = QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Моделі провайдерів (Anthropic / Google / OpenAI):"))
        layout.addWidget(self.table)
        layout.addLayout(btn_row)

        self.refresh()

    def refresh(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for model in self.state.models:
            row = self.table.rowCount()
            self.table.insertRow(row)
            masked = "••••" + model.api_key[-4:] if len(model.api_key) > 4 else (
                "••••" if model.api_key else "—"
            )
            values = [
                model.name,
                model.provider,
                model.model_id,
                model.reasoning_type,
                masked,
                f"{model.price_in:g}",
                f"{model.price_out:g}",
                str(model.max_tokens),
                "—" if model.temperature is None else f"{model.temperature:g}",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, model.id)
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)

    def _selected_model(self) -> Optional[ModelConfig]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        model_id = item.data(Qt.UserRole)
        return self.state.model_by_id(model_id)

    def _add(self) -> None:
        dlg = ModelDialog(None, self)
        if dlg.exec() == QDialog.Accepted:
            self.state.models.append(dlg.model())
            self.state.save()
            self.refresh()
            self.models_changed.emit()

    def _edit(self) -> None:
        model = self._selected_model()
        if model is None:
            QMessageBox.information(self, "Моделі", "Оберіть модель для редагування.")
            return
        dlg = ModelDialog(model, self)
        if dlg.exec() == QDialog.Accepted:
            self.state.save()
            self.refresh()
            self.models_changed.emit()

    def _delete(self) -> None:
        model = self._selected_model()
        if model is None:
            QMessageBox.information(self, "Моделі", "Оберіть модель для видалення.")
            return
        if (
            QMessageBox.question(
                self,
                "Видалити модель",
                f"Видалити модель «{model.name}»?",
            )
            != QMessageBox.Yes
        ):
            return
        self.state.models = [m for m in self.state.models if m.id != model.id]
        self.state.save()
        self.refresh()
        self.models_changed.emit()
