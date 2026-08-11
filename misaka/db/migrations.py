"""
Database migration system for Misaka.

Handles schema versioning and incremental migrations for the SQLite backend.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

# Current schema version. Increment when adding new migrations.
SCHEMA_VERSION = 7


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

    if current < 4:
        _migrate_v4(conn)

    if current < 5:
        _migrate_v5(conn)

    if current < 6:
        _migrate_v6(conn)

    if current < 7:
        _migrate_v7(conn)

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


def _migrate_v4(conn: sqlite3.Connection) -> None:
    """Migration v4: Remove the legacy api_providers table."""
    logger.info("Running migration v4")
    conn.execute("DROP TABLE IF EXISTS api_providers")


def _migrate_v5(conn: sqlite3.Connection) -> None:
    """Migration v5: Add Knowledge Base infrastructure tables.

    Creates four new tables:
    - router_models: detected models (LLM / embedding / reranker) per router config
    - knowledge_bases: top-level KB metadata
    - kb_documents: uploaded documents per KB
    - kb_chunks: text chunks per document
    """
    logger.info("Running migration v5")

    existing_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    if "router_models" not in existing_tables:
        conn.execute("""
            CREATE TABLE router_models (
                id TEXT PRIMARY KEY,
                router_config_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                model_type TEXT NOT NULL DEFAULT 'llm'
                    CHECK(model_type IN ('llm', 'embedding', 'reranker')),
                is_selected INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (router_config_id)
                    REFERENCES router_configs(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_router_models_config_id
                ON router_models(router_config_id)
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_router_models_unique_model
                ON router_models(router_config_id, model_id)
        """)

    if "knowledge_bases" not in existing_tables:
        conn.execute("""
            CREATE TABLE knowledge_bases (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',

                embedding_model_id TEXT NOT NULL DEFAULT '',
                embedding_router_config_id TEXT NOT NULL DEFAULT '',
                embedding_dimensions INTEGER NOT NULL DEFAULT 0,

                reranker_model_id TEXT NOT NULL DEFAULT '',
                reranker_router_config_id TEXT NOT NULL DEFAULT '',

                chunk_size INTEGER NOT NULL DEFAULT 512,
                chunk_overlap INTEGER NOT NULL DEFAULT 64,

                top_k INTEGER NOT NULL DEFAULT 5,
                similarity_threshold REAL NOT NULL DEFAULT 0.0,
                reranker_top_k INTEGER NOT NULL DEFAULT 3,

                document_count INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 0,

                status TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active', 'building', 'error')),

                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    if "kb_documents" not in existing_tables:
        conn.execute("""
            CREATE TABLE kb_documents (
                id TEXT PRIMARY KEY,
                knowledge_base_id TEXT NOT NULL,

                file_name TEXT NOT NULL DEFAULT '',
                file_type TEXT NOT NULL DEFAULT 'txt'
                    CHECK(file_type IN ('txt', 'markdown', 'docx', 'xlsx', 'pdf')),
                file_size INTEGER NOT NULL DEFAULT 0,
                file_hash TEXT NOT NULL DEFAULT '',
                storage_path TEXT NOT NULL DEFAULT '',

                content_text TEXT NOT NULL DEFAULT '',
                content_length INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 0,

                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'parsing', 'embedding', 'ready', 'error')),
                error_message TEXT NOT NULL DEFAULT '',

                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (knowledge_base_id)
                    REFERENCES knowledge_bases(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kb_documents_kb_id
                ON kb_documents(knowledge_base_id)
        """)

    if "kb_chunks" not in existing_tables:
        conn.execute("""
            CREATE TABLE kb_chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                knowledge_base_id TEXT NOT NULL,

                content TEXT NOT NULL DEFAULT '',
                chunk_index INTEGER NOT NULL DEFAULT 0,

                start_char INTEGER NOT NULL DEFAULT 0,
                end_char INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',

                is_embedded INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (document_id)
                    REFERENCES kb_documents(id) ON DELETE CASCADE,
                FOREIGN KEY (knowledge_base_id)
                    REFERENCES knowledge_bases(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kb_chunks_document_id
                ON kb_chunks(document_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kb_chunks_kb_id
                ON kb_chunks(knowledge_base_id)
        """)


def _migrate_v6(conn: sqlite3.Connection) -> None:
    """Migration v6: Add the singleton SeekDB remote connection configuration."""
    logger.info("Running migration v6")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seekdb_config (
            id TEXT PRIMARY KEY DEFAULT 'default',
            host TEXT NOT NULL DEFAULT '127.0.0.1',
            port INTEGER NOT NULL DEFAULT 2881,
            user TEXT NOT NULL DEFAULT 'root',
            password TEXT NOT NULL DEFAULT '',
            database_name TEXT NOT NULL DEFAULT 'misaka_kb',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _migrate_v7(conn: sqlite3.Connection) -> None:
    """Migration v7: versioned KB indexes and durable cleanup jobs.

    Existing rows continue to address the legacy vector-table name through
    the empty version string.  New writes always receive an opaque version
    and are made visible only after a complete index has been built.
    """
    logger.info("Running migration v7")
    existing_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "knowledge_bases" in existing_tables:
        kb_columns = _get_column_names(conn, "knowledge_bases")
        if "active_index_version" not in kb_columns:
            conn.execute(
                "ALTER TABLE knowledge_bases "
                "ADD COLUMN active_index_version TEXT NOT NULL DEFAULT ''"
            )

    if "kb_chunks" in existing_tables:
        chunk_columns = _get_column_names(conn, "kb_chunks")
        if "index_version" not in chunk_columns:
            conn.execute(
                "ALTER TABLE kb_chunks "
                "ADD COLUMN index_version TEXT NOT NULL DEFAULT ''"
            )
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kb_chunks_index_version
                ON kb_chunks(knowledge_base_id, index_version)
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kb_cleanup_jobs (
            id TEXT PRIMARY KEY,
            knowledge_base_id TEXT NOT NULL,
            index_version TEXT NOT NULL DEFAULT '',
            operation TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_kb_cleanup_jobs_pending
            ON kb_cleanup_jobs(status, created_at)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kb_jobs (
            id TEXT PRIMARY KEY,
            knowledge_base_id TEXT NOT NULL,
            document_id TEXT NOT NULL DEFAULT '',
            operation TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_kb_jobs_active
            ON kb_jobs(knowledge_base_id, status, updated_at)
    """)
