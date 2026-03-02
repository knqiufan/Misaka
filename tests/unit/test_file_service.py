"""
Tests for the file service.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from misaka.services.file.file_service import FileService


@pytest.fixture
def file_service() -> FileService:
    return FileService()


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a sample project structure for testing."""
    # Create directories
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "utils").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "node_modules").mkdir()  # Should be ignored

    # Create files
    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("print('hello')\n")
    (tmp_path / "src" / "utils" / "helpers.py").write_text("def help(): pass\n")
    (tmp_path / "tests" / "test_main.py").write_text("def test_it(): pass\n")
    (tmp_path / "node_modules" / "pkg.json").write_text("{}")

    return tmp_path


class TestFileService:

    @pytest.mark.asyncio
    async def test_scan_directory(self, file_service: FileService, sample_project: Path) -> None:
        nodes = await file_service.scan_directory(str(sample_project))
        names = {n.name for n in nodes}
        assert "src" in names
        assert "tests" in names
        assert "README.md" in names
        # node_modules should be filtered out
        assert "node_modules" not in names

    @pytest.mark.asyncio
    async def test_scan_directory_depth(
        self, file_service: FileService, sample_project: Path
    ) -> None:
        nodes = await file_service.scan_directory(str(sample_project), depth=1)
        # At depth 1, directories should have no children
        for node in nodes:
            if node.type == "directory":
                assert node.children == []

    @pytest.mark.asyncio
    async def test_scan_root_rejected(self, file_service: FileService) -> None:
        # Use the actual system drive root on Windows, "/" on Unix
        root = "C:\\" if os.name == "nt" else "/"
        with pytest.raises(ValueError, match="root"):
            await file_service.scan_directory(root)

    @pytest.mark.asyncio
    async def test_scan_nonexistent(self, file_service: FileService) -> None:
        with pytest.raises(FileNotFoundError):
            await file_service.scan_directory("/nonexistent/path/xyz")

    @pytest.mark.asyncio
    async def test_read_file_preview(
        self, file_service: FileService, sample_project: Path
    ) -> None:
        preview = await file_service.read_file_preview(
            str(sample_project / "src" / "main.py")
        )
        assert "hello" in preview.content
        assert preview.language == "python"
        assert preview.line_count >= 1

    @pytest.mark.asyncio
    async def test_read_file_preview_with_base_dir(
        self, file_service: FileService, sample_project: Path
    ) -> None:
        preview = await file_service.read_file_preview(
            str(sample_project / "src" / "main.py"),
            base_dir=str(sample_project),
        )
        assert preview.language == "python"

    @pytest.mark.asyncio
    async def test_read_file_preview_outside_base(
        self, file_service: FileService, sample_project: Path,
    ) -> None:
        # Create a file outside the project using a separate temp dir
        import tempfile
        with tempfile.TemporaryDirectory() as other_dir:
            outside = Path(other_dir) / "outside.txt"
            outside.write_text("secret")

            with pytest.raises(ValueError, match="outside"):
                await file_service.read_file_preview(
                    str(outside),
                    base_dir=str(sample_project),
                )
