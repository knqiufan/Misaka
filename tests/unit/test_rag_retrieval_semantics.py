"""Regression coverage for the Phase 2 retrieval semantics fixes."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from misaka.db.models import KBDocument, KnowledgeBase
from misaka.services.chat.preprocessors import RAGPreprocessor
from misaka.services.knowledge.rag.abstractions import (
    ChunkData,
    EmbeddingConfig,
    EmbeddingProvider,
    KBRetrievalConfig,
    Reranker,
    RerankerConfig,
    RetrievalResult,
    Retriever,
)
from misaka.services.knowledge.rag.factory import RAGComponentFactory
from misaka.services.knowledge.rag.langchain.retriever import LCHybridRetriever
from misaka.services.knowledge.rag_orchestrator import (
    RAGOrchestrator,
    RAGRetrievalOutcome,
)


class _Embedding(EmbeddingProvider):
    async def embed_texts(self, texts, config, batch_size=32):
        return [[1.0] for _ in texts]

    async def embed_query(self, query, config):
        return [1.0]

    def get_dimensions(self, embedding):
        return len(embedding)


class _SlowEmbedding(_Embedding):
    async def embed_query(self, query, config):
        await asyncio.sleep(60)
        return [1.0]


class _Reranker(Reranker):
    async def rerank(self, query, results, config):
        return results


class _RecordingReranker(_Reranker):
    def __init__(self) -> None:
        self.model_ids: list[str] = []

    async def rerank(self, query, results, config):
        self.model_ids.append(config.model_id)
        return results


class _Retriever(Retriever):
    requires_bm25_chunks = False

    def __init__(self, *, failing_tables: set[str] | None = None) -> None:
        self.calls: list[tuple[str, int]] = []
        self.failing_tables = failing_tables or set()

    async def retrieve(self, query, query_embedding, table_name, top_k=5, chunks_for_bm25=None):
        self.calls.append((table_name, top_k))
        if table_name in self.failing_tables:
            raise RuntimeError("backend unavailable")
        return [
            RetrievalResult(
                chunk_id=f"{table_name}-low",
                content="low relevance",
                score=0.2,
                metadata={"document_id": f"doc-{table_name}", "chunk_index": 0},
            ),
            RetrievalResult(
                chunk_id=f"{table_name}-high",
                content="high relevance",
                score=0.8,
                metadata={"document_id": f"doc-{table_name}", "chunk_index": 1},
            ),
        ][:top_k]


class _Factory(RAGComponentFactory):
    def __init__(self, retriever, embedding=None, reranker=None) -> None:
        super().__init__(":memory:")
        self.retriever = retriever
        self.embedding = embedding or _Embedding()
        self.reranker = reranker or _Reranker()

    def create_embedding_provider(self):
        return self.embedding

    def create_retriever(self, vector_store):
        return self.retriever

    def create_reranker(self):
        return self.reranker

    def create_parser(self):  # pragma: no cover - retrieval tests only
        return SimpleNamespace()

    def create_chunker(self):  # pragma: no cover - retrieval tests only
        return SimpleNamespace()

    def create_vector_store(self):  # pragma: no cover - retrieval tests only
        return SimpleNamespace()


def _create_kb_and_document(db, kb_id: str) -> KnowledgeBase:
    kb = KnowledgeBase(
        id=kb_id,
        name=kb_id,
        embedding_model_id="embed",
        embedding_router_config_id="router",
    )
    db.create_knowledge_base(kb)
    db.create_kb_document(KBDocument(
        id=f"doc-{kb_id}",
        knowledge_base_id=kb_id,
        file_name=f"{kb_id}.txt",
        status="ready",
    ))
    return kb


def test_rrf_merges_bm25_and_vector_hits_by_real_chunk_id() -> None:
    retriever = LCHybridRetriever(SimpleNamespace())
    chunk = ChunkData(
        content="needle keyword",
        index=0,
        metadata={"chunk_db_id": "uuid-1", "document_id": "doc-1"},
    )
    vector = RetrievalResult("uuid-1", chunk.content, 0.9, dict(chunk.metadata))

    bm25 = retriever._bm25_search(
        "needle",
        [chunk, ChunkData("other", 1), ChunkData("different", 2)],
        top_k=1,
    )
    fused = retriever._rrf_fusion([vector], bm25, top_k=5)

    assert [result.chunk_id for result in fused] == ["uuid-1"]
    assert fused[0].score > retriever._vector_weight / 60


def test_bm25_fallback_id_does_not_collide_between_documents() -> None:
    chunk_a = ChunkData("needle one", 0, metadata={"document_id": "doc-a"})
    chunk_b = ChunkData("needle two", 0, metadata={"document_id": "doc-b"})

    result_a = LCHybridRetriever._bm25_search(
        "needle", [chunk_a, ChunkData("other", 1), ChunkData("different", 2)], top_k=1,
    )[0]
    result_b = LCHybridRetriever._bm25_search(
        "needle", [chunk_b, ChunkData("other", 1), ChunkData("different", 2)], top_k=1,
    )[0]

    assert result_a.chunk_id != result_b.chunk_id
    assert result_a.chunk_id.startswith("doc-a")
    assert result_b.chunk_id.startswith("doc-b")


async def test_per_kb_top_k_threshold_and_final_top_k_are_applied(db) -> None:
    kb_one = _create_kb_and_document(db, "kb-one")
    kb_two = _create_kb_and_document(db, "kb-two")
    retriever = _Retriever()
    orchestrator = RAGOrchestrator(_Factory(retriever), db)
    configs = {
        kb_one.id: EmbeddingConfig("embed", "https://example.test", "key"),
        kb_two.id: EmbeddingConfig("embed", "https://example.test", "key"),
    }

    outcome = await orchestrator.retrieve_with_diagnostics(
        query="query",
        kb_ids=[kb_one.id, kb_two.id],
        embedding_configs=configs,
        top_k=2,
        kb_retrieval_configs={
            kb_one.id: KBRetrievalConfig(top_k=2, similarity_threshold=0.75),
            kb_two.id: KBRetrievalConfig(top_k=1, similarity_threshold=0.0),
        },
    )

    assert {top_k for _, top_k in retriever.calls} == {1, 2}
    assert len(outcome.results) == 2
    assert {result.knowledge_base_id for result in outcome.results} == {kb_one.id, kb_two.id}
    assert all(result.score == 1.0 for result in outcome.results)


async def test_partial_failure_preserves_other_kb_results(db) -> None:
    healthy = _create_kb_and_document(db, "kb-healthy")
    failing = _create_kb_and_document(db, "kb-failing")
    failing_table = RAGOrchestrator._get_table_name(failing.id)
    orchestrator = RAGOrchestrator(_Factory(_Retriever(failing_tables={failing_table})), db)
    config = EmbeddingConfig("embed", "https://example.test", "key")

    outcome = await orchestrator.retrieve_with_diagnostics(
        query="query",
        kb_ids=[healthy.id, failing.id],
        embedding_configs={healthy.id: config, failing.id: config},
    )

    assert outcome.timed_out is False
    assert outcome.results
    assert failing.id in outcome.per_kb_errors
    assert healthy.id not in outcome.per_kb_errors


async def test_each_kb_uses_its_own_reranker_policy(db) -> None:
    kb_one = _create_kb_and_document(db, "kb-rerank-one")
    kb_two = _create_kb_and_document(db, "kb-rerank-two")
    recording_reranker = _RecordingReranker()
    orchestrator = RAGOrchestrator(
        _Factory(_Retriever(), reranker=recording_reranker),
        db,
    )
    config = EmbeddingConfig("embed", "https://example.test", "key")

    await orchestrator.retrieve_with_diagnostics(
        query="query",
        kb_ids=[kb_one.id, kb_two.id],
        embedding_configs={kb_one.id: config, kb_two.id: config},
        kb_retrieval_configs={
            kb_one.id: KBRetrievalConfig(
                reranker_config=RerankerConfig("rank-one", "https://rank.test", "key"),
            ),
            kb_two.id: KBRetrievalConfig(
                reranker_config=RerankerConfig("rank-two", "https://rank.test", "key"),
            ),
        },
    )

    assert recording_reranker.model_ids == ["rank-one", "rank-two"]


async def test_global_deadline_returns_structured_timeout(db, monkeypatch) -> None:
    kb = _create_kb_and_document(db, "kb-slow")
    orchestrator = RAGOrchestrator(_Factory(_Retriever(), _SlowEmbedding()), db)
    monkeypatch.setattr(
        "misaka.services.knowledge.rag_orchestrator.RETRIEVAL_DEADLINE_SECONDS", 0.01,
    )

    outcome = await orchestrator.retrieve_with_diagnostics(
        query="query",
        kb_ids=[kb.id],
        embedding_configs={
            kb.id: EmbeddingConfig("embed", "https://example.test", "key"),
        },
    )

    assert outcome == RAGRetrievalOutcome(timed_out=True)


def test_preprocessor_builds_each_kb_retrieval_policy(db) -> None:
    from misaka.services.knowledge.kb_service import KnowledgeBaseService

    kb = _create_kb_and_document(db, "kb-policy")
    db.update_knowledge_base(
        kb.id,
        top_k=7,
        similarity_threshold=0.42,
        reranker_model_id="rerank",
        reranker_router_config_id="rerank-router",
        reranker_top_k=4,
    )
    model_info = SimpleNamespace(
        model_id="embed",
        router_config_id="router",
        base_url="https://embed.test",
        api_key="embed-key",
    )
    reranker_info = SimpleNamespace(
        model_id="rerank",
        router_config_id="rerank-router",
        base_url="https://rerank.test",
        api_key="rerank-key",
    )
    router_service = SimpleNamespace(
        get_models_by_config=lambda config_id: (
            [model_info] if config_id == "router" else [reranker_info]
        ),
    )
    preprocessor = RAGPreprocessor(
        KnowledgeBaseService(db),
        SimpleNamespace(),
        router_service,
    )

    embedding_configs, policies = preprocessor._build_rag_configs([kb.id])

    assert embedding_configs[kb.id].model_id == "embed"
    assert policies[kb.id].top_k == 7
    assert policies[kb.id].similarity_threshold == 0.42
    assert policies[kb.id].reranker_config == RerankerConfig(
        "rerank", "https://rerank.test", "rerank-key", top_n=4,
    )
