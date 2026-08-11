"""Validation shared by KB UI, services, and persistence boundaries."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from misaka.db.models import KnowledgeBase


class KnowledgeBaseConfigError(ValueError):
    """Raised when persisted retrieval settings would be unsafe or invalid."""

    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors.values()))


def validate_knowledge_base_config(kb: KnowledgeBase) -> None:
    """Reject invalid numeric settings before they can reach an index build."""
    errors: dict[str, str] = {}

    if not _is_positive_int(kb.chunk_size):
        errors["chunk_size"] = "Chunk size must be a positive integer."
    if not _is_nonnegative_int(kb.chunk_overlap):
        errors["chunk_overlap"] = "Chunk overlap must be a non-negative integer."
    elif _is_positive_int(kb.chunk_size) and kb.chunk_overlap >= kb.chunk_size:
        errors["chunk_overlap"] = "Chunk overlap must be smaller than chunk size."
    if not _is_positive_int(kb.top_k):
        errors["top_k"] = "Top K must be a positive integer."
    if not _is_positive_int(kb.reranker_top_k):
        errors["reranker_top_k"] = "Reranker Top K must be a positive integer."
    if not _is_finite_number(kb.similarity_threshold):
        errors["similarity_threshold"] = "Similarity threshold must be a finite number."
    elif not 0.0 <= float(kb.similarity_threshold) <= 1.0:
        errors["similarity_threshold"] = "Similarity threshold must be between 0 and 1."
    if not _is_nonnegative_int(kb.embedding_dimensions):
        errors["embedding_dimensions"] = "Embedding dimensions must be a non-negative integer."

    if errors:
        raise KnowledgeBaseConfigError(errors)


def validate_knowledge_base_changes(kb: KnowledgeBase, changes: dict[str, Any]) -> None:
    """Validate a partial update against the complete existing configuration."""
    known = {
        key: value
        for key, value in changes.items()
        if key in KnowledgeBase.__dataclass_fields__
    }
    validate_knowledge_base_config(replace(kb, **known))


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
