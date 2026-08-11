"""Tests for cross-platform environment detection and installation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from misaka.services.skills.env_check_service import (
    EnvCheckService,
    EnvironmentCheckResult,
    InstallResult,
    ToolStatus,
    _get_install_info,
    _get_install_spec,
)


@pytest.fixture
def service() -> EnvCheckService:
    return EnvCheckService()


def _process(
    *,
    stdout: bytes = b"",
    stderr: bytes = b"",
    returncode: int = 0,
    communicate_error: Exception | None = None,
) -> MagicMock:
    proc = MagicMock()
    if communicate_error is None:
        proc.communicate = AsyncMock(return_value=(stdout, stderr))
    else:
        proc.communicate = AsyncMock(side_effect=communicate_error)
    proc.wait = AsyncMock(return_value=returncode)
    proc.kill = MagicMock()
    proc.returncode = returncode
    return proc


class TestDataModels:
    def test_tool_status(self) -> None:
        status = ToolStatus("Node.js", "node", "24.1.0", True, "url", "command")
        assert status.is_installed is True
        assert status.version == "24.1.0"

    def test_environment_result(self) -> None:
        result = EnvironmentCheckResult([], True, "2026-01-01T00:00:00Z")
        assert result.all_installed is True

    def test_install_result(self) -> None:
        result = InstallResult("Git", False, "failed", "git install", 1)
        assert result.success is False
        assert result.returncode == 1


class TestInstallSpecs:
    @pytest.mark.parametrize(
        ("tool_name", "package_id"),
        [
            ("Claude Code CLI", "Anthropic.ClaudeCode"),
            ("Node.js", "OpenJS.NodeJS.LTS"),
            ("Python", "Python.Python.3.13"),
            ("Git", "Git.Git"),
        ],
    )
    def test_windows_specs_are_exact_and_non_interactive(
        self,
        tool_name: str,
        package_id: str,
    ) -> None:
        spec = _get_install_spec(tool_name, "windows")
        assert spec is not None
        step = spec.steps[0]
        assert step[:4] == ("winget", "install", "--id", package_id)
        assert "--exact" in step
        assert "--source" in step
        assert "--accept-source-agreements" in step
        assert "--accept-package-agreements" in step
        assert "--disable-interactivity" in step

    @pytest.mark.parametrize(
        ("tool_name", "expected"),
        [
            ("Claude Code CLI", ("brew", "install", "--cask", "claude-code")),
            ("Node.js", ("brew", "install", "node")),
            ("Python", ("brew", "install", "python")),
            ("Git", ("brew", "install", "git")),
        ],
    )
    def test_macos_specs_use_homebrew(
        self,
        tool_name: str,
        expected: tuple[str, ...],
    ) -> None:
        spec = _get_install_spec(tool_name, "macos")
        assert spec is not None
        assert spec.steps == (expected,)

    @pytest.mark.parametrize(
        ("tool_name", "package"),
        [("Node.js", "nodejs"), ("Python", "python3"), ("Git", "git")],
    )
    def test_linux_specs_use_apt_get(self, tool_name: str, package: str) -> None:
        spec = _get_install_spec(tool_name, "linux")
        assert spec is not None
        assert spec.steps == (
            ("apt-get", "update"),
            ("apt-get", "install", "-y", package),
        )
        assert spec.requires_elevation is True

    def test_linux_claude_uses_official_native_installer(self) -> None:
        spec = _get_install_spec("Claude Code CLI", "linux")
        assert spec is not None
        assert "https://claude.ai/install.sh" in spec.steps[0][-1]
        assert spec.required_commands == ("bash", "curl")

    def test_unknown_tool_has_no_spec(self) -> None:
        assert _get_install_spec("Unknown", "windows") is None
        assert _get_install_info("Unknown") == ("", "")


class TestDetection:
    async def test_check_tool_found(self, service: EnvCheckService) -> None:
        with patch(
            "misaka.services.skills.env_check_service.shutil.which",
            return_value="/usr/bin/node",
        ), patch.object(service, "_get_version", return_value="24.1.0"):
            result = await service.check_tool("node")
        assert result.name == "Node.js"
        assert result.is_installed is True
        assert result.version == "24.1.0"

    async def test_check_tool_not_found(self, service: EnvCheckService) -> None:
        with patch(
            "misaka.services.skills.env_check_service.shutil.which",
            return_value=None,
        ):
            result = await service.check_tool("node")
        assert result.is_installed is False

    async def test_python_falls_back_to_second_command(self, service: EnvCheckService) -> None:
        def which(command: str, path: str | None = None) -> str | None:
            return "/usr/bin/python" if command == "python" else None

        with patch(
            "misaka.services.skills.env_check_service.shutil.which",
            side_effect=which,
        ), patch.object(service, "_get_version", return_value="3.13.1"):
            result = await service._check_tool_multi(
                "Python",
                ["python3", "python"],
                "--version",
            )
        assert result.command == "python"
        assert result.is_installed is True

    async def test_claude_requires_parseable_version(self, service: EnvCheckService) -> None:
        with patch(
            "misaka.utils.platform.find_claude_binary",
            return_value="/usr/bin/claude",
        ), patch(
            "misaka.services.skills.env_check_service.shutil.which",
            return_value=None,
        ), patch.object(
            service,
            "_get_version",
            return_value=None,
        ), patch.object(
            service,
            "_get_version_lenient",
            return_value=None,
        ):
            result = await service._check_tool_multi(
                "Claude Code CLI",
                ["claude"],
                "--version",
            )
        assert result.is_installed is False
        assert result.version is None

    async def test_claude_lenient_version_is_accepted(self, service: EnvCheckService) -> None:
        with patch(
            "misaka.utils.platform.find_claude_binary",
            return_value="/usr/bin/claude",
        ), patch.object(
            service,
            "_get_version",
            return_value=None,
        ), patch.object(
            service,
            "_get_version_lenient",
            return_value="2.1.204",
        ):
            result = await service._check_tool_multi(
                "Claude Code CLI",
                ["claude"],
                "--version",
            )
        assert result.is_installed is True
        assert result.version == "2.1.204"

    async def test_check_all_preserves_tool_name_on_exception(
        self,
        service: EnvCheckService,
    ) -> None:
        async def check(name: str, commands: list[str], flag: str) -> ToolStatus:
            if name == "Node.js":
                raise RuntimeError("boom")
            return ToolStatus(name, commands[0], "1.0.0", True, "", "")

        with patch.object(service, "_check_tool_multi", side_effect=check):
            result = await service.check_all()

        assert [tool.name for tool in result.tools] == [
            "Claude Code CLI",
            "Node.js",
            "Python",
            "Git",
        ]
        node = result.tools[1]
        assert node.is_installed is False
        assert node.install_command
        assert result.all_installed is False


class TestVersionCapture:
    @pytest.mark.parametrize(
        ("stdout", "stderr", "expected"),
        [
            (b"v24.1.0\n", b"", "24.1.0"),
            (b"git version 2.52.0\n", b"", "2.52.0"),
            (b"", b"Python 3.13.1\n", "3.13.1"),
            (b"2.1.204 (Claude Code)\n", b"", "2.1.204"),
        ],
    )
    async def test_parses_supported_outputs(
        self,
        service: EnvCheckService,
        stdout: bytes,
        stderr: bytes,
        expected: str,
    ) -> None:
        proc = _process(stdout=stdout, stderr=stderr)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            assert await service._get_version("/usr/bin/tool", "--version") == expected

    async def test_strict_rejects_nonzero_exit(self, service: EnvCheckService) -> None:
        proc = _process(stdout=b"2.1.204\n", returncode=1)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            assert await service._get_version("/usr/bin/claude", "--version") is None

    async def test_lenient_accepts_nonzero_exit(self, service: EnvCheckService) -> None:
        proc = _process(stdout=b"2.1.204\n", returncode=1)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            version = await service._get_version_lenient("/usr/bin/claude", "--version")
        assert version == "2.1.204"

    async def test_timeout_terminates_process(self, service: EnvCheckService) -> None:
        proc = _process(communicate_error=asyncio.TimeoutError())
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            version = await service._get_version("/usr/bin/slow", "--version")
        assert version is None
        proc.kill.assert_called_once_with()
        proc.wait.assert_awaited_once_with()


class TestInstallation:
    @pytest.fixture(autouse=True)
    def successful_verification(self, service: EnvCheckService):
        with patch.object(
            service,
            "_verify_installed_tool",
            new=AsyncMock(return_value=True),
        ):
            yield

    async def test_windows_install_uses_non_interactive_winget(
        self,
        service: EnvCheckService,
    ) -> None:
        proc = _process(stdout=b"installed\n")
        progress: list[str] = []
        with patch(
            "misaka.services.skills.env_check_service._current_platform",
            return_value="windows",
        ), patch.object(
            service,
            "_resolve_install_executable",
            return_value=r"C:\Windows\winget.exe",
        ), patch(
            "asyncio.create_subprocess_exec",
            return_value=proc,
        ) as create_process:
            result = await service.install_tool("Node.js", progress.append)

        assert result.success is True
        assert "--accept-source-agreements" in result.command
        assert "--disable-interactivity" in result.command
        create_process.assert_awaited_once()
        command = create_process.await_args.args
        assert command[:4] == (
            r"C:\Windows\winget.exe",
            "install",
            "--id",
            "OpenJS.NodeJS.LTS",
        )
        assert create_process.await_args.kwargs["stdin"] == asyncio.subprocess.DEVNULL
        assert create_process.await_args.kwargs["env"] is not None
        assert any("successfully" in message for message in progress)

    async def test_macos_install_uses_brew(self, service: EnvCheckService) -> None:
        proc = _process()
        with patch(
            "misaka.services.skills.env_check_service._current_platform",
            return_value="macos",
        ), patch.object(
            service,
            "_resolve_install_executable",
            return_value="/opt/homebrew/bin/brew",
        ), patch("asyncio.create_subprocess_exec", return_value=proc) as create_process:
            result = await service.install_tool("Git")

        assert result.success is True
        assert create_process.await_args.args == ("/opt/homebrew/bin/brew", "install", "git")

    async def test_linux_apt_runs_update_then_install_as_root(
        self,
        service: EnvCheckService,
    ) -> None:
        processes = [_process(), _process()]
        with patch(
            "misaka.services.skills.env_check_service._current_platform",
            return_value="linux",
        ), patch.object(
            service,
            "_resolve_install_executable",
            return_value="/usr/bin/apt-get",
        ), patch.object(
            service,
            "_is_root",
            return_value=True,
        ), patch(
            "asyncio.create_subprocess_exec",
            side_effect=processes,
        ) as create_process:
            result = await service.install_tool("Git")

        assert result.success is True
        assert create_process.await_args_list[0].args[:2] == ("/usr/bin/apt-get", "update")
        assert create_process.await_args_list[1].args[:4] == (
            "/usr/bin/apt-get",
            "install",
            "-y",
            "git",
        )

    async def test_linux_apt_uses_noninteractive_elevation(
        self,
        service: EnvCheckService,
    ) -> None:
        proc = _process()
        with patch(
            "misaka.services.skills.env_check_service._current_platform",
            return_value="linux",
        ), patch.object(
            service,
            "_resolve_install_executable",
            return_value="/usr/bin/apt-get",
        ), patch.object(service, "_is_root", return_value=False), patch.object(
            service,
            "_resolve_elevation_command",
            return_value=["/usr/bin/sudo", "--non-interactive"],
        ), patch("asyncio.create_subprocess_exec", return_value=proc) as create_process:
            result = await service.install_tool("Python")

        assert result.success is True
        assert create_process.await_args_list[0].args[:4] == (
            "/usr/bin/sudo",
            "--non-interactive",
            "/usr/bin/apt-get",
            "update",
        )

    async def test_missing_launcher_returns_actionable_error(
        self,
        service: EnvCheckService,
    ) -> None:
        with patch(
            "misaka.services.skills.env_check_service._current_platform",
            return_value="macos",
        ), patch.object(service, "_resolve_install_executable", return_value=None):
            result = await service.install_tool("Node.js")
        assert result.success is False
        assert "brew" in result.message
        assert "nodejs.org" in result.message

    async def test_failure_returns_stderr_and_code(self, service: EnvCheckService) -> None:
        proc = _process(stderr=b"permission denied\n", returncode=1)
        with patch.object(
            service,
            "_resolve_install_executable",
            return_value=r"C:\Windows\winget.exe",
        ), patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await service.install_tool("Git")
        assert result.success is False
        assert result.returncode == 1
        assert "permission denied" in result.message

    async def test_zero_exit_still_requires_detectable_tool(
        self,
        service: EnvCheckService,
    ) -> None:
        proc = _process()
        with patch.object(
            service,
            "_resolve_install_executable",
            return_value=r"C:\Windows\winget.exe",
        ), patch.object(
            service,
            "_verify_installed_tool",
            new=AsyncMock(return_value=False),
        ), patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await service.install_tool("Git")

        assert result.success is False
        assert result.returncode == 0
        assert "could not be detected" in result.message

    async def test_progress_callback_failure_does_not_abort_install(
        self,
        service: EnvCheckService,
    ) -> None:
        proc = _process()
        progress = MagicMock(side_effect=RuntimeError("detached UI"))
        with patch.object(
            service,
            "_resolve_install_executable",
            return_value=r"C:\Windows\winget.exe",
        ), patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await service.install_tool("Git", progress)

        assert result.success is True

    async def test_timeout_kills_process(self, service: EnvCheckService) -> None:
        proc = _process(communicate_error=asyncio.TimeoutError())
        with patch.object(
            service,
            "_resolve_install_executable",
            return_value=r"C:\Windows\winget.exe",
        ), patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await service.install_tool("Git")
        assert result.success is False
        assert "timed out" in result.message
        proc.kill.assert_called_once_with()
        proc.wait.assert_awaited_once_with()

    async def test_unknown_tool_returns_failure(self, service: EnvCheckService) -> None:
        result = await service.install_tool("Unknown")
        assert result.success is False
        assert result.command == ""

    async def test_subprocess_receives_hidden_window_kwargs(
        self,
        service: EnvCheckService,
    ) -> None:
        proc = _process()
        with patch(
            "misaka.services.skills.env_check_service._current_platform",
            return_value="windows",
        ), patch.object(
            service,
            "_resolve_install_executable",
            return_value=r"C:\Windows\winget.exe",
        ), patch(
            "misaka.services.skills.env_check_service.build_background_subprocess_kwargs",
            return_value={"creationflags": 1, "startupinfo": "hidden"},
        ), patch("asyncio.create_subprocess_exec", return_value=proc) as create_process:
            await service.install_tool("Git")
        create_process.assert_awaited_once()
        kwargs = create_process.await_args.kwargs
        assert kwargs["stdin"] == asyncio.subprocess.DEVNULL
        assert kwargs["stdout"] == asyncio.subprocess.PIPE
        assert kwargs["stderr"] == asyncio.subprocess.PIPE
        assert kwargs["env"] is not None
        assert kwargs["creationflags"] == 1
        assert kwargs["startupinfo"] == "hidden"
