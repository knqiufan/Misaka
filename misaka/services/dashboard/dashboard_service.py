"""
Dashboard aggregation service.

Provides statistics queries for the unified dashboard:
session counts, message counts, token usage, and skill statistics.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
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


@dataclass
class DailyUsage:
    """Token usage aggregated for a single day."""

    date: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class SkillStats:
    """Skill counts broken down by source."""

    total: int = 0
    global_count: int = 0
    project_count: int = 0
    installed_count: int = 0
    plugin_count: int = 0


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

    def get_daily_usage(self, days: int = 30) -> list[DailyUsage]:
        """Return per-day token usage for the last *days* days, sorted by date."""
        rows = self._db.get_daily_token_usage_rows(days)

        buckets: dict[str, dict[str, float]] = defaultdict(
            lambda: {"in": 0, "out": 0, "cache": 0, "cost": 0.0},
        )

        for day, raw in rows:
            try:
                data = json.loads(raw)
                b = buckets[day]
                b["in"] += data.get("input_tokens", 0) or 0
                b["out"] += data.get("output_tokens", 0) or 0
                b["cache"] += data.get("cache_read_input_tokens", 0) or 0
                cost = data.get("cost_usd")
                if cost is not None:
                    b["cost"] += float(cost)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        result = [
            DailyUsage(
                date=day,
                input_tokens=int(vals["in"]),
                output_tokens=int(vals["out"]),
                cache_read_tokens=int(vals["cache"]),
                cost_usd=vals["cost"],
            )
            for day, vals in sorted(buckets.items())
        ]
        return result

    @staticmethod
    def get_skill_stats() -> SkillStats:
        """Scan skill sources and return counts by category."""
        try:
            from misaka.services.skills.skill_service import SkillService
            svc = SkillService()
            skills = svc.list_skills()
        except Exception:
            logger.exception("Failed to scan skills")
            return SkillStats()

        g = sum(1 for s in skills if s.source == "global")
        p = sum(1 for s in skills if s.source == "project")
        i = sum(1 for s in skills if s.source == "installed")
        pl = sum(1 for s in skills if s.source == "plugin")
        return SkillStats(
            total=len(skills),
            global_count=g,
            project_count=p,
            installed_count=i,
            plugin_count=pl,
        )

    @staticmethod
    def get_cli_session_count() -> int:
        """Count CLI session files under ``~/.claude/projects/``."""
        try:
            from misaka.services.session.session_import_service import (
                SessionImportService,
            )
            svc = SessionImportService()
            return len(svc.list_cli_session_paths())
        except Exception:
            logger.exception("Failed to count CLI sessions")
            return 0
