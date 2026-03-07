"""
Tests for the EnvCheckService.
"""

from __future__ import annotations

import asyncio
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from misaka.services.skills.env_check_service import (
    EnvCheckService,
    EnvironmentCheckResult,
    ToolStatus,
    _get_install_info,
)


@pytest.fixture
def service() -> EnvCheckService:
    return EnvCheckService()


class TestToolStatus:

    def test_tool_status_dataclass(self) -> None:
        status = ToolStatus(
            name="Node.js",
            command="node",
            version="20.11.1",
            is_installed=True,
            install_url="https://nodejs.org",
            install_command="brew install node",
        )
        assert status.name == "Node.js"
        assert status.is_installed is True
        assert status.version == "20.11.1"


class TestEnvironmentCheckResult:

    def test_all_installed_true(self) -> None:
        tools = [
            ToolStatus("A", "a", "1.0", True, "", ""),
            ToolStatus("B", "b", "2.0", True, "", ""),
        ]
        result = EnvironmentCheckResult(
            tools=tools, all_installed=True, checked_at="2026-01-01T00:00:00"
        )
        assert result.all_installed is True

    def test_all_installed_false(self) -> None:
        tools = [
            ToolStatus("A", "a", "1.0", True, "", ""),
            ToolStatus("B", "b", None, False, "", ""),
        ]
        result = EnvironmentCheckResult(
            tools=tools, all_installed=False, checked_at="2026-01-01T00:00:00"
        )
        assert result.all_installed is False


class TestGetInstallInfo:

    def test_claude_cli_install_info(self) -> None:
        cmd, url = _get_install_info("Claude Code CLI")
        assert "npm install -g" in cmd
        assert "claude-code" in cmd
        assert url != ""

    def test_nodejs_install_info(self) -> None:
        cmd, url = _get_install_info("Node.js")
        assert cmd != ""
        assert "nodejs.org" in url

    def test_python_install_info(self) -> None:
        cmd, url = _get_install_info("Python")
        assert cmd != ""
        assert "python.org" in url

    def test_git_install_info(self) -> None:
        cmd, url = _get_install_info("Git")
        assert cmd != ""
        assert "git-scm.com" in url

    def test_unknown_tool_returns_empty(self) -> None:
        cmd, url = _get_install_info("UnknownTool")
        assert cmd == ""
        assert url == ""


class TestEnvCheckService:

    async def test_check_tool_found(self, service: EnvCheckService) -> None:
        """check_tool returns is_installed=True when binary exists and responds."""
        with patch("shutil.which", return_value="/usr/bin/node"), \
             patch.object(service, "_get_version", return_value="20.11.1"):
            result = await service.check_tool("node", "--version")
            assert result.is_installed is True
            assert result.version == "20.11.1"

    async def test_check_tool_not_found(self, service: EnvCheckService) -> None:
        """check_tool returns is_installed=False when binary is missing."""
        with patch("shutil.which", return_value=None):
            result = await service.check_tool("nonexistent")
            assert result.is_installed is False
            assert result.version is None

    async def test_check_tool_found_but_version_fails(self, service: EnvCheckService) -> None:
        """check_tool returns is_installed=False when version check fails."""
        with patch("shutil.which", return_value="/usr/bin/node"), \
             patch.object(service, "_get_version", return_value=None):
            result = await service.check_tool("node", "--version")
            assert result.is_installed is False

    async def test_check_all_returns_four_tools(self, service: EnvCheckService) -> None:
        """check_all should return results for all 4 tools."""
        mock_status = ToolStatus(
            name="test", command="test", version="1.0",
            is_installed=True, install_url="", install_command="",
        )
        with patch.object(service, "_check_tool_multi", return_value=mock_status):
            result = await service.check_all()
            assert len(result.tools) == 4
            assert result.all_installed is True
            assert result.checked_at != ""

    async def test_check_all_with_missing_tool(self, service: EnvCheckService) -> None:
        """check_all sets all_installed=False when any tool is missing."""
        installed = ToolStatus(
            name="test", command="test", version="1.0",
            is_installed=True, install_url="", install_command="",
        )
        not_installed = ToolStatus(
            name="missing", command="missing", version=None,
            is_installed=False, install_url="", install_command="",
        )

        call_count = 0

        async def mock_check(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return not_installed if call_count == 2 else installed

        with patch.object(service, "_check_tool_multi", side_effect=mock_check):
            result = await service.check_all()
            assert result.all_installed is False

    async def test_check_all_handles_exception(self, service: EnvCheckService) -> None:
        """check_all should handle exceptions from individual tool checks."""
        async def mock_check(*args, **kwargs):
            raise RuntimeError("test error")

        with patch.object(service, "_check_tool_multi", side_effect=mock_check):
            result = await service.check_all()
            assert len(result.tools) == 4
            assert result.all_installed is False

    async def test_get_version_parses_standard_output(self, service: EnvCheckService) -> None:
        """_get_version should parse version from standard output."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"v20.11.1\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            version = await service._get_version("/usr/bin/node", "--version")
            assert version == "20.11.1"

    async def test_get_version_parses_git_output(self, service: EnvCheckService) -> None:
        """_get_version should parse version from git-style output."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"git version 2.43.0\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            version = await service._get_version("/usr/bin/git", "--version")
            assert version == "2.43.0"

    async def test_get_version_returns_none_on_failure(self, service: EnvCheckService) -> None:
        """_get_version should return None when the command fails."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"error")
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            version = await service._get_version("/usr/bin/nonexistent", "--version")
            assert version is None

    async def test_get_version_returns_none_on_timeout(self, service: EnvCheckService) -> None:
        """_get_version should return None on timeout."""
        with patch("asyncio.create_subprocess_exec", side_effect=asyncio.TimeoutError()):
            version = await service._get_version("/usr/bin/slow", "--version")
            assert version is None

    async def test_get_version_reads_stderr_fallback(self, service: EnvCheckService) -> None:
        """_get_version should read stderr when stdout is empty."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"Python 3.12.1\n")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            version = await service._get_version("/usr/bin/python3", "--version")
            assert version == "3.12.1"

    async def test_install_tool_success(self, service: EnvCheckService) -> None:
        """install_tool should return True on successful installation."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"installed\n", b"")
        mock_proc.returncode = 0

        progress_messages: list[str] = []

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await service.install_tool(
                "Node.js", on_progress=progress_messages.append
            )
            assert result is True
            assert any("successfully" in m for m in progress_messages)

    async def test_install_tool_failure(self, service: EnvCheckService) -> None:
        """install_tool should return False on installation failure."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"permission denied\n")
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await service.install_tool("Node.js")
            assert result is False

    async def test_install_tool_unknown_returns_false(self, service: EnvCheckService) -> None:
        """install_tool should return False for unknown tools."""
        result = await service.install_tool("UnknownTool")
        assert result is False

    async def test_install_tool_timeout(self, service: EnvCheckService) -> None:
        """install_tool should return False on timeout."""
        mock_proc = AsyncMock()
        mock_proc.communicate.side_effect = asyncio.TimeoutError()

        progress_messages: list[str] = []

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await service.install_tool(
                "Node.js", on_progress=progress_messages.append
            )
            assert result is False
            assert any("timed out" in m for m in progress_messages)

    async def test_install_tool_os_error(self, service: EnvCheckService) -> None:
        """install_tool should return False on OSError (e.g., command not found)."""
        progress_messages: list[str] = []

        with patch("asyncio.create_subprocess_exec", side_effect=OSError("not found")):
            result = await service.install_tool(
                "Git", on_progress=progress_messages.append
            )
            assert result is False
            assert any("failed" in m.lower() for m in progress_messages)

    async def test_get_version_no_version_in_output(self, service: EnvCheckService) -> None:
        """_get_version should return None when output has no version pattern."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"some random output\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            version = await service._get_version("/usr/bin/tool", "--version")
            assert version is None

    async def test_get_version_os_error(self, service: EnvCheckService) -> None:
        """_get_version should return None on OSError."""
        with patch("asyncio.create_subprocess_exec", side_effect=OSError("No such file")):
            version = await service._get_version("/nonexistent/path", "--version")
            assert version is None

    async def test_get_version_windows_cmd_wrapper(self, service: EnvCheckService) -> None:
        """_get_version should delegate .cmd wrappers to the shared command helper."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"v18.0.0\n", b"")
        mock_proc.returncode = 0

        with patch(
            "misaka.services.skills.env_check_service.wrap_windows_script_command",
            return_value=["cmd.exe", "/d", "/s", "/c", '""C:/npm/node.cmd" --version"'],
        ) as mock_wrap, patch(
            "misaka.services.skills.env_check_service.build_background_subprocess_kwargs",
            return_value={"creationflags": 1, "startupinfo": "hidden"},
        ) as mock_kwargs, patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            version = await service._get_version("C:\\npm\\node.cmd", "--version")
            assert version == "18.0.0"
            mock_wrap.assert_called_once_with("C:\\npm\\node.cmd", ["--version"])
            mock_kwargs.assert_called_once_with()
            mock_exec.assert_called_once_with(
                "cmd.exe",
                "/d",
                "/s",
                "/c",
                '""C:/npm/node.cmd" --version"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=1,
                startupinfo="hidden",
            )

    async def test_check_tool_multi_uses_first_found(self, service: EnvCheckService) -> None:
        """_check_tool_multi should use the first working command."""
        call_count = 0

        def mock_which(cmd, path=None):
            nonlocal call_count
            call_count += 1
            # python3 not found, python found
            if cmd == "python3":
                return None
            return "/usr/bin/python"

        with patch("shutil.which", side_effect=mock_which), \
             patch.object(service, "_get_version", return_value="3.12.1"):
            result = await service._check_tool_multi(
                "Python", ["python3", "python"], "--version"
            )
            assert result.is_installed is True
            assert result.command == "python"

    async def test_check_tool_multi_all_missing(self, service: EnvCheckService) -> None:
        """_check_tool_multi should return not installed when all commands missing."""
        with patch("shutil.which", return_value=None):
            result = await service._check_tool_multi(
                "Python", ["python3", "python"], "--version"
            )
            assert result.is_installed is False
            assert result.command == "python3"  # Returns first command as default

    async def test_install_tool_no_progress_callback(self, service: EnvCheckService) -> None:
        """install_tool should work without a progress callback."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"ok\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await service.install_tool("Git", on_progress=None)
            assert result is True
