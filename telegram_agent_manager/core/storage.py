"""Зберігання даних: SQLite (config.db) + шифрування ключів (Fernet).

Модель безпеки:
- Майстер-пароль ніде не зберігається у відкритому вигляді.
- З пароля через scrypt виводиться 32-байтний ключ Fernet.
- Для перевірки пароля зберігається лише зашифрований «маркер» (master_check):
  якщо його вдалося розшифрувати введеним паролем — пароль правильний.
- Telegram-токени та Claude-ключі зберігаються тільки зашифровано.
- Розшифровані значення існують лише в оперативній пам'яті.
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .paths import db_path

_CHECK_PLAINTEXT = b"TAM_MASTER_OK"
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1


def _derive_key(password: str, salt: bytes) -> bytes:
    """Виводить ключ Fernet (base64, 32 байти) з пароля та солі через scrypt."""
    kdf = Scrypt(salt=salt, length=32, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    raw = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


@dataclass
class Agent:
    """Опис одного агента (бота). Поля *_enc — зашифровані рядки в БД."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Новий агент"
    telegram_token_enc: str = ""
    claude_api_key_enc: str = ""
    model: str = "claude-sonnet-5"
    system_prompt: str = "Ти ввічливий і корисний асистент."
    temperature: float = 0.7
    max_tokens: int = 1024
    history_depth: int = 10
    autostart: bool = False
    status: str = "stopped"  # stopped | running | error

    # Розшифровані значення (тільки в пам'яті, не пишуться в БД напряму)
    telegram_token: str = ""
    claude_api_key: str = ""

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "telegram_token_enc": self.telegram_token_enc,
            "claude_api_key_enc": self.claude_api_key_enc,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "history_depth": self.history_depth,
            "autostart": 1 if self.autostart else 0,
            "status": self.status,
        }


class Storage:
    """Обгортка над SQLite з прозорим шифруванням чутливих полів."""

    def __init__(self) -> None:
        self._conn = sqlite3.connect(str(db_path()))
        self._conn.row_factory = sqlite3.Row
        self._fernet: Optional[Fernet] = None
        self._init_schema()

    # ---- Ініціалізація ----------------------------------------------------
    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT,
                telegram_token_enc TEXT,
                claude_api_key_enc TEXT,
                model TEXT,
                system_prompt TEXT,
                temperature REAL,
                max_tokens INTEGER,
                history_depth INTEGER,
                autostart INTEGER,
                status TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                agent_id TEXT,
                chat_id INTEGER,
                role TEXT,
                content TEXT,
                ts REAL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_history ON history(agent_id, chat_id, ts)"
        )
        self._conn.commit()

    # ---- Майстер-пароль ---------------------------------------------------
    def is_master_set(self) -> bool:
        return self._get_meta("master_salt") is not None

    def set_master_password(self, password: str) -> None:
        """Задає майстер-пароль (перший запуск)."""
        salt = os.urandom(16)
        key = _derive_key(password, salt)
        self._fernet = Fernet(key)
        check = self._fernet.encrypt(_CHECK_PLAINTEXT).decode()
        self._set_meta("master_salt", base64.b64encode(salt).decode())
        self._set_meta("master_check", check)

    def unlock(self, password: str) -> bool:
        """Розблоковує сховище введеним паролем. True — успіх."""
        salt_b64 = self._get_meta("master_salt")
        check = self._get_meta("master_check")
        if salt_b64 is None or check is None:
            return False
        salt = base64.b64decode(salt_b64)
        key = _derive_key(password, salt)
        fernet = Fernet(key)
        try:
            if fernet.decrypt(check.encode()) == _CHECK_PLAINTEXT:
                self._fernet = fernet
                return True
        except InvalidToken:
            return False
        return False

    def change_master_password(self, old: str, new: str) -> bool:
        """Змінює майстер-пароль, перешифровуючи всі чутливі значення."""
        if not self.unlock(old):
            return False
        # Розшифровуємо все наявне на старому ключі
        agents = self.list_agents(decrypt=True)
        global_key = self.get_global_claude_key()
        # Ставимо новий пароль (новий ключ)
        self.set_master_password(new)
        # Перешифровуємо
        for a in agents:
            a.telegram_token_enc = self._enc(a.telegram_token)
            a.claude_api_key_enc = self._enc(a.claude_api_key)
            self.save_agent(a)
        if global_key:
            self.set_global_claude_key(global_key)
        return True

    @property
    def unlocked(self) -> bool:
        return self._fernet is not None

    # ---- Низькорівневе шифрування ----------------------------------------
    def _enc(self, plain: str) -> str:
        if not plain:
            return ""
        assert self._fernet is not None, "Сховище не розблоковане"
        return self._fernet.encrypt(plain.encode("utf-8")).decode()

    def _dec(self, token: str) -> str:
        if not token:
            return ""
        assert self._fernet is not None, "Сховище не розблоковане"
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return ""

    # ---- meta / settings --------------------------------------------------
    def _get_meta(self, key: str) -> Optional[str]:
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._conn.commit()

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    def set_setting(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT INTO settings(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        self._conn.commit()

    # Глобальний Claude-ключ зберігається зашифровано у settings
    def get_global_claude_key(self) -> str:
        enc = self.get_setting("global_claude_key_enc", "")
        return self._dec(enc) if enc else ""

    def set_global_claude_key(self, key: str) -> None:
        self.set_setting("global_claude_key_enc", self._enc(key))

    # ---- Агенти -----------------------------------------------------------
    def list_agents(self, decrypt: bool = True) -> list[Agent]:
        rows = self._conn.execute("SELECT * FROM agents ORDER BY name").fetchall()
        result: list[Agent] = []
        for r in rows:
            agent = Agent(
                id=r["id"],
                name=r["name"],
                telegram_token_enc=r["telegram_token_enc"] or "",
                claude_api_key_enc=r["claude_api_key_enc"] or "",
                model=r["model"],
                system_prompt=r["system_prompt"] or "",
                temperature=r["temperature"],
                max_tokens=r["max_tokens"],
                history_depth=r["history_depth"],
                autostart=bool(r["autostart"]),
                status="stopped",  # при завантаженні всі зупинені
            )
            if decrypt:
                agent.telegram_token = self._dec(agent.telegram_token_enc)
                agent.claude_api_key = self._dec(agent.claude_api_key_enc)
            result.append(agent)
        return result

    def get_agent(self, agent_id: str, decrypt: bool = True) -> Optional[Agent]:
        for a in self.list_agents(decrypt=decrypt):
            if a.id == agent_id:
                return a
        return None

    def save_agent(self, agent: Agent) -> None:
        """Зберігає агента, перешифровуючи чутливі поля з відкритих значень.

        Порожнє відкрите значення → порожній enc (наприклад, очищений ключ
        агента означає «використовувати глобальний ключ»).
        """
        agent.telegram_token_enc = self._enc(agent.telegram_token)
        agent.claude_api_key_enc = self._enc(agent.claude_api_key)
        row = agent.to_row()
        self._conn.execute(
            """
            INSERT INTO agents (
                id, name, telegram_token_enc, claude_api_key_enc, model,
                system_prompt, temperature, max_tokens, history_depth,
                autostart, status
            ) VALUES (
                :id, :name, :telegram_token_enc, :claude_api_key_enc, :model,
                :system_prompt, :temperature, :max_tokens, :history_depth,
                :autostart, :status
            )
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                telegram_token_enc=excluded.telegram_token_enc,
                claude_api_key_enc=excluded.claude_api_key_enc,
                model=excluded.model,
                system_prompt=excluded.system_prompt,
                temperature=excluded.temperature,
                max_tokens=excluded.max_tokens,
                history_depth=excluded.history_depth,
                autostart=excluded.autostart,
                status=excluded.status
            """,
            row,
        )
        self._conn.commit()

    def delete_agent(self, agent_id: str) -> None:
        self._conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
        self._conn.execute("DELETE FROM history WHERE agent_id=?", (agent_id,))
        self._conn.commit()

    # ---- Історія діалогів -------------------------------------------------
    def add_history(self, agent_id: str, chat_id: int, role: str, content: str) -> None:
        self._conn.execute(
            "INSERT INTO history(agent_id, chat_id, role, content, ts) VALUES(?,?,?,?,?)",
            (agent_id, chat_id, role, content, time.time()),
        )
        self._conn.commit()

    def get_history(self, agent_id: str, chat_id: int, limit: int) -> list[dict]:
        """Повертає останні `limit` повідомлень у хронологічному порядку."""
        rows = self._conn.execute(
            "SELECT role, content FROM history WHERE agent_id=? AND chat_id=? "
            "ORDER BY ts DESC LIMIT ?",
            (agent_id, chat_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def trim_history(self, agent_id: str, chat_id: int, keep: int) -> None:
        """Обрізає історію конкретного чату, лишаючи останні `keep` записів."""
        self._conn.execute(
            """
            DELETE FROM history
            WHERE agent_id=? AND chat_id=? AND rowid NOT IN (
                SELECT rowid FROM history WHERE agent_id=? AND chat_id=?
                ORDER BY ts DESC LIMIT ?
            )
            """,
            (agent_id, chat_id, agent_id, chat_id, keep),
        )
        self._conn.commit()

    def clear_history(self, agent_id: str, chat_id: Optional[int] = None) -> None:
        if chat_id is None:
            self._conn.execute("DELETE FROM history WHERE agent_id=?", (agent_id,))
        else:
            self._conn.execute(
                "DELETE FROM history WHERE agent_id=? AND chat_id=?",
                (agent_id, chat_id),
            )
        self._conn.commit()

    # ---- Експорт / Імпорт бекапу -----------------------------------------
    def export_backup(self, path: str, backup_password: str) -> None:
        """Експортує всю конфігурацію у зашифрований файл.

        Дані розшифровуються поточним майстер-ключем і перешифровуються
        окремим паролем бекапу (щоб файл можна було відновити на іншій машині).
        """
        agents = self.list_agents(decrypt=True)
        payload = {
            "version": 1,
            "settings": {
                "theme": self.get_setting("theme", "dark"),
                "autostart_windows": self.get_setting("autostart_windows", False),
                "minimize_to_tray": self.get_setting("minimize_to_tray", True),
                "proxy_telegram": self.get_setting("proxy_telegram", ""),
                "proxy_claude": self.get_setting("proxy_claude", ""),
                "global_claude_key": self.get_global_claude_key(),
            },
            "agents": [
                {
                    "id": a.id,
                    "name": a.name,
                    "telegram_token": a.telegram_token,
                    "claude_api_key": a.claude_api_key,
                    "model": a.model,
                    "system_prompt": a.system_prompt,
                    "temperature": a.temperature,
                    "max_tokens": a.max_tokens,
                    "history_depth": a.history_depth,
                    "autostart": a.autostart,
                }
                for a in agents
            ],
        }
        salt = os.urandom(16)
        key = _derive_key(backup_password, salt)
        token = Fernet(key).encrypt(json.dumps(payload).encode("utf-8"))
        blob = base64.b64encode(salt) + b"." + token
        with open(path, "wb") as f:
            f.write(blob)

    def import_backup(self, path: str, backup_password: str) -> int:
        """Імпортує конфігурацію із зашифрованого файлу. Повертає к-сть агентів."""
        with open(path, "rb") as f:
            blob = f.read()
        salt_b64, _, token = blob.partition(b".")
        salt = base64.b64decode(salt_b64)
        key = _derive_key(backup_password, salt)
        data = Fernet(key).decrypt(token)
        payload = json.loads(data.decode("utf-8"))

        s = payload.get("settings", {})
        self.set_setting("theme", s.get("theme", "dark"))
        self.set_setting("autostart_windows", s.get("autostart_windows", False))
        self.set_setting("minimize_to_tray", s.get("minimize_to_tray", True))
        self.set_setting("proxy_telegram", s.get("proxy_telegram", ""))
        self.set_setting("proxy_claude", s.get("proxy_claude", ""))
        if s.get("global_claude_key"):
            self.set_global_claude_key(s["global_claude_key"])

        count = 0
        for a in payload.get("agents", []):
            agent = Agent(
                id=a.get("id", str(uuid.uuid4())),
                name=a.get("name", "Агент"),
                model=a.get("model", "claude-sonnet-5"),
                system_prompt=a.get("system_prompt", ""),
                temperature=a.get("temperature", 0.7),
                max_tokens=a.get("max_tokens", 1024),
                history_depth=a.get("history_depth", 10),
                autostart=a.get("autostart", False),
                telegram_token=a.get("telegram_token", ""),
                claude_api_key=a.get("claude_api_key", ""),
            )
            self.save_agent(agent)
            count += 1
        return count

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
