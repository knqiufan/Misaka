"""Environment detection and guided tool installation for Misaka."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from misaka.config import IS_MACOS, IS_WINDOWS, get_expanded_path
from misaka.utils.platform import (
    build_background_subprocess_kwargs,
    wrap_windows_script_command,
)

logger = logging.getLogger(__name__)

PlatformName = Literal["windows", "macos", "linux"]
_VERSION_RE = re.compile(r"v?(\d+\.\d+(?:\.\d+)?)")
_INSTALL_TIMEOUT_SECONDS = 300
_VERSION_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ToolDefinition:
    """Definition of a tool checked by :class:`EnvCheckService`."""

    name: str
    commands: tuple[str, ...]
    version_flag: str = "--version"


@dataclass
class ToolStatus:
    """Status of a single tool dependency."""

    name: str
    command: str
    version: str | None
    is_installed: bool
    install_url: str
    install_command: str


@dataclass
class EnvironmentCheckResult:
    """Aggregated result of all environment checks."""

    tools: list[ToolStatus]
    all_installed: bool
    checked_at: str


@dataclass(frozen=True)
class InstallSpec:
    """Executable steps and prerequisites for one platform installer."""

    steps: tuple[tuple[str, ...], ...]
    url: str
    required_commands: tuple[str, ...] = ()
    requires_elevation: bool = False


@dataclass(frozen=True)
class InstallResult:
    """Structured result returned to UI callers after an install attempt."""

    tool_name: str
    success: bool
    message: str
    command: str = ""
    returncode: int | None = None


_TOOL_DEFINITIONS = (
    ToolDefinition("Claude Code CLI", ("claude",)),
    ToolDefinition("Node.js", ("node",)),
    ToolDefinition(
        "Python",
        ("py", "python", "python3") if IS_WINDOWS else ("python3", "python"),
    ),
    ToolDefinition("Git", ("git",)),
)


def _current_platform() -> PlatformName:
    if IS_WINDOWS:
        return "windows"
    if IS_MACOS:
        return "macos"
    return "linux"


def _winget_step(package_id: str) -> tuple[str, ...]:
    """Build a deterministic, non-interactive WinGet install command."""
    return (
        "winget",
        "install",
        "--id",
        package_id,
        "--exact",
        "--source",
        "winget",
        "--accept-source-agreements",
        "--accept-package-agreements",
        "--disable-interactivity",
    )


def _get_install_spec(
    tool_name: str,
    platform_name: PlatformName | None = None,
) -> InstallSpec | None:
    """Return the structured install specification for *tool_name*."""
    platform_name = platform_name or _current_platform()

    urls = {
        "Claude Code CLI": "https://code.claude.com/docs/en/setup",
        "Node.js": "https://nodejs.org/en/download/",
        "Python": "https://www.python.org/downloads/",
        "Git": "https://git-scm.com/downloads",
    }
    url = urls.get(tool_name)
    if url is None:
        return None

    if platform_name == "windows":
        package_ids = {
            "Claude Code CLI": "Anthropic.ClaudeCode",
            "Node.js": "OpenJS.NodeJS.LTS",
            "Python": "Python.Python.3.13",
            "Git": "Git.Git",
        }
        return InstallSpec(steps=(_winget_step(package_ids[tool_name]),), url=url)

    if platform_name == "macos":
        brew_args = {
            "Claude Code CLI": ("brew", "install", "--cask", "claude-code"),
            "Node.js": ("brew", "install", "node"),
            "Python": ("brew", "install", "python"),
            "Git": ("brew", "install", "git"),
        }
        return InstallSpec(steps=(brew_args[tool_name],), url=url)

    if tool_name == "Claude Code CLI":
        return InstallSpec(
            steps=(("bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"),),
            url=url,
            required_commands=("bash", "curl"),
        )

    apt_packages = {
        "Node.js": "nodejs",
        "Python": "python3",
        "Git": "git",
    }
    package = apt_packages[tool_name]
    return InstallSpec(
        steps=(
            ("apt-get", "update"),
            ("apt-get", "install", "-y", package),
        ),
        url=url,
        required_commands=("apt-get",),
        requires_elevation=True,
    )


def _format_command(command: tuple[str, ...], platform_name: PlatformName) -> str:
    if platform_name == "windows":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def _get_install_info(tool_name: str) -> tuple[str, str]:
    """Return a display command and manual-install URL for *tool_name*."""
    platform_name = _current_platform()
    spec = _get_install_spec(tool_name, platform_name)
    if spec is None:
        return "", ""
    command = " && ".join(_format_command(step, platform_name) for step in spec.steps)
    return command, spec.url


class EnvCheckService:
    """Check and install the external tools used by Misaka."""

    async def check_all(self) -> EnvironmentCheckResult:
        """Check all tools concurrently while preserving failure identity."""
        tools = await asyncio.gather(
            *(self._check_definition_safe(definition) for definition in _TOOL_DEFINITIONS)
        )
        return EnvironmentCheckResult(
            tools=list(tools),
            all_installed=all(tool.is_installed for tool in tools),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _check_definition_safe(self, definition: ToolDefinition) -> ToolStatus:
        try:
            return await self._check_tool_multi(
                definition.name,
                list(definition.commands),
                definition.version_flag,
            )
        except Exception as exc:
            logger.warning("Tool check failed for %s: %s", definition.name, exc)
            install_command, install_url = _get_install_info(definition.name)
            return ToolStatus(
                name=definition.name,
                command=definition.commands[0],
                version=None,
                is_installed=False,
                install_url=install_url,
                install_command=install_command,
            )

    async def check_tool(
        self,
        command: str,
        version_flag: str = "--version",
    ) -> ToolStatus:
        """Check a single command and return its executable version."""
        definition = next(
            (item for item in _TOOL_DEFINITIONS if command in item.commands),
            ToolDefinition(command, (command,), version_flag),
        )
        return await self._check_tool_multi(
            definition.name,
            [command],
            version_flag,
            use_claude_resolver=False,
        )

    async def _check_tool_multi(
        self,
        name: str,
        commands: list[str],
        version_flag: str,
        *,
        use_claude_resolver: bool = True,
    ) -> ToolStatus:
        """Try all supported command names and require a parseable version."""
        expanded_path = get_expanded_path()
        install_command, install_url = _get_install_info(name)

        if name == "Claude Code CLI" and use_claude_resolver:
            from misaka.utils.platform import find_claude_binary

            claude_path = find_claude_binary()
            if claude_path:
                version = await self._get_version(claude_path, version_flag)
                if version is None:
                    version = await self._get_version_lenient(claude_path, version_flag)
                if version is not None:
                    return ToolStatus(
                        name=name,
                        command="claude",
                        version=version,
                        is_installed=True,
                        install_url=install_url,
                        install_command=install_command,
                    )

        for command in commands:
            binary_path = shutil.which(command, path=expanded_path)
            if not binary_path:
                continue
            version = await self._get_version(binary_path, version_flag)
            if version is not None:
                return ToolStatus(
                    name=name,
                    command=command,
                    version=version,
                    is_installed=True,
                    install_url=install_url,
                    install_command=install_command,
                )

        return ToolStatus(
            name=name,
            command=commands[0],
            version=None,
            is_installed=False,
            install_url=install_url,
            install_command=install_command,
        )

    async def install_tool(
        self,
        tool_name: str,
        on_progress: Callable[[str], None] | None = None,
    ) -> InstallResult:
        """Install a tool and return a structured, user-displayable result."""
        platform_name = _current_platform()
        spec = _get_install_spec(tool_name, platform_name)
        if spec is None:
            return InstallResult(tool_name, False, f"No install command for {tool_name}")

        display_command = " && ".join(
            _format_command(step, platform_name) for step in spec.steps
        )
        missing = self._find_missing_prerequisite(spec)
        if missing:
            message = f"Required command not found: {missing}. Manual install: {spec.url}"
            self._report_progress(on_progress, message)
            return InstallResult(tool_name, False, message, display_command)

        self._report_progress(on_progress, f"Installing {tool_name}...")
        last_returncode: int | None = None

        try:
            for step in spec.steps:
                command = self._prepare_install_command(step, spec)
                if command is None:
                    message = (
                        "Administrator authorization is unavailable. "
                        f"Run manually: {display_command}"
                    )
                    self._report_progress(on_progress, message)
                    return InstallResult(tool_name, False, message, display_command)

                proc = await asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self._build_install_env(),
                    **build_background_subprocess_kwargs(),
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=_INSTALL_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    await self._terminate_process(proc)
                    raise

                last_returncode = proc.returncode
                if proc.returncode != 0:
                    detail = self._decode_process_error(stdout, stderr)
                    message = f"Install failed: {detail}"
                    logger.warning(
                        "Install of %s failed (rc=%s): %s",
                        tool_name,
                        proc.returncode,
                        detail,
                    )
                    self._report_progress(on_progress, message)
                    return InstallResult(
                        tool_name,
                        False,
                        message,
                        display_command,
                        proc.returncode,
                    )

            if tool_name == "Claude Code CLI":
                from misaka.utils.platform import clear_claude_cache

                clear_claude_cache()

            if not await self._verify_installed_tool(tool_name):
                message = (
                    f"Installer completed, but {tool_name} could not be detected. "
                    f"Restart Misaka or install manually: {spec.url}"
                )
                self._report_progress(on_progress, message)
                return InstallResult(
                    tool_name,
                    False,
                    message,
                    display_command,
                    last_returncode,
                )

            message = f"{tool_name} installed successfully"
            self._report_progress(on_progress, message)
            return InstallResult(
                tool_name,
                True,
                message,
                display_command,
                last_returncode,
            )
        except asyncio.TimeoutError:
            message = "Installation timed out"
            logger.warning("Install of %s timed out", tool_name)
            self._report_progress(on_progress, message)
            return InstallResult(tool_name, False, message, display_command)
        except Exception as exc:
            message = f"Install failed: {exc}"
            logger.warning("Install of %s failed: %s", tool_name, exc)
            self._report_progress(on_progress, message)
            return InstallResult(tool_name, False, message, display_command)

    def _find_missing_prerequisite(self, spec: InstallSpec) -> str | None:
        for command in spec.required_commands:
            if not self._resolve_install_executable(command):
                return command
        for step in spec.steps:
            if not self._resolve_install_executable(step[0]):
                return step[0]
        return None

    def _prepare_install_command(
        self,
        step: tuple[str, ...],
        spec: InstallSpec,
    ) -> list[str] | None:
        executable = self._resolve_install_executable(step[0])
        if executable is None:
            return None
        command = [executable, *step[1:]]

        if spec.requires_elevation and not self._is_root():
            elevation = self._resolve_elevation_command()
            if elevation is None:
                return None
            command = [*elevation, *command]

        return wrap_windows_script_command(command[0], command[1:])

    @staticmethod
    def _is_root() -> bool:
        get_euid = getattr(os, "geteuid", None)
        return bool(get_euid and get_euid() == 0)

    def _resolve_elevation_command(self) -> list[str] | None:
        expanded_path = get_expanded_path()
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            pkexec = shutil.which("pkexec", path=expanded_path)
            if pkexec:
                return [pkexec]
        sudo = shutil.which("sudo", path=expanded_path)
        if sudo:
            return [sudo, "--non-interactive"]
        return None

    @staticmethod
    def _build_install_env() -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = get_expanded_path()
        env.setdefault("HOMEBREW_NO_AUTO_UPDATE", "1")
        env.setdefault("DEBIAN_FRONTEND", "noninteractive")
        return env

    @staticmethod
    async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()

    @staticmethod
    def _decode_process_error(stdout: bytes, stderr: bytes) -> str:
        output = (stderr or stdout).decode(errors="replace").strip()
        if not output:
            return "Unknown error"
        return output[-2000:]

    @staticmethod
    def _report_progress(
        callback: Callable[[str], None] | None,
        message: str,
    ) -> None:
        if not callback:
            return
        try:
            callback(message)
        except Exception:
            logger.debug("Install progress callback failed", exc_info=True)

    def _resolve_install_executable(self, executable: str) -> str | None:
        return shutil.which(executable, path=get_expanded_path())

    async def _verify_installed_tool(self, tool_name: str) -> bool:
        definition = next(
            (item for item in _TOOL_DEFINITIONS if item.name == tool_name),
            None,
        )
        if definition is None:
            return False
        status = await self._check_definition_safe(definition)
        return status.is_installed

    async def _get_version(self, binary_path: str, version_flag: str) -> str | None:
        return await self._capture_version(binary_path, version_flag, require_success=True)

    async def _get_version_lenient(
        self,
        binary_path: str,
        version_flag: str,
    ) -> str | None:
        return await self._capture_version(binary_path, version_flag, require_success=False)

    async def _capture_version(
        self,
        binary_path: str,
        version_flag: str,
        *,
        require_success: bool,
    ) -> str | None:
        proc: asyncio.subprocess.Process | None = None
        try:
            command = wrap_windows_script_command(binary_path, [version_flag])
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_install_env(),
                **build_background_subprocess_kwargs(),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=_VERSION_TIMEOUT_SECONDS,
            )
            if require_success and proc.returncode != 0:
                return None
            output = "\n".join(
                part.decode(errors="replace") for part in (stdout, stderr) if part
            )
            match = _VERSION_RE.search(output)
            return match.group(1) if match else None
        except asyncio.TimeoutError:
            if proc is not None:
                await self._terminate_process(proc)
            logger.debug("Version check timed out for %s", binary_path)
            return None
        except Exception as exc:
            logger.debug("Version check failed for %s: %s", binary_path, exc)
            return None
