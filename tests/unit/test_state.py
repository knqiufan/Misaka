"""
Tests for the AppState class.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from misaka.db.models import ChatSession
from misaka.state import AppState


class TestAppState:

    def test_initial_state(self) -> None:
        page = MagicMock()
        state = AppState(page)
        assert state.current_session_id is None
        assert state.sessions == []
        assert state.messages == []
        assert state.is_streaming is False
        assert state.left_panel_open is True
        assert state.right_panel_open is True

    def test_current_session_property(self) -> None:
        page = MagicMock()
        state = AppState(page)
        state.sessions = [
            ChatSession(id="abc", title="Session A"),
            ChatSession(id="def", title="Session B"),
        ]
        state.current_session_id = "def"
        assert state.current_session is not None
        assert state.current_session.title == "Session B"

    def test_current_session_none(self) -> None:
        page = MagicMock()
        state = AppState(page)
        assert state.current_session is None

    def test_clear_streaming(self) -> None:
        page = MagicMock()
        state = AppState(page)
        state.is_streaming = True
        state.streaming_blocks = [MagicMock()]
        state.clear_streaming()
        assert state.is_streaming is False
        assert state.streaming_blocks == []

    def test_update_calls_page_update(self) -> None:
        page = MagicMock()
        state = AppState(page)
        state.update()
        page.update.assert_called_once()
