"""
Row-to-model mapping functions for the SQLite backend.

Converts ``sqlite3.Row`` objects into typed dataclass instances.
"""

from __future__ import annotations

import sqlite3

from misaka.db.models import (
    ChatSession,
    KBChunk,
    KBDocument,
    KnowledgeBase,
    Message,
    RouterConfig,
    RouterModel,
    TaskItem,
)


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


def row_to_router_model(row: sqlite3.Row) -> RouterModel:
    return RouterModel(
        id=row["id"],
        router_config_id=row["router_config_id"],
        model_id=row["model_id"],
        model_type=row["model_type"],
        is_selected=row["is_selected"],
        created_at=row["created_at"],
    )


def row_to_knowledge_base(row: sqlite3.Row) -> KnowledgeBase:
    return KnowledgeBase(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        embedding_model_id=row["embedding_model_id"],
        embedding_router_config_id=row["embedding_router_config_id"],
        embedding_dimensions=row["embedding_dimensions"],
        reranker_model_id=row["reranker_model_id"],
        reranker_router_config_id=row["reranker_router_config_id"],
        chunk_size=row["chunk_size"],
        chunk_overlap=row["chunk_overlap"],
        top_k=row["top_k"],
        similarity_threshold=row["similarity_threshold"],
        reranker_top_k=row["reranker_top_k"],
        document_count=row["document_count"],
        chunk_count=row["chunk_count"],
        status=row["status"],
        active_index_version=row["active_index_version"],
        active_index_fingerprint=row["active_index_fingerprint"],
        active_vector_table_name=row["active_vector_table_name"],
        active_vector_backend_fingerprint=row["active_vector_backend_fingerprint"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_kb_document(row: sqlite3.Row) -> KBDocument:
    return KBDocument(
        id=row["id"],
        knowledge_base_id=row["knowledge_base_id"],
        file_name=row["file_name"],
        file_type=row["file_type"],
        file_size=row["file_size"],
        file_hash=row["file_hash"],
        storage_path=row["storage_path"],
        content_text=row["content_text"],
        content_length=row["content_length"],
        chunk_count=row["chunk_count"],
        status=row["status"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_kb_chunk(row: sqlite3.Row) -> KBChunk:
    return KBChunk(
        id=row["id"],
        document_id=row["document_id"],
        knowledge_base_id=row["knowledge_base_id"],
        content=row["content"],
        chunk_index=row["chunk_index"],
        start_char=row["start_char"],
        end_char=row["end_char"],
        metadata_json=row["metadata_json"],
        is_embedded=row["is_embedded"],
        index_version=row["index_version"],
        created_at=row["created_at"],
    )
