"""
Environment check service for Misaka.

Detects installed development tools (Claude Code CLI, Node.js, Python, Git)
and provides one-click installation via platform-appropriate methods.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from misaka.config import IS_MACOS, IS_WINDOWS, get_expanded_path

logger = logging.getLogger(__name__)

# Version extraction pattern
_VERSION_RE = re.compile(r"v?(\d+\.\d+(?:\.\d+)?)")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ToolStatus:
    """Status of a single tool dependency."""

    name: str  # "Claude Code CLI", "Node.js", "Python", "Git"
    command: str  # "claude", "node", "python3", "git"
    version: str | None  # "1.2.3" or None if not found
    is_installed: bool  # True if binary found and responds to --version
    install_url: str  # URL for manual download
    install_command: str  # Platform-specific install command


@dataclass
class EnvironmentCheckResult:
    """Aggregated result of all environment checks."""

    tools: list[ToolStatus]
    all_installed: bool  # True if every tool is installed
    checked_at: str  # ISO timestamp


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_TOOL_DEFINITIONS = [
    {
        "name": "Claude Code CLI",
        "commands": ["claude"],
        "version_flag": "--version",
    },
    {
        "name": "Node.js",
        "commands": ["node"],
        "version_flag": "--version",
    },
    {
        "name": "Python",
        # On Windows try python first, on Unix try python3 first
        "commands": ["python", "python3"] if IS_WINDOWS else ["python3", "python"],
        "version_flag": "--version",
    },
    {
        "name": "Git",
        "commands": ["git"],
        "version_flag": "--version",
    },
]


# ---------------------------------------------------------------------------
# Install info (platform-specific)
# ---------------------------------------------------------------------------

def _get_install_info(tool_name: str) -> tuple[str, str]:
    """Return (install_command, install_url) for the given tool.

    Returns platform-specific install commands and download URLs.
    """
    if tool_name == "Claude Code CLI":
        return (
            "npm install -g @anthropic-ai/claude-code",
            "https://docs.anthropic.com/en/docs/claude-code/overview",
        )

    if tool_name == "Node.js":
        url = "https://nodejs.org/en/download/"
        if IS_WINDOWS:
            return ("winget install OpenJS.NodeJS.LTS", url)
        elif IS_MACOS:
            return ("brew install node", url)
        else:
            return ("sudo apt install -y nodejs", url)

    if tool_name == "Python":
        url = "https://www.python.org/downloads/"
        if IS_WINDOWS:
            return ("winget install Python.Python.3.12", url)
        elif IS_MACOS:
            return ("brew install python@3.12", url)
        else:
            return ("sudo apt install -y python3", url)

    if tool_name == "Git":
        url = "https://git-scm.com/downloads"
        if IS_WINDOWS:
            return ("winget install Git.Git", url)
        elif IS_MACOS:
            return ("brew install git", url)
        else:
            return ("sudo apt install -y git", url)

    return ("", "")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EnvCheckService:
    """Service for checking and installing development tool dependencies."""

    async def check_all(self) -> EnvironmentCheckResult:
        """Run all environment checks concurrently.

        Uses asyncio.gather to check all tools in parallel.
        Returns an EnvironmentCheckResult with status for each tool.
        """
        tasks = []
        for tool_def in _TOOL_DEFINITIONS:
            tasks.append(
                self._check_tool_multi(
                    tool_def["name"],
                    tool_def["commands"],
                    tool_def["version_flag"],
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        tools: list[ToolStatus] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Tool check failed: %s", result)
                tools.append(
                    ToolStatus(
                        name="Unknown",
                        command="",
                        version=None,
                        is_installed=False,
                        install_url="",
                        install_command="",
                    )
                )
            else:
                tools.append(result)

        return EnvironmentCheckResult(
            tools=tools,
            all_installed=all(t.is_installed for t in tools),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    async def check_tool(
        self, command: str, version_flag: str = "--version"
    ) -> ToolStatus:
        """Check a single tool by running `command version_flag`.

        Handles Windows .cmd/.bat wrappers, expanded PATH lookup.
        Parses version string from stdout.
        """
        expanded_path = get_expanded_path()

        # Find the binary
        binary_path = shutil.which(command, path=expanded_path)
        if not binary_path:
            install_cmd, install_url = _get_install_info(command)
            return ToolStatus(
                name=command,
                command=command,
                version=None,
                is_installed=False,
                install_url=install_url,
                install_command=install_cmd,
            )

        # Run version check
        version = await self._get_version(binary_path, version_flag)
        install_cmd, install_url = _get_install_info(command)
        return ToolStatus(
            name=command,
            command=command,
            version=version,
            is_installed=version is not None,
            install_url=install_url,
            install_command=install_cmd,
        )

    async def _check_tool_multi(
        self, name: str, commands: list[str], version_flag: str
    ) -> ToolStatus:
        """Check a tool that may have multiple command names.

        Tries each command in order, returns the first one found.
        """
        expanded_path = get_expanded_path()
        install_cmd, install_url = _get_install_info(name)

        # Special handling for Claude CLI: reuse existing platform utility
        if name == "Claude Code CLI":
            try:
                from misaka.utils.platform import find_claude_binary

                claude_path = find_claude_binary()
                if claude_path:
                    version = await self._get_version(claude_path, version_flag)
                    return ToolStatus(
                        name=name,
                        command="claude",
                        version=version,
                        is_installed=True,
                        install_url=install_url,
                        install_command=install_cmd,
                    )
            except Exception:
                pass

        for cmd in commands:
            binary_path = shutil.which(cmd, path=expanded_path)
            if not binary_path:
                continue

            version = await self._get_version(binary_path, version_flag)
            if version is not None:
                return ToolStatus(
                    name=name,
                    command=cmd,
                    version=version,
                    is_installed=True,
                    install_url=install_url,
                    install_command=install_cmd,
                )

        return ToolStatus(
            name=name,
            command=commands[0],
            version=None,
            is_installed=False,
            install_url=install_url,
            install_command=install_cmd,
        )

    async def install_tool(
        self,
        tool_name: str,
        on_progress: Callable[[str], None] | None = None,
    ) -> bool:
        """Install a tool via platform-appropriate method.

        Returns True on success, False on failure.
        Calls on_progress with status messages during install.
        """
        install_cmd, _ = _get_install_info(tool_name)
        if not install_cmd:
            logger.warning("No install command for tool: %s", tool_name)
            return False

        if on_progress:
            on_progress(f"Installing {tool_name}...")

        try:
            # Split command into args list for safe subprocess execution
            args = install_cmd.split()

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=300
            )

            if proc.returncode == 0:
                if on_progress:
                    on_progress(f"{tool_name} installed successfully")

                # Clear cached claude binary path after installation
                if tool_name == "Claude Code CLI":
                    try:
                        from misaka.utils.platform import clear_claude_cache

                        clear_claude_cache()
                    except Exception:
                        pass

                return True
            else:
                error_msg = stderr.decode(errors="replace").strip() if stderr else "Unknown error"
                logger.warning(
                    "Install of %s failed (rc=%d): %s",
                    tool_name,
                    proc.returncode,
                    error_msg,
                )
                if on_progress:
                    on_progress(f"Install failed: {error_msg}")
                return False

        except asyncio.TimeoutError:
            logger.warning("Install of %s timed out", tool_name)
            if on_progress:
                on_progress("Installation timed out")
            return False
        except Exception as exc:
            logger.warning("Install of %s failed: %s", tool_name, exc)
            if on_progress:
                on_progress(f"Install failed: {exc}")
            return False

    async def _get_version(
        self, binary_path: str, version_flag: str
    ) -> str | None:
        """Run a binary with its version flag and parse the version string."""
        try:
            # On Windows, .cmd/.bat files need shell=True equivalent,
            # but asyncio.create_subprocess_exec doesn't support shell=True.
            # Instead we handle it by running cmd.exe /c for .cmd/.bat files.
            cmd: list[str]
            if IS_WINDOWS and binary_path.lower().endswith((".cmd", ".bat")):
                cmd = ["cmd", "/c", binary_path, version_flag]
            else:
                cmd = [binary_path, version_flag]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=10
            )

            if proc.returncode != 0:
                return None

            output = (stdout or b"").decode(errors="replace")
            # Some tools output version to stderr (e.g., python --version on some systems)
            if not output.strip():
                output = (stderr or b"").decode(errors="replace")

            match = _VERSION_RE.search(output)
            return match.group(1) if match else None

        except (asyncio.TimeoutError, OSError, Exception) as exc:
            logger.debug("Version check failed for %s: %s", binary_path, exc)
            return None
