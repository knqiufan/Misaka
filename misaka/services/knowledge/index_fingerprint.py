"""Stable fingerprints for knowledge-base indexes.

The fingerprint describes every persisted setting that changes the contents or
shape of an index. It deliberately excludes credentials: rotating a secret
must not make a valid local index appear stale.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from misaka.db.models import KnowledgeBase


# Bump either value whenever the corresponding implementation changes in a
# way that changes persisted chunks. Keeping them in the fingerprint makes
# the required rebuild explicit rather than relying on a UI-only prompt.
_PARSER_STRATEGY_VERSION = "langchain-document-parser-v1"
_CHUNKER_STRATEGY_VERSION = "langchain-text-chunker-v1"
_INDEX_FORMAT_VERSION = 1


def build_index_fingerprint(
    kb: KnowledgeBase,
    *,
    embedding_dimensions: int | None = None,
) -> str:
    """Return a deterministic fingerprint for the index represented by *kb*."""
    payload = {
        "format": _INDEX_FORMAT_VERSION,
        "embedding": {
            "model_id": kb.embedding_model_id,
            "router_config_id": kb.embedding_router_config_id,
            "dimensions": (
                kb.embedding_dimensions
                if embedding_dimensions is None
                else embedding_dimensions
            ),
        },
        "chunking": {
            "chunk_size": kb.chunk_size,
            "chunk_overlap": kb.chunk_overlap,
            "strategy": _CHUNKER_STRATEGY_VERSION,
        },
        "parser": _PARSER_STRATEGY_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
