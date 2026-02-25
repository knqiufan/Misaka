"""
Tests for path safety utilities.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from misaka.utils.path_safety import is_path_safe, is_root_path, sanitize_filename


class TestIsPathSafe:

    def test_child_is_safe(self, tmp_path: Path) -> None:
        child = tmp_path / "subdir" / "file.txt"
        child.parent.mkdir(parents=True, exist_ok=True)
        child.touch()
        assert is_path_safe(str(tmp_path), str(child)) is True

    def test_same_path_is_safe(self, tmp_path: Path) -> None:
        assert is_path_safe(str(tmp_path), str(tmp_path)) is True

    def test_parent_traversal_is_unsafe(self, tmp_path: Path) -> None:
        target = tmp_path / ".." / ".."
        assert is_path_safe(str(tmp_path), str(target)) is False

    def test_sibling_is_unsafe(self, tmp_path: Path) -> None:
        sibling = tmp_path.parent / "other"
        assert is_path_safe(str(tmp_path), str(sibling)) is False


class TestIsRootPath:

    def test_unix_root(self) -> None:
        assert is_root_path("/") is True

    def test_regular_path(self, tmp_path: Path) -> None:
        assert is_root_path(str(tmp_path)) is False

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_windows_drive_root(self) -> None:
        assert is_root_path("C:\\") is True


class TestSanitizeFilename:

    def test_safe_name_unchanged(self) -> None:
        assert sanitize_filename("hello-world_123.txt") == "hello-world_123.txt"

    def test_spaces_replaced(self) -> None:
        assert sanitize_filename("my file.txt") == "my_file.txt"

    def test_special_chars_replaced(self) -> None:
        assert sanitize_filename("file<>|.txt") == "file___.txt"
