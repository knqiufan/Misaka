"""
In-memory notification queue for Misaka.

Manages an append-only ring buffer of :class:`Notification` objects.
Thread-safe; no database persistence — notifications are cleared on
application restart.
"""

from __future__ import annotations

import secrets
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from misaka.db.models import Notification


def _now() -> str:
    """Return the current UTC datetime as an ISO string without microseconds."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class NotificationService:
    """In-memory notification queue backed by a fixed-size ring buffer."""

    MAX_NOTIFICATIONS = 100

    def __init__(self) -> None:
        self._queue: deque[Notification] = deque(maxlen=self.MAX_NOTIFICATIONS)
        self._lock = threading.Lock()
        self._on_new: Callable[[Notification], None] | None = None

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(
        self,
        *,
        type: str,  # noqa: A002 – shadows builtin intentionally for API clarity
        title: str,
        message: str,
        source: str = "system",
        session_id: str | None = None,
        action_label: str | None = None,
        action_data: dict[str, Any] | None = None,
    ) -> Notification:
        """Create and enqueue a new notification.

        Returns the newly created :class:`Notification`.
        """
        notif = Notification(
            id=secrets.token_hex(8),
            type=type,  # type: ignore[arg-type]
            title=title,
            message=message,
            timestamp=_now(),
            source=source,
            session_id=session_id,
            action_label=action_label,
            action_data=action_data,
        )
        with self._lock:
            self._queue.appendleft(notif)
        if self._on_new:
            self._on_new(notif)
        return notif

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def unread_count(self) -> int:
        with self._lock:
            return sum(1 for n in self._queue if not n.read)

    def get_all(self) -> list[Notification]:
        """Return all notifications, newest first."""
        with self._lock:
            return list(self._queue)

    def get_unread(self) -> list[Notification]:
        """Return only unread notifications, newest first."""
        with self._lock:
            return [n for n in self._queue if not n.read]

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def mark_read(self, notif_id: str) -> None:
        """Mark a single notification as read."""
        with self._lock:
            for n in self._queue:
                if n.id == notif_id:
                    n.read = True
                    break

    def mark_all_read(self) -> None:
        """Mark every notification as read."""
        with self._lock:
            for n in self._queue:
                n.read = True

    def dismiss(self, notif_id: str) -> None:
        """Remove a single notification from the queue."""
        with self._lock:
            self._queue = deque(
                (n for n in self._queue if n.id != notif_id),
                maxlen=self.MAX_NOTIFICATIONS,
            )

    def clear_all(self) -> None:
        """Remove all notifications."""
        with self._lock:
            self._queue.clear()
