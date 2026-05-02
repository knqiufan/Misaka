"""LangChain-based embedding provider adapter."""

from __future__ import annotations

import logging

from misaka.services.knowledge.rag.abstractions import EmbeddingConfig, EmbeddingProvider

logger = logging.getLogger(__name__)


class LCEmbeddingProvider(EmbeddingProvider):
    """Embed texts via ``langchain_openai.OpenAIEmbeddings``.

    Supports any OpenAI-compatible embedding API endpoint.
    """

    async def embed_texts(
        self,
        texts: list[str],
        config: EmbeddingConfig,
        batch_size: int = 32,
    ) -> list[list[float]]:
        if not texts:
            return []

        embeddings = self._create_lc_embeddings(config)
        all_vectors: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            vectors = await embeddings.aembed_documents(batch)
            all_vectors.extend(vectors)

        return all_vectors

    async def embed_query(
        self,
        query: str,
        config: EmbeddingConfig,
    ) -> list[float]:
        embeddings = self._create_lc_embeddings(config)
        return await embeddings.aembed_query(query)

    def get_dimensions(self, embedding: list[float]) -> int:
        return len(embedding)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_lc_embeddings(config: EmbeddingConfig):  # noqa: ANN205
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=config.model_id,
            openai_api_base=config.base_url,
            openai_api_key=config.api_key,
            timeout=60.0,
            max_retries=1,
        )
