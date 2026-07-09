"""Діалог майстер-пароля: перший запуск (створення) та вхід (розблокування)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core.storage import Storage


class MasterPasswordDialog(QDialog):
    """Повертає True (accepted), якщо сховище успішно розблоковане/створене."""

    def __init__(self, storage: Storage, parent=None) -> None:
        super().__init__(parent)
        self._storage = storage
        self._is_setup = not storage.is_master_set()
        self.setWindowTitle("Telegram Agent Manager")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        title = QLabel("Створення майстер-пароля" if self._is_setup else "Вхід")
        title.setObjectName("Title")
        lay.addWidget(title)

        hint = QLabel(
            "Придумайте майстер-пароль. Ним шифруються всі токени й ключі.\n"
            "Пароль ніде не зберігається — відновити його неможливо."
            if self._is_setup
            else "Введіть майстер-пароль для доступу до збережених агентів."
        )
        hint.setObjectName("Subtle")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.pwd = QLineEdit()
        self.pwd.setEchoMode(QLineEdit.Password)
        self.pwd.setPlaceholderText("Майстер-пароль")
        lay.addWidget(self.pwd)

        self.pwd2 = QLineEdit()
        self.pwd2.setEchoMode(QLineEdit.Password)
        self.pwd2.setPlaceholderText("Повторіть пароль")
        if not self._is_setup:
            self.pwd2.hide()
        lay.addWidget(self.pwd2)

        self.error = QLabel("")
        self.error.setStyleSheet("color:#e5534b;")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)

        self.ok_btn = QPushButton("Створити" if self._is_setup else "Увійти")
        self.ok_btn.setObjectName("Primary")
        self.ok_btn.clicked.connect(self._submit)
        lay.addWidget(self.ok_btn)

        self.pwd.returnPressed.connect(self._submit)
        self.pwd2.returnPressed.connect(self._submit)

    def _submit(self) -> None:
        pwd = self.pwd.text()
        if len(pwd) < 4:
            self.error.setText("Пароль занадто короткий (мінімум 4 символи).")
            return
        if self._is_setup:
            if pwd != self.pwd2.text():
                self.error.setText("Паролі не збігаються.")
                return
            self._storage.set_master_password(pwd)
            self.accept()
        else:
            if self._storage.unlock(pwd):
                self.accept()
            else:
                self.error.setText("Невірний пароль. Спробуйте ще раз.")
                self.pwd.clear()
