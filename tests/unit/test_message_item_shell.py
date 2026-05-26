"""Tests for MessageItemShell (P1-B)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from misaka.db.models import Message
from misaka.ui.chat.components.message_item_shell import MessageItemShell


@pytest.mark.asyncio
async def test_shell_materialize_calls_on_replaced() -> None:
    message = Message(
        id="m1",
        session_id="s1",
        role="assistant",
        content="[]",
    )
    replaced: list[object] = []

    shell = MessageItemShell(
        message,
        assistant_label="Claude",
        tool_count=15,
        build_full_item=lambda: MagicMock(key="m1"),
        on_replaced=lambda c: replaced.append(c),
    )
    await shell._load_async()
    assert shell._loaded is True
    assert len(replaced) == 1
