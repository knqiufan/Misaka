"""Shared tool-call rendering helpers for history and streaming messages."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from misaka.db.models import MessageContentBlock
from misaka.state import StreamingBlock, StreamingToolUseBlock
from misaka.ui.chat.components.subagent_block import SubAgentBlock
from misaka.ui.chat.components.tool_call_block import ToolCallBlock
from misaka.ui.chat.components.tool_group_block import ToolCallInfo, ToolGroupBlock

TOOL_GROUP_MIN = 3
MESSAGE_TOOL_ENVELOPE_MIN = 8
HEAVY_MESSAGE_TOOL_MIN = 12
LIGHT_MESSAGE_TOOL_MAX = 3

ResultResolver = Callable[[str], tuple[str | None, bool]]


def build_result_map(
    blocks: list[MessageContentBlock],
) -> dict[str, MessageContentBlock]:
    """Map tool_use_id -> tool_result block."""
    return {
        b.tool_use_id: b
        for b in blocks
        if b.type == "tool_result" and b.tool_use_id
    }


def count_tool_uses(blocks: list[MessageContentBlock]) -> int:
    """Count tool_use blocks with a name."""
    return sum(1 for b in blocks if b.type == "tool_use" and b.name)


def segment_assistant_blocks(
    blocks: list[MessageContentBlock],
) -> list[list[MessageContentBlock]]:
    """Split blocks into segments; tool_result does not break tool_use runs."""
    segments: list[list[MessageContentBlock]] = []
    current_tool_run: list[MessageContentBlock] = []

    for block in blocks:
        if block.type == "tool_result":
            continue
        if block.type == "tool_use" and block.name:
            current_tool_run.append(block)
            continue
        if current_tool_run:
            segments.append(current_tool_run)
            current_tool_run = []
        segments.append([block])

    if current_tool_run:
        segments.append(current_tool_run)
    return segments


def make_result_resolver(
    result_map: dict[str, MessageContentBlock],
) -> ResultResolver:
    """Build a resolver that looks up results by tool_use id."""

    def resolve(tool_use_id: str) -> tuple[str | None, bool]:
        block = result_map.get(tool_use_id)
        if block is None:
            return None, False
        return block.content, block.is_error

    return resolve


def _tool_info_from_block(
    block: MessageContentBlock,
    result_map: dict[str, MessageContentBlock],
    consumed_results: set[str],
) -> ToolCallInfo:
    result_block = result_map.get(block.id or "") if block.id else None
    if block.id and result_block:
        consumed_results.add(block.id)
    return ToolCallInfo(
        name=block.name or "unknown",
        tool_input=block.input if isinstance(block.input, dict) else None,
        tool_use_id=block.id,
        is_error=result_block.is_error if result_block else False,
    )


def flush_tool_run(
    tool_blocks: list[MessageContentBlock],
    result_map: dict[str, MessageContentBlock],
    consumed_results: set[str],
    *,
    result_resolver: ResultResolver | None = None,
) -> list[ft.Control]:
    """Render a run of non-SubAgent tool_use blocks."""
    resolver = result_resolver or make_result_resolver(result_map)

    if len(tool_blocks) >= TOOL_GROUP_MIN:
        tool_infos = [
            _tool_info_from_block(b, result_map, consumed_results)
            for b in tool_blocks
        ]
        return [ToolGroupBlock(tool_infos, result_resolver=resolver)]

    controls: list[ft.Control] = []
    for block in tool_blocks:
        info = _tool_info_from_block(block, result_map, consumed_results)
        output, is_err = resolver(info.tool_use_id or "")
        controls.append(
            ToolCallBlock(
                tool_name=info.name,
                tool_input=info.tool_input,
                tool_output=output,
                is_error=is_err,
            )
        )
    return controls


def render_tool_segment(
    tool_blocks: list[MessageContentBlock],
    result_map: dict[str, MessageContentBlock],
    consumed_results: set[str],
    *,
    result_resolver: ResultResolver | None = None,
) -> list[ft.Control]:
    """Render consecutive tool_use blocks (Task -> SubAgentBlock)."""
    controls: list[ft.Control] = []
    non_subagent_run: list[MessageContentBlock] = []
    resolver = result_resolver or make_result_resolver(result_map)

    for block in tool_blocks:
        if block.name == "Task":
            if non_subagent_run:
                controls.extend(
                    flush_tool_run(
                        non_subagent_run, result_map, consumed_results,
                        result_resolver=resolver,
                    )
                )
                non_subagent_run = []
            result_block = result_map.get(block.id or "") if block.id else None
            if block.id and result_block:
                consumed_results.add(block.id)
            controls.append(
                SubAgentBlock(
                    tool_input=block.input if isinstance(block.input, dict) else None,
                    tool_output=result_block.content if result_block else None,
                    is_error=result_block.is_error if result_block else False,
                )
            )
        else:
            non_subagent_run.append(block)

    if non_subagent_run:
        controls.extend(
            flush_tool_run(
                non_subagent_run, result_map, consumed_results,
                result_resolver=resolver,
            )
        )
    return controls


def segment_streaming_blocks(
    blocks: list[StreamingBlock],
) -> list[list[StreamingBlock]]:
    """Segment streaming blocks; consecutive tools stay in one run."""
    segments: list[list[StreamingBlock]] = []
    current_tool_run: list[StreamingBlock] = []

    for block in blocks:
        if isinstance(block, StreamingToolUseBlock) and block.name:
            current_tool_run.append(block)
            continue
        if current_tool_run:
            segments.append(current_tool_run)
            current_tool_run = []
        segments.append([block])

    if current_tool_run:
        segments.append(current_tool_run)
    return segments


def flush_streaming_tool_run(
    tool_blocks: list[StreamingToolUseBlock],
) -> list[ft.Control]:
    """Render streaming tool blocks with grouping."""
    if len(tool_blocks) >= TOOL_GROUP_MIN:
        tool_infos = [
            ToolCallInfo(
                name=b.name or "unknown",
                tool_input=b.input or None,
                tool_use_id=b.id or None,
                is_error=b.is_error,
                result=b.output,
            )
            for b in tool_blocks
        ]

        def resolve(tid: str) -> tuple[str | None, bool]:
            for b in tool_blocks:
                if b.id == tid:
                    return b.output, b.is_error
            return None, False

        return [ToolGroupBlock(tool_infos, result_resolver=resolve)]

    controls: list[ft.Control] = []
    for b in tool_blocks:
        controls.append(
            ToolCallBlock(
                tool_name=b.name,
                tool_input=b.input,
                tool_output=b.output,
                is_error=b.is_error,
                initially_expanded=b.output is None,
            )
        )
    return controls


def render_streaming_tool_segment(
    tool_blocks: list[StreamingBlock],
) -> list[ft.Control]:
    """Render a streaming tool segment including Task tools."""
    controls: list[ft.Control] = []
    non_subagent: list[StreamingToolUseBlock] = []

    for block in tool_blocks:
        if not isinstance(block, StreamingToolUseBlock):
            continue
        tb = block
        if tb.name == "Task":
            if non_subagent:
                controls.extend(flush_streaming_tool_run(non_subagent))
                non_subagent = []
            controls.append(
                SubAgentBlock(
                    tool_input=tb.input,
                    tool_output=tb.output,
                    is_error=tb.is_error,
                    initially_expanded=tb.output is None,
                )
            )
        else:
            non_subagent.append(tb)

    if non_subagent:
        controls.extend(flush_streaming_tool_run(non_subagent))
    return controls
