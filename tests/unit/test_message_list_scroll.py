"""Tests for MessageList async scroll scheduling (Flet 0.80+)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from misaka.state import AppState
from misaka.ui.chat.components.message_list import MessageList


@pytest.fixture
def message_list() -> MessageList:
    page = MagicMock()
    state = AppState(page)
    with patch.object(MessageList, "_build_ui", return_value=None):
        ml = MessageList(state)
    ml._list_view = MagicMock()
    ml._list_view.page = page
    ml._list_view.update = MagicMock()
    ml._empty_view = MagicMock()
    ml._empty_view.page = None
    return ml


class TestMessageListScroll:
    def test_schedule_bottom_scroll_uses_run_task(self, message_list: MessageList) -> None:
        message_list.state.is_streaming = False
        message_list._schedule_list_scroll(scroll_to_bottom=True)

        message_list.state.page.run_task.assert_called_once_with(
            message_list._scroll_list_to_bottom,
        )

    def test_schedule_anchor_scroll_passes_key(self, message_list: MessageList) -> None:
        message_list._schedule_list_scroll(anchor_key="msg-1")

        message_list.state.page.run_task.assert_called_once_with(
            message_list._scroll_list_to_anchor,
            "msg-1",
        )

    def test_throttle_skips_rapid_bottom_scroll_during_streaming(
        self, message_list: MessageList,
    ) -> None:
        message_list.state.is_streaming = True
        message_list._last_scroll_time = 1000.0
        with patch("misaka.ui.chat.components.message_list.time.monotonic", return_value=1000.05):
            message_list._schedule_list_scroll(
                scroll_to_bottom=True,
                throttle_bottom=True,
            )

        message_list.state.page.run_task.assert_not_called()

    def test_update_list_view_schedules_async_scroll_on_growth(
        self, message_list: MessageList,
    ) -> None:
        with patch.object(message_list, "_schedule_list_scroll") as schedule:
            message_list._update_list_view(auto_scroll=True, content_grew=True)

        schedule.assert_called_once_with(
            scroll_to_bottom=True,
            throttle_bottom=message_list.state.is_streaming,
        )

    def test_update_list_view_schedules_anchor_scroll(
        self, message_list: MessageList,
    ) -> None:
        with patch.object(message_list, "_schedule_list_scroll") as schedule:
            message_list._update_list_view(anchor_key="anchor-id", content_grew=True)

        schedule.assert_called_once_with(anchor_key="anchor-id")

    @pytest.mark.asyncio
    async def test_scroll_list_to_bottom_awaits_scroll_to(
        self, message_list: MessageList,
    ) -> None:
        message_list._list_view.scroll_to = AsyncMock()
        await message_list._scroll_list_to_bottom()
        message_list._list_view.scroll_to.assert_awaited_once_with(
            offset=-1, duration=0,
        )

    @pytest.mark.asyncio
    async def test_scroll_list_to_anchor_uses_scroll_key(
        self, message_list: MessageList,
    ) -> None:
        message_list._list_view.scroll_to = AsyncMock()
        await message_list._scroll_list_to_anchor("msg-42")
        message_list._list_view.scroll_to.assert_awaited_once_with(
            scroll_key="msg-42", duration=0,
        )

    def test_schedule_scroll_no_page_is_noop(self, message_list: MessageList) -> None:
        message_list.state.page = None
        message_list._schedule_list_scroll(scroll_to_bottom=True)
