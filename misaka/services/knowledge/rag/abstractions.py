"""RAG abstraction layer — framework-agnostic ABC interfaces and data types.

This module defines the contracts that any RAG framework adapter must satisfy.
Business-layer code (``RAGOrchestrator``, ``DocumentService``, …) depends
**only** on these abstractions, never on LangChain / LlamaIndex / etc.

Design principles
-----------------
* All inputs and outputs use project-owned data types (``ChunkData``,
  ``ParsedDocument``, …) — no framework types leak into the interface.
* Configuration is passed via plain data classes (``EmbeddingConfig``,
  ``RerankerConfig``).
* Async methods for I/O-bound operations (file I/O, network calls); sync
  methods for CPU-only / in-memory computation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Common data types
# ---------------------------------------------------------------------------

@dataclass
class ChunkData:
    """Framework-agnostic representation of a text chunk."""

    content: str
    index: int
    start_char: int = 0
    end_char: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocumentSegment:
    """A logical unit of parsed content, such as a PDF page or Excel sheet."""

    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """Result of parsing a file into plain text."""

    text: str
    metadata: dict = field(default_factory=dict)
    page_breaks: list[int] = field(default_factory=list)
    # Keep source-level boundaries so retrieval can cite the original PDF
    # page or workbook sheet instead of an anonymous flattened document.
    segments: list[ParsedDocumentSegment] = field(default_factory=list)


@dataclass
class RetrievalResult:
    """A single retrieval hit (vector / BM25 / hybrid)."""

    chunk_id: str
    content: str
    score: float
    metadata: dict = field(default_factory=dict)


@dataclass
class IngestResult:
    """Summary returned after a document has been ingested."""

    content_text: str
    content_length: int
    chunk_count: int
    chunks: list[ChunkData]
    dimensions: int
    error: str | None = None


@dataclass
class EmbeddingConfig:
    """Connection parameters for an embedding model."""

    model_id: str
    base_url: str
    api_key: str


@dataclass
class RerankerConfig:
    """Connection parameters for a reranker model."""

    model_id: str
    base_url: str
    api_key: str
    top_n: int = 3


@dataclass
class KBRetrievalConfig:
    """Retrieval policy belonging to one knowledge base.

    ``top_k`` limits the candidates contributed by this KB. After every KB
    has applied its own policy, the orchestrator applies the session-level
    final limit.
    """

    top_k: int = 5
    similarity_threshold: float = 0.0
    reranker_config: RerankerConfig | None = None


# ---------------------------------------------------------------------------
# ABC interfaces
# ---------------------------------------------------------------------------

class DocumentParser(ABC):
    """Parse various file formats into plain text."""

    @abstractmethod
    async def parse(self, file_path: str, file_type: str) -> ParsedDocument:
        """Parse a file and return its textual representation.

        Args:
            file_path: Absolute path to the file on disk.
            file_type: One of ``txt``, ``markdown``, ``docx``, ``xlsx``, ``pdf``.
        """

    @abstractmethod
    def supported_types(self) -> list[str]:
        """Return the file type identifiers this parser can handle."""


class TextChunker(ABC):
    """Split text into semantically coherent chunks."""

    @abstractmethod
    def chunk(
        self,
        text: str,
        file_type: str,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        metadata: dict | None = None,
    ) -> list[ChunkData]:
        """Chunk *text* using a strategy suited for *file_type*.

        Args:
            text: Raw document text.
            file_type: Original file type (different types may use different
                strategies).
            chunk_size: Target chunk size in characters.
            chunk_overlap: Overlap between consecutive chunks.
            metadata: Document-level metadata merged into each chunk.
        """


class EmbeddingProvider(ABC):
    """Convert text into vector embeddings."""

    @abstractmethod
    async def embed_texts(
        self,
        texts: list[str],
        config: EmbeddingConfig,
        batch_size: int = 32,
    ) -> list[list[float]]:
        """Embed a batch of texts, returning one vector per text."""

    @abstractmethod
    async def embed_query(
        self,
        query: str,
        config: EmbeddingConfig,
    ) -> list[float]:
        """Embed a single query string."""

    @abstractmethod
    def get_dimensions(self, embedding: list[float]) -> int:
        """Return the dimensionality of an embedding vector."""


class VectorStore(ABC):
    """Low-level vector storage — CRUD and KNN search."""

    @abstractmethod
    def add_chunks(
        self,
        table_name: str,
        chunks: list[ChunkData],
        embeddings: list[list[float]],
    ) -> None:
        """Insert chunks and their embeddings into *table_name*."""

    @abstractmethod
    def search(
        self,
        table_name: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """Perform KNN search and return the *top_k* closest chunks."""

    @abstractmethod
    def delete_by_ids(
        self,
        table_name: str,
        chunk_ids: list[str],
    ) -> None:
        """Remove specific chunks by their IDs."""

    @abstractmethod
    def ensure_table(self, table_name: str, dimensions: int) -> None:
        """Create the vector table if it does not exist (idempotent)."""

    @abstractmethod
    def drop_table(self, table_name: str) -> None:
        """Delete the entire vector table."""

    @abstractmethod
    def close(self) -> None:
        """Release any underlying connections / resources."""


class Retriever(ABC):
    """High-level retrieval strategy (vector-only or hybrid)."""

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        query_embedding: list[float],
        table_name: str,
        top_k: int = 5,
        chunks_for_bm25: list[ChunkData] | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve relevant chunks.

        Args:
            query: Raw query text (used by BM25 when available).
            query_embedding: Pre-computed query vector.
            table_name: Name of the vector table.
            top_k: Maximum number of results.
            chunks_for_bm25: All chunks for BM25 scoring.  When *None*,
                fall back to vector-only retrieval.
        """


class Reranker(ABC):
    """Re-rank retrieval results using a cross-encoder or similar model."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        config: RerankerConfig,
    ) -> list[RetrievalResult]:
        """Re-rank *results* and return them sorted by relevance (desc)."""
