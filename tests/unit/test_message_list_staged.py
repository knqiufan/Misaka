"""Tests for MessageList staged history loading."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from misaka.db.models import Message
from misaka.state import AppState
from misaka.ui.chat.components.message_list import (
    INITIAL_VISIBLE,
    STAGED_BATCH_SIZE,
    MessageList,
)


def _make_messages(count: int, session_id: str = "sess-1") -> list[Message]:
    return [
        Message(
            id=f"msg-{i}",
            session_id=session_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f'"message {i}"',
        )
        for i in range(count)
    ]


@pytest.fixture
def message_list() -> MessageList:
    page = MagicMock()
    state = AppState(page)
    with patch.object(MessageList, "_build_ui", return_value=None):
        ml = MessageList(state)
    ml._list_view = MagicMock()
    ml._list_view.controls = []
    ml._list_view.page = page
    ml._list_view.update = MagicMock()
    ml._empty_view = MagicMock()
    ml._empty_view.page = None
    ml._streaming_msg = MagicMock()
    ml._streaming_msg.refresh = MagicMock()
    return ml


class TestMessageListStaged:
    def test_rebuild_for_session_sync_when_few_messages(
        self, message_list: MessageList,
    ) -> None:
        messages = _make_messages(INITIAL_VISIBLE)
        message_list.state.messages = messages
        with patch.object(message_list, "_get_or_create_item", side_effect=lambda m: MagicMock(key=m.id)):
            message_list._rebuild_for_session()

        assert message_list._staged_build_in_progress is False
        assert message_list._rendered_message_ids == [m.id for m in messages]

    def test_rebuild_for_session_staged_tail_first(
        self, message_list: MessageList,
    ) -> None:
        total = INITIAL_VISIBLE + 3
        messages = _make_messages(total)
        message_list.state.messages = messages
        created: list[str] = []

        def track_create(msg: Message, **kwargs: object) -> MagicMock:
            created.append(msg.id)
            return MagicMock(key=msg.id)

        with patch.object(message_list, "_get_or_create_item", side_effect=track_create):
            with patch.object(message_list, "_schedule_staged_build_remaining") as schedule:
                message_list._rebuild_for_session()

        tail_ids = [m.id for m in messages[-INITIAL_VISIBLE:]]
        assert message_list._staged_build_in_progress is True
        assert message_list._rendered_message_ids == tail_ids
        assert created == tail_ids
        schedule.assert_called_once()
        token, head = schedule.call_args[0]
        assert token == message_list._staged_build_token
        assert head == messages[:-INITIAL_VISIBLE]

    def test_append_message_queues_during_staged_build(
        self, message_list: MessageList,
    ) -> None:
        message_list._staged_build_in_progress = True
        msg = _make_messages(1)[0]
        message_list.append_message(msg)
        assert message_list._pending_append_messages == [msg]

    def test_prepend_queues_during_staged_build(
        self, message_list: MessageList,
    ) -> None:
        message_list._staged_build_in_progress = True
        message_list._rendered_message_ids = ["visible"]
        older = _make_messages(2)
        message_list.state.messages = older + [
            Message(id="visible", session_id="s", role="user", content='"hi"'),
        ]
        message_list.prepend_older_messages(older)
        assert len(message_list._pending_prepends) == 1
        queued_msgs, anchor = message_list._pending_prepends[0]
        assert queued_msgs == older
        assert anchor == "visible"

    def test_cancel_staged_build_invalidates_token(
        self, message_list: MessageList,
    ) -> None:
        old_token = message_list._staged_build_token
        message_list._staged_build_in_progress = True
        message_list._cancel_staged_build()
        assert message_list._staged_build_token == old_token + 1
        assert message_list._staged_build_in_progress is False

    @pytest.mark.asyncio
    async def test_staged_build_remaining_inserts_batches(
        self, message_list: MessageList,
    ) -> None:
        remaining = _make_messages(STAGED_BATCH_SIZE + 1)
        message_list._staged_build_token = 1
        message_list._rendered_message_ids = ["tail"]

        with patch.object(message_list, "_get_or_create_item", side_effect=lambda m: MagicMock(key=m.id)):
            await message_list._staged_build_remaining(1, remaining)

        assert message_list._staged_build_in_progress is False
        assert message_list._rendered_message_ids[0] == remaining[0].id
        assert len(message_list._list_view.controls) == len(remaining)

    @pytest.mark.asyncio
    async def test_staged_build_remaining_aborts_on_token_mismatch(
        self, message_list: MessageList,
    ) -> None:
        remaining = _make_messages(4)
        message_list._staged_build_token = 2
        with patch.object(message_list, "_get_or_create_item", side_effect=lambda m: MagicMock(key=m.id)):
            await message_list._staged_build_remaining(1, remaining)

        assert message_list._list_view.controls == []
