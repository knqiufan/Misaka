"""
Settings management service.

Key-value store for application settings with type-safe accessors
for well-known keys. Includes an in-memory cache to avoid repeated
database reads for frequently accessed settings.
"""

from __future__ import annotations

import logging

from misaka.config import SettingKeys
from misaka.db.database import DatabaseBackend

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing application settings with caching."""

    def __init__(self, db: DatabaseBackend) -> None:
        self._db = db
        self._cache: dict[str, str | None] = {}
        self._cache_loaded: bool = False

    def _ensure_cache(self) -> None:
        """Populate the cache from DB on first access."""
        if not self._cache_loaded:
            all_settings = self._db.get_all_settings()
            self._cache = {k: v for k, v in all_settings.items()}
            self._cache_loaded = True

    def invalidate_cache(self) -> None:
        """Force the cache to reload on next access."""
        self._cache.clear()
        self._cache_loaded = False

    def get(self, key: str) -> str | None:
        """Get a setting value by key (cached)."""
        self._ensure_cache()
        if key in self._cache:
            return self._cache[key]
        value = self._db.get_setting(key)
        self._cache[key] = value
        return value

    def set(self, key: str, value: str) -> None:
        """Set a setting value."""
        self._db.set_setting(key, value)
        self._cache[key] = value

    def get_all(self) -> dict[str, str]:
        """Get all settings as a dict."""
        self._ensure_cache()
        return {k: v for k, v in self._cache.items() if v is not None}

    def set_many(self, settings: dict[str, str]) -> None:
        """Set multiple settings in a single transaction."""
        if hasattr(self._db, "set_settings_batch"):
            self._db.set_settings_batch(settings)
        else:
            for key, value in settings.items():
                self._db.set_setting(key, value)
        self._cache.update(settings)

    # --- Typed accessors for well-known keys ---

    def get_default_model(self) -> str | None:
        return self.get(SettingKeys.DEFAULT_MODEL)

    def get_default_system_prompt(self) -> str | None:
        return self.get(SettingKeys.DEFAULT_SYSTEM_PROMPT)

    def get_theme(self) -> str:
        return self.get(SettingKeys.THEME) or "system"

    def get_permission_mode(self) -> str:
        return self.get(SettingKeys.PERMISSION_MODE) or "default"

    def set_theme(self, theme: str) -> None:
        """Set the theme preference."""
        self.set(SettingKeys.THEME, theme)

    def is_skip_permissions(self) -> bool:
        return self.get(SettingKeys.DANGEROUSLY_SKIP_PERMISSIONS) == "true"
