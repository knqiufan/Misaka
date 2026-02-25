"""
File type detection and language mapping for Misaka.

Maps file extensions to programming language names for syntax highlighting
and display purposes. Compatible with the TypeScript LANGUAGE_MAP.
"""

from __future__ import annotations

# Extension to language mapping (same as the TypeScript version)
LANGUAGE_MAP: dict[str, str] = {
    "ts": "typescript",
    "tsx": "typescript",
    "js": "javascript",
    "jsx": "javascript",
    "py": "python",
    "rb": "ruby",
    "rs": "rust",
    "go": "go",
    "java": "java",
    "kt": "kotlin",
    "swift": "swift",
    "c": "c",
    "cpp": "cpp",
    "h": "c",
    "hpp": "cpp",
    "cs": "csharp",
    "css": "css",
    "scss": "scss",
    "less": "less",
    "html": "html",
    "xml": "xml",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "toml": "toml",
    "md": "markdown",
    "mdx": "markdown",
    "sql": "sql",
    "sh": "bash",
    "bash": "bash",
    "zsh": "bash",
    "fish": "fish",
    "ps1": "powershell",
    "dockerfile": "dockerfile",
    "graphql": "graphql",
    "gql": "graphql",
    "vue": "vue",
    "svelte": "svelte",
    "prisma": "prisma",
    "env": "dotenv",
    "lua": "lua",
    "r": "r",
    "php": "php",
    "dart": "dart",
    "zig": "zig",
}

# Directories to skip during file tree scanning
IGNORED_DIRS: frozenset[str] = frozenset({
    "node_modules",
    ".git",
    "dist",
    ".next",
    "__pycache__",
    ".cache",
    ".turbo",
    "coverage",
    ".output",
    "build",
    ".venv",
    "venv",
    "env",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
})

# Maximum file size (in bytes) for text preview
MAX_PREVIEW_SIZE: int = 1024 * 1024  # 1 MB

# Image MIME types
IMAGE_MIME_TYPES: frozenset[str] = frozenset({
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/bmp",
    "image/tiff",
})


def get_file_language(ext: str) -> str:
    """Map a file extension to a language name for syntax highlighting.

    Args:
        ext: The file extension, with or without a leading dot.

    Returns:
        The language identifier, or ``"plaintext"`` if unknown.
    """
    normalized = ext.lstrip(".").lower()
    return LANGUAGE_MAP.get(normalized, "plaintext")


def is_image_mime(mime_type: str) -> bool:
    """Check if a MIME type represents an image."""
    return mime_type.startswith("image/")


def format_file_size(size_bytes: int) -> str:
    """Format a file size in bytes to a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"
