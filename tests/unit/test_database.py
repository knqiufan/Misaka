"""
Tests for the database backend.
"""

from __future__ import annotations

from misaka.db.database import DatabaseBackend


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
        # SDK session ID should be reset
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

    def test_provider_crud(self, db: DatabaseBackend) -> None:
        provider = db.create_provider("Test Provider", api_key="sk-test")
        assert provider.name == "Test Provider"
        assert provider.api_key == "sk-test"
        assert provider.is_active == 0

        # Update
        updated = db.update_provider(provider.id, name="Updated Provider")
        assert updated is not None
        assert updated.name == "Updated Provider"

        # Activate
        assert db.activate_provider(provider.id) is True
        active = db.get_active_provider()
        assert active is not None
        assert active.id == provider.id

        # Deactivate all
        db.deactivate_all_providers()
        assert db.get_active_provider() is None

        # Delete
        assert db.delete_provider(provider.id) is True
        assert db.get_provider(provider.id) is None
