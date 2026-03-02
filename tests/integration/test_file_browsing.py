"""
Integration test: file browsing.

Tests file tree scanning and file preview with real filesystem operations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from misaka.services.file.file_service import FileService


@pytest.fixture
def file_service() -> FileService:
    return FileService()


class TestFileBrowsing:

    @pytest.mark.asyncio
    async def test_full_scan_and_preview(self, file_service: FileService, tmp_path: Path) -> None:
        # Setup
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("# Main application\nprint('hello')\n")
        (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42\n")
        (tmp_path / "README.md").write_text("# Project\n\nDescription here.\n")

        # Scan
        tree = await file_service.scan_directory(str(tmp_path))
        assert len(tree) >= 2  # src/ and README.md

        # Find the src directory
        src_node = next((n for n in tree if n.name == "src"), None)
        assert src_node is not None
        assert src_node.type == "directory"
        assert len(src_node.children) == 2

        # Preview a file
        preview = await file_service.read_file_preview(str(tmp_path / "src" / "app.py"))
        assert "Main application" in preview.content
        assert preview.language == "python"
        # Trailing newline gives 3 lines when split by "\n"
        assert preview.line_count >= 2

    @pytest.mark.asyncio
    async def test_hidden_files_ignored(self, file_service: FileService, tmp_path: Path) -> None:
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / ".env").write_text("KEY=value")  # .env should be kept
        (tmp_path / "visible.txt").write_text("hello")

        tree = await file_service.scan_directory(str(tmp_path))
        names = {n.name for n in tree}
        assert "visible.txt" in names
        assert ".env" in names
        assert ".hidden" not in names
