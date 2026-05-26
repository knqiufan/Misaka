"""Tests for MessageToolEnvelope (P1-A)."""

from __future__ import annotations

import flet as ft

from misaka.ui.chat.components.message_tool_envelope import (
    MessageToolEnvelope,
    compute_tool_type_summary,
)


class TestMessageToolEnvelope:
    def test_initially_collapsed_without_children(self) -> None:
        child = ft.Text("tool")
        env = MessageToolEnvelope(
            [child],
            tool_count=10,
            type_summary="Glob x10",
        )
        assert env._children_host is not None
        assert env._children_host.controls == []

    def test_type_summary(self) -> None:
        summary = compute_tool_type_summary(["Glob", "Glob", "Bash"])
        assert "Glob x2" in summary
        assert "Bash x1" in summary

    def test_expand_mounts_children(self) -> None:
        child = ft.Text("tool-detail")
        env = MessageToolEnvelope(
            [child],
            tool_count=8,
            type_summary="Glob x8",
        )
        assert env._expanded is False
        env._toggle(None)  # type: ignore[arg-type]
        assert env._expanded is True
        assert child in env._children_host.controls  # type: ignore[union-attr]
