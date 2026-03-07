"""
Tests for the Claude service.

These are unit tests for the service's environment building logic.
Full SDK integration tests require a running Claude Code CLI.
"""

from __future__ import annotations

import json

import pytest

from misaka.services.chat.claude_service import ClaudeService


@pytest.fixture
def claude_service(db) -> ClaudeService:
    return ClaudeService(db)


class TestClaudeService:

    def test_build_env_with_active_router_config(self, claude_service: ClaudeService, db) -> None:
        db.create_router_config(
            "Router A",
            api_key="sk-router",
            base_url="https://router.example.com",
            main_model="claude-main",
            haiku_model="claude-haiku",
            opus_model="claude-opus",
            sonnet_model="claude-sonnet",
            agent_team=True,
            config_json=json.dumps({
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "sk-router",
                    "ANTHROPIC_BASE_URL": "https://router.example.com",
                    "CUSTOM_VAR": "value",
                }
            }),
            is_active=1,
        )

        env = claude_service._build_env()

        assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-router"
        assert env["ANTHROPIC_API_KEY"] == "sk-router"
        assert env["ANTHROPIC_BASE_URL"] == "https://router.example.com"
        assert env["CUSTOM_VAR"] == "value"
        assert env["ANTHROPIC_MODEL"] == "claude-main"
        assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "claude-haiku"
        assert env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "claude-opus"
        assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "claude-sonnet"
        assert env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "1"

    def test_build_env_router_backfills_missing_values(self, claude_service: ClaudeService, db) -> None:
        db.create_router_config(
            "Router A",
            api_key="sk-router",
            base_url="https://router.example.com",
            main_model="claude-main",
            config_json=json.dumps({"env": {"CUSTOM_VAR": "value"}}),
            is_active=1,
        )

        env = claude_service._build_env()

        assert env["CUSTOM_VAR"] == "value"
        assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-router"
        assert env["ANTHROPIC_API_KEY"] == "sk-router"
        assert env["ANTHROPIC_BASE_URL"] == "https://router.example.com"
        assert env["ANTHROPIC_MODEL"] == "claude-main"

    def test_build_env_router_invalid_json_uses_structured_fields(
        self, claude_service: ClaudeService, db
    ) -> None:
        db.create_router_config(
            "Router A",
            api_key="sk-router",
            base_url="https://router.example.com",
            sonnet_model="claude-sonnet",
            config_json="not valid json",
            is_active=1,
        )

        env = claude_service._build_env()

        assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-router"
        assert env["ANTHROPIC_API_KEY"] == "sk-router"
        assert env["ANTHROPIC_BASE_URL"] == "https://router.example.com"
        assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "claude-sonnet"

    def test_build_env_router_overrides_legacy_settings(self, claude_service: ClaudeService, db) -> None:
        db.set_setting("anthropic_auth_token", "sk-legacy")
        db.set_setting("anthropic_base_url", "https://legacy.api.com")
        db.create_router_config(
            "Router A",
            api_key="sk-router",
            base_url="https://router.example.com",
            config_json=json.dumps({
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "sk-router",
                    "ANTHROPIC_BASE_URL": "https://router.example.com",
                }
            }),
            is_active=1,
        )

        env = claude_service._build_env()

        assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-router"
        assert env["ANTHROPIC_API_KEY"] == "sk-router"
        assert env["ANTHROPIC_BASE_URL"] == "https://router.example.com"

    def test_build_env_without_active_router_uses_legacy_settings(
        self, claude_service: ClaudeService, db
    ) -> None:
        db.set_setting("anthropic_auth_token", "sk-legacy")
        db.set_setting("anthropic_base_url", "https://legacy.api.com")

        env = claude_service._build_env()

        assert env.get("ANTHROPIC_AUTH_TOKEN") == "sk-legacy"
        assert env.get("ANTHROPIC_API_KEY") == "sk-legacy"
        assert env.get("ANTHROPIC_BASE_URL") == "https://legacy.api.com"

    def test_build_env_without_router_or_legacy(self, claude_service: ClaudeService) -> None:
        env = claude_service._build_env()
        assert "HOME" in env or "USERPROFILE" in env
