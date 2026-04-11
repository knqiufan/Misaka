"""
Structured error classification for Misaka.

Provides a 16-category error taxonomy with ``ErrorClassifier`` that maps
Python exceptions to user-readable, i18n-aware messages with suggested
recovery actions.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Enumeration of structured error categories."""

    NETWORK = "network"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    PARSE = "parse"
    PERMISSION = "permission"
    TIMEOUT = "timeout"
    CLI_NOT_FOUND = "cli_not_found"
    CLI_CONNECTION = "cli_connection"
    PROCESS = "process"
    SDK = "sdk"
    FILE_NOT_FOUND = "file_not_found"
    FILE_EXISTS = "file_exists"
    VALIDATION = "validation"
    IMPORT = "import"
    IO = "io"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassifiedError:
    """A classified error with category, message, and suggested action.

    Attributes:
        category: The error category from ``ErrorCategory``.
        message_key: i18n key for the user-facing message
            (e.g. ``"errors.network.message"``).
        suggestion_key: i18n key for the suggested recovery action
            (e.g. ``"errors.network.suggestion"``).
        detail: Optional raw detail string (original exception message).
        original: The original exception, if available.
    """

    category: ErrorCategory
    message_key: str
    suggestion_key: str
    detail: str = ""
    original: BaseException | None = None


# ---------------------------------------------------------------------------
# Pattern-based sub-classifiers for ambiguous exception types
# ---------------------------------------------------------------------------

_AUTH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"api.?key",
        r"auth",
        r"unauthorized",
        r"401",
        r"403",
        r"invalid.?key",
        r"credential",
        r"token.*(invalid|expired|missing)",
    )
]

_RATE_LIMIT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"rate.?limit",
        r"429",
        r"too many requests",
        r"quota",
        r"throttl",
        r"overloaded",
    )
]

_NETWORK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"connect",
        r"network",
        r"dns",
        r"refused",
        r"unreachable",
        r"reset by peer",
        r"broken pipe",
        r"ssl",
        r"tls",
        r"socket",
    )
]

_TIMEOUT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"timeout",
        r"timed?\s*out",
        r"deadline",
    )
]


def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


# ---------------------------------------------------------------------------
# ErrorClassifier
# ---------------------------------------------------------------------------

class ErrorClassifier:
    """Maps Python exceptions to ``ClassifiedError`` instances.

    The classifier uses a two-stage strategy:
    1. Match by exception *type* (precise mapping).
    2. Fall back to *message pattern* matching for generic types like
       ``Exception``, ``OSError``, ``RuntimeError``.
    """

    @staticmethod
    def classify(exc: BaseException) -> ClassifiedError:
        """Classify an exception into a structured error.

        Args:
            exc: The exception to classify.

        Returns:
            A ``ClassifiedError`` with category, i18n keys, and detail.
        """
        detail = str(exc)
        exc_type_name = type(exc).__name__

        # --- Stage 1: type-based matching ---

        # Claude SDK specific types (matched by class name to avoid
        # hard imports that fail when the SDK is not installed).
        if exc_type_name == "CLINotFoundError":
            return _make(ErrorCategory.CLI_NOT_FOUND, detail, exc)

        if exc_type_name == "CLIConnectionError":
            return _make(ErrorCategory.CLI_CONNECTION, detail, exc)

        if exc_type_name == "ProcessError":
            return _make(ErrorCategory.PROCESS, detail, exc)

        if exc_type_name == "ClaudeSDKError":
            return _classify_by_message(detail, exc, fallback=ErrorCategory.SDK)

        # Standard library types
        if isinstance(exc, asyncio_timeout_error()):
            return _make(ErrorCategory.TIMEOUT, detail, exc)

        if isinstance(exc, json.JSONDecodeError):
            return _make(ErrorCategory.PARSE, detail, exc)

        if isinstance(exc, FileNotFoundError):
            return _make(ErrorCategory.FILE_NOT_FOUND, detail, exc)

        if isinstance(exc, FileExistsError):
            return _make(ErrorCategory.FILE_EXISTS, detail, exc)

        if isinstance(exc, PermissionError):
            return _make(ErrorCategory.PERMISSION, detail, exc)

        if isinstance(exc, ValueError):
            return _make(ErrorCategory.VALIDATION, detail, exc)

        if isinstance(exc, ImportError):
            return _make(ErrorCategory.IMPORT, detail, exc)

        if isinstance(exc, OSError):
            return _classify_oserror(exc, detail)

        # asyncio.CancelledError — not really an "error" the user sees,
        # but classify it so callers can filter.
        if isinstance(exc, _cancelled_error_type()):
            return _make(ErrorCategory.UNKNOWN, detail, exc)

        # --- Stage 2: message-based matching for generic types ---
        return _classify_by_message(detail, exc, fallback=ErrorCategory.UNKNOWN)

    @staticmethod
    def classify_error_string(error_msg: str) -> ClassifiedError:
        """Classify a plain error message string (no exception object).

        Useful when the error comes from a callback like ``on_error``
        that only provides a string.
        """
        return _classify_by_message(error_msg, original=None, fallback=ErrorCategory.UNKNOWN)

    @staticmethod
    def format_user_message(
        classified: ClassifiedError,
        translate: Any = None,
    ) -> str:
        """Format a user-readable message from a classified error.

        Args:
            classified: The classified error.
            translate: Optional translation function ``t(key, **kw) -> str``.
                When omitted, falls back to the i18n key itself.

        Returns:
            A formatted string like ``"[Network Error] <message>\\n<suggestion>"``
        """
        if translate is None:
            from misaka.i18n import t as translate

        msg = translate(classified.message_key, detail=classified.detail)
        suggestion = translate(classified.suggestion_key)
        return f"{msg}\n{suggestion}" if suggestion != classified.suggestion_key else msg


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make(
    category: ErrorCategory,
    detail: str,
    original: BaseException | None,
) -> ClassifiedError:
    return ClassifiedError(
        category=category,
        message_key=f"errors.{category.value}.message",
        suggestion_key=f"errors.{category.value}.suggestion",
        detail=detail,
        original=original,
    )


def _classify_by_message(
    detail: str,
    original: BaseException | None,
    *,
    fallback: ErrorCategory,
) -> ClassifiedError:
    """Attempt to classify by scanning the error message text."""
    if _matches_any(detail, _RATE_LIMIT_PATTERNS):
        return _make(ErrorCategory.RATE_LIMIT, detail, original)
    if _matches_any(detail, _AUTH_PATTERNS):
        return _make(ErrorCategory.AUTH, detail, original)
    if _matches_any(detail, _TIMEOUT_PATTERNS):
        return _make(ErrorCategory.TIMEOUT, detail, original)
    if _matches_any(detail, _NETWORK_PATTERNS):
        return _make(ErrorCategory.NETWORK, detail, original)
    return _make(fallback, detail, original)


def _classify_oserror(exc: OSError, detail: str) -> ClassifiedError:
    """Sub-classify ``OSError`` by errno or message patterns."""
    import errno

    if exc.errno in (errno.EACCES, errno.EPERM):
        return _make(ErrorCategory.PERMISSION, detail, exc)
    if exc.errno == errno.ENOENT:
        return _make(ErrorCategory.FILE_NOT_FOUND, detail, exc)
    if exc.errno == errno.EEXIST:
        return _make(ErrorCategory.FILE_EXISTS, detail, exc)
    if exc.errno in (
        errno.ECONNREFUSED,
        errno.ECONNRESET,
        errno.ECONNABORTED,
        getattr(errno, "ENETUNREACH", -1),
        getattr(errno, "EHOSTUNREACH", -1),
    ):
        return _make(ErrorCategory.NETWORK, detail, exc)
    if exc.errno == getattr(errno, "ETIMEDOUT", -1):
        return _make(ErrorCategory.TIMEOUT, detail, exc)
    # Generic IO
    return _make(ErrorCategory.IO, detail, exc)


def asyncio_timeout_error() -> type:
    """Return the asyncio timeout error class (varies by Python version)."""
    import asyncio
    return asyncio.TimeoutError


def _cancelled_error_type() -> type:
    import asyncio
    return asyncio.CancelledError
