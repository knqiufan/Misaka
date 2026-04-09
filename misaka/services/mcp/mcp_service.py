"""
MCP (Model Context Protocol) server management service.

Loads MCP server configurations from Claude config files,
converts them to the format expected by the SDK, and manages
MCP server subprocess lifecycles.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from pathlib import Path
from typing import Any

from misaka.config import IS_WINDOWS
from misaka.db.models import MCPServerConfig
from misaka.utils.platform import (
    build_background_subprocess_kwargs,
    wrap_windows_script_command,
)

logger = logging.getLogger(__name__)


class MCPServerProcess:
    """Manages a single MCP server subprocess (stdio transport)."""

    def __init__(self, name: str, config: MCPServerConfig) -> None:
        self.name = name
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._healthy: bool = False
        self._start_count: int = 0

    @property
    def is_running(self) -> bool:
        """Check if the subprocess is currently running."""
        return self._process is not None and self._process.returncode is None

    @property
    def is_healthy(self) -> bool:
        return self._healthy and self.is_running

    async def start(self) -> bool:
        """Start the MCP server subprocess.

        Returns True if the process started successfully.
        """
        if self.is_running:
            logger.warning("MCP server '%s' is already running", self.name)
            return True

        if self.config.type != "stdio":
            logger.info(
                "MCP server '%s' uses %s transport, no subprocess needed",
                self.name,
                self.config.type,
            )
            self._healthy = True
            return True

        if not self.config.command:
            logger.error("MCP server '%s' has no command configured", self.name)
            return False

        self._start_count += 1
        env = {**os.environ, **self.config.env} if self.config.env else None

        try:
            command = wrap_windows_script_command(
                self.config.command,
                list(self.config.args),
            )
            self._process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                **build_background_subprocess_kwargs(),
            )
            self._healthy = True
            logger.info(
                "Started MCP server '%s' (pid=%s, attempt=%d)",
                self.name,
                self._process.pid,
                self._start_count,
            )
            return True

        except FileNotFoundError:
            logger.error(
                "MCP server '%s': command not found: %s",
                self.name,
                self.config.command,
            )
            self._healthy = False
            return False

        except OSError as exc:
            logger.error("MCP server '%s' failed to start: %s", self.name, exc)
            self._healthy = False
            return False

    async def stop(self) -> None:
        """Stop the MCP server subprocess gracefully."""
        if not self._process or self._process.returncode is not None:
            self._process = None
            self._healthy = False
            return

        pid = self._process.pid
        logger.info("Stopping MCP server '%s' (pid=%s)", self.name, pid)

        try:
            if IS_WINDOWS:
                # On Windows, use taskkill for tree-kill
                kill_proc = await asyncio.create_subprocess_exec(
                    "taskkill", "/T", "/F", "/PID", str(pid),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    **build_background_subprocess_kwargs(),
                )
                await asyncio.wait_for(kill_proc.wait(), timeout=5)
            else:
                self._process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
        except ProcessLookupError:
            pass
        except OSError as exc:
            logger.warning("Error stopping MCP server '%s': %s", self.name, exc)

        self._process = None
        self._healthy = False

    async def restart(self) -> bool:
        """Restart the MCP server subprocess."""
        await self.stop()
        return await self.start()

    async def check_health(self) -> bool:
        """Check if the subprocess is still alive."""
        if self.config.type != "stdio":
            return self._healthy

        if not self._process or self._process.returncode is not None:
            self._healthy = False
            return False

        self._healthy = True
        return True


class MCPService:
    """Service for managing MCP server configurations and processes."""

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerProcess] = {}

    def load_mcp_servers(
        self,
        working_directory: str | None = None,
    ) -> dict[str, MCPServerConfig]:
        """Load MCP server configs from Claude configuration files.

        Reads from ``~/.claude.json``, ``~/.claude/settings.json``, and
        optionally a project-level ``.mcp.json`` in *working_directory*.
        Project-level configs override global ones with the same name.
        """
        home = Path.home()
        config_paths: list[Path] = [
            home / ".claude.json",
            home / ".claude" / "settings.json",
        ]
        if working_directory:
            project_mcp = Path(working_directory) / ".mcp.json"
            if project_mcp.is_file():
                config_paths.append(project_mcp)

        merged: dict[str, MCPServerConfig] = {}

        for config_path in config_paths:
            if not config_path.is_file():
                continue
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                servers = data.get("mcpServers", {})
                for name, config in servers.items():
                    merged[name] = MCPServerConfig(
                        command=config.get("command", ""),
                        args=config.get("args", []),
                        env=config.get("env", {}),
                        type=config.get("type", "stdio"),
                        url=config.get("url", ""),
                        headers=config.get("headers", {}),
                    )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load MCP config from %s: %s", config_path, exc)

        return merged

    def to_sdk_format(self, servers: dict[str, MCPServerConfig]) -> dict[str, Any]:
        """Convert MCPServerConfig objects to the SDK's expected format.

        The SDK accepts dicts with type-specific fields for stdio, sse, and http.
        """
        result: dict[str, Any] = {}

        for name, config in servers.items():
            transport = config.type or "stdio"

            if transport == "sse":
                if not config.url:
                    logger.warning("SSE server '%s' is missing url, skipping", name)
                    continue
                entry: dict[str, Any] = {"type": "sse", "url": config.url}
                if config.headers:
                    entry["headers"] = config.headers
                result[name] = entry

            elif transport == "http":
                if not config.url:
                    logger.warning("HTTP server '%s' is missing url, skipping", name)
                    continue
                entry = {"type": "http", "url": config.url}
                if config.headers:
                    entry["headers"] = config.headers
                result[name] = entry

            else:  # stdio
                if not config.command:
                    logger.warning("stdio server '%s' is missing command, skipping", name)
                    continue
                entry = {"command": config.command, "args": config.args}
                if config.env:
                    entry["env"] = config.env
                result[name] = entry

        return result

    def to_config_file_path(self) -> str | None:
        """Return a path to an MCP config file for the SDK, if one exists.

        The SDK can accept a ``str | Path`` pointing to a JSON config file
        instead of an inline dict. This allows the SDK to read the config
        directly.
        """
        home = Path.home()
        candidates = [
            home / ".claude" / "settings.json",
            home / ".claude.json",
        ]
        for path in candidates:
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if data.get("mcpServers"):
                        return str(path)
                except (json.JSONDecodeError, OSError):
                    continue
        return None

    async def start_server(self, name: str, config: MCPServerConfig) -> bool:
        """Start a managed MCP server subprocess."""
        if name in self._servers and self._servers[name].is_running:
            logger.info("MCP server '%s' already running", name)
            return True

        process = MCPServerProcess(name, config)
        result = await process.start()
        if result:
            self._servers[name] = process
        return result

    async def stop_server(self, name: str) -> None:
        """Stop a managed MCP server subprocess."""
        process = self._servers.pop(name, None)
        if process:
            await process.stop()

    async def restart_server(self, name: str) -> bool:
        """Restart a managed MCP server subprocess."""
        process = self._servers.get(name)
        if not process:
            logger.warning("MCP server '%s' not found, cannot restart", name)
            return False
        return await process.restart()

    async def check_health(self) -> dict[str, bool]:
        """Check the health of all managed MCP servers.

        Returns a dict mapping server names to health status.
        """
        results: dict[str, bool] = {}
        for name, process in self._servers.items():
            results[name] = await process.check_health()
        return results

    async def stop_all(self) -> None:
        """Stop all managed MCP server subprocesses."""
        tasks = [process.stop() for process in self._servers.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._servers.clear()
        logger.info("All MCP servers stopped")

    def get_server_status(self) -> dict[str, dict[str, Any]]:
        """Return status information for all managed servers."""
        status: dict[str, dict[str, Any]] = {}
        for name, process in self._servers.items():
            status[name] = {
                "is_running": process.is_running,
                "is_healthy": process.is_healthy,
                "transport": process.config.type,
            }
        return status
