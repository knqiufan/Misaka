"""
Integration test: provider management.

Tests CRUD and activation of API provider configurations.
"""

from __future__ import annotations

import pytest

from misaka.db.database import DatabaseBackend
from misaka.services.settings.provider_service import ProviderService


class TestProviderManagement:

    def test_full_crud_lifecycle(self, db: DatabaseBackend) -> None:
        svc = ProviderService(db)

        # Create
        p1 = svc.create("Anthropic Direct", api_key="sk-ant-123", base_url="https://api.anthropic.com")
        assert p1.name == "Anthropic Direct"
        assert p1.api_key == "sk-ant-123"

        p2 = svc.create("AWS Bedrock", api_key="sk-aws-456", provider_type="bedrock")
        assert p2.provider_type == "bedrock"

        # Read all
        providers = svc.get_all()
        assert len(providers) == 2

        # Update
        updated = svc.update(p1.id, name="Anthropic API", base_url="https://new.api.com")
        assert updated is not None
        assert updated.name == "Anthropic API"
        assert updated.base_url == "https://new.api.com"

        # Delete
        assert svc.delete(p2.id) is True
        assert svc.get(p2.id) is None
        assert len(svc.get_all()) == 1

    def test_activation_flow(self, db: DatabaseBackend) -> None:
        svc = ProviderService(db)

        p1 = svc.create("P1", api_key="sk-1")
        p2 = svc.create("P2", api_key="sk-2")
        p3 = svc.create("P3", api_key="sk-3")

        # No active provider initially
        assert svc.get_active() is None

        # Activate P1
        svc.activate(p1.id)
        active = svc.get_active()
        assert active is not None
        assert active.id == p1.id

        # Switch to P2
        svc.activate(p2.id)
        active = svc.get_active()
        assert active.id == p2.id

        # Verify P1 is no longer active
        p1_refreshed = svc.get(p1.id)
        assert p1_refreshed is not None
        assert p1_refreshed.is_active == 0

        # Deactivate all
        svc.deactivate_all()
        assert svc.get_active() is None

    def test_extra_env_roundtrip(self, db: DatabaseBackend) -> None:
        svc = ProviderService(db)
        p = svc.create(
            "Custom Provider",
            api_key="sk-custom",
            extra_env='{"CUSTOM_VAR": "hello", "ANOTHER": "world"}',
        )

        loaded = svc.get(p.id)
        assert loaded is not None
        env = loaded.parse_extra_env()
        assert env["CUSTOM_VAR"] == "hello"
        assert env["ANOTHER"] == "world"
