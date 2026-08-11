"""Send-pipeline preprocessors for the chat module.

Each preprocessor can inspect and modify the user's text and images
*before* the message is handed to the Claude SDK for streaming.
Preprocessors are registered as a simple list and run sequentially;
adding or removing a feature is just a matter of appending or
omitting the relevant processor.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from misaka.services.knowledge.kb_service import KBService
    from misaka.services.knowledge.rag_orchestrator import RAGOrchestrator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SendPreprocessor(Protocol):
    """Protocol for send-pipeline preprocessors.

    Each preprocessor receives the user's raw text, image list, and a
    read-only *context* dict.  It must return a ``(text, images)`` tuple
    which may be modified.  The next preprocessor in the chain receives
    the output of the previous one.
    """

    async def process(
        self, text: str, images: list, context: dict,
    ) -> tuple[str, list]:
        """Process and return ``(modified_text, modified_images)``.

        *context* carries read-only metadata such as ``selected_kb_ids``
        and ``session_id``.  Preprocessors should **not** mutate it.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# RAG preprocessor
# ---------------------------------------------------------------------------


class RAGPreprocessor:
    """Augment the user message with RAG-retrieved context.

    When knowledge bases are selected for the current session, this
    preprocessor runs the retrieval pipeline and prepends reference
    materials to the prompt text so that Claude can ground its answer
    in the user's knowledge base.

    The logic was extracted from ``ChatPage._send_with_rag()`` and
    ``ChatPage._do_rag_retrieve()``.
    """

    def __init__(
        self,
        kb_service: KBService,
        rag_orchestrator: RAGOrchestrator,
        router_config_service: Any,
    ) -> None:
        self._kb_service = kb_service
        self._rag = rag_orchestrator
        self._router_svc = router_config_service

    async def process(
        self, text: str, images: list, context: dict,
    ) -> tuple[str, list]:
        selected_kb_ids: list[str] = context.get("selected_kb_ids", [])
        if not selected_kb_ids or not text.strip():
            return text, images

        augmented_text, search_results = await self._do_rag_retrieve(
            text, selected_kb_ids, context,
        )

        # Store results in context so the caller can cache them.
        context["_rag_results"] = search_results
        context["_rag_augmented_text"] = augmented_text
        return augmented_text, images

    # ── Private helpers (extracted from ChatPage) ─────────────────────

    async def _do_rag_retrieve(
        self,
        query: str,
        kb_ids: list[str],
        context: dict,
    ) -> tuple[str, list]:
        """Execute RAG retrieval and build the augmented prompt text."""
        embedding_configs, kb_retrieval_configs = self._build_rag_configs(kb_ids)
        if not embedding_configs:
            context["_rag_per_kb_errors"] = {
                kb_id: "No embedding configuration is available" for kb_id in kb_ids
            }
            return query, []

        outcome = await self._rag.retrieve_with_diagnostics(
            query=query,
            kb_ids=kb_ids,
            embedding_configs=embedding_configs,
            kb_retrieval_configs=kb_retrieval_configs,
        )
        context["_rag_per_kb_errors"] = outcome.per_kb_errors
        context["_rag_timed_out"] = outcome.timed_out
        results = outcome.results

        if not results:
            return query, []

        context_text = self._rag.format_context(results)
        if context_text:
            return f"{query}\n\n{context_text}", results
        return query, results

    def _build_rag_configs(self, kb_ids: list[str]) -> tuple[dict, dict]:
        """Build embedding and retrieval policies for each selected KB."""
        from misaka.services.knowledge.rag.abstractions import (
            EmbeddingConfig,
            KBRetrievalConfig,
            RerankerConfig,
        )

        if not self._router_svc:
            return {}, {}

        embedding_configs: dict[str, EmbeddingConfig] = {}
        kb_retrieval_configs: dict[str, KBRetrievalConfig] = {}

        for kb_id in kb_ids:
            kb = self._kb_service.get(kb_id)
            if not kb:
                continue
            emb_info = _find_model_info(
                self._router_svc, kb.embedding_model_id, kb.embedding_router_config_id,
            )
            if emb_info:
                embedding_configs[kb_id] = EmbeddingConfig(
                    model_id=emb_info.model_id,
                    base_url=emb_info.base_url,
                    api_key=emb_info.api_key,
                )
            reranker_config = None
            if kb.reranker_model_id:
                rnk_info = _find_model_info(
                    self._router_svc, kb.reranker_model_id, kb.reranker_router_config_id,
                )
                if rnk_info:
                    reranker_config = RerankerConfig(
                        model_id=rnk_info.model_id,
                        base_url=rnk_info.base_url,
                        api_key=rnk_info.api_key,
                        top_n=kb.reranker_top_k,
                    )
            kb_retrieval_configs[kb_id] = KBRetrievalConfig(
                top_k=kb.top_k,
                similarity_threshold=kb.similarity_threshold,
                reranker_config=reranker_config,
            )

        return embedding_configs, kb_retrieval_configs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_model_info(router_svc: Any, model_id: str, config_id: str) -> Any | None:
    """Look up a specific model from the router service."""
    if not model_id or not config_id:
        return None
    try:
        models = router_svc.get_models_by_config(config_id)
        for m in models:
            if m.model_id == model_id:
                return m
    except Exception:
        logger.warning("Failed to find model %s in config %s", model_id, config_id)
    return None
