"""
API provider management service.

Handles CRUD and activation of API provider configurations.
"""

from __future__ import annotations

import logging
from typing import Any

from misaka.db.database import DatabaseBackend
from misaka.db.models import ApiProvider

logger = logging.getLogger(__name__)


class ProviderService:
    """Service for managing API providers."""

    def __init__(self, db: DatabaseBackend) -> None:
        self._db = db

    def get_all(self) -> list[ApiProvider]:
        """Return all providers ordered by sort order."""
        return self._db.get_all_providers()

    def get(self, provider_id: str) -> ApiProvider | None:
        """Return a provider by ID."""
        return self._db.get_provider(provider_id)

    def get_active(self) -> ApiProvider | None:
        """Return the currently active provider."""
        return self._db.get_active_provider()

    def create(self, name: str, **kwargs: Any) -> ApiProvider:
        """Create a new API provider."""
        provider = self._db.create_provider(name, **kwargs)
        logger.info("Created provider %s: %s", provider.id, provider.name)
        return provider

    def update(self, provider_id: str, **kwargs: Any) -> ApiProvider | None:
        """Update an existing provider."""
        return self._db.update_provider(provider_id, **kwargs)

    def delete(self, provider_id: str) -> bool:
        """Delete a provider."""
        result = self._db.delete_provider(provider_id)
        if result:
            logger.info("Deleted provider %s", provider_id)
        return result

    def activate(self, provider_id: str) -> bool:
        """Set a provider as active (deactivates all others)."""
        result = self._db.activate_provider(provider_id)
        if result:
            logger.info("Activated provider %s", provider_id)
        return result

    def deactivate_all(self) -> None:
        """Deactivate all providers."""
        self._db.deactivate_all_providers()
