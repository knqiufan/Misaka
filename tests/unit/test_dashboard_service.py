"""
Tests for the DashboardService.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from misaka.services.dashboard.dashboard_service import (
    DashboardService,
    SessionStats,
    SkillStats,
    TokenUsageSummary,
)


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_db: MagicMock) -> DashboardService:
    return DashboardService(mock_db)


class TestSessionStats:

    def test_default_values(self) -> None:
        stats = SessionStats()
        assert stats.total_sessions == 0
        assert stats.active_sessions == 0
        assert stats.archived_sessions == 0
        assert stats.total_messages == 0

    def test_get_session_stats(self, service: DashboardService, mock_db: MagicMock) -> None:
        mock_db.get_session_counts.return_value = {
            "total": 10,
            "active": 7,
            "archived": 3,
            "messages": 150,
        }
        stats = service.get_session_stats()
        assert stats.total_sessions == 10
        assert stats.active_sessions == 7
        assert stats.archived_sessions == 3
        assert stats.total_messages == 150


class TestTokenUsageSummary:

    def test_default_values(self) -> None:
        summary = TokenUsageSummary()
        assert summary.total_input_tokens == 0
        assert summary.total_output_tokens == 0
        assert summary.total_cache_read_tokens == 0
        assert summary.total_cost_usd == 0.0

    def test_get_token_usage_summary(
        self, service: DashboardService, mock_db: MagicMock,
    ) -> None:
        rows = [
            json.dumps({
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 20,
                "cost_usd": 0.01,
            }),
            json.dumps({
                "input_tokens": 200,
                "output_tokens": 100,
                "cache_read_input_tokens": 30,
                "cost_usd": 0.02,
            }),
        ]
        mock_db.get_token_usage_rows.return_value = rows
        summary = service.get_token_usage_summary()
        assert summary.total_input_tokens == 300
        assert summary.total_output_tokens == 150
        assert summary.total_cache_read_tokens == 50
        assert summary.total_cost_usd == pytest.approx(0.03)

    def test_get_token_usage_handles_bad_json(
        self, service: DashboardService, mock_db: MagicMock,
    ) -> None:
        rows = [
            json.dumps({"input_tokens": 100, "output_tokens": 50}),
            "not valid json",
            json.dumps({"input_tokens": 200, "output_tokens": 100}),
        ]
        mock_db.get_token_usage_rows.return_value = rows
        summary = service.get_token_usage_summary()
        assert summary.total_input_tokens == 300
        assert summary.total_output_tokens == 150

    def test_get_token_usage_handles_none_values(
        self, service: DashboardService, mock_db: MagicMock,
    ) -> None:
        rows = [
            json.dumps({
                "input_tokens": None,
                "output_tokens": None,
                "cache_read_input_tokens": None,
                "cost_usd": None,
            }),
        ]
        mock_db.get_token_usage_rows.return_value = rows
        summary = service.get_token_usage_summary()
        assert summary.total_input_tokens == 0
        assert summary.total_output_tokens == 0
        assert summary.total_cache_read_tokens == 0
        assert summary.total_cost_usd == 0.0

    def test_get_token_usage_empty_rows(
        self, service: DashboardService, mock_db: MagicMock,
    ) -> None:
        mock_db.get_token_usage_rows.return_value = []
        summary = service.get_token_usage_summary()
        assert summary.total_input_tokens == 0
        assert summary.total_cost_usd == 0.0


class TestSkillStats:

    def test_default_values(self) -> None:
        stats = SkillStats()
        assert stats.total == 0
        assert stats.global_count == 0
        assert stats.project_count == 0
        assert stats.installed_count == 0
        assert stats.plugin_count == 0

    def test_get_skill_stats(self) -> None:
        mock_skills = []
        for source in ["global", "global", "project", "installed", "plugin", "plugin"]:
            s = MagicMock()
            s.source = source
            mock_skills.append(s)

        mock_svc = MagicMock()
        mock_svc.list_skills.return_value = mock_skills

        with patch(
            "misaka.services.skills.skill_service.SkillService",
            return_value=mock_svc,
        ):
            stats = DashboardService.get_skill_stats()
            assert stats.total == 6
            assert stats.global_count == 2
            assert stats.project_count == 1
            assert stats.installed_count == 1
            assert stats.plugin_count == 2

    def test_get_skill_stats_handles_exception(self) -> None:
        with patch(
            "misaka.services.skills.skill_service.SkillService",
            side_effect=RuntimeError("fail"),
        ):
            stats = DashboardService.get_skill_stats()
            assert stats.total == 0


class TestCliSessionCount:

    def test_get_cli_session_count(self) -> None:
        mock_svc = MagicMock()
        mock_svc.list_cli_session_paths.return_value = ["a", "b", "c"]

        with patch(
            "misaka.services.session.session_import_service.SessionImportService",
            return_value=mock_svc,
        ):
            count = DashboardService.get_cli_session_count()
            assert count == 3

    def test_get_cli_session_count_handles_exception(self) -> None:
        with patch(
            "misaka.services.session.session_import_service.SessionImportService",
            side_effect=RuntimeError("fail"),
        ):
            count = DashboardService.get_cli_session_count()
            assert count == 0
