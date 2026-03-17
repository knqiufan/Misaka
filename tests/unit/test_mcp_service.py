"""
Tests for MCP server management service.

Tests MCPServerProcess lifecycle (start/stop/restart/health check)
and MCPService configuration loading and SDK format conversion.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from misaka.db.models import MCPServerConfig
from misaka.services.mcp.mcp_service import MCPServerProcess, MCPService


# ---------------------------------------------------------------------------
# MCPServerProcess tests
# ---------------------------------------------------------------------------

class TestMCPServerProcess:

    def test_initial_state(self) -> None:
        config = MCPServerConfig(command="node", args=["server.js"])
        process = MCPServerProcess("test-server", config)
        assert process.name == "test-server"
        assert process.is_running is False
        assert process.is_healthy is False

    @pytest.mark.asyncio
    async def test_start_stdio_server_uses_hidden_subprocess_helpers(self) -> None:
        config = MCPServerConfig(command="C:/npm/server.cmd", args=["--stdio"])
        process = MCPServerProcess("echo-server", config)

        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.pid = 12345

        with patch(
            "misaka.services.mcp.mcp_service.wrap_windows_script_command",
            return_value=["cmd.exe", "/d", "/s", "/c", '"C:/npm/server.cmd" --stdio'],
        ) as mock_wrap, patch(
            "misaka.services.mcp.mcp_service.build_background_subprocess_kwargs",
            return_value={"creationflags": 1, "startupinfo": "hidden"},
        ) as mock_kwargs, patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc
        ) as mock_exec:
            result = await process.start()

        assert result is True
        assert process.is_running is True
        assert process.is_healthy is True
        mock_wrap.assert_called_once_with("C:/npm/server.cmd", ["--stdio"])
        mock_kwargs.assert_called_once_with()
        mock_exec.assert_called_once_with(
            "cmd.exe",
            "/d",
            "/s",
            "/c",
            '"C:/npm/server.cmd" --stdio',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=None,
            creationflags=1,
            startupinfo="hidden",
        )

    @pytest.mark.asyncio
    async def test_start_already_running(self) -> None:
        config = MCPServerConfig(command="echo", args=[])
        process = MCPServerProcess("test", config)
        process._process = MagicMock(returncode=None)

        result = await process.start()
        assert result is True  # Already running, returns True

    @pytest.mark.asyncio
    async def test_start_non_stdio(self) -> None:
        """SSE/HTTP servers don't need subprocess, just mark as healthy."""
        config = MCPServerConfig(type="sse", url="http://localhost:3000")
        process = MCPServerProcess("sse-server", config)
        result = await process.start()
        assert result is True
        # Note: is_healthy property requires is_running (subprocess), which is N/A for SSE.
        # But _healthy flag is set, and check_health returns True for non-stdio.
        assert process._healthy is True
        health = await process.check_health()
        assert health is True

    @pytest.mark.asyncio
    async def test_start_no_command(self) -> None:
        config = MCPServerConfig(command="")
        process = MCPServerProcess("empty", config)
        result = await process.start()
        assert result is False

    @pytest.mark.asyncio
    async def test_start_command_not_found(self) -> None:
        config = MCPServerConfig(command="nonexistent_binary_xyz")
        process = MCPServerProcess("missing", config)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=FileNotFoundError):
            result = await process.start()

        assert result is False
        assert process.is_healthy is False

    @pytest.mark.asyncio
    async def test_start_os_error(self) -> None:
        config = MCPServerConfig(command="bad")
        process = MCPServerProcess("bad", config)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=OSError("fail")):
            result = await process.start()

        assert result is False

    @pytest.mark.asyncio
    async def test_stop_not_running(self) -> None:
        config = MCPServerConfig(command="echo")
        process = MCPServerProcess("test", config)
        await process.stop()  # Should not raise
        assert process.is_healthy is False

    @pytest.mark.asyncio
    async def test_stop_already_exited(self) -> None:
        config = MCPServerConfig(command="echo")
        process = MCPServerProcess("test", config)
        process._process = MagicMock(returncode=0, pid=123)
        await process.stop()
        assert process._process is None
        assert process.is_healthy is False

    @pytest.mark.asyncio
    async def test_stop_running_windows_uses_hidden_taskkill(self) -> None:
        config = MCPServerConfig(command="echo")
        process = MCPServerProcess("test", config)

        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.pid = 999
        process._process = mock_proc
        process._healthy = True

        mock_kill_proc = MagicMock()
        mock_kill_proc.wait = AsyncMock()

        with patch("misaka.services.mcp.mcp_service.IS_WINDOWS", True), patch(
            "misaka.services.mcp.mcp_service.build_background_subprocess_kwargs",
            return_value={"creationflags": 1, "startupinfo": "hidden"},
        ) as mock_kwargs, patch(
            "asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_kill_proc
        ) as mock_exec:
            await process.stop()

        mock_kwargs.assert_called_once_with()
        mock_exec.assert_called_once_with(
            "taskkill",
            "/T",
            "/F",
            "/PID",
            "999",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=1,
            startupinfo="hidden",
        )
        assert process._process is None
        assert process.is_healthy is False

    @pytest.mark.asyncio
    async def test_restart(self) -> None:
        config = MCPServerConfig(command="echo", args=["hi"])
        process = MCPServerProcess("test", config)

        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.pid = 100

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            result = await process.restart()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_health_no_process(self) -> None:
        config = MCPServerConfig(command="echo")
        process = MCPServerProcess("test", config)
        result = await process.check_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_health_running(self) -> None:
        config = MCPServerConfig(command="echo")
        process = MCPServerProcess("test", config)
        process._process = MagicMock(returncode=None)
        result = await process.check_health()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_health_exited(self) -> None:
        config = MCPServerConfig(command="echo")
        process = MCPServerProcess("test", config)
        process._process = MagicMock(returncode=1)
        result = await process.check_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_health_non_stdio(self) -> None:
        config = MCPServerConfig(type="sse", url="http://localhost:3000")
        process = MCPServerProcess("sse", config)
        process._healthy = True
        result = await process.check_health()
        assert result is True

    def test_start_count_increments(self) -> None:
        config = MCPServerConfig(command="echo")
        process = MCPServerProcess("test", config)
        assert process._start_count == 0

    @pytest.mark.asyncio
    async def test_start_with_env(self) -> None:
        config = MCPServerConfig(command="echo", env={"MY_VAR": "hello"})
        process = MCPServerProcess("test", config)

        mock_proc = MagicMock(returncode=None, pid=1)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc) as mock_exec:
            await process.start()
            # Verify env was passed
            call_kwargs = mock_exec.call_args
            assert call_kwargs.kwargs.get("env") is not None


# ---------------------------------------------------------------------------
# MCPService tests
# ---------------------------------------------------------------------------

class TestMCPService:

    def test_to_sdk_format_stdio(self) -> None:
        service = MCPService()
        servers = {
            "fs": MCPServerConfig(command="npx", args=["-y", "@anthropic/fs-mcp"], env={"ROOT": "/tmp"}),
        }
        result = service.to_sdk_format(servers)
        assert "fs" in result
        assert result["fs"]["command"] == "npx"
        assert result["fs"]["args"] == ["-y", "@anthropic/fs-mcp"]
        assert result["fs"]["env"]["ROOT"] == "/tmp"

    def test_to_sdk_format_sse(self) -> None:
        service = MCPService()
        servers = {
            "api": MCPServerConfig(type="sse", url="http://localhost:8080/mcp", headers={"auth": "token"}),
        }
        result = service.to_sdk_format(servers)
        assert result["api"]["type"] == "sse"
        assert result["api"]["url"] == "http://localhost:8080/mcp"
        assert result["api"]["headers"]["auth"] == "token"

    def test_to_sdk_format_http(self) -> None:
        service = MCPService()
        servers = {
            "web": MCPServerConfig(type="http", url="http://localhost:9090/mcp"),
        }
        result = service.to_sdk_format(servers)
        assert result["web"]["type"] == "http"
        assert result["web"]["url"] == "http://localhost:9090/mcp"

    def test_to_sdk_format_skip_missing_url(self) -> None:
        service = MCPService()
        servers = {
            "broken-sse": MCPServerConfig(type="sse"),
            "broken-http": MCPServerConfig(type="http"),
        }
        result = service.to_sdk_format(servers)
        assert len(result) == 0

    def test_to_sdk_format_skip_missing_command(self) -> None:
        service = MCPService()
        servers = {"broken": MCPServerConfig(command="")}
        result = service.to_sdk_format(servers)
        assert len(result) == 0

    def test_load_mcp_servers_from_file(self, tmp_path: Path) -> None:
        service = MCPService()
        config = {
            "mcpServers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@anthropic/fs-mcp"],
                    "env": {"ROOT": "/home"},
                },
                "web-api": {
                    "type": "sse",
                    "url": "http://localhost:3000/mcp",
                },
            }
        }
        config_file = tmp_path / ".claude.json"
        config_file.write_text(json.dumps(config))

        with patch.object(Path, "home", return_value=tmp_path):
            servers = service.load_mcp_servers()

        assert "filesystem" in servers
        assert servers["filesystem"].command == "npx"
        assert "web-api" in servers
        assert servers["web-api"].type == "sse"

    def test_load_mcp_servers_empty(self, tmp_path: Path) -> None:
        service = MCPService()
        with patch.object(Path, "home", return_value=tmp_path):
            servers = service.load_mcp_servers()
        assert servers == {}

    def test_load_mcp_servers_invalid_json(self, tmp_path: Path) -> None:
        service = MCPService()
        config_file = tmp_path / ".claude.json"
        config_file.write_text("not json{{{")

        with patch.object(Path, "home", return_value=tmp_path):
            servers = service.load_mcp_servers()
        assert servers == {}

    @pytest.mark.asyncio
    async def test_start_server(self) -> None:
        service = MCPService()
        config = MCPServerConfig(command="echo", args=["hi"])

        mock_proc = MagicMock(returncode=None, pid=1)
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            result = await service.start_server("test", config)
        assert result is True
        assert "test" in service._servers

    @pytest.mark.asyncio
    async def test_start_server_already_running(self) -> None:
        service = MCPService()
        mock_process = MagicMock()
        mock_process.is_running = True
        service._servers["test"] = mock_process

        result = await service.start_server("test", MCPServerConfig(command="echo"))
        assert result is True

    @pytest.mark.asyncio
    async def test_stop_server(self) -> None:
        service = MCPService()
        mock_process = AsyncMock()
        service._servers["test"] = mock_process

        await service.stop_server("test")
        mock_process.stop.assert_awaited_once()
        assert "test" not in service._servers

    @pytest.mark.asyncio
    async def test_stop_server_not_found(self) -> None:
        service = MCPService()
        await service.stop_server("nonexistent")  # Should not raise

    @pytest.mark.asyncio
    async def test_restart_server(self) -> None:
        service = MCPService()
        mock_process = AsyncMock()
        mock_process.restart = AsyncMock(return_value=True)
        service._servers["test"] = mock_process

        result = await service.restart_server("test")
        assert result is True
        mock_process.restart.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_restart_server_not_found(self) -> None:
        service = MCPService()
        result = await service.restart_server("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_health(self) -> None:
        service = MCPService()
        process1 = MCPServerProcess("p1", MCPServerConfig(command="echo"))
        process1._process = MagicMock(returncode=None)
        process2 = MCPServerProcess("p2", MCPServerConfig(command="echo"))
        # p2 has no process
        service._servers = {"p1": process1, "p2": process2}

        results = await service.check_health()
        assert results["p1"] is True
        assert results["p2"] is False

    @pytest.mark.asyncio
    async def test_stop_all(self) -> None:
        service = MCPService()
        p1 = AsyncMock()
        p2 = AsyncMock()
        service._servers = {"a": p1, "b": p2}

        await service.stop_all()
        p1.stop.assert_awaited_once()
        p2.stop.assert_awaited_once()
        assert service._servers == {}

    def test_get_server_status(self) -> None:
        service = MCPService()
        process = MCPServerProcess("test", MCPServerConfig(command="echo"))
        process._process = MagicMock(returncode=None)
        process._healthy = True
        service._servers["test"] = process

        status = service.get_server_status()
        assert status["test"]["is_running"] is True
        assert status["test"]["is_healthy"] is True
        assert status["test"]["transport"] == "stdio"

    def test_to_config_file_path(self, tmp_path: Path) -> None:
        service = MCPService()
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(json.dumps({"mcpServers": {"test": {}}}))

        with patch.object(Path, "home", return_value=tmp_path):
            result = service.to_config_file_path()
        assert result is not None
        assert "settings.json" in result

    def test_to_config_file_path_none(self, tmp_path: Path) -> None:
        service = MCPService()
        with patch.object(Path, "home", return_value=tmp_path):
            result = service.to_config_file_path()
        assert result is None

    def test_load_mcp_servers_with_headers(self, tmp_path: Path) -> None:
        """Test that headers are loaded from config files."""
        service = MCPService()
        config = {
            "mcpServers": {
                "api-server": {
                    "type": "sse",
                    "url": "http://localhost:8080/mcp",
                    "headers": {
                        "Authorization": "Bearer secret-token",
                        "X-API-Key": "api-key-123",
                    },
                },
            }
        }
        config_file = tmp_path / ".claude.json"
        config_file.write_text(json.dumps(config))

        with patch.object(Path, "home", return_value=tmp_path):
            servers = service.load_mcp_servers()

        assert "api-server" in servers
        assert servers["api-server"].headers == {
            "Authorization": "Bearer secret-token",
            "X-API-Key": "api-key-123",
        }

    def test_to_sdk_format_includes_headers_for_sse(self) -> None:
        """Test that headers are included in SDK format for SSE servers."""
        service = MCPService()
        servers = {
            "api": MCPServerConfig(
                type="sse",
                url="http://localhost:8080/mcp",
                headers={"Authorization": "Bearer token", "X-Custom": "value"},
            ),
        }
        result = service.to_sdk_format(servers)
        assert result["api"]["type"] == "sse"
        assert result["api"]["url"] == "http://localhost:8080/mcp"
        assert result["api"]["headers"] == {"Authorization": "Bearer token", "X-Custom": "value"}

    def test_to_sdk_format_includes_headers_for_http(self) -> None:
        """Test that headers are included in SDK format for HTTP servers."""
        service = MCPService()
        servers = {
            "web": MCPServerConfig(
                type="http",
                url="http://localhost:9090/mcp",
                headers={"X-API-Key": "key123"},
            ),
        }
        result = service.to_sdk_format(servers)
        assert result["web"]["type"] == "http"
        assert result["web"]["headers"] == {"X-API-Key": "key123"}

    def test_to_sdk_format_omits_empty_headers(self) -> None:
        """Test that empty headers dict is omitted from SDK format."""
        service = MCPService()
        servers = {
            "api": MCPServerConfig(type="sse", url="http://localhost:8080/mcp", headers={}),
        }
        result = service.to_sdk_format(servers)
        assert "headers" not in result["api"]
