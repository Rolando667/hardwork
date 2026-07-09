"""Головне вікно застосунку: вкладки Агенти / Логи / Налаштування, трей."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.bot_worker import BotWorker
from core.logger import bridge, get_logger
from core.storage import Agent, Storage

from .bot_card import BotCard
from .theme import load_stylesheet

STATUS_DOT = {"running": "🟢", "stopped": "🔴", "error": "🟡"}
LEVELS = ["Усі", "INFO", "WARNING", "ERROR"]
_MAX_LOG_LINES = 3000


def _make_icon(color: str = "#4c8bf5") -> QIcon:
    """Проста програмна іконка (кольоровий кружечок) — без зовнішніх файлів."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    from PySide6.QtGui import QPainter

    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(8, 8, 48, 48)
    p.end()
    return QIcon(pix)


class MainWindow(QWidget):
    def __init__(self, storage: Storage) -> None:
        super().__init__()
        self._storage = storage
        self._workers: dict[str, BotWorker] = {}
        self._counts: dict[str, int] = {}
        self._items: dict[str, QListWidgetItem] = {}
        self._log_records: list[tuple[str, str, str, str, str]] = []
        self._log = get_logger()

        self.setWindowTitle("Telegram Agent Manager")
        self.resize(1120, 720)
        self.setWindowIcon(_make_icon())

        self._build()
        self._apply_theme(self._storage.get_setting("theme", "dark"))
        self._setup_tray()

        bridge.record.connect(self._on_log_record)

        self._reload_agent_list()
        self._log.info("Застосунок запущено.")
        self._autostart_agents()

    # ================= Побудова UI =========================================
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.tabs.addTab(self._build_agents_tab(), "Агенти")
        self.tabs.addTab(self._build_logs_tab(), "Логи")
        self.tabs.addTab(self._build_settings_tab(), "Налаштування")

    def _build_agents_tab(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        splitter = QSplitter(Qt.Horizontal)
        lay.addWidget(splitter)

        # Ліва панель
        left = QWidget()
        left.setObjectName("Panel")
        left_lay = QVBoxLayout(left)
        add_btn = QPushButton("＋ Додати агента")
        add_btn.setObjectName("Primary")
        add_btn.clicked.connect(self._add_agent)
        left_lay.addWidget(add_btn)
        self.agent_list = QListWidget()
        self.agent_list.currentItemChanged.connect(self._on_agent_selected)
        left_lay.addWidget(self.agent_list)
        splitter.addWidget(left)

        # Права панель — stacked: заглушка або картка
        self.right_stack = QStackedWidget()
        placeholder = QLabel("Оберіть агента зі списку\nабо додайте нового.")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setObjectName("Subtle")
        self.right_stack.addWidget(placeholder)

        self.card = BotCard(
            get_global_key=self._storage.get_global_claude_key,
            get_claude_proxy=lambda: self._storage.get_setting("proxy_claude", ""),
        )
        self.card.save_clicked.connect(self._save_current)
        self.card.toggle_clicked.connect(self._toggle_current)
        self.card.duplicate_clicked.connect(self._duplicate_current)
        self.card.delete_clicked.connect(self._delete_current)
        self.right_stack.addWidget(self.card)

        splitter.addWidget(self.right_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 780])
        return w

    def _build_logs_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Бот:"))
        self.log_bot_filter = QComboBox()
        self.log_bot_filter.addItem("Усі", "")
        self.log_bot_filter.currentIndexChanged.connect(self._render_logs)
        filters.addWidget(self.log_bot_filter)

        filters.addWidget(QLabel("Рівень:"))
        self.log_level_filter = QComboBox()
        self.log_level_filter.addItems(LEVELS)
        self.log_level_filter.currentIndexChanged.connect(self._render_logs)
        filters.addWidget(self.log_level_filter)

        clear_btn = QPushButton("Очистити")
        clear_btn.clicked.connect(self._clear_logs)
        filters.addWidget(clear_btn)
        filters.addStretch(1)
        lay.addLayout(filters)

        self.log_view = QTextEdit()
        self.log_view.setObjectName("Logs")
        self.log_view.setReadOnly(True)
        lay.addWidget(self.log_view)
        return w

    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        panel = QWidget()
        panel.setObjectName("Card")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)
        outer.addWidget(panel)
        outer.addStretch(1)

        t = QLabel("Налаштування")
        t.setObjectName("Title")
        lay.addWidget(t)

        # Тема
        row = QHBoxLayout()
        row.addWidget(QLabel("Тема оформлення:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Темна", "Світла"])
        self.theme_combo.setCurrentIndex(
            0 if self._storage.get_setting("theme", "dark") == "dark" else 1
        )
        self.theme_combo.currentIndexChanged.connect(self._change_theme)
        row.addWidget(self.theme_combo)
        row.addStretch(1)
        lay.addLayout(row)

        # Автозапуск Windows
        self.autostart_win_chk = QCheckBox("Запускати програму разом із Windows")
        self.autostart_win_chk.setChecked(
            bool(self._storage.get_setting("autostart_windows", False))
        )
        self.autostart_win_chk.toggled.connect(self._toggle_windows_autostart)
        lay.addWidget(self.autostart_win_chk)

        # Згортання в трей
        self.tray_chk = QCheckBox("Згортати в трей замість закриття")
        self.tray_chk.setChecked(
            bool(self._storage.get_setting("minimize_to_tray", True))
        )
        self.tray_chk.toggled.connect(
            lambda v: self._storage.set_setting("minimize_to_tray", v)
        )
        lay.addWidget(self.tray_chk)

        # Глобальний Claude key
        lay.addWidget(QLabel("Глобальний Claude API Key (за замовчуванням):"))
        key_row = QHBoxLayout()
        self.global_key_edit = QLineEdit()
        self.global_key_edit.setEchoMode(QLineEdit.Password)
        self.global_key_edit.setText(self._storage.get_global_claude_key())
        show = QPushButton("👁")
        show.setFixedWidth(40)
        show.setCheckable(True)
        show.toggled.connect(
            lambda v: self.global_key_edit.setEchoMode(
                QLineEdit.Normal if v else QLineEdit.Password
            )
        )
        key_row.addWidget(self.global_key_edit)
        key_row.addWidget(show)
        lay.addLayout(key_row)

        # Проксі
        lay.addWidget(QLabel("Проксі для Telegram (напр. socks5://user:pass@host:port):"))
        self.proxy_tg_edit = QLineEdit(self._storage.get_setting("proxy_telegram", ""))
        lay.addWidget(self.proxy_tg_edit)
        lay.addWidget(QLabel("Проксі для Claude API (напр. http://host:port):"))
        self.proxy_claude_edit = QLineEdit(self._storage.get_setting("proxy_claude", ""))
        lay.addWidget(self.proxy_claude_edit)

        save_settings = QPushButton("💾 Зберегти налаштування")
        save_settings.setObjectName("Primary")
        save_settings.clicked.connect(self._save_settings)
        lay.addWidget(save_settings)

        # Бекап
        backup_row = QHBoxLayout()
        exp = QPushButton("⬆ Експорт конфігурації")
        exp.clicked.connect(self._export_backup)
        imp = QPushButton("⬇ Імпорт конфігурації")
        imp.clicked.connect(self._import_backup)
        backup_row.addWidget(exp)
        backup_row.addWidget(imp)
        lay.addLayout(backup_row)

        # Зміна майстер-пароля
        chpw = QPushButton("🔑 Змінити майстер-пароль")
        chpw.clicked.connect(self._change_master_password)
        lay.addWidget(chpw)

        return w

    # ================= Тема / трей =========================================
    def _apply_theme(self, theme: str) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(load_stylesheet(theme))

    def _change_theme(self, index: int) -> None:
        theme = "dark" if index == 0 else "light"
        self._storage.set_setting("theme", theme)
        self._apply_theme(theme)

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(_make_icon(), self)
        self.tray.setToolTip("Telegram Agent Manager")
        menu = QMenu()
        show_act = QAction("Показати", self)
        show_act.triggered.connect(self._show_from_tray)
        stop_all_act = QAction("Зупинити всіх агентів", self)
        stop_all_act.triggered.connect(self._stop_all_agents)
        quit_act = QAction("Вихід", self)
        quit_act.triggered.connect(self._quit)
        menu.addAction(show_act)
        menu.addAction(stop_all_act)
        menu.addSeparator()
        menu.addAction(quit_act)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._show_from_tray()
            if reason == QSystemTrayIcon.Trigger
            else None
        )
        self.tray.show()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ================= Список агентів ======================================
    def _reload_agent_list(self) -> None:
        self.agent_list.blockSignals(True)
        self.agent_list.clear()
        self._items.clear()
        self.log_bot_filter.blockSignals(True)
        self.log_bot_filter.clear()
        self.log_bot_filter.addItem("Усі", "")
        for agent in self._storage.list_agents(decrypt=True):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, agent.id)
            self.agent_list.addItem(item)
            self._items[agent.id] = item
            self._refresh_item(agent.id, agent.status, agent.name)
            self.log_bot_filter.addItem(agent.name, agent.id)
        self.log_bot_filter.blockSignals(False)
        self.agent_list.blockSignals(False)

    def _refresh_item(self, agent_id: str, status: str, name: Optional[str] = None) -> None:
        item = self._items.get(agent_id)
        if item is None:
            return
        if name is None:
            agent = self._storage.get_agent(agent_id, decrypt=False)
            name = agent.name if agent else "Агент"
        dot = STATUS_DOT.get(status, "🔴")
        count = self._counts.get(agent_id, 0)
        item.setText(f"{dot}  {name}\n      оброблено: {count}")

    def _current_agent_id(self) -> Optional[str]:
        item = self.agent_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_agent_selected(self, current, _previous) -> None:
        if current is None:
            self.right_stack.setCurrentIndex(0)
            return
        agent_id = current.data(Qt.UserRole)
        agent = self._storage.get_agent(agent_id, decrypt=True)
        if agent is None:
            return
        # Актуальний статус з воркера
        worker = self._workers.get(agent_id)
        if worker and worker.is_running:
            agent.status = "running"
        self.card.load_agent(agent)
        self.right_stack.setCurrentIndex(1)

    # ================= Дії з агентами ======================================
    def _add_agent(self) -> None:
        agent = Agent()
        # Підтягуємо глобальний ключ як підказку — але лишаємо порожнім (= глобальний)
        self._storage.save_agent(agent)
        self._reload_agent_list()
        item = self._items.get(agent.id)
        if item:
            self.agent_list.setCurrentItem(item)
        self._log.info(f"Додано нового агента: {agent.name}")

    def _save_current(self) -> None:
        agent = self.card.apply_to_agent()
        if agent is None:
            return
        self._storage.save_agent(agent)
        self._refresh_item(agent.id, agent.status, agent.name)
        # оновити назву у фільтрі логів
        idx = self.log_bot_filter.findData(agent.id)
        if idx >= 0:
            self.log_bot_filter.setItemText(idx, agent.name)
        self._log.info(f"Збережено агента: {agent.name}")
        QMessageBox.information(self, "Збережено", "Налаштування агента збережені.")

    def _toggle_current(self) -> None:
        agent = self.card.apply_to_agent()
        if agent is None:
            return
        self._storage.save_agent(agent)
        worker = self._workers.get(agent.id)
        if worker and worker.is_running:
            asyncio.ensure_future(self._stop_agent(agent.id))
        else:
            self._start_agent(agent)

    def _start_agent(self, agent: Agent) -> None:
        # Свіжа копія з розшифрованими ключами
        fresh = self._storage.get_agent(agent.id, decrypt=True)
        if fresh is None:
            return
        worker = BotWorker(
            fresh,
            self._storage,
            proxy_telegram=self._storage.get_setting("proxy_telegram", ""),
            proxy_claude=self._storage.get_setting("proxy_claude", ""),
        )
        worker.status_changed.connect(self._on_worker_status)
        worker.count_changed.connect(self._on_worker_count)
        self._workers[agent.id] = worker
        worker.start()
        self.card.set_running(True)

    async def _stop_agent(self, agent_id: str) -> None:
        worker = self._workers.get(agent_id)
        if worker:
            await worker.stop()
            self._workers.pop(agent_id, None)
        if self._current_agent_id() == agent_id:
            self.card.set_running(False)

    def _on_worker_status(self, agent_id: str, status: str) -> None:
        self._refresh_item(agent_id, status)
        if self._current_agent_id() == agent_id:
            self.card.set_running(status == "running")

    def _on_worker_count(self, agent_id: str, count: int) -> None:
        self._counts[agent_id] = count
        self._refresh_item(agent_id, "running")

    def _duplicate_current(self) -> None:
        src = self.card.apply_to_agent()
        if src is None:
            return
        self._storage.save_agent(src)
        clone = Agent(
            name=f"{src.name} (копія)",
            model=src.model,
            system_prompt=src.system_prompt,
            temperature=src.temperature,
            max_tokens=src.max_tokens,
            history_depth=src.history_depth,
            autostart=False,
            telegram_token=src.telegram_token,
            claude_api_key=src.claude_api_key,
        )
        self._storage.save_agent(clone)
        self._reload_agent_list()
        item = self._items.get(clone.id)
        if item:
            self.agent_list.setCurrentItem(item)
        self._log.info(f"Дубльовано агента: {clone.name}")

    def _delete_current(self) -> None:
        agent_id = self._current_agent_id()
        if not agent_id:
            return
        agent = self._storage.get_agent(agent_id, decrypt=False)
        name = agent.name if agent else "агента"
        if (
            QMessageBox.question(
                self,
                "Видалення",
                f"Видалити «{name}» разом з історією діалогів?",
            )
            != QMessageBox.Yes
        ):
            return
        if agent_id in self._workers:
            asyncio.ensure_future(self._stop_agent(agent_id))
        self._storage.delete_agent(agent_id)
        self._counts.pop(agent_id, None)
        self._reload_agent_list()
        self.right_stack.setCurrentIndex(0)
        self._log.info(f"Видалено агента: {name}")

    def _autostart_agents(self) -> None:
        for agent in self._storage.list_agents(decrypt=True):
            if agent.autostart and agent.telegram_token:
                self._start_agent(agent)

    def _stop_all_agents(self) -> None:
        for agent_id in list(self._workers.keys()):
            asyncio.ensure_future(self._stop_agent(agent_id))
        self._log.info("Зупинено всіх агентів (за командою з трею).")

    # ================= Логи ================================================
    def _on_log_record(self, agent_id: str, agent_name: str, level: str, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_records.append((ts, agent_id, agent_name, level, msg))
        if len(self._log_records) > _MAX_LOG_LINES:
            self._log_records = self._log_records[-_MAX_LOG_LINES:]
        if self._passes_filter(agent_id, level):
            self.log_view.append(self._format_log(ts, agent_name, level, msg))

    def _passes_filter(self, agent_id: str, level: str) -> bool:
        bot_id = self.log_bot_filter.currentData()
        if bot_id and bot_id != agent_id:
            return False
        lvl = self.log_level_filter.currentText()
        if lvl != "Усі" and lvl != level:
            return False
        return True

    def _format_log(self, ts: str, name: str, level: str, msg: str) -> str:
        color = {"ERROR": "#e5534b", "WARNING": "#e0a030", "INFO": "#8b94a3"}.get(
            level, "#8b94a3"
        )
        return (
            f'<span style="color:#6b7280">{ts}</span> '
            f'<b style="color:{color}">[{level}]</b> '
            f'<span style="color:#4c8bf5">{name}</span>: {msg}'
        )

    def _render_logs(self) -> None:
        self.log_view.clear()
        for ts, agent_id, name, level, msg in self._log_records:
            if self._passes_filter(agent_id, level):
                self.log_view.append(self._format_log(ts, name, level, msg))

    def _clear_logs(self) -> None:
        self._log_records.clear()
        self.log_view.clear()

    # ================= Налаштування ========================================
    def _save_settings(self) -> None:
        self._storage.set_global_claude_key(self.global_key_edit.text().strip())
        self._storage.set_setting("proxy_telegram", self.proxy_tg_edit.text().strip())
        self._storage.set_setting("proxy_claude", self.proxy_claude_edit.text().strip())
        self._log.info("Налаштування збережені.")
        QMessageBox.information(self, "Збережено", "Налаштування збережені.")

    def _toggle_windows_autostart(self, enabled: bool) -> None:
        self._storage.set_setting("autostart_windows", enabled)
        if os.name != "nt":
            return
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            if enabled:
                import sys

                if getattr(sys, "frozen", False):  # зібраний .exe
                    cmd = f'"{sys.executable}"'
                else:  # режим розробки
                    script = os.path.abspath(
                        os.path.join(os.path.dirname(__file__), "..", "main.py")
                    )
                    cmd = f'"{sys.executable}" "{script}"'
                winreg.SetValueEx(key, "TelegramAgentManager", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, "TelegramAgentManager")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as exc:
            self._log.warning(f"Не вдалося змінити автозапуск Windows: {exc}")

    def _export_backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Експорт конфігурації", "tam_backup.tam", "TAM backup (*.tam)"
        )
        if not path:
            return
        pwd, ok = QInputDialog.getText(
            self, "Пароль бекапу", "Пароль для шифрування файлу:", QLineEdit.Password
        )
        if not ok or not pwd:
            return
        try:
            self._storage.export_backup(path, pwd)
            QMessageBox.information(self, "Готово", "Конфігурацію експортовано.")
        except Exception as exc:
            QMessageBox.critical(self, "Помилка", f"Не вдалося експортувати: {exc}")

    def _import_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Імпорт конфігурації", "", "TAM backup (*.tam);;Усі файли (*)"
        )
        if not path:
            return
        pwd, ok = QInputDialog.getText(
            self, "Пароль бекапу", "Пароль файлу бекапу:", QLineEdit.Password
        )
        if not ok or not pwd:
            return
        try:
            count = self._storage.import_backup(path, pwd)
            self._reload_agent_list()
            QMessageBox.information(self, "Готово", f"Імпортовано агентів: {count}.")
        except Exception as exc:
            QMessageBox.critical(
                self, "Помилка", f"Не вдалося імпортувати (невірний пароль?): {exc}"
            )

    def _change_master_password(self) -> None:
        old, ok = QInputDialog.getText(
            self, "Зміна пароля", "Поточний майстер-пароль:", QLineEdit.Password
        )
        if not ok:
            return
        new, ok = QInputDialog.getText(
            self, "Зміна пароля", "Новий майстер-пароль:", QLineEdit.Password
        )
        if not ok or len(new) < 4:
            QMessageBox.warning(self, "Помилка", "Новий пароль занадто короткий.")
            return
        if self._storage.change_master_password(old, new):
            QMessageBox.information(self, "Готово", "Майстер-пароль змінено.")
        else:
            QMessageBox.critical(self, "Помилка", "Невірний поточний пароль.")

    # ================= Закриття / трей =====================================
    def closeEvent(self, event) -> None:  # noqa: N802
        if self._storage.get_setting("minimize_to_tray", True) and self.tray.isVisible():
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Telegram Agent Manager",
                "Програма згорнута в трей. Агенти продовжують працювати.",
                QSystemTrayIcon.Information,
                3000,
            )
        else:
            self._quit()

    def _quit(self) -> None:
        for agent_id in list(self._workers.keys()):
            worker = self._workers.get(agent_id)
            if worker:
                asyncio.ensure_future(worker.stop())
        self._storage.close()
        self.tray.hide()
        QApplication.instance().quit()
