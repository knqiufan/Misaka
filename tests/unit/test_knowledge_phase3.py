"""Regression coverage for the final knowledge-base audit fixes."""

from __future__ import annotations

from pathlib import Path

import pytest

from misaka.db.models import KBDocument, KnowledgeBase
from misaka.services.knowledge.document_service import SUPPORTED_EXTENSIONS
from misaka.services.knowledge.rag.abstractions import (
    ChunkData,
    DocumentParser,
    EmbeddingConfig,
    EmbeddingProvider,
    ParsedDocument,
    ParsedDocumentSegment,
    Reranker,
    RerankerConfig,
    Retriever,
    TextChunker,
    VectorStore,
)
from misaka.services.knowledge.rag.factory import RAGComponentFactory
from misaka.services.knowledge.rag_orchestrator import RAGOrchestrator


def test_database_rejects_invalid_retrieval_configuration(db) -> None:
    with pytest.raises(ValueError, match="Chunk overlap"):
        db.create_knowledge_base(KnowledgeBase(
            id="invalid", name="Invalid", chunk_size=64, chunk_overlap=64,
        ))

    kb = KnowledgeBase(id="valid", name="Valid")
    db.create_knowledge_base(kb)
    with pytest.raises(ValueError, match="Similarity threshold"):
        db.update_knowledge_base(kb.id, similarity_threshold=float("nan"))


def test_document_page_does_not_materialize_content_and_slices_are_bounded(db) -> None:
    kb = KnowledgeBase(id="kb-page", name="Paged")
    db.create_knowledge_base(kb)
    db.create_kb_document(KBDocument(
        id="doc-page",
        knowledge_base_id=kb.id,
        file_name="large.txt",
        content_text="abcdef" * 10_000,
        content_length=60_000,
    ))

    page = db.get_kb_documents_page(kb.id, 0, 100)
    assert len(page) == 1
    assert page[0].content_text == ""
    assert db.get_kb_document_content_slice("doc-page", 10, 5) == "efabc"


def test_xls_is_not_claimed_as_a_supported_format() -> None:
    assert ".xls" not in SUPPORTED_EXTENSIONS


class _SegmentParser(DocumentParser):
    async def parse(self, file_path: str, file_type: str) -> ParsedDocument:
        return ParsedDocument(
            text="page one\n\npage two",
            segments=[
                ParsedDocumentSegment("page one", {"page": 1}),
                ParsedDocumentSegment("page two", {"page": 2}),
            ],
        )

    def supported_types(self) -> list[str]:
        return ["txt"]


class _Chunker(TextChunker):
    def chunk(self, text, file_type, chunk_size=512, chunk_overlap=64, metadata=None):
        return [ChunkData(text, 0, metadata=metadata or {})]


class _Embedding(EmbeddingProvider):
    async def embed_texts(self, texts, config, batch_size=32):
        return [[1.0] for _ in texts]

    async def embed_query(self, query, config):
        return [1.0]

    def get_dimensions(self, embedding):
        return len(embedding)


class _Store(VectorStore):
    def __init__(self) -> None:
        self.chunks: list[ChunkData] = []

    def ensure_table(self, table_name, dimensions):
        return None

    def add_chunks(self, table_name, chunks, embeddings):
        self.chunks.extend(chunks)

    def search(self, table_name, query_embedding, top_k=5):
        return []

    def delete_by_ids(self, table_name, chunk_ids):
        return None

    def drop_table(self, table_name):
        return None

    def close(self):
        return None


class _Retriever(Retriever):
    async def retrieve(self, query, query_embedding, table_name, top_k=5, chunks_for_bm25=None):
        return []


class _Reranker(Reranker):
    async def rerank(self, query, results, config: RerankerConfig):
        return results


class _Factory(RAGComponentFactory):
    def __init__(self) -> None:
        super().__init__(":memory:")
        self.store = _Store()

    def create_parser(self):
        return _SegmentParser()

    def create_chunker(self):
        return _Chunker()

    def create_embedding_provider(self):
        return _Embedding()

    def create_vector_store(self):
        return self.store

    def create_retriever(self, vector_store):
        return _Retriever()

    def create_reranker(self):
        return _Reranker()


async def test_ingest_preserves_pdf_page_or_sheet_segment_metadata(db, tmp_path: Path) -> None:
    factory = _Factory()
    orchestrator = RAGOrchestrator(factory, db)
    kb = KnowledgeBase(id="segmented", name="Segmented")
    source = tmp_path / "segments.txt"
    source.write_text("irrelevant", encoding="utf-8")

    result = await orchestrator.ingest_document(
        str(source),
        "txt",
        kb,
        EmbeddingConfig("embed", "https://example.test", "key"),
    )

    assert result.chunk_count == 2
    assert [chunk.metadata["page"] for chunk in result.chunks] == [1, 2]
    assert [chunk.index for chunk in result.chunks] == [0, 1]
