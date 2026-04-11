"""
Tests for the database backend.
"""

from __future__ import annotations

import sqlite3

from misaka.db.database import DatabaseBackend
from misaka.db.migrations import run_migrations


class TestSQLiteBackend:
    """Tests for the SQLite database backend."""

    def test_create_session(self, db: DatabaseBackend) -> None:
        session = db.create_session(title="Test Session", working_directory="/tmp/test")
        assert session.id
        assert session.title == "Test Session"
        assert session.working_directory == "/tmp/test"
        assert session.project_name == "test"
        assert session.status == "active"
        assert session.mode == "agent"

    def test_get_all_sessions(self, db: DatabaseBackend) -> None:
        db.create_session(title="Session 1")
        db.create_session(title="Session 2")
        sessions = db.get_all_sessions()
        assert len(sessions) == 2

    def test_get_session(self, db: DatabaseBackend) -> None:
        created = db.create_session(title="Find Me")
        found = db.get_session(created.id)
        assert found is not None
        assert found.title == "Find Me"

    def test_get_session_not_found(self, db: DatabaseBackend) -> None:
        assert db.get_session("nonexistent") is None

    def test_update_session_title(self, db: DatabaseBackend) -> None:
        session = db.create_session(title="Old Title")
        db.update_session_title(session.id, "New Title")
        updated = db.get_session(session.id)
        assert updated is not None
        assert updated.title == "New Title"

    def test_delete_session(self, db: DatabaseBackend) -> None:
        session = db.create_session(title="Delete Me")
        assert db.delete_session(session.id) is True
        assert db.get_session(session.id) is None

    def test_delete_session_not_found(self, db: DatabaseBackend) -> None:
        assert db.delete_session("nonexistent") is False

    def test_add_and_get_messages(self, db: DatabaseBackend) -> None:
        session = db.create_session(title="Chat")
        db.add_message(session.id, "user", "Hello")
        db.add_message(session.id, "assistant", "Hi there!")
        messages, has_more = db.get_messages(session.id)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert has_more is False

    def test_clear_session_messages(self, db: DatabaseBackend) -> None:
        session = db.create_session(title="Chat")
        db.add_message(session.id, "user", "Hello")
        db.clear_session_messages(session.id)
        messages, _ = db.get_messages(session.id)
        assert len(messages) == 0
        updated = db.get_session(session.id)
        assert updated is not None
        assert updated.sdk_session_id == ""

    def test_settings(self, db: DatabaseBackend) -> None:
        assert db.get_setting("key1") is None
        db.set_setting("key1", "value1")
        assert db.get_setting("key1") == "value1"
        db.set_setting("key1", "value2")
        assert db.get_setting("key1") == "value2"

    def test_get_all_settings(self, db: DatabaseBackend) -> None:
        db.set_setting("a", "1")
        db.set_setting("b", "2")
        settings = db.get_all_settings()
        assert settings == {"a": "1", "b": "2"}

    def test_create_and_get_task(self, db: DatabaseBackend) -> None:
        session = db.create_session(title="Chat")
        task = db.create_task(session.id, "Fix bug", description="Important fix")
        assert task.title == "Fix bug"
        assert task.status == "pending"
        assert task.description == "Important fix"

        found = db.get_task(task.id)
        assert found is not None
        assert found.title == "Fix bug"

    def test_update_task(self, db: DatabaseBackend) -> None:
        session = db.create_session(title="Chat")
        task = db.create_task(session.id, "Task 1")
        updated = db.update_task(task.id, status="completed", title="Task 1 Done")
        assert updated is not None
        assert updated.status == "completed"
        assert updated.title == "Task 1 Done"

    def test_delete_task(self, db: DatabaseBackend) -> None:
        session = db.create_session(title="Chat")
        task = db.create_task(session.id, "Delete Me")
        assert db.delete_task(task.id) is True
        assert db.get_task(task.id) is None

    def test_router_config_crud(self, db: DatabaseBackend) -> None:
        config = db.create_router_config("Router A", api_key="sk-test", base_url="https://router")
        assert config.name == "Router A"
        assert config.api_key == "sk-test"
        assert config.is_active == 0

        updated = db.update_router_config(config.id, name="Router B")
        assert updated is not None
        assert updated.name == "Router B"

        assert db.activate_router_config(config.id) is True
        active = db.get_active_router_config()
        assert active is not None
        assert active.id == config.id

        assert db.delete_router_config(config.id) is True
        assert db.get_router_config(config.id) is None

    def test_get_daily_token_usage_rows(self, db) -> None:
        session = db.create_session(title="Test Session")
        import json
        usage1 = json.dumps({
            "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.01,
        })
        usage2 = json.dumps({
            "input_tokens": 200, "output_tokens": 100, "cost_usd": 0.02,
        })
        db.add_message(session.id, "assistant", "msg1", token_usage=usage1)
        db.add_message(session.id, "assistant", "msg2", token_usage=usage2)
        db.add_message(session.id, "user", "hello")
        db.add_message(session.id, "assistant", "msg3")

        rows = db.get_daily_token_usage_rows(days=30)
        assert len(rows) == 2
        for day, raw in rows:
            assert day is not None
            data = json.loads(raw)
            assert "input_tokens" in data

    def test_get_daily_token_usage_rows_empty(self, db) -> None:
        rows = db.get_daily_token_usage_rows(days=30)
        assert rows == []

    def test_migration_drops_api_providers_table(self, tmp_path) -> None:
        db_path = tmp_path / "migrate.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE _schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO _schema_version (version) VALUES (3)")
        conn.execute("CREATE TABLE api_providers (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
        conn.commit()

        run_migrations(conn)

        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='api_providers'"
        ).fetchone()
        version = conn.execute("SELECT version FROM _schema_version").fetchone()
        conn.close()

        assert row is None
        assert version is not None
        assert version[0] == 4
