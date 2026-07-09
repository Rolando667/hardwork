"""Вкладка «Діалоги»: список транскриптів + редагування, імпорт .txt пачкою."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from core.models import ETALON_OPTIONS, V_DASH, Dialog


class DialogsTab(QWidget):
    dialogs_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Назва діалогу")

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("Текст транскрипта діалогу…")

        self.etalon_combo = QComboBox()
        self.etalon_combo.addItems(ETALON_OPTIONS)

        add_btn = QPushButton("Новий (вставити текст)")
        import_btn = QPushButton("Завантажити .txt пачкою")
        import_btn.setObjectName("secondary")
        save_btn = QPushButton("Зберегти")
        del_btn = QPushButton("Видалити")
        del_btn.setObjectName("danger")
        add_btn.clicked.connect(self._new)
        import_btn.clicked.connect(self._import_txt)
        save_btn.clicked.connect(self._save)
        del_btn.clicked.connect(self._delete)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Діалоги:"))
        left_layout.addWidget(self.list)
        left_btn_row = QHBoxLayout()
        left_btn_row.addWidget(add_btn)
        left_btn_row.addWidget(import_btn)
        left_layout.addLayout(left_btn_row)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Назва:"))
        right_layout.addWidget(self.name_edit)
        right_layout.addWidget(QLabel("Транскрипт:"))
        right_layout.addWidget(self.text_edit)
        etalon_row = QHBoxLayout()
        etalon_row.addWidget(QLabel("Еталон:"))
        etalon_row.addWidget(self.etalon_combo)
        etalon_row.addStretch()
        right_layout.addLayout(etalon_row)
        btn_row = QHBoxLayout()
        btn_row.addWidget(save_btn)
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

        self._current_id: str | None = None
        self.refresh()

    def refresh(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for dialog in storage.list_dialogs():
            item = QListWidgetItem(dialog.name or "(без назви)")
            item.setData(Qt.UserRole, dialog.id)
            self.list.addItem(item)
        self.list.blockSignals(False)

    def _on_select(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            return
        dialog_id = current.data(Qt.UserRole)
        for dialog in storage.list_dialogs():
            if dialog.id == dialog_id:
                self._current_id = dialog.id
                self.name_edit.setText(dialog.name)
                self.text_edit.setPlainText(dialog.text)
                idx = self.etalon_combo.findText(dialog.etalon)
                self.etalon_combo.setCurrentIndex(idx if idx >= 0 else 0)
                return

    def _new(self) -> None:
        self.list.clearSelection()
        self._current_id = None
        self.name_edit.clear()
        self.text_edit.clear()
        self.etalon_combo.setCurrentText(V_DASH)
        self.name_edit.setFocus()

    def _save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Діалоги", "Вкажіть назву діалогу.")
            return
        dialog = Dialog(
            name=name,
            text=self.text_edit.toPlainText(),
            etalon=self.etalon_combo.currentText(),
        )
        if self._current_id:
            dialog.id = self._current_id
        storage.save_dialog(dialog)
        self._current_id = dialog.id
        self.refresh()
        self._select_by_id(dialog.id)
        self.dialogs_changed.emit()

    def _delete(self) -> None:
        if not self._current_id:
            QMessageBox.information(self, "Діалоги", "Оберіть діалог для видалення.")
            return
        if (
            QMessageBox.question(self, "Видалити діалог", "Видалити обраний діалог?")
            != QMessageBox.Yes
        ):
            return
        storage.delete_dialog(self._current_id)
        self._current_id = None
        self.name_edit.clear()
        self.text_edit.clear()
        self.refresh()
        self.dialogs_changed.emit()

    def _import_txt(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Завантажити .txt файли діалогів", "", "Текстові файли (*.txt);;Усі файли (*)"
        )
        if not paths:
            return
        count = 0
        for p in paths:
            path = Path(p)
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                try:
                    text = path.read_text(encoding="cp1251")
                except OSError:
                    continue
            dialog = Dialog(name=path.stem, text=text, etalon=V_DASH)
            storage.save_dialog(dialog)
            count += 1
        self.refresh()
        self.dialogs_changed.emit()
        QMessageBox.information(self, "Імпорт", f"Імпортовано діалогів: {count}")

    def _select_by_id(self, dialog_id: str) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == dialog_id:
                self.list.setCurrentRow(i)
                return
