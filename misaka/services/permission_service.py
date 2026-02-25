"""
Permission request/response registry.

Manages pending permission requests from the Claude SDK and
resolves them when the user makes a decision in the UI.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5 * 60  # 5 minutes


@dataclass
class PendingPermission:
    """A permission request awaiting user decision."""
    future: asyncio.Future[dict[str, Any]]
    tool_input: dict[str, Any]
    created_at: float = field(default_factory=time.time)


class PermissionService:
    """Service for managing tool permission requests.

    The Claude SDK calls ``can_use_tool`` which registers a pending
    permission. The UI displays a dialog, and the user's decision
    is sent back via :meth:`resolve`.
    """

    def __init__(self) -> None:
        self._pending: dict[str, PendingPermission] = {}

    def _cleanup_expired(self) -> None:
        """Remove expired permission requests."""
        now = time.time()
        expired = [
            pid for pid, p in self._pending.items()
            if now - p.created_at > TIMEOUT_SECONDS
        ]
        for pid in expired:
            entry = self._pending.pop(pid, None)
            if entry and not entry.future.done():
                entry.future.set_result({"behavior": "deny", "message": "Permission timed out"})

    def register(
        self,
        permission_id: str,
        tool_input: dict[str, Any],
    ) -> asyncio.Future[dict[str, Any]]:
        """Register a pending permission request.

        Returns a Future that resolves when the user responds.
        """
        self._cleanup_expired()

        loop = asyncio.get_event_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[permission_id] = PendingPermission(
            future=future,
            tool_input=tool_input,
        )
        return future

    def resolve(self, permission_id: str, decision: dict[str, Any]) -> bool:
        """Resolve a pending permission request with the user's decision.

        Returns True if the permission was found and resolved.
        """
        entry = self._pending.pop(permission_id, None)
        if not entry:
            return False

        # Inject original tool input for 'allow' decisions
        if decision.get("behavior") == "allow" and "updatedInput" not in decision:
            decision["updatedInput"] = entry.tool_input

        if not entry.future.done():
            entry.future.set_result(decision)
        return True

    def has_pending(self) -> bool:
        """Check if there are any pending permission requests."""
        self._cleanup_expired()
        return len(self._pending) > 0
