"""Tests for persistent vector-backend rebuild state."""

from __future__ import annotations

from misaka.db.models import KBChunk, KBDocument
from misaka.services.knowledge.kb_service import KnowledgeBaseService


def test_backend_switch_marks_only_kbs_with_documents(db) -> None:
    service = KnowledgeBaseService(db)
    populated = service.create("Populated")
    empty = service.create("Empty")
    db.create_kb_document(
        KBDocument(
            id="doc-1",
            knowledge_base_id=populated.id,
            file_name="notes.txt",
        )
    )
    db.create_kb_chunks_batch([
        KBChunk(
            id="chunk-1",
            document_id="doc-1",
            knowledge_base_id=populated.id,
            content="Indexed note",
            is_embedded=1,
        ),
    ])
    db.update_knowledge_base(populated.id, document_count=1, chunk_count=1)

    service.mark_all_indexes_stale()

    assert service.is_index_stale(populated.id) is True
    assert service.is_index_stale(empty.id) is False
    assert service.get_kb_for_chat_selection() == []

    service.mark_index_rebuilt(populated.id)
    assert service.is_index_stale(populated.id) is False
    assert service.get_kb_for_chat_selection()[0]["id"] == populated.id
