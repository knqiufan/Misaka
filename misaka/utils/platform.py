"""
Platform-specific utilities for Misaka.

Handles Claude CLI binary discovery, Git Bash detection on Windows,
and other platform-dependent operations.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path

from misaka.config import IS_WINDOWS, get_expanded_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Subprocess window suppression (Windows + PyInstaller)
# ---------------------------------------------------------------------------

# When running as a PyInstaller GUI exe (console=False) on Windows, every
# subprocess.Popen / asyncio.create_subprocess_exec call will briefly flash
# a console window. Passing CREATE_NO_WINDOW and STARTF_USESHOWWINDOW hides it.
_SUBPROCESS_FLAGS: int = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0


def build_background_subprocess_kwargs() -> dict[str, object]:
    """Return hidden-window subprocess kwargs for background commands."""
    if not IS_WINDOWS:
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": _SUBPROCESS_FLAGS,
        "startupinfo": startupinfo,
    }


def subprocess_creation_flags() -> dict[str, int]:
    """Return ``creationflags`` kwarg dict for subprocess calls on Windows.

    Usage::

        await asyncio.create_subprocess_exec(
            *cmd, stdout=PIPE, stderr=PIPE, **subprocess_creation_flags(),
        )
    """
    kwargs = build_background_subprocess_kwargs()
    creationflags = kwargs.get("creationflags")
    if isinstance(creationflags, int) and creationflags:
        return {"creationflags": creationflags}
    return {}


def wrap_windows_script_command(binary_path: str, args: list[str]) -> list[str]:
    """Wrap Windows script launchers so they run silently under cmd.exe."""
    if IS_WINDOWS and binary_path.lower().endswith((".cmd", ".bat")):
        quoted_binary = f'"{binary_path}"'
        quoted_args = subprocess.list2cmdline(args)
        cmdline = quoted_binary if not quoted_args else f"{quoted_binary} {quoted_args}"
        return ["cmd.exe", "/d", "/s", "/c", cmdline]
    return [binary_path, *args]


# ---------------------------------------------------------------------------
# Generic binary discovery
# ---------------------------------------------------------------------------


def find_binary_in_path(cmd: str) -> str | None:
    """Locate a binary on the expanded PATH.

    Combines the platform-expanded PATH with ``shutil.which`` so that
    callers don't need to repeat this two-step pattern.
    """
    expanded = get_expanded_path()
    return shutil.which(cmd, path=expanded)


# ---------------------------------------------------------------------------
# Claude CLI discovery
# ---------------------------------------------------------------------------

_cached_claude_path: str | None = None
_cached_claude_sdk_path: str | None = None
_cache_valid: bool = False
_cache_sdk_valid: bool = False


def find_claude_binary() -> str | None:
    """Find and validate the Claude Code CLI binary.

    Checks known installation paths first, then falls back to
    ``which``/``where`` with an expanded PATH.

    Returns:
        The path to the Claude binary, or None if not found.
    """
    global _cached_claude_path, _cache_valid
    if _cache_valid:
        return _cached_claude_path

    found = _find_claude_binary_uncached()
    if found:
        _cached_claude_path = found
        _cache_valid = True
    return found


def clear_claude_cache() -> None:
    """Clear the cached Claude binary path (e.g., after installation)."""
    global _cached_claude_path, _cached_claude_sdk_path, _cache_valid, _cache_sdk_valid
    _cached_claude_path = None
    _cached_claude_sdk_path = None
    _cache_valid = False
    _cache_sdk_valid = False


def find_claude_sdk_binary() -> str | None:
    """Find a Claude CLI path suitable for SDK process launch on Windows."""
    global _cached_claude_sdk_path, _cache_sdk_valid
    if _cache_sdk_valid:
        return _cached_claude_sdk_path

    found = _find_claude_sdk_binary_uncached()
    if found:
        _cached_claude_sdk_path = found
        _cache_sdk_valid = True
    return found

def _get_claude_candidate_paths() -> list[str]:
    """Return candidate paths where the Claude CLI might be installed."""
    home = str(Path.home())
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
        local_appdata = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        exts = [".cmd", ".exe", ".bat", ""]
        base_dirs = [
            os.path.join(appdata, "npm"),
            os.path.join(local_appdata, "npm"),
            os.path.join(home, ".npm-global", "bin"),
            os.path.join(home, ".claude", "bin"),
            os.path.join(home, ".local", "bin"),
        ]
        candidates = []
        for d in base_dirs:
            for ext in exts:
                candidates.append(os.path.join(d, f"claude{ext}"))
        return candidates
    return [
        "/usr/local/bin/claude",
        "/opt/homebrew/bin/claude",
        os.path.join(home, ".npm-global", "bin", "claude"),
        os.path.join(home, ".local", "bin", "claude"),
        os.path.join(home, ".claude", "bin", "claude"),
    ]


def _find_claude_binary_uncached() -> str | None:
    """Search for the Claude binary without caching."""
    # Try known candidate paths first
    for p in _get_claude_candidate_paths():
        if _validate_claude_binary(p):
            return p

    # Fallback: use shutil.which with expanded PATH
    expanded = get_expanded_path()
    found = shutil.which("claude", path=expanded)
    if found and _validate_claude_binary(found):
        return found

    return None


def _find_claude_sdk_binary_uncached() -> str | None:
    """Search for a Claude binary, preferring direct executables on Windows."""
    if not IS_WINDOWS:
        return _find_claude_binary_uncached()

    candidates = _get_claude_candidate_paths()
    direct_candidates = [
        path for path in candidates
        if Path(path).suffix.lower() in {".exe", ""}
    ]
    wrapper_candidates = [
        path for path in candidates
        if Path(path).suffix.lower() in {".cmd", ".bat"}
    ]

    for path in [*direct_candidates, *wrapper_candidates]:
        if _validate_claude_binary(path):
            return path

    expanded = get_expanded_path()
    found = shutil.which("claude", path=expanded)
    if found and _validate_claude_binary(found):
        return found
    return None


def _validate_claude_binary(path: str) -> bool:
    """Verify that a binary at *path* is a working Claude CLI."""
    if not os.path.isfile(path):
        return False
    try:
        command = wrap_windows_script_command(path, ["--version"])
        subprocess.run(
            command,
            capture_output=True,
            timeout=5,
            **build_background_subprocess_kwargs(),
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


# ---------------------------------------------------------------------------
# Git Bash detection (Windows only)
# ---------------------------------------------------------------------------

def find_git_bash() -> str | None:
    """Find Git Bash (bash.exe) on Windows.

    Returns:
        The path to bash.exe, or None if not found.
    """
    if not IS_WINDOWS:
        return None

    # Check user-specified environment variable
    env_path = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    # Check common installation paths
    common_paths = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p

    # Try to locate git.exe and derive bash.exe path
    git_path = shutil.which("git")
    if git_path:
        git_dir = Path(git_path).resolve().parent.parent
        bash_path = git_dir / "bin" / "bash.exe"
        if bash_path.is_file():
            return str(bash_path)

    return None


# ---------------------------------------------------------------------------
# Claude CLI version
# ---------------------------------------------------------------------------

async def get_claude_version(claude_path: str) -> str | None:
    """Execute ``claude --version`` and return the version string."""
    try:
        proc = await _run_async(
            [claude_path, "--version"],
            timeout=5,
        )
        return proc.stdout.strip() if proc.returncode == 0 else None
    except (OSError, asyncio.TimeoutError):
        return None


def open_in_file_manager(path: str) -> bool:
    """Open path in system file manager, selecting if a file.

    Returns True if successful, False otherwise.
    """
    import sys

    path_obj = Path(path)
    if not path_obj.exists():
        return False

    try:
        if sys.platform == "win32":
            # Windows: explorer /select,"path" selects the file
            subprocess.run(
                ["explorer", "/select,", path],
                check=False,
                **subprocess_creation_flags(),
            )
        elif sys.platform == "darwin":
            # macOS: open -R reveals in Finder
            subprocess.run(["open", "-R", path], check=False)
        else:
            # Linux: xdg-open the parent directory
            target = path_obj.parent if path_obj.is_file() else path_obj
            subprocess.run(["xdg-open", str(target)], check=False)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


async def _run_async(
    cmd: list[str],
    timeout: int = 10,
) -> subprocess.CompletedProcess[str]:
    """Run a command asynchronously using anyio/asyncio."""
    import asyncio
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **build_background_subprocess_kwargs(),
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return subprocess.CompletedProcess(
        cmd,
        proc.returncode or 0,
        stdout.decode() if stdout else "",
        stderr.decode() if stderr else "",
    )
