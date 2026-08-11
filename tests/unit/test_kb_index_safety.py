"""Regression tests for copy-on-write knowledge-base index operations."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from misaka.services.knowledge.document_service import DocumentService
from misaka.services.knowledge.kb_service import KnowledgeBaseService
from misaka.services.knowledge.rag.abstractions import (
    ChunkData,
    DocumentParser,
    EmbeddingConfig,
    EmbeddingProvider,
    ParsedDocument,
    Reranker,
    RerankerConfig,
    RetrievalResult,
    Retriever,
    TextChunker,
    VectorStore,
)
from misaka.services.knowledge.rag.factory import RAGComponentFactory
from misaka.services.knowledge.rag_orchestrator import RAGOrchestrator


class SafetyParser(DocumentParser):
    def __init__(self) -> None:
        self.fail = False

    async def parse(self, file_path: str, file_type: str) -> ParsedDocument:
        if self.fail:
            raise RuntimeError("parser unavailable")
        return ParsedDocument(text=Path(file_path).read_text(encoding="utf-8"))

    def supported_types(self) -> list[str]:
        return ["txt"]


class SafetyChunker(TextChunker):
    def chunk(
        self,
        text: str,
        file_type: str,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        metadata: dict | None = None,
    ) -> list[ChunkData]:
        return [ChunkData(content=text, index=0, metadata=metadata or {})]


class SafetyEmbedding(EmbeddingProvider):
    async def embed_texts(
        self,
        texts: list[str],
        config: EmbeddingConfig,
        batch_size: int = 32,
    ) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    async def embed_query(self, query: str, config: EmbeddingConfig) -> list[float]:
        return [1.0, 0.0]

    def get_dimensions(self, embedding: list[float]) -> int:
        return len(embedding)


class SafetyStore(VectorStore):
    def __init__(self) -> None:
        self.tables: dict[str, dict[str, ChunkData]] = {}
        self.fail_drops = False

    def ensure_table(self, table_name: str, dimensions: int) -> None:
        self.tables.setdefault(table_name, {})

    def add_chunks(
        self, table_name: str, chunks: list[ChunkData], embeddings: list[list[float]],
    ) -> None:
        self.tables.setdefault(table_name, {}).update({
            str(chunk.metadata["chunk_db_id"]): chunk for chunk in chunks
        })

    def search(
        self, table_name: str, query_embedding: list[float], top_k: int = 5,
    ) -> list[RetrievalResult]:
        return [
            RetrievalResult(
                chunk_id=chunk_id,
                content=chunk.content,
                score=1.0,
                metadata=chunk.metadata,
            )
            for chunk_id, chunk in self.tables.get(table_name, {}).items()
        ][:top_k]

    def delete_by_ids(self, table_name: str, chunk_ids: list[str]) -> None:
        for chunk_id in chunk_ids:
            self.tables.get(table_name, {}).pop(chunk_id, None)

    def drop_table(self, table_name: str) -> None:
        if self.fail_drops:
            raise RuntimeError("remote cleanup unavailable")
        self.tables.pop(table_name, None)

    def close(self) -> None:
        return


class SafetyRetriever(Retriever):
    async def retrieve(
        self,
        query: str,
        query_embedding: list[float],
        table_name: str,
        top_k: int = 5,
        chunks_for_bm25: list[ChunkData] | None = None,
    ) -> list[RetrievalResult]:
        return []


class SafetyReranker(Reranker):
    async def rerank(
        self, query: str, results: list[RetrievalResult], config: RerankerConfig,
    ) -> list[RetrievalResult]:
        return results


class SafetyFactory(RAGComponentFactory):
    def __init__(self) -> None:
        super().__init__(":memory:")
        self.parser = SafetyParser()
        self.store = SafetyStore()

    def create_parser(self) -> DocumentParser:
        return self.parser

    def create_chunker(self) -> TextChunker:
        return SafetyChunker()

    def create_embedding_provider(self) -> EmbeddingProvider:
        return SafetyEmbedding()

    def create_vector_store(self) -> VectorStore:
        return self.store

    def create_retriever(self, vector_store: VectorStore):
        return SafetyRetriever()

    def create_reranker(self) -> Reranker:
        return SafetyReranker()


def _services(db, tmp_path, monkeypatch):
    storage_root = tmp_path / "knowledge"
    monkeypatch.setattr(
        "misaka.services.knowledge.document_service.get_kb_storage_dir",
        lambda kb_id: storage_root / kb_id,
    )
    monkeypatch.setattr(
        "misaka.services.knowledge.kb_service.get_kb_storage_dir",
        lambda kb_id: storage_root / kb_id,
    )
    factory = SafetyFactory()
    orchestrator = RAGOrchestrator(factory, db)
    kb_service = KnowledgeBaseService(db, orchestrator)
    doc_service = DocumentService(db, orchestrator)
    return factory, kb_service, doc_service


def _config() -> EmbeddingConfig:
    return EmbeddingConfig("embedding", "https://example.test", "key")


async def test_reprocess_failure_keeps_active_index_and_statistics(
    db, tmp_path, monkeypatch,
) -> None:
    factory, kb_service, doc_service = _services(db, tmp_path, monkeypatch)
    kb = kb_service.create("Safety", embedding_model_id="embedding", embedding_router_config_id="r")
    source = tmp_path / "notes.txt"
    source.write_text("known good content", encoding="utf-8")
    document = await doc_service.upload_document(kb.id, str(source), _config())
    before = kb_service.get(kb.id)
    before_chunks = db.get_kb_chunks_by_index(kb.id, before.active_index_version)

    factory.parser.fail = True
    with pytest.raises(RuntimeError, match="parser unavailable"):
        await doc_service.reprocess_document(document.id, _config())

    after = kb_service.get(kb.id)
    assert after.active_index_version == before.active_index_version
    assert db.get_kb_chunks_by_index(kb.id, after.active_index_version) == before_chunks
    assert after.chunk_count == 1
    assert kb_service.get_kb_for_chat_selection()[0]["id"] == kb.id


async def test_rebuild_missing_source_preserves_active_index(db, tmp_path, monkeypatch) -> None:
    _, kb_service, doc_service = _services(db, tmp_path, monkeypatch)
    kb = kb_service.create("Safety", embedding_model_id="embedding", embedding_router_config_id="r")
    source = tmp_path / "notes.txt"
    source.write_text("known good content", encoding="utf-8")
    document = await doc_service.upload_document(kb.id, str(source), _config())
    before = kb_service.get(kb.id)
    Path(document.storage_path).unlink()

    result = await kb_service.rebuild_embeddings(kb.id, _config())

    after = kb_service.get(kb.id)
    assert result["error_count"] == 1
    assert after.active_index_version == before.active_index_version
    assert after.chunk_count == 1
    assert kb_service.get_kb_for_chat_selection()[0]["id"] == kb.id


async def test_vector_cleanup_failure_is_durable_and_retryable(db, tmp_path, monkeypatch) -> None:
    factory, kb_service, doc_service = _services(db, tmp_path, monkeypatch)
    kb = kb_service.create("Safety", embedding_model_id="embedding", embedding_router_config_id="r")
    source = tmp_path / "notes.txt"
    source.write_text("known good content", encoding="utf-8")
    document = await doc_service.upload_document(kb.id, str(source), _config())
    old_version = kb_service.get(kb.id).active_index_version

    factory.store.fail_drops = True
    await doc_service.reprocess_document(document.id, _config())

    pending = db.get_pending_kb_cleanup_jobs()
    assert len(pending) == 1
    assert pending[0].index_version == old_version
    assert db.get_kb_chunks_by_index(kb.id, old_version)

    factory.store.fail_drops = False
    assert await kb_service.retry_pending_cleanup() == 1
    assert db.get_pending_kb_cleanup_jobs() == []
    assert db.get_kb_chunks_by_index(kb.id, old_version) == []


async def test_delete_cancels_and_waits_for_active_upload(db, tmp_path, monkeypatch) -> None:
    factory, kb_service, doc_service = _services(db, tmp_path, monkeypatch)
    kb = kb_service.create("Safety", embedding_model_id="embedding", embedding_router_config_id="r")
    source = tmp_path / "notes.txt"
    source.write_text("known good content", encoding="utf-8")

    started = asyncio.Event()
    release = asyncio.Event()
    original_embed = SafetyEmbedding.embed_texts

    async def slow_embed(self, texts, config, batch_size=32):
        started.set()
        await release.wait()
        return await original_embed(self, texts, config, batch_size)

    monkeypatch.setattr(SafetyEmbedding, "embed_texts", slow_embed)
    upload = asyncio.create_task(doc_service.upload_document(kb.id, str(source), _config()))
    await started.wait()
    processing_doc = doc_service.get_documents(kb.id)[0]

    assert await doc_service.delete_document(processing_doc.id, _config()) is True
    with pytest.raises(asyncio.CancelledError):
        await upload
    assert doc_service.get_document(processing_doc.id) is None
    assert kb_service.get_kb_for_chat_selection() == []
