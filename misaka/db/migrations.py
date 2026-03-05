"""
Database migration system for Misaka.

Handles schema versioning and incremental migrations for the SQLite backend.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

# Current schema version. Increment when adding new migrations.
SCHEMA_VERSION = 3


def run_migrations(conn: sqlite3.Connection) -> None:
    """Run any pending migrations on the given SQLite connection.

    This is called automatically by :meth:`SQLiteBackend.initialize`.
    Each migration checks for the presence of columns/tables before
    altering, making it safe to run multiple times (idempotent).
    """
    _ensure_version_table(conn)
    current = _get_version(conn)

    if current < 1:
        _migrate_v1(conn)

    if current < 2:
        _migrate_v2(conn)

    if current < 3:
        _migrate_v3(conn)

    _set_version(conn, SCHEMA_VERSION)
    conn.commit()


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _schema_version (
            version INTEGER NOT NULL
        )
    """)
    row = conn.execute("SELECT version FROM _schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO _schema_version (version) VALUES (0)")
    conn.commit()


def _get_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT version FROM _schema_version").fetchone()
    return row[0] if row else 0


def _set_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("UPDATE _schema_version SET version = ?", (version,))


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """Migration v1: Ensure all columns added in TypeScript migrations exist."""
    logger.info("Running migration v1")

    # chat_sessions columns
    session_cols = _get_column_names(conn, "chat_sessions")
    if "model" not in session_cols:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN model TEXT NOT NULL DEFAULT ''")
    if "system_prompt" not in session_cols:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN system_prompt TEXT NOT NULL DEFAULT ''")
    if "sdk_session_id" not in session_cols:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN sdk_session_id TEXT NOT NULL DEFAULT ''")
    if "project_name" not in session_cols:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN project_name TEXT NOT NULL DEFAULT ''")
    if "status" not in session_cols:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    if "mode" not in session_cols:
        conn.execute("ALTER TABLE chat_sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'code'")

    # messages columns
    msg_cols = _get_column_names(conn, "messages")
    if "token_usage" not in msg_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN token_usage TEXT")


def _get_column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    # SAFETY: table names are hardcoded constants, not user input.
    # SQLite parameterized queries (?) do not support table/column name binding.
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """Migration v2: Add router_configs table."""
    logger.info("Running migration v2")

    existing_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "router_configs" not in existing_tables:
        conn.execute("""
            CREATE TABLE router_configs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                api_key TEXT NOT NULL DEFAULT '',
                base_url TEXT NOT NULL DEFAULT '',
                main_model TEXT NOT NULL DEFAULT '',
                haiku_model TEXT NOT NULL DEFAULT '',
                opus_model TEXT NOT NULL DEFAULT '',
                sonnet_model TEXT NOT NULL DEFAULT '',
                agent_team INTEGER NOT NULL DEFAULT 0,
                config_json TEXT NOT NULL DEFAULT '{}',
                is_active INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)


def _migrate_v3(conn: sqlite3.Connection) -> None:
    """Migration v3: Rename 'code' mode to 'agent'."""
    logger.info("Running migration v3")
    conn.execute("UPDATE chat_sessions SET mode = 'agent' WHERE mode = 'code'")
