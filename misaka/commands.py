"""Slash command definitions.

Built-in commands available via the "/" trigger in the message input,
mirroring the Claude Code CLI command set.
"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass
class SlashCommand:
    """A slash command that can be triggered from the input box."""

    name: str
    description: str
    icon: str
    immediate: bool
    prompt: str = ""


BUILT_IN_COMMANDS: list[SlashCommand] = [
    SlashCommand(
        name="model",
        description="切换模型",
        icon=ft.Icons.MODEL_TRAINING,
        immediate=True,
    ),
    SlashCommand(
        name="help",
        description="显示可用命令和提示",
        icon=ft.Icons.HELP_OUTLINE,
        immediate=True,
    ),
    SlashCommand(
        name="clear",
        description="清空对话历史记录",
        icon=ft.Icons.DELETE_SWEEP,
        immediate=True,
    ),
    SlashCommand(
        name="cost",
        description="显示 Token 用量统计",
        icon=ft.Icons.MONETIZATION_ON_OUTLINED,
        immediate=True,
    ),
    SlashCommand(
        name="compact",
        description="压缩对话上下文",
        icon=ft.Icons.COMPRESS,
        immediate=False,
        prompt="Compress and summarize the conversation context so far, "
               "preserving key decisions and context.",
    ),
    SlashCommand(
        name="doctor",
        description="诊断提供商健康状态",
        icon=ft.Icons.HEALTH_AND_SAFETY,
        immediate=True,
    ),
    SlashCommand(
        name="init",
        description="初始化 CLAUDE.md 项目文件",
        icon=ft.Icons.NOTE_ADD,
        immediate=False,
        prompt="Initialize a CLAUDE.md file for this project with useful "
               "context, conventions, and instructions.",
    ),
    SlashCommand(
        name="review",
        description="审查代码质量",
        icon=ft.Icons.RATE_REVIEW,
        immediate=False,
        prompt="Review code quality in this project. Look for bugs, "
               "anti-patterns, and suggest improvements.",
    ),
    SlashCommand(
        name="terminal-setup",
        description="配置终端设置",
        icon=ft.Icons.TERMINAL,
        immediate=False,
        prompt="Help me configure my terminal for optimal use with "
               "Claude Code. Check current setup and suggest improvements.",
    ),
    SlashCommand(
        name="memory",
        description="编辑项目记忆文件",
        icon=ft.Icons.PSYCHOLOGY,
        immediate=False,
        prompt="Show the current CLAUDE.md project memory file and "
               "help me review or edit it.",
    ),
]

COMMAND_MAP: dict[str, SlashCommand] = {cmd.name: cmd for cmd in BUILT_IN_COMMANDS}


def filter_commands(query: str) -> list[SlashCommand]:
    """Return commands whose name starts with the given query prefix."""
    q = query.lower().lstrip("/")
    if not q:
        return list(BUILT_IN_COMMANDS)
    return [cmd for cmd in BUILT_IN_COMMANDS if cmd.name.startswith(q)]
