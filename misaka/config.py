"""
Configuration management for Misaka.

Handles data directory paths, environment variable loading,
and platform-specific configuration.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

IS_WINDOWS: bool = sys.platform == "win32"
IS_MACOS: bool = sys.platform == "darwin"
IS_LINUX: bool = sys.platform == "linux"


# ---------------------------------------------------------------------------
# Data directory
# ---------------------------------------------------------------------------

def _get_data_dir() -> Path:
    """Return the Misaka data directory.

    Respects the ``MISAKA_DATA_DIR`` environment variable.
    Falls back to ``~/.misaka/``.
    """
    env_dir = os.environ.get("MISAKA_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return Path.home() / ".misaka"


DATA_DIR: Path = _get_data_dir()
"""Root data directory for Misaka (default ``~/.misaka/``)."""

DB_PATH: Path = DATA_DIR / "misaka.db"
"""Path to the database file."""

LOG_PATH: Path = DATA_DIR / "misaka.log"
"""Path to the application log file."""

ATTACHMENTS_DIR: Path = DATA_DIR / "attachments"
"""Root directory for image attachments (organized by session_id)."""

KNOWLEDGE_BASE_DIR: Path = DATA_DIR / "knowledge_base"
"""Root directory for knowledge base file storage (organized by kb_id)."""


def get_session_attachments_dir(session_id: str) -> Path:
    """Return the attachments directory for a specific session."""
    return ATTACHMENTS_DIR / session_id


def get_kb_storage_dir(kb_id: str) -> Path:
    """Return the file storage directory for a specific knowledge base."""
    return KNOWLEDGE_BASE_DIR / kb_id


def ensure_data_dir() -> None:
    """Create the data directory if it does not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_BASE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Claude Code configuration
# ---------------------------------------------------------------------------

def get_claude_config_paths() -> list[Path]:
    """Return paths to Claude configuration files (``~/.claude.json``, etc.)."""
    home = Path.home()
    return [
        home / ".claude.json",
        home / ".claude" / "settings.json",
    ]


def get_api_key_from_env() -> str | None:
    """Return the Anthropic API key from environment variables, if set."""
    return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")


# ---------------------------------------------------------------------------
# Well-known setting keys (mirrors TypeScript SETTING_KEYS)
# ---------------------------------------------------------------------------

class SettingKeys:
    """Constants for well-known settings stored in the database."""

    DEFAULT_MODEL = "default_model"
    DEFAULT_SYSTEM_PROMPT = "default_system_prompt"
    THEME = "theme"
    PERMISSION_MODE = "permission_mode"
    MAX_THINKING_TOKENS = "max_thinking_tokens"
    DANGEROUSLY_SKIP_PERMISSIONS = "dangerously_skip_permissions"
    CLAUDE_DEBUG_LOG = "claude_debug_log"
    LANGUAGE = "language"
    ACCENT_COLOR = "accent_color"
    CHAT_GROUP_MODE = "chat_group_mode"
    SETUP_WIZARD_COMPLETED = "setup_wizard_completed"
    VECTOR_BACKEND = "vector_backend"
    VECTOR_BACKEND_FINGERPRINT = "vector_backend_fingerprint"
    VECTOR_BACKEND_PENDING_KBS = "vector_backend_pending_kbs"


# ---------------------------------------------------------------------------
# PATH expansion (for finding Claude CLI)
# ---------------------------------------------------------------------------

def get_extra_path_dirs() -> list[str]:
    """Return additional directories to search for CLI tools."""
    home = str(Path.home())
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
        local_appdata = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        paths = [
            os.path.join(appdata, "npm"),
            os.path.join(local_appdata, "npm"),
            os.path.join(local_appdata, "Microsoft", "WindowsApps"),
            os.path.join(local_appdata, "Microsoft", "WinGet", "Links"),
            os.path.join(local_appdata, "Programs", "Python"),
            os.path.join(program_files, "nodejs"),
            os.path.join(program_files, "Git", "cmd"),
            os.path.join(home, ".npm-global", "bin"),
            os.path.join(home, ".claude", "bin"),
            os.path.join(home, ".local", "bin"),
            os.path.join(home, ".nvm", "current", "bin"),
        ]
        python_root = Path(local_appdata) / "Programs" / "Python"
        if python_root.is_dir():
            for python_dir in python_root.glob("Python*"):
                paths.extend((str(python_dir), str(python_dir / "Scripts")))
        return paths
    return [
        "/usr/local/bin",
        "/opt/homebrew/bin",
        "/usr/bin",
        "/bin",
        os.path.join(home, ".npm-global", "bin"),
        os.path.join(home, ".nvm", "current", "bin"),
        os.path.join(home, ".local", "bin"),
        os.path.join(home, ".claude", "bin"),
    ]


def get_assets_path() -> Path:
    """Return the path to the assets directory.

    Uses sys._MEIPASS when running as a frozen executable (PyInstaller),
    otherwise the project's assets folder relative to the package root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent / "assets"


def get_expanded_path() -> str:
    """Build a fresh PATH including package-manager changes made after startup."""
    current = os.environ.get("PATH", "")
    parts = [p for p in current.split(os.pathsep) if p]
    candidates = [*parts, *_get_windows_registry_path_dirs(), *get_extra_path_dirs()]
    result: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        normalized = os.path.expandvars(path.strip().strip('"'))
        key = os.path.normcase(normalized)
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return os.pathsep.join(result)


def _get_windows_registry_path_dirs() -> list[str]:
    """Read current user/machine PATH values so post-install checks see updates."""
    if not IS_WINDOWS:
        return []

    import winreg

    locations = (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    )
    paths: list[str] = []
    for hive, key_path in locations:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        if isinstance(value, str):
            paths.extend(part for part in value.split(os.pathsep) if part)
    return paths
