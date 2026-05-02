"""RAG component factory — single entry point for framework switching.

All ``create_*`` methods use **lazy imports** so that missing framework
dependencies (e.g. LangChain) only trigger an error when a component is
actually requested, not at module-import time.
"""

from __future__ import annotations

from misaka.services.knowledge.rag.abstractions import (
    DocumentParser,
    EmbeddingProvider,
    Reranker,
    Retriever,
    TextChunker,
    VectorStore,
)


class RAGComponentFactory:
    """Create RAG components for the configured backend.

    Currently only the ``"langchain"`` backend is implemented.
    To add a new backend, extend each ``create_*`` method with a new branch
    and provide an adapter that satisfies the corresponding ABC.
    """

    def __init__(self, db_path: str, backend: str = "langchain") -> None:
        self._db_path = db_path
        self._backend = backend

    def create_parser(self) -> DocumentParser:
        if self._backend == "langchain":
            from .langchain.parser import LCDocumentParser
            return LCDocumentParser()
        raise ValueError(f"Unknown backend: {self._backend}")

    def create_chunker(self) -> TextChunker:
        if self._backend == "langchain":
            from .langchain.chunker import LCTextChunker
            return LCTextChunker()
        raise ValueError(f"Unknown backend: {self._backend}")

    def create_embedding_provider(self) -> EmbeddingProvider:
        if self._backend == "langchain":
            from .langchain.embedding import LCEmbeddingProvider
            return LCEmbeddingProvider()
        raise ValueError(f"Unknown backend: {self._backend}")

    def create_vector_store(self) -> VectorStore:
        if self._backend == "langchain":
            from .langchain.vector_store import LCSqliteVecStore
            return LCSqliteVecStore(self._db_path)
        raise ValueError(f"Unknown backend: {self._backend}")

    def create_retriever(self, vector_store: VectorStore) -> Retriever:
        if self._backend == "langchain":
            from .langchain.retriever import LCHybridRetriever
            return LCHybridRetriever(vector_store)
        raise ValueError(f"Unknown backend: {self._backend}")

    def create_reranker(self) -> Reranker:
        if self._backend == "langchain":
            from .langchain.reranker import LCReranker
            return LCReranker()
        raise ValueError(f"Unknown backend: {self._backend}")
