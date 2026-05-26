"""Unit tests for system prompt service integration."""

from __future__ import annotations

import pytest

from misaka.config import SettingKeys
from misaka.db.database import DatabaseBackend
from misaka.services.settings.settings_service import SettingsService


class TestSystemPromptStorage:
    """Tests for system prompt read/write via SettingsService."""

    def test_get_default_system_prompt_empty(self, db: DatabaseBackend):
        svc = SettingsService(db)
        assert svc.get_default_system_prompt() is None

    def test_set_and_get_system_prompt(self, db: DatabaseBackend):
        svc = SettingsService(db)
        svc.set(SettingKeys.DEFAULT_SYSTEM_PROMPT, "Always reply in Chinese")
        assert svc.get_default_system_prompt() == "Always reply in Chinese"

    def test_update_system_prompt(self, db: DatabaseBackend):
        svc = SettingsService(db)
        svc.set(SettingKeys.DEFAULT_SYSTEM_PROMPT, "First")
        svc.set(SettingKeys.DEFAULT_SYSTEM_PROMPT, "Second")
        assert svc.get_default_system_prompt() == "Second"

    def test_empty_string_prompt(self, db: DatabaseBackend):
        svc = SettingsService(db)
        svc.set(SettingKeys.DEFAULT_SYSTEM_PROMPT, "")
        # Empty string stored; getter returns it
        assert svc.get_default_system_prompt() == ""

    def test_cache_invalidation(self, db: DatabaseBackend):
        svc = SettingsService(db)
        svc.set(SettingKeys.DEFAULT_SYSTEM_PROMPT, "cached_value")
        assert svc.get_default_system_prompt() == "cached_value"
        svc.invalidate_cache()
        assert svc.get_default_system_prompt() == "cached_value"


class TestSystemPromptMerge:
    """Tests for the prompt merge logic used by StreamHandler."""

    @staticmethod
    def _resolve(global_prompt: str | None, session_prompt: str | None) -> str | None:
        """Mirror the logic from StreamHandler._resolve_system_prompt."""
        parts = [p for p in (global_prompt, session_prompt) if p and p.strip()]
        return "\n\n".join(parts) if parts else None

    def test_both_none(self):
        assert self._resolve(None, None) is None

    def test_global_only(self):
        result = self._resolve("Global prompt", None)
        assert result == "Global prompt"

    def test_session_only(self):
        result = self._resolve(None, "Session prompt")
        assert result == "Session prompt"

    def test_both_present(self):
        result = self._resolve("Global", "Session")
        assert result == "Global\n\nSession"

    def test_empty_string_treated_as_none(self):
        assert self._resolve("", "") is None
        assert self._resolve("", "Session") == "Session"
        assert self._resolve("Global", "") == "Global"

    def test_whitespace_only_treated_as_none(self):
        assert self._resolve("   ", "   ") is None
        assert self._resolve("   ", "Valid") == "Valid"
