"""Tests for the structured error classification system."""

from __future__ import annotations

import asyncio
import errno
import json

import pytest

from misaka.errors import ClassifiedError, ErrorCategory, ErrorClassifier

# ---------------------------------------------------------------------------
# Type-based classification
# ---------------------------------------------------------------------------


class TestClassifyByType:
    """Test classification based on exception type."""

    def test_file_not_found(self) -> None:
        exc = FileNotFoundError("config.json")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.FILE_NOT_FOUND
        assert result.message_key == "errors.file_not_found.message"
        assert result.suggestion_key == "errors.file_not_found.suggestion"
        assert result.detail == "config.json"
        assert result.original is exc

    def test_file_exists(self) -> None:
        exc = FileExistsError("output.txt")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.FILE_EXISTS

    def test_permission_error(self) -> None:
        exc = PermissionError("Access denied")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.PERMISSION

    def test_value_error(self) -> None:
        exc = ValueError("invalid input")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.VALIDATION

    def test_json_decode_error(self) -> None:
        exc = json.JSONDecodeError("Expecting value", "", 0)
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.PARSE

    def test_import_error(self) -> None:
        exc = ImportError("No module named 'foo'")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.IMPORT

    def test_timeout_error(self) -> None:
        exc = asyncio.TimeoutError()
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.TIMEOUT

    def test_cancelled_error(self) -> None:
        exc = asyncio.CancelledError()
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.UNKNOWN


# ---------------------------------------------------------------------------
# SDK exception classification (matched by class name)
# ---------------------------------------------------------------------------


class _FakeSDKError(Exception):
    """Simulate SDK exceptions without importing the SDK."""


class CLINotFoundError(_FakeSDKError):
    pass


class CLIConnectionError(_FakeSDKError):
    pass


class ProcessError(_FakeSDKError):
    pass


class ClaudeSDKError(_FakeSDKError):
    pass


class TestClassifySDKTypes:
    """Test classification of Claude SDK exception types (by class name)."""

    def test_cli_not_found(self) -> None:
        exc = CLINotFoundError("not found")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.CLI_NOT_FOUND

    def test_cli_connection(self) -> None:
        exc = CLIConnectionError("connection refused")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.CLI_CONNECTION

    def test_process_error(self) -> None:
        exc = ProcessError("exit code 1")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.PROCESS

    def test_sdk_error_generic(self) -> None:
        exc = ClaudeSDKError("something failed")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.SDK

    def test_sdk_error_with_auth_message(self) -> None:
        exc = ClaudeSDKError("401 Unauthorized: invalid API key")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.AUTH

    def test_sdk_error_with_rate_limit_message(self) -> None:
        exc = ClaudeSDKError("429 Too Many Requests")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.RATE_LIMIT


# ---------------------------------------------------------------------------
# OSError sub-classification
# ---------------------------------------------------------------------------


class TestClassifyOSError:
    """Test OSError sub-classification by errno."""

    def test_oserror_eacces(self) -> None:
        exc = OSError(errno.EACCES, "Permission denied", "/secret")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.PERMISSION

    def test_oserror_enoent(self) -> None:
        exc = OSError(errno.ENOENT, "No such file", "/missing")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.FILE_NOT_FOUND

    def test_oserror_eexist(self) -> None:
        exc = OSError(errno.EEXIST, "File exists", "/existing")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.FILE_EXISTS

    def test_oserror_econnrefused(self) -> None:
        exc = OSError(errno.ECONNREFUSED, "Connection refused")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.NETWORK

    def test_oserror_generic(self) -> None:
        exc = OSError(errno.EIO, "I/O error")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.IO


# ---------------------------------------------------------------------------
# Message-based (pattern) classification
# ---------------------------------------------------------------------------


class TestClassifyByMessage:
    """Test fallback classification via message pattern matching."""

    def test_network_pattern(self) -> None:
        exc = Exception("Connection refused by remote host")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.NETWORK

    def test_auth_pattern(self) -> None:
        exc = Exception("Invalid API key provided")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.AUTH

    def test_rate_limit_pattern(self) -> None:
        exc = Exception("Rate limit exceeded, retry after 30s")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.RATE_LIMIT

    def test_timeout_pattern(self) -> None:
        exc = Exception("Operation timed out after 60s")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.TIMEOUT

    def test_unknown_fallback(self) -> None:
        exc = Exception("something completely unexpected happened")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.UNKNOWN

    def test_dns_pattern(self) -> None:
        exc = RuntimeError("DNS resolution failed for api.anthropic.com")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.NETWORK

    def test_ssl_pattern(self) -> None:
        exc = RuntimeError("SSL handshake failed")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.NETWORK

    def test_quota_pattern(self) -> None:
        exc = RuntimeError("Account quota exceeded")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.RATE_LIMIT

    def test_token_expired_pattern(self) -> None:
        exc = RuntimeError("Token expired, please re-authenticate")
        result = ErrorClassifier.classify(exc)
        assert result.category == ErrorCategory.AUTH


# ---------------------------------------------------------------------------
# classify_error_string (no exception object)
# ---------------------------------------------------------------------------


class TestClassifyErrorString:
    """Test classification from plain error strings."""

    def test_network_string(self) -> None:
        result = ErrorClassifier.classify_error_string("Connection reset by peer")
        assert result.category == ErrorCategory.NETWORK
        assert result.original is None

    def test_auth_string(self) -> None:
        result = ErrorClassifier.classify_error_string("401 Unauthorized")
        assert result.category == ErrorCategory.AUTH

    def test_unknown_string(self) -> None:
        result = ErrorClassifier.classify_error_string("generic failure")
        assert result.category == ErrorCategory.UNKNOWN

    def test_rate_limit_string(self) -> None:
        result = ErrorClassifier.classify_error_string("429 Too many requests")
        assert result.category == ErrorCategory.RATE_LIMIT


# ---------------------------------------------------------------------------
# format_user_message
# ---------------------------------------------------------------------------


class TestFormatUserMessage:
    """Test user-facing message formatting."""

    def test_format_with_custom_translate(self) -> None:
        classified = ClassifiedError(
            category=ErrorCategory.NETWORK,
            message_key="errors.network.message",
            suggestion_key="errors.network.suggestion",
            detail="Connection refused",
        )

        def fake_t(key: str, **kwargs: str) -> str:
            translations = {
                "errors.network.message": "Network error: {detail}",
                "errors.network.suggestion": "Check your internet connection.",
            }
            text = translations.get(key, key)
            return text.format(**kwargs) if kwargs else text

        result = ErrorClassifier.format_user_message(classified, translate=fake_t)
        assert "Network error: Connection refused" in result
        assert "Check your internet connection." in result

    def test_format_without_suggestion(self) -> None:
        """When translate returns the key itself (no translation), omit suggestion."""
        classified = ClassifiedError(
            category=ErrorCategory.UNKNOWN,
            message_key="errors.unknown.message",
            suggestion_key="errors.unknown.suggestion",
            detail="oops",
        )

        def noop_t(key: str, **kwargs: str) -> str:
            return key

        result = ErrorClassifier.format_user_message(classified, translate=noop_t)
        assert result == "errors.unknown.message"
        assert "suggestion" not in result


# ---------------------------------------------------------------------------
# ClassifiedError immutability
# ---------------------------------------------------------------------------


class TestClassifiedError:
    """Test ClassifiedError dataclass properties."""

    def test_frozen(self) -> None:
        err = ClassifiedError(
            category=ErrorCategory.NETWORK,
            message_key="errors.network.message",
            suggestion_key="errors.network.suggestion",
        )
        with pytest.raises(AttributeError):
            err.category = ErrorCategory.AUTH  # type: ignore[misc]

    def test_defaults(self) -> None:
        err = ClassifiedError(
            category=ErrorCategory.UNKNOWN,
            message_key="errors.unknown.message",
            suggestion_key="errors.unknown.suggestion",
        )
        assert err.detail == ""
        assert err.original is None


# ---------------------------------------------------------------------------
# ErrorCategory enum completeness
# ---------------------------------------------------------------------------


class TestErrorCategory:
    """Test that all 16 categories are present."""

    def test_has_16_members(self) -> None:
        assert len(ErrorCategory) == 16

    def test_all_values_unique(self) -> None:
        values = [c.value for c in ErrorCategory]
        assert len(values) == len(set(values))

    def test_expected_categories(self) -> None:
        expected = {
            "network", "auth", "rate_limit", "parse", "permission",
            "timeout", "cli_not_found", "cli_connection", "process",
            "sdk", "file_not_found", "file_exists", "validation",
            "import", "io", "unknown",
        }
        assert {c.value for c in ErrorCategory} == expected
