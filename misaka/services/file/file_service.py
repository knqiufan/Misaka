"""
File system operations service.

Provides directory scanning, file preview, and path validation
with security checks.
"""

from __future__ import annotations

import logging
from pathlib import Path

from misaka.db.models import FilePreview, FileTreeNode
from misaka.utils.file_utils import IGNORED_DIRS, get_file_language
from misaka.utils.path_safety import is_path_safe, is_root_path

logger = logging.getLogger(__name__)


class FileService:
    """Service for file system operations."""

    async def scan_directory(self, directory: str, depth: int = 3) -> list[FileTreeNode]:
        """Scan a directory and return a tree of FileTreeNode objects.

        Args:
            directory: The root directory to scan.
            depth: Maximum recursion depth (default 3).

        Returns:
            List of FileTreeNode objects representing the directory contents.

        Raises:
            ValueError: If the directory is a filesystem root.
            FileNotFoundError: If the directory does not exist.
        """
        resolved = Path(directory).resolve()

        if is_root_path(str(resolved)):
            raise ValueError(f"Cannot scan filesystem root: {resolved}")

        if not resolved.is_dir():
            raise FileNotFoundError(f"Directory not found: {directory}")

        return self._scan_recursive(resolved, depth)

    def _scan_recursive(self, directory: Path, depth: int) -> list[FileTreeNode]:
        """Recursively scan a directory up to the given depth."""
        if depth <= 0:
            return []

        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except PermissionError:
            return []

        nodes: list[FileTreeNode] = []

        for entry in entries:
            name = entry.name

            # Skip hidden files (except .env*)
            if name.startswith(".") and not name.startswith(".env"):
                continue

            if entry.is_dir():
                if name in IGNORED_DIRS:
                    continue
                children = self._scan_recursive(entry, depth - 1)
                nodes.append(FileTreeNode(
                    name=name,
                    path=str(entry),
                    type="directory",
                    children=children,
                ))
            elif entry.is_file():
                ext = entry.suffix.lstrip(".")
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = None
                nodes.append(FileTreeNode(
                    name=name,
                    path=str(entry),
                    type="file",
                    size=size,
                    extension=ext or None,
                ))

        return nodes

    async def read_file_preview(
        self,
        file_path: str,
        max_lines: int = 200,
        base_dir: str | None = None,
    ) -> FilePreview:
        """Read a file and return a preview with language detection.

        Args:
            file_path: Path to the file.
            max_lines: Maximum number of lines to include.
            base_dir: If provided, validate that file_path is within this directory.

        Raises:
            ValueError: If the file is outside the base directory.
            FileNotFoundError: If the file does not exist.
        """
        resolved = Path(file_path).resolve()

        if base_dir and not is_path_safe(base_dir, str(resolved)):
            raise ValueError(f"File path is outside the allowed directory: {file_path}")

        if not resolved.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = resolved.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        truncated = "\n".join(lines[:max_lines])

        ext = resolved.suffix.lstrip(".")
        language = get_file_language(ext)

        return FilePreview(
            path=str(resolved),
            content=truncated,
            language=language,
            line_count=len(lines),
        )
