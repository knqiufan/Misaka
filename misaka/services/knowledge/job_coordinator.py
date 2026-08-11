"""Mutual exclusion and cancellation for knowledge-base operations."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend


class KnowledgeBaseJobCoordinator:
    """Serialise mutating operations per KB and persist their lifecycle.

    A single KB index is the consistency boundary: permitting concurrent
    upload/reprocess/delete operations would let one operation publish a
    stale snapshot over another.  The coordinator therefore uses a KB-wide
    lock and lets destructive operations cancel and await the active job.
    """

    def __init__(self, db: DatabaseBackend) -> None:
        self._db = db
        self._locks: dict[str, asyncio.Lock] = {}
        self._active: dict[str, tuple[asyncio.Task[object], str]] = {}

    @asynccontextmanager
    async def job(
        self, kb_id: str, operation: str, document_id: str = "",
    ) -> AsyncIterator[str]:
        """Run one KB mutation, recording queued/running/final states."""
        job_id = self._db.create_kb_job(kb_id, document_id, operation)
        lock = self._locks.setdefault(kb_id, asyncio.Lock())
        async with lock:
            task = asyncio.current_task()
            if task is None:  # pragma: no cover - asyncio always supplies one
                raise RuntimeError("Knowledge-base operations require an asyncio task")
            self._active[kb_id] = (task, job_id)
            self._db.update_kb_job(job_id, "running")
            try:
                yield job_id
            except asyncio.CancelledError:
                self._db.update_kb_job(job_id, "cancelled", "Operation cancelled")
                raise
            except Exception as exc:
                self._db.update_kb_job(job_id, "failed", str(exc))
                raise
            else:
                self._db.update_kb_job(job_id, "completed")
            finally:
                current = self._active.get(kb_id)
                if current and current[1] == job_id:
                    self._active.pop(kb_id, None)

    async def cancel_and_wait(self, kb_id: str) -> None:
        """Cancel the active KB job, if any, and wait for it to finish."""
        active = self._active.get(kb_id)
        if not active:
            return
        task, job_id = active
        if task is asyncio.current_task() or task.done():
            return
        self._db.update_kb_job(job_id, "cancelling", "Cancelled by a destructive operation")
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    def is_busy(self, kb_id: str) -> bool:
        """Return whether an in-process mutating operation owns this KB."""
        active = self._active.get(kb_id)
        return bool(active and not active[0].done())
