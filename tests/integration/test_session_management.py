"""
Integration test: session management.

Tests session lifecycle including creation, update, archiving, and deletion.
"""

from __future__ import annotations

import pytest

from misaka.db.database import DatabaseBackend
from misaka.services.chat.session_service import SessionService
from misaka.services.task.task_service import TaskService


class TestSessionManagement:

    def test_session_lifecycle(self, db: DatabaseBackend) -> None:
        svc = SessionService(db)

        # Create
        session = svc.create(
            title="My Project",
            model="claude-sonnet-4-5",
            working_directory="/home/user/project",
            mode="code",
        )
        assert session.model == "claude-sonnet-4-5"
        assert session.mode == "code"

        # Update mode
        svc.update_mode(session.id, "plan")
        updated = svc.get(session.id)
        assert updated is not None
        assert updated.mode == "plan"

        # Archive
        svc.update_status(session.id, "archived")
        archived = svc.get(session.id)
        assert archived is not None
        assert archived.status == "archived"

        # Delete
        assert svc.delete(session.id) is True

    def test_cascade_delete(self, db: DatabaseBackend) -> None:
        session_svc = SessionService(db)
        task_svc = TaskService(db)

        session = session_svc.create(title="Test")
        task_svc.create(session.id, "Task 1")
        task_svc.create(session.id, "Task 2")

        # Deleting session should cascade to tasks
        session_svc.delete(session.id)
        tasks = task_svc.get_by_session(session.id)
        assert len(tasks) == 0

    def test_sdk_session_id_persistence(self, db: DatabaseBackend) -> None:
        svc = SessionService(db)
        session = svc.create(title="Test")
        svc.update_sdk_session_id(session.id, "sdk-session-123")
        updated = svc.get(session.id)
        assert updated is not None
        assert updated.sdk_session_id == "sdk-session-123"
