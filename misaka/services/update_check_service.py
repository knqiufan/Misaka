"""
Update check service for Misaka.

Detects if a newer version of Claude Code CLI is available
and provides one-click upgrade functionality.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from misaka.config import IS_WINDOWS, get_expanded_path

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_NPM_REGISTRY_URL = "https://registry.npmjs.org/@anthropic-ai/claude-code/latest"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class UpdateCheckResult:
    """Result of checking for Claude Code CLI updates."""

    current_version: str | None  # Currently installed version
    latest_version: str | None  # Latest version from npm registry
    update_available: bool  # True if latest > current
    checked_at: str  # ISO timestamp


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class UpdateCheckService:
    """Service for detecting Claude Code CLI updates."""

    async def check_for_update(self) -> UpdateCheckResult:
        """Check if a newer version of Claude Code CLI is available.

        Steps:
        1. Get current version via claude --version (reuse platform utility)
        2. Get latest version from npm registry API
        3. Compare using version tuple comparison
        """
        checked_at = datetime.now(timezone.utc).isoformat()

        # Get current installed version
        current_version = await self._get_current_version()

        # Get latest version from npm
        latest_version = await self._get_latest_npm_version(
            "@anthropic-ai/claude-code"
        )

        # Compare versions
        update_available = False
        if current_version and latest_version:
            update_available = self._compare_versions(
                current_version, latest_version
            )

        return UpdateCheckResult(
            current_version=current_version,
            latest_version=latest_version,
            update_available=update_available,
            checked_at=checked_at,
        )

    async def perform_update(
        self,
        on_progress: Callable[[str], None] | None = None,
    ) -> bool:
        """Update Claude Code CLI to the latest version.

        Runs: npm install -g @anthropic-ai/claude-code@latest
        Returns True on success.
        After update, clears the cached claude binary path.
        """
        if on_progress:
            on_progress("Updating Claude Code CLI...")

        try:
            expanded_path = get_expanded_path()
            import shutil

            npm_path = shutil.which("npm", path=expanded_path)
            if not npm_path:
                if on_progress:
                    on_progress("npm not found, cannot update")
                return False

            cmd: list[str]
            if IS_WINDOWS and npm_path.lower().endswith((".cmd", ".bat")):
                cmd = [
                    "cmd", "/c", npm_path,
                    "install", "-g", "@anthropic-ai/claude-code@latest",
                ]
            else:
                cmd = [
                    npm_path,
                    "install", "-g", "@anthropic-ai/claude-code@latest",
                ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=300
            )

            if proc.returncode == 0:
                # Clear cached claude binary path
                try:
                    from misaka.utils.platform import clear_claude_cache
                    clear_claude_cache()
                except (ImportError, OSError) as exc:
                    logger.debug("Failed to clear claude cache: %s", exc)

                if on_progress:
                    on_progress("Update completed successfully")
                return True
            else:
                error_msg = (stderr or b"").decode(errors="replace").strip()
                logger.warning(
                    "Claude Code update failed (rc=%d): %s",
                    proc.returncode,
                    error_msg,
                )
                if on_progress:
                    on_progress(f"Update failed: {error_msg}")
                return False

        except asyncio.TimeoutError:
            logger.warning("Claude Code update timed out")
            if on_progress:
                on_progress("Update timed out")
            return False
        except Exception as exc:
            logger.warning("Claude Code update failed: %s", exc)
            if on_progress:
                on_progress(f"Update failed: {exc}")
            return False

    async def _get_current_version(self) -> str | None:
        """Get the currently installed Claude Code CLI version."""
        try:
            from misaka.utils.platform import (
                find_claude_binary,
                get_claude_version,
            )

            claude_path = find_claude_binary()
            if not claude_path:
                return None

            version_str = await get_claude_version(claude_path)
            if not version_str:
                return None

            match = _VERSION_RE.search(version_str)
            return match.group(0) if match else None
        except Exception as exc:
            logger.debug("Failed to get current Claude version: %s", exc)
            return None

    async def _get_latest_npm_version(self, package_name: str) -> str | None:
        """Fetch the latest version of an npm package.

        Strategy:
        1. Try npm registry HTTP API (fast, no dependency on npm CLI)
        2. Fallback to `npm view` subprocess
        """
        # Strategy 1: HTTP request to npm registry
        version = await self._fetch_version_from_registry()
        if version:
            return version

        # Strategy 2: npm view fallback
        version = await self._fetch_version_via_npm_cli(package_name)
        return version

    async def _fetch_version_from_registry(self) -> str | None:
        """Fetch latest version from npm registry HTTP API."""
        try:
            # Run HTTP request in executor to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            version = await asyncio.wait_for(
                loop.run_in_executor(None, self._http_get_version),
                timeout=10,
            )
            return version
        except Exception as exc:
            logger.debug("npm registry fetch failed: %s", exc)
            return None

    def _http_get_version(self) -> str | None:
        """Synchronous HTTP GET to npm registry (run in executor)."""
        try:
            req = Request(
                _NPM_REGISTRY_URL,
                headers={"Accept": "application/json"},
            )
            with urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                version = data.get("version")
                if version and _VERSION_RE.match(version):
                    return version
        except (URLError, json.JSONDecodeError, OSError) as exc:
            logger.debug("HTTP registry request failed: %s", exc)
        return None

    async def _fetch_version_via_npm_cli(self, package_name: str) -> str | None:
        """Fallback: get version via `npm view <package> version`."""
        try:
            expanded_path = get_expanded_path()
            import shutil

            npm_path = shutil.which("npm", path=expanded_path)
            if not npm_path:
                return None

            cmd: list[str]
            if IS_WINDOWS and npm_path.lower().endswith((".cmd", ".bat")):
                cmd = ["cmd", "/c", npm_path, "view", package_name, "version"]
            else:
                cmd = [npm_path, "view", package_name, "version"]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=15
            )

            if proc.returncode == 0 and stdout:
                version = stdout.decode(errors="replace").strip()
                match = _VERSION_RE.match(version)
                return match.group(0) if match else None
        except Exception as exc:
            logger.debug("npm view fallback failed: %s", exc)
        return None

    @staticmethod
    def _compare_versions(current: str, latest: str) -> bool:
        """Return True if latest > current using tuple comparison.

        Parses "x.y.z" -> (x, y, z) and compares.
        """
        current_match = _VERSION_RE.match(current)
        latest_match = _VERSION_RE.match(latest)

        if not current_match or not latest_match:
            return False

        current_tuple = tuple(int(x) for x in current_match.groups())
        latest_tuple = tuple(int(x) for x in latest_match.groups())

        return latest_tuple > current_tuple
