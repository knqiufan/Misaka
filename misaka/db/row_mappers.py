"""
Row-to-model mapping functions for the SQLite backend.

Converts ``sqlite3.Row`` objects into typed dataclass instances.
"""

from __future__ import annotations

import sqlite3

from misaka.db.models import ChatSession, Message, RouterConfig, TaskItem


def row_to_session(row: sqlite3.Row) -> ChatSession:
    return ChatSession(
        id=row["id"],
        title=row["title"],
        model=row["model"],
        system_prompt=row["system_prompt"],
        working_directory=row["working_directory"],
        project_name=row["project_name"],
        sdk_session_id=row["sdk_session_id"],
        status=row["status"],
        mode=row["mode"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_message(row: sqlite3.Row) -> Message:
    return Message(
        id=row["id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
        token_usage=row["token_usage"],
        _rowid=row["_rowid"] if "_rowid" in row.keys() else None,  # noqa: SIM118
    )


def row_to_task(row: sqlite3.Row) -> TaskItem:
    return TaskItem(
        id=row["id"],
        session_id=row["session_id"],
        title=row["title"],
        status=row["status"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_router_config(row: sqlite3.Row) -> RouterConfig:
    return RouterConfig(
        id=row["id"],
        name=row["name"],
        api_key=row["api_key"],
        base_url=row["base_url"],
        main_model=row["main_model"],
        haiku_model=row["haiku_model"],
        opus_model=row["opus_model"],
        sonnet_model=row["sonnet_model"],
        agent_team=bool(row["agent_team"]),
        config_json=row["config_json"],
        is_active=row["is_active"],
        sort_order=row["sort_order"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
