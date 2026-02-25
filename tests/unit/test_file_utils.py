"""
Tests for file utility functions.
"""

from __future__ import annotations

import pytest

from misaka.utils.file_utils import (
    IGNORED_DIRS,
    get_file_language,
    is_image_mime,
    format_file_size,
)


class TestGetFileLanguage:

    def test_python(self) -> None:
        assert get_file_language("py") == "python"

    def test_typescript(self) -> None:
        assert get_file_language("ts") == "typescript"
        assert get_file_language("tsx") == "typescript"

    def test_javascript(self) -> None:
        assert get_file_language("js") == "javascript"

    def test_rust(self) -> None:
        assert get_file_language("rs") == "rust"

    def test_unknown_returns_plaintext(self) -> None:
        assert get_file_language("xyz") == "plaintext"
        assert get_file_language("") == "plaintext"

    def test_with_leading_dot(self) -> None:
        assert get_file_language(".py") == "python"

    def test_case_insensitive(self) -> None:
        assert get_file_language("PY") == "python"
        assert get_file_language("Ts") == "typescript"


class TestIsImageMime:

    def test_image_types(self) -> None:
        assert is_image_mime("image/png") is True
        assert is_image_mime("image/jpeg") is True
        assert is_image_mime("image/webp") is True

    def test_non_image_types(self) -> None:
        assert is_image_mime("text/plain") is False
        assert is_image_mime("application/json") is False


class TestFormatFileSize:

    def test_bytes(self) -> None:
        assert format_file_size(500) == "500 B"

    def test_kilobytes(self) -> None:
        assert format_file_size(2048) == "2.0 KB"

    def test_megabytes(self) -> None:
        assert format_file_size(1048576) == "1.0 MB"
        assert format_file_size(5 * 1024 * 1024) == "5.0 MB"


class TestIgnoredDirs:

    def test_common_dirs_ignored(self) -> None:
        assert "node_modules" in IGNORED_DIRS
        assert ".git" in IGNORED_DIRS
        assert "__pycache__" in IGNORED_DIRS
        assert ".venv" in IGNORED_DIRS
        assert "venv" in IGNORED_DIRS

    def test_is_frozenset(self) -> None:
        assert isinstance(IGNORED_DIRS, frozenset)
