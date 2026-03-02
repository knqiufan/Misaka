"""
Tests for the ProviderService.
"""

from __future__ import annotations

import pytest

from misaka.services.settings.provider_service import ProviderService


@pytest.fixture
def provider_service(db) -> ProviderService:
    return ProviderService(db)


class TestProviderService:

    def test_create_and_get_all(self, provider_service: ProviderService) -> None:
        provider_service.create("Provider A", api_key="sk-a")
        provider_service.create("Provider B", api_key="sk-b")
        providers = provider_service.get_all()
        assert len(providers) == 2

    def test_get_by_id(self, provider_service: ProviderService) -> None:
        created = provider_service.create("Test", api_key="sk-test")
        found = provider_service.get(created.id)
        assert found is not None
        assert found.name == "Test"

    def test_get_nonexistent(self, provider_service: ProviderService) -> None:
        assert provider_service.get("nonexistent") is None

    def test_update(self, provider_service: ProviderService) -> None:
        created = provider_service.create("Old Name")
        updated = provider_service.update(created.id, name="New Name")
        assert updated is not None
        assert updated.name == "New Name"

    def test_delete(self, provider_service: ProviderService) -> None:
        created = provider_service.create("Delete Me")
        assert provider_service.delete(created.id) is True
        assert provider_service.get(created.id) is None

    def test_delete_nonexistent(self, provider_service: ProviderService) -> None:
        assert provider_service.delete("nonexistent") is False

    def test_activate_and_get_active(self, provider_service: ProviderService) -> None:
        p1 = provider_service.create("P1")
        p2 = provider_service.create("P2")

        provider_service.activate(p1.id)
        active = provider_service.get_active()
        assert active is not None
        assert active.id == p1.id

        # Activate another
        provider_service.activate(p2.id)
        active = provider_service.get_active()
        assert active.id == p2.id

    def test_deactivate_all(self, provider_service: ProviderService) -> None:
        p1 = provider_service.create("P1")
        provider_service.activate(p1.id)
        provider_service.deactivate_all()
        assert provider_service.get_active() is None

    def test_no_active_by_default(self, provider_service: ProviderService) -> None:
        assert provider_service.get_active() is None

    def test_create_with_extra_env(self, provider_service: ProviderService) -> None:
        p = provider_service.create(
            "Custom",
            api_key="sk-test",
            base_url="https://api.example.com",
            extra_env='{"CUSTOM_KEY": "value"}',
        )
        assert p.api_key == "sk-test"
        assert p.base_url == "https://api.example.com"
        parsed = p.parse_extra_env()
        assert parsed == {"CUSTOM_KEY": "value"}
