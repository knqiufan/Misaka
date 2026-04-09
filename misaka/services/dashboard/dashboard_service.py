"""
Dashboard aggregation service.

Provides statistics queries for the unified dashboard:
session counts, message counts, and cumulative token usage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend

logger = logging.getLogger(__name__)


@dataclass
class SessionStats:
    """Aggregated session and message counts."""

    total_sessions: int = 0
    active_sessions: int = 0
    archived_sessions: int = 0
    total_messages: int = 0


@dataclass
class TokenUsageSummary:
    """Cumulative token usage across all messages."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cost_usd: float = 0.0


class DashboardService:
    """Aggregation queries for the dashboard page."""

    def __init__(self, db: DatabaseBackend) -> None:
        self._db = db

    def get_session_stats(self) -> SessionStats:
        """Return aggregated session and message counts."""
        counts = self._db.get_session_counts()
        return SessionStats(
            total_sessions=counts["total"],
            active_sessions=counts["active"],
            archived_sessions=counts["archived"],
            total_messages=counts["messages"],
        )

    def get_token_usage_summary(self) -> TokenUsageSummary:
        """Return cumulative token usage parsed from message JSON."""
        rows = self._db.get_token_usage_rows()

        total_in = 0
        total_out = 0
        total_cache = 0
        total_cost = 0.0

        for raw in rows:
            try:
                data = json.loads(raw)
                total_in += data.get("input_tokens", 0) or 0
                total_out += data.get("output_tokens", 0) or 0
                total_cache += (
                    data.get("cache_read_input_tokens", 0) or 0
                )
                cost = data.get("cost_usd")
                if cost is not None:
                    total_cost += float(cost)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        return TokenUsageSummary(
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            total_cache_read_tokens=total_cache,
            total_cost_usd=total_cost,
        )
