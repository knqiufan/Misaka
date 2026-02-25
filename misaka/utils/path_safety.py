"""
Path safety validation for Misaka.

Ensures file operations stay within expected directory boundaries
to prevent path traversal attacks.
"""

from __future__ import annotations

from pathlib import Path


def is_path_safe(base_path: str | Path, target_path: str | Path) -> bool:
    """Check that *target_path* is within or equal to *base_path*.

    Both paths are resolved to their absolute, real form before comparison
    to prevent traversal via symlinks or ``..`` components.

    Args:
        base_path: The allowed root directory.
        target_path: The path to validate.

    Returns:
        True if the target is under (or equal to) the base directory.
    """
    try:
        resolved_base = Path(base_path).resolve()
        resolved_target = Path(target_path).resolve()
    except (OSError, ValueError):
        return False

    # Check if target is the base itself or a child of it
    try:
        resolved_target.relative_to(resolved_base)
        return True
    except ValueError:
        return False


def is_root_path(p: str | Path) -> bool:
    """Check if *p* is a filesystem root (e.g., ``/``, ``C:\\``).

    Root paths are rejected as base directories for file browsing
    to prevent scanning the entire filesystem.
    """
    try:
        resolved = Path(p).resolve()
        # Compare as strings: on Windows, anchor is "C:\\" and root is "\\",
        # so we check if the resolved path equals its own parent (i.e., is a root).
        return resolved == resolved.parent
    except (OSError, ValueError):
        return False


def sanitize_filename(name: str) -> str:
    """Remove or replace characters that are unsafe in filenames.

    Keeps alphanumeric characters, dots, hyphens, and underscores.
    Everything else is replaced with an underscore.
    """
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return "".join(c if c in safe_chars else "_" for c in name)
