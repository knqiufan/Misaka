"""Knowledge-base upload and chat RAG flow across every vector backend."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from misaka.services.chat.preprocessors import RAGPreprocessor
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
    TextChunker,
)
from misaka.services.knowledge.rag.factory import RAGComponentFactory
from misaka.services.knowledge.rag_orchestrator import RAGOrchestrator


class FlowParser(DocumentParser):
    async def parse(self, file_path: str, file_type: str) -> ParsedDocument:
        return ParsedDocument(text=Path(file_path).read_text(encoding="utf-8"))

    def supported_types(self) -> list[str]:
        return ["txt"]


class FlowChunker(TextChunker):
    def chunk(
        self,
        text: str,
        file_type: str,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        metadata: dict | None = None,
    ) -> list[ChunkData]:
        return [ChunkData(content=text, index=0, metadata=metadata or {})]


class FlowEmbedding(EmbeddingProvider):
    async def embed_texts(
        self,
        texts: list[str],
        config: EmbeddingConfig,
        batch_size: int = 32,
    ) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    async def embed_query(
        self,
        query: str,
        config: EmbeddingConfig,
    ) -> list[float]:
        return [1.0, 0.0]

    def get_dimensions(self, embedding: list[float]) -> int:
        return len(embedding)


class FlowReranker(Reranker):
    async def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        config: RerankerConfig,
    ) -> list[RetrievalResult]:
        return results


class FlowFactory(RAGComponentFactory):
    def create_parser(self) -> DocumentParser:
        return FlowParser()

    def create_chunker(self) -> TextChunker:
        return FlowChunker()

    def create_embedding_provider(self) -> EmbeddingProvider:
        return FlowEmbedding()

    def create_reranker(self) -> Reranker:
        return FlowReranker()


class MemoryCollection:
    def __init__(self) -> None:
        self.rows: dict[str, tuple[str, dict]] = {}

    def upsert(self, *, ids, embeddings, documents, metadatas) -> None:
        self.rows.update(
            {
                item_id: (document, metadata)
                for item_id, document, metadata in zip(
                    ids,
                    documents,
                    metadatas,
                    strict=False,
                )
            }
        )

    def refresh_index(self) -> None:
        return

    def query(self, **kwargs):
        return self._results()

    def hybrid_search(self, **kwargs):
        return self._results()

    def delete(self, *, ids) -> None:
        for item_id in ids:
            self.rows.pop(item_id, None)

    def _results(self) -> dict:
        ids = list(self.rows)
        return {
            "ids": [ids],
            "documents": [[self.rows[item_id][0] for item_id in ids]],
            "metadatas": [[self.rows[item_id][1] for item_id in ids]],
            "distances": [[0.1 for _ in ids]],
        }


class MemoryClient:
    def __init__(self, **kwargs) -> None:
        self.collections: dict[str, MemoryCollection] = {}

    def get_or_create_collection(self, name, **kwargs):
        return self.collections.setdefault(name, MemoryCollection())

    def get_collection(self, name, **kwargs):
        return self.collections[name]

    def delete_collection(self, name) -> None:
        self.collections.pop(name, None)


def _install_memory_pyseekdb(monkeypatch) -> None:
    module = ModuleType("pyseekdb")
    module.Client = MemoryClient
    module.Configuration = lambda **kwargs: kwargs
    module.HNSWConfiguration = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "pyseekdb", module)


@pytest.mark.parametrize(
    ("vector_backend", "factory_backend", "seekdb_mode"),
    [
        ("sqlite", "langchain", ""),
        ("seekdb_embedded", "seekdb", "seekdb_embedded"),
        ("seekdb_remote", "seekdb", "seekdb_remote"),
    ],
)
async def test_create_upload_and_chat_rag_flow(
    db,
    tmp_path,
    monkeypatch,
    vector_backend,
    factory_backend,
    seekdb_mode,
) -> None:
    if factory_backend == "seekdb":
        _install_memory_pyseekdb(monkeypatch)

    storage_root = tmp_path / "knowledge"
    monkeypatch.setattr(
        "misaka.services.knowledge.document_service.get_kb_storage_dir",
        lambda kb_id: storage_root / kb_id,
    )
    monkeypatch.setattr(
        "misaka.services.knowledge.kb_service.get_kb_storage_dir",
        lambda kb_id: storage_root / kb_id,
    )

    factory = FlowFactory(
        db._db_path,
        backend=factory_backend,
        seekdb_mode=seekdb_mode,
        seekdb_config={
            "host": "localhost",
            "port": 2881,
            "user": "root",
            "password": "",
            "database_name": "misaka_kb",
        },
    )
    orchestrator = RAGOrchestrator(factory, db)
    kb_service = KnowledgeBaseService(db, orchestrator)
    document_service = DocumentService(db, orchestrator)
    kb = kb_service.create(
        "Backend Flow",
        embedding_model_id="embed-model",
        embedding_router_config_id="router-1",
    )
    source = tmp_path / f"{vector_backend}.txt"
    source.write_text("SeekDB and sqlite-vec both support Misaka RAG.", encoding="utf-8")
    embedding_config = EmbeddingConfig(
        model_id="embed-model",
        base_url="https://example.test",
        api_key="test",
    )

    document = await document_service.upload_document(
        kb.id,
        str(source),
        embedding_config,
    )
    kb_service.update_statistics(kb.id)

    model_info = SimpleNamespace(
        model_id="embed-model",
        router_config_id="router-1",
        base_url="https://example.test",
        api_key="test",
    )
    router_service = SimpleNamespace(
        get_models_by_config=lambda config_id: [model_info]
    )
    preprocessor = RAGPreprocessor(kb_service, orchestrator, router_service)
    context = {"selected_kb_ids": [kb.id]}
    augmented, _ = await preprocessor.process(
        "Which vector backends are supported?",
        [],
        context,
    )

    assert document.status == "ready"
    assert document.chunk_count == 1
    assert context["_rag_results"]
    assert context["_rag_results"][0].document_name == source.name
    assert "Misaka RAG" in augmented
