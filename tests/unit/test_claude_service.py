"""
Tests for the Claude service.

These are unit tests for the service's environment building logic.
Full SDK integration tests require a running Claude Code CLI.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from misaka.db.models import ApiProvider
from misaka.services.chat.claude_service import ClaudeService


@pytest.fixture
def claude_service(db) -> ClaudeService:
    return ClaudeService(db)


class TestClaudeService:

    def test_build_env_with_provider(self, claude_service: ClaudeService) -> None:
        provider = ApiProvider(
            id="test-id",
            name="Test",
            api_key="sk-test-key",
            base_url="https://custom.api.com",
            extra_env='{"CUSTOM_VAR": "value"}',
        )
        env = claude_service._build_env(provider)
        assert env["ANTHROPIC_API_KEY"] == "sk-test-key"
        assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-test-key"
        assert env["ANTHROPIC_BASE_URL"] == "https://custom.api.com"
        assert env["CUSTOM_VAR"] == "value"

    def test_build_env_extra_env_delete(self, claude_service: ClaudeService) -> None:
        provider = ApiProvider(
            id="test-id",
            name="Test",
            api_key="sk-test",
            extra_env='{"ANTHROPIC_API_KEY": ""}',
        )
        env = claude_service._build_env(provider)
        # Empty string means delete the variable
        assert "ANTHROPIC_API_KEY" not in env

    def test_build_env_without_provider(self, claude_service: ClaudeService) -> None:
        env = claude_service._build_env(None)
        assert "HOME" in env or "USERPROFILE" in env

    def test_build_env_legacy_settings(self, claude_service: ClaudeService, db) -> None:
        db.set_setting("anthropic_auth_token", "sk-legacy")
        db.set_setting("anthropic_base_url", "https://legacy.api.com")
        env = claude_service._build_env(None)
        assert env.get("ANTHROPIC_AUTH_TOKEN") == "sk-legacy"
        assert env.get("ANTHROPIC_BASE_URL") == "https://legacy.api.com"
