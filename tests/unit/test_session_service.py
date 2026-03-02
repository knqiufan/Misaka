"""
Tests for the session service.
"""

from __future__ import annotations

import pytest

from misaka.services.chat.session_service import SessionService


@pytest.fixture
def session_service(db) -> SessionService:
    return SessionService(db)


class TestSessionService:

    def test_create_and_get_all(self, session_service: SessionService) -> None:
        session_service.create(title="Test 1")
        session_service.create(title="Test 2")
        sessions = session_service.get_all()
        assert len(sessions) == 2

    def test_create_with_working_directory(self, session_service: SessionService) -> None:
        session = session_service.create(
            title="Project",
            working_directory="/home/user/project",
        )
        assert session.working_directory == "/home/user/project"
        assert session.project_name == "project"

    def test_update_title(self, session_service: SessionService) -> None:
        session = session_service.create(title="Old")
        session_service.update_title(session.id, "New")
        updated = session_service.get(session.id)
        assert updated is not None
        assert updated.title == "New"

    def test_delete(self, session_service: SessionService) -> None:
        session = session_service.create(title="Delete Me")
        assert session_service.delete(session.id) is True
        assert session_service.get(session.id) is None
