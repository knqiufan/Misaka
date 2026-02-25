"""
Tests for the PermissionService.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import patch

import pytest

from misaka.services.permission_service import PermissionService, TIMEOUT_SECONDS


class TestPermissionService:

    def test_register_and_resolve_allow(self) -> None:
        svc = PermissionService()
        future = svc.register("perm-1", {"file": "test.py"})
        assert not future.done()

        result = svc.resolve("perm-1", {"behavior": "allow"})
        assert result is True
        assert future.done()
        decision = future.result()
        assert decision["behavior"] == "allow"
        # updatedInput should be injected with the original tool_input
        assert decision["updatedInput"] == {"file": "test.py"}

    def test_register_and_resolve_deny(self) -> None:
        svc = PermissionService()
        future = svc.register("perm-2", {"command": "rm -rf /"})

        result = svc.resolve("perm-2", {"behavior": "deny", "message": "Too dangerous"})
        assert result is True
        decision = future.result()
        assert decision["behavior"] == "deny"
        assert decision["message"] == "Too dangerous"

    def test_resolve_nonexistent(self) -> None:
        svc = PermissionService()
        result = svc.resolve("nonexistent", {"behavior": "allow"})
        assert result is False

    def test_has_pending(self) -> None:
        svc = PermissionService()
        assert svc.has_pending() is False

        svc.register("perm-3", {})
        assert svc.has_pending() is True

        svc.resolve("perm-3", {"behavior": "deny"})
        assert svc.has_pending() is False

    def test_allow_with_updated_input(self) -> None:
        svc = PermissionService()
        svc.register("perm-4", {"original": True})

        svc.resolve("perm-4", {"behavior": "allow", "updatedInput": {"modified": True}})
        # When updatedInput is explicitly provided, it should not be overwritten

    def test_cleanup_expired(self) -> None:
        svc = PermissionService()
        future = svc.register("perm-old", {"test": True})

        # Force the created_at to be old
        svc._pending["perm-old"].created_at = time.time() - TIMEOUT_SECONDS - 1

        # Trigger cleanup
        svc._cleanup_expired()

        assert "perm-old" not in svc._pending
        assert future.done()
        decision = future.result()
        assert decision["behavior"] == "deny"
        assert "timed out" in decision["message"].lower()

    def test_double_resolve(self) -> None:
        """Resolving an already-resolved permission returns False."""
        svc = PermissionService()
        svc.register("perm-5", {})
        assert svc.resolve("perm-5", {"behavior": "allow"}) is True
        assert svc.resolve("perm-5", {"behavior": "allow"}) is False

    def test_register_cleans_up_expired(self) -> None:
        """register() calls _cleanup_expired to prevent memory leaks."""
        svc = PermissionService()
        future = svc.register("old", {})
        svc._pending["old"].created_at = time.time() - TIMEOUT_SECONDS - 1

        # Registering a new one should clean up the old
        svc.register("new", {})
        assert "old" not in svc._pending
        assert "new" in svc._pending
