"""
In-memory ring-buffer log handler with automatic sanitization.

Provides a ``RingBufferHandler`` that keeps the most recent *maxlen*
log records in a ``collections.deque``, plus a ``SanitizingFilter``
that redacts sensitive data (API keys, tokens, passwords) before the
record is emitted.
"""

from __future__ import annotations

import logging
import re
import threading
from collections import deque
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

_SENSITIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Generic API keys (sk-ant-..., sk-..., key-...)
    (re.compile(r"(sk-ant-api\d{2}-)[A-Za-z0-9\-_]{20,}"), r"\1***"),
    (re.compile(r"(sk-)[A-Za-z0-9\-_]{20,}"), r"\1***"),
    (re.compile(r"(key-)[A-Za-z0-9]{20,}"), r"\1***"),
    # Bearer / Authorization tokens
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-_\.]{20,}", re.IGNORECASE), r"\1***"),
    (re.compile(r"(Authorization:\s*(?:Bearer\s+)?)[^\s]{20,}", re.IGNORECASE), r"\1***"),
    # password=... / token=... / secret=... in query strings or assignments
    (
        re.compile(
            r"((?:password|token|secret|api_key|apikey)[\s]*[=:]\s*)[^\s,;\"']{8,}",
            re.IGNORECASE,
        ),
        r"\1***",
    ),
]


def sanitize(text: str) -> str:
    """Redact sensitive values from *text*."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Logging filter
# ---------------------------------------------------------------------------

class SanitizingFilter(logging.Filter):
    """``logging.Filter`` that rewrites ``record.msg`` to redact secrets."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: sanitize(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    sanitize(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


# ---------------------------------------------------------------------------
# Formatted log entry
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LogEntry:
    """A single formatted log line kept in the ring buffer."""
    timestamp: str
    level: str
    logger_name: str
    message: str

    def format_line(self) -> str:
        return f"{self.timestamp} [{self.level}] {self.logger_name}: {self.message}"


# ---------------------------------------------------------------------------
# Ring-buffer handler
# ---------------------------------------------------------------------------

_DEFAULT_MAX_ENTRIES = 200


class RingBufferHandler(logging.Handler):
    """A ``logging.Handler`` backed by a fixed-size ``collections.deque``.

    Thread-safe; callers may read *entries* at any time from any thread.
    """

    def __init__(self, maxlen: int = _DEFAULT_MAX_ENTRIES, level: int = logging.DEBUG) -> None:
        super().__init__(level)
        self._entries: deque[LogEntry] = deque(maxlen=maxlen)
        self._lock_rw = threading.Lock()
        self.addFilter(SanitizingFilter())

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = LogEntry(
                timestamp=self.format_time(record),
                level=record.levelname,
                logger_name=record.name,
                message=self.format(record) if self.formatter else record.getMessage(),
            )
            with self._lock_rw:
                self._entries.append(entry)
        except Exception:  # noqa: BLE001
            self.handleError(record)

    @staticmethod
    def format_time(record: logging.LogRecord) -> str:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def get_entries(self, level_filter: str | None = None) -> list[LogEntry]:
        """Return a snapshot of buffered entries, optionally filtered by level."""
        with self._lock_rw:
            entries = list(self._entries)
        if level_filter:
            upper = level_filter.upper()
            entries = [e for e in entries if e.level == upper]
        return entries

    def clear(self) -> None:
        with self._lock_rw:
            self._entries.clear()

    @property
    def entry_count(self) -> int:
        with self._lock_rw:
            return len(self._entries)

    @property
    def max_entries(self) -> int:
        return self._entries.maxlen or _DEFAULT_MAX_ENTRIES


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_ring_handler: RingBufferHandler | None = None


def get_ring_handler() -> RingBufferHandler:
    """Return the global ``RingBufferHandler`` singleton, creating it if needed."""
    global _ring_handler  # noqa: PLW0603
    if _ring_handler is None:
        _ring_handler = RingBufferHandler()
    return _ring_handler


def install_ring_handler(
    logger_name: str | None = None,
    maxlen: int = _DEFAULT_MAX_ENTRIES,
) -> RingBufferHandler:
    """Create (or reuse) the singleton and attach it to the given logger.

    Args:
        logger_name: Logger name; ``None`` means root logger.
        maxlen: Maximum number of entries to keep.

    Returns:
        The handler instance for later querying.
    """
    global _ring_handler  # noqa: PLW0603
    if _ring_handler is None:
        _ring_handler = RingBufferHandler(maxlen=maxlen)
    target = logging.getLogger(logger_name)
    if _ring_handler not in target.handlers:
        target.addHandler(_ring_handler)
    return _ring_handler
