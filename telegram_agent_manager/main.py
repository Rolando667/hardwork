"""Точка входу Telegram Agent Manager.

Інтегрує asyncio (aiogram + anthropic) з Qt event loop через qasync,
щоб фонові агенти не блокували інтерфейс.
"""
from __future__ import annotations

import asyncio
import sys

import qasync
from PySide6.QtWidgets import QApplication

from core.logger import setup_logging
from core.storage import Storage
from ui.main_window import MainWindow
from ui.master_dialog import MasterPasswordDialog
from ui.theme import load_stylesheet


def main() -> int:
    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("TelegramAgentManager")
    # Не закривати застосунок, коли ховаємо вікно в трей
    app.setQuitOnLastWindowClosed(False)

    storage = Storage()
    theme = storage.get_setting("theme", "dark")
    app.setStyleSheet(load_stylesheet(theme))

    # Майстер-пароль (створення при першому запуску або вхід)
    dialog = MasterPasswordDialog(storage)
    if dialog.exec() != MasterPasswordDialog.Accepted:
        storage.close()
        return 0

    # qasync event loop — єдиний цикл для Qt і asyncio
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow(storage)
    window.show()

    with loop:
        return loop.run_forever()


if __name__ == "__main__":
    sys.exit(main() or 0)
