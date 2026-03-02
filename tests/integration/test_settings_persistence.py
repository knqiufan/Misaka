"""
Integration test: settings persistence.

Tests save/load of settings through the full service + database stack.
"""

from __future__ import annotations

import pytest

from misaka.db.database import DatabaseBackend
from misaka.services.settings.settings_service import SettingsService


class TestSettingsPersistence:

    def test_save_and_reload(self, db: DatabaseBackend) -> None:
        svc = SettingsService(db)
        svc.set("theme", "dark")
        svc.set("default_model", "claude-sonnet-4-5")

        # Simulate "reload" by creating a new service instance with the same db
        svc2 = SettingsService(db)
        assert svc2.get("theme") == "dark"
        assert svc2.get("default_model") == "claude-sonnet-4-5"

    def test_overwrite_setting(self, db: DatabaseBackend) -> None:
        svc = SettingsService(db)
        svc.set("key", "value1")
        svc.set("key", "value2")
        assert svc.get("key") == "value2"

    def test_set_many_persists(self, db: DatabaseBackend) -> None:
        svc = SettingsService(db)
        svc.set_many({
            "a": "1",
            "b": "2",
            "c": "3",
        })

        all_settings = svc.get_all()
        assert all_settings["a"] == "1"
        assert all_settings["b"] == "2"
        assert all_settings["c"] == "3"

    def test_nonexistent_key_returns_none(self, db: DatabaseBackend) -> None:
        svc = SettingsService(db)
        assert svc.get("nonexistent") is None

    def test_typed_accessors_with_defaults(self, db: DatabaseBackend) -> None:
        svc = SettingsService(db)
        # Defaults when no setting exists
        assert svc.get_theme() == "system"
        assert svc.get_permission_mode() == "acceptEdits"
        assert svc.is_skip_permissions() is False
        assert svc.get_default_model() is None
