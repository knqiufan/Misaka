"""
Tests for the SettingsService.
"""

from __future__ import annotations

import pytest

from misaka.services.settings.settings_service import SettingsService


@pytest.fixture
def settings_service(db) -> SettingsService:
    return SettingsService(db)


class TestSettingsService:

    def test_get_set(self, settings_service: SettingsService) -> None:
        assert settings_service.get("theme") is None
        settings_service.set("theme", "dark")
        assert settings_service.get("theme") == "dark"

    def test_get_all(self, settings_service: SettingsService) -> None:
        settings_service.set("a", "1")
        settings_service.set("b", "2")
        result = settings_service.get_all()
        assert result == {"a": "1", "b": "2"}

    def test_set_many(self, settings_service: SettingsService) -> None:
        settings_service.set_many({"x": "10", "y": "20"})
        assert settings_service.get("x") == "10"
        assert settings_service.get("y") == "20"

    def test_get_default_model(self, settings_service: SettingsService) -> None:
        assert settings_service.get_default_model() is None
        settings_service.set("default_model", "claude-sonnet-4-5")
        assert settings_service.get_default_model() == "claude-sonnet-4-5"

    def test_get_default_system_prompt(self, settings_service: SettingsService) -> None:
        assert settings_service.get_default_system_prompt() is None
        settings_service.set("default_system_prompt", "Be helpful")
        assert settings_service.get_default_system_prompt() == "Be helpful"

    def test_get_theme(self, settings_service: SettingsService) -> None:
        assert settings_service.get_theme() == "system"  # default
        settings_service.set("theme", "dark")
        assert settings_service.get_theme() == "dark"

    def test_get_permission_mode(self, settings_service: SettingsService) -> None:
        assert settings_service.get_permission_mode() == "acceptEdits"  # default
        settings_service.set("permission_mode", "bypassPermissions")
        assert settings_service.get_permission_mode() == "bypassPermissions"

    def test_is_skip_permissions(self, settings_service: SettingsService) -> None:
        assert settings_service.is_skip_permissions() is False
        settings_service.set("dangerously_skip_permissions", "true")
        assert settings_service.is_skip_permissions() is True
        settings_service.set("dangerously_skip_permissions", "false")
        assert settings_service.is_skip_permissions() is False
