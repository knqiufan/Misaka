"""
SQLite database backend for Misaka.

Uses Python's built-in ``sqlite3`` module with WAL mode.
Compatible with the original TypeScript schema for data migration.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from misaka.db.database import DatabaseBackend
from misaka.db.models import ChatSession, Message, RouterConfig, TaskItem
from misaka.db.row_mappers import (
    row_to_message,
    row_to_router_config,
    row_to_session,
    row_to_task,
)


def _now() -> str:
    """Return the current UTC datetime as an ISO string without microseconds."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _generate_id() -> str:
    """Generate a 32-character hex ID (same as crypto.randomBytes(16).toString('hex'))."""
    return secrets.token_hex(16)


class SQLiteBackend(DatabaseBackend):
    """SQLite-based persistence backend."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    # ----- Lifecycle -----

    def initialize(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New Chat',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                model TEXT NOT NULL DEFAULT '',
                system_prompt TEXT NOT NULL DEFAULT '',
                working_directory TEXT NOT NULL DEFAULT '',
                sdk_session_id TEXT NOT NULL DEFAULT '',
                project_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                mode TEXT NOT NULL DEFAULT 'agent'
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                token_usage TEXT,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'in_progress', 'completed', 'failed')),
                description TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON chat_sessions(updated_at);
            CREATE INDEX IF NOT EXISTS idx_sessions_sdk_id ON chat_sessions(sdk_session_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_session_id ON tasks(session_id);
        """)
        conn.commit()

        from misaka.db.migrations import run_migrations
        run_migrations(conn)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ----- Sessions -----

    def get_all_sessions(self) -> list[ChatSession]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM chat_sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [row_to_session(r) for r in rows]

    def get_session(self, session_id: str) -> ChatSession | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row_to_session(row) if row else None

    def get_session_by_sdk_id(self, sdk_session_id: str) -> ChatSession | None:
        """Lookup a session by its Claude SDK session ID (O(1) via index)."""
        if not sdk_session_id:
            return None
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM chat_sessions WHERE sdk_session_id = ? LIMIT 1",
            (sdk_session_id,),
        ).fetchone()
        return row_to_session(row) if row else None

    def create_session(
        self,
        title: str = "New Chat",
        model: str = "",
        system_prompt: str = "",
        working_directory: str = "",
        mode: str = "agent",
    ) -> ChatSession:
        conn = self._get_conn()
        sid = _generate_id()
        now = _now()
        project_name = os.path.basename(working_directory) if working_directory else ""
        conn.execute(
            """INSERT INTO chat_sessions
               (id, title, created_at, updated_at, model, system_prompt,
                working_directory, sdk_session_id, project_name, status, mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, 'active', ?)""",
            (sid, title, now, now, model, system_prompt, working_directory, project_name, mode),
        )
        conn.commit()
        return ChatSession(
            id=sid, title=title, model=model, system_prompt=system_prompt,
            working_directory=working_directory, project_name=project_name,
            sdk_session_id="", status="active", mode=mode,
            created_at=now, updated_at=now,
        )

    def update_session_title(self, session_id: str, title: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id)
        )
        conn.commit()

    def update_session_timestamp(self, session_id: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (_now(), session_id)
        )
        conn.commit()

    def update_sdk_session_id(self, session_id: str, sdk_session_id: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE chat_sessions SET sdk_session_id = ? WHERE id = ?",
            (sdk_session_id, session_id),
        )
        conn.commit()

    def update_session_working_directory(self, session_id: str, working_directory: str) -> None:
        conn = self._get_conn()
        project_name = os.path.basename(working_directory) if working_directory else ""
        conn.execute(
            "UPDATE chat_sessions SET working_directory = ?, project_name = ? WHERE id = ?",
            (working_directory, project_name, session_id),
        )
        conn.commit()

    def update_session_mode(self, session_id: str, mode: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE chat_sessions SET mode = ? WHERE id = ?", (mode, session_id)
        )
        conn.commit()

    def update_session_model(self, session_id: str, model: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE chat_sessions SET model = ? WHERE id = ?", (model, session_id)
        )
        conn.commit()

    def update_session_status(self, session_id: str, status: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE chat_sessions SET status = ? WHERE id = ?", (status, session_id)
        )
        conn.commit()

    def delete_session(self, session_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM chat_sessions WHERE id = ?", (session_id,)
        )
        conn.commit()
        return cursor.rowcount > 0

    # ----- Messages -----

    def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        before_rowid: int | None = None,
    ) -> tuple[list[Message], bool]:
        conn = self._get_conn()
        if before_rowid is not None:
            rows = conn.execute(
                """SELECT *, rowid as _rowid FROM messages
                   WHERE session_id = ? AND rowid < ?
                   ORDER BY rowid DESC LIMIT ?""",
                (session_id, before_rowid, limit + 1),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT *, rowid as _rowid FROM messages
                   WHERE session_id = ?
                   ORDER BY rowid DESC LIMIT ?""",
                (session_id, limit + 1),
            ).fetchall()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        rows.reverse()
        return [row_to_message(r) for r in rows], has_more

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        token_usage: str | None = None,
    ) -> Message:
        conn = self._get_conn()
        mid = _generate_id()
        now = _now()
        if isinstance(content, list):
            content = json.dumps(content, ensure_ascii=False)
        cursor = conn.execute(
            """INSERT INTO messages (id, session_id, role, content, created_at, token_usage)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (mid, session_id, role, content, now, token_usage),
        )
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        conn.commit()
        return Message(
            id=mid, session_id=session_id, role=role, content=content,
            created_at=now, token_usage=token_usage, _rowid=cursor.lastrowid,
        )

    def add_messages_batch(
        self,
        session_id: str,
        messages: list[dict[str, str | None]],
    ) -> None:
        """Insert multiple messages in a single transaction.

        Each dict must have keys: role, content, and optionally token_usage.
        """
        if not messages:
            return
        conn = self._get_conn()
        now = _now()
        rows = [
            (_generate_id(), session_id, m["role"], m["content"], now, m.get("token_usage"))
            for m in messages
        ]
        conn.executemany(
            """INSERT INTO messages (id, session_id, role, content, created_at, token_usage)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        conn.commit()

    def clear_session_messages(self, session_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute(
            "UPDATE chat_sessions SET sdk_session_id = '' WHERE id = ?", (session_id,)
        )
        conn.commit()

    def delete_message(self, message_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        conn.commit()
        return cursor.rowcount > 0

    # ----- Settings -----

    def get_setting(self, key: str) -> str | None:
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        conn.commit()

    def set_settings_batch(self, settings: dict[str, str]) -> None:
        """Write multiple settings in a single transaction."""
        if not settings:
            return
        conn = self._get_conn()
        conn.executemany(
            """INSERT INTO settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            list(settings.items()),
        )
        conn.commit()

    def get_all_settings(self) -> dict[str, str]:
        conn = self._get_conn()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}

    # ----- Tasks -----

    def get_tasks_by_session(self, session_id: str) -> list[TaskItem]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM tasks WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [row_to_task(r) for r in rows]

    def get_task(self, task_id: str) -> TaskItem | None:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_task(row) if row else None

    def create_task(self, session_id: str, title: str, description: str | None = None) -> TaskItem:
        conn = self._get_conn()
        tid = _generate_id()
        now = _now()
        conn.execute(
            """INSERT INTO tasks
               (id, session_id, title, status, description, created_at, updated_at)
               VALUES (?, ?, ?, 'pending', ?, ?, ?)""",
            (tid, session_id, title, description, now, now),
        )
        conn.commit()
        return TaskItem(
            id=tid, session_id=session_id, title=title, status="pending",
            description=description, created_at=now, updated_at=now,
        )

    def update_task(self, task_id: str, **kwargs: Any) -> TaskItem | None:
        conn = self._get_conn()
        now = _now()
        sets: list[str] = ["updated_at = ?"]
        params: list[Any] = [now]
        for col in ("title", "status", "description"):
            if col in kwargs:
                sets.append(f"{col} = ?")
                params.append(kwargs[col])
        params.append(task_id)
        cursor = conn.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?",  # noqa: S608
            params,
        )
        conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cursor.rowcount > 0

    # ----- Router Configs -----

    def get_all_router_configs(self) -> list[RouterConfig]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM router_configs ORDER BY sort_order ASC, created_at ASC"
        ).fetchall()
        return [row_to_router_config(r) for r in rows]

    def get_router_config(self, config_id: str) -> RouterConfig | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM router_configs WHERE id = ?", (config_id,)
        ).fetchone()
        return row_to_router_config(row) if row else None

    def get_active_router_config(self) -> RouterConfig | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM router_configs WHERE is_active = 1 LIMIT 1"
        ).fetchone()
        return row_to_router_config(row) if row else None

    def create_router_config(self, name: str, **kwargs: Any) -> RouterConfig:
        conn = self._get_conn()
        cid = _generate_id()
        now = _now()
        max_row = conn.execute(
            "SELECT MAX(sort_order) as max_order FROM router_configs"
        ).fetchone()
        sort_order = (max_row["max_order"] or -1) + 1 if max_row else 0
        api_key = kwargs.get("api_key", "")
        base_url = kwargs.get("base_url", "")
        main_model = kwargs.get("main_model", "")
        haiku_model = kwargs.get("haiku_model", "")
        opus_model = kwargs.get("opus_model", "")
        sonnet_model = kwargs.get("sonnet_model", "")
        agent_team = kwargs.get("agent_team", False)
        config_json = kwargs.get("config_json", "{}")
        is_active = kwargs.get("is_active", 0)
        conn.execute(
            """INSERT INTO router_configs
               (id, name, api_key, base_url, main_model, haiku_model,
                opus_model, sonnet_model, agent_team, config_json,
                is_active, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cid, name, api_key, base_url, main_model, haiku_model,
             opus_model, sonnet_model, 1 if agent_team else 0,
             config_json, is_active, sort_order, now, now),
        )
        conn.commit()
        return RouterConfig(
            id=cid, name=name, api_key=api_key, base_url=base_url,
            main_model=main_model, haiku_model=haiku_model,
            opus_model=opus_model, sonnet_model=sonnet_model,
            agent_team=bool(agent_team), config_json=config_json,
            is_active=is_active, sort_order=sort_order,
            created_at=now, updated_at=now,
        )

    def update_router_config(self, config_id: str, **kwargs: Any) -> RouterConfig | None:
        existing = self.get_router_config(config_id)
        if not existing:
            return None
        conn = self._get_conn()
        now = _now()
        conn.execute(
            """UPDATE router_configs
               SET name = ?, api_key = ?, base_url = ?, main_model = ?,
                   haiku_model = ?, opus_model = ?, sonnet_model = ?,
                   agent_team = ?, config_json = ?, sort_order = ?,
                   updated_at = ?
               WHERE id = ?""",
            (
                kwargs.get("name", existing.name),
                kwargs.get("api_key", existing.api_key),
                kwargs.get("base_url", existing.base_url),
                kwargs.get("main_model", existing.main_model),
                kwargs.get("haiku_model", existing.haiku_model),
                kwargs.get("opus_model", existing.opus_model),
                kwargs.get("sonnet_model", existing.sonnet_model),
                1 if kwargs.get("agent_team", existing.agent_team) else 0,
                kwargs.get("config_json", existing.config_json),
                kwargs.get("sort_order", existing.sort_order),
                now,
                config_id,
            ),
        )
        conn.commit()
        return self.get_router_config(config_id)

    def delete_router_config(self, config_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM router_configs WHERE id = ?", (config_id,))
        conn.commit()
        return cursor.rowcount > 0

    def activate_router_config(self, config_id: str) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM router_configs WHERE id = ?", (config_id,)
        ).fetchone()
        if not row:
            return False
        conn.execute("UPDATE router_configs SET is_active = 0")
        conn.execute(
            "UPDATE router_configs SET is_active = 1 WHERE id = ?", (config_id,)
        )
        conn.commit()
        return True

    # ----- Dashboard aggregation -----

    def get_session_counts(self) -> dict[str, int]:
        conn = self._get_conn()
        row = conn.execute(
            """SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN status='archived' THEN 1 ELSE 0 END) AS archived
            FROM chat_sessions"""
        ).fetchone()
        msg_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM messages"
        ).fetchone()
        return {
            "total": row["total"] or 0,
            "active": row["active"] or 0,
            "archived": row["archived"] or 0,
            "messages": msg_row["cnt"] or 0,
        }

    def get_token_usage_rows(self) -> list[str]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT token_usage FROM messages "
            "WHERE role = 'assistant' AND token_usage IS NOT NULL"
        ).fetchall()
        return [r["token_usage"] for r in rows if r["token_usage"]]
