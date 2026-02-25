"""
Settings management service.

Key-value store for application settings with type-safe accessors
for well-known keys.
"""

from __future__ import annotations

import logging

from misaka.config import SettingKeys
from misaka.db.database import DatabaseBackend

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing application settings."""

    def __init__(self, db: DatabaseBackend) -> None:
        self._db = db

    def get(self, key: str) -> str | None:
        """Get a setting value by key."""
        return self._db.get_setting(key)

    def set(self, key: str, value: str) -> None:
        """Set a setting value."""
        self._db.set_setting(key, value)

    def get_all(self) -> dict[str, str]:
        """Get all settings as a dict."""
        return self._db.get_all_settings()

    def set_many(self, settings: dict[str, str]) -> None:
        """Set multiple settings at once."""
        for key, value in settings.items():
            self._db.set_setting(key, value)

    # --- Typed accessors for well-known keys ---

    def get_default_model(self) -> str | None:
        return self.get(SettingKeys.DEFAULT_MODEL)

    def get_default_system_prompt(self) -> str | None:
        return self.get(SettingKeys.DEFAULT_SYSTEM_PROMPT)

    def get_theme(self) -> str:
        return self.get(SettingKeys.THEME) or "system"

    def get_permission_mode(self) -> str:
        return self.get(SettingKeys.PERMISSION_MODE) or "acceptEdits"

    def set_theme(self, theme: str) -> None:
        """Set the theme preference."""
        self.set(SettingKeys.THEME, theme)

    def is_skip_permissions(self) -> bool:
        return self.get(SettingKeys.DANGEROUSLY_SKIP_PERMISSIONS) == "true"
