"""Tests for official MCP Registry discovery and config generation."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from misaka.services.mcp.mcp_market_service import (
    MarketMCPServer,
    MCPInstallPlan,
    MCPMarketService,
)


@pytest.fixture
def service() -> MCPMarketService:
    return MCPMarketService()


def _server(**overrides) -> MarketMCPServer:
    values = {
        "name": "io.github.owner/example-mcp",
        "title": "Example MCP",
        "description": "Example server",
        "version": "1.2.3",
    }
    values.update(overrides)
    return MarketMCPServer(**values)


class TestSearch:
    async def test_searches_latest_registry_entries(self, service: MCPMarketService) -> None:
        response = {
            "servers": [
                {
                    "server": {
                        "name": "io.github.owner/example",
                        "title": "Example",
                        "description": "Current",
                        "version": "2.0.0",
                        "repository": {"url": "https://github.com/owner/example"},
                        "remotes": [
                            {"type": "streamable-http", "url": "https://example.test/mcp"}
                        ],
                    },
                    "_meta": {
                        "io.modelcontextprotocol.registry/official": {
                            "status": "active",
                            "isLatest": True,
                        }
                    },
                }
            ],
            "metadata": {"count": 1},
        }
        with patch.object(service, "_http_get_json", return_value=response) as http_get:
            result = await service.search(" github ", limit=500)

        assert result.error is None
        assert result.query == "github"
        assert result.total == 1
        assert result.servers[0].repository_url == "https://github.com/owner/example"
        url = http_get.call_args.args[0]
        assert "search=github" in url
        assert "version=latest" in url
        assert "limit=100" in url

    async def test_browse_omits_empty_search(self, service: MCPMarketService) -> None:
        with patch.object(
            service,
            "_http_get_json",
            return_value={"servers": [], "metadata": {}},
        ) as http_get:
            result = await service.search("")
        assert result.servers == []
        assert "search=" not in http_get.call_args.args[0]

    async def test_timeout(self, service: MCPMarketService) -> None:
        with patch.object(service, "_http_get_json", side_effect=asyncio.TimeoutError):
            result = await service.search("github")
        assert result.error == "timeout"

    async def test_network_error(self, service: MCPMarketService) -> None:
        with patch.object(
            service,
            "_http_get_json",
            side_effect=RuntimeError("offline"),
        ):
            result = await service.search("github")
        assert result.error == "offline"

    def test_deduplicates_and_prefers_latest_active_version(self) -> None:
        entries = [
            {
                "server": {"name": "owner/server", "version": "1.0.0"},
                "_meta": {
                    "io.modelcontextprotocol.registry/official": {
                        "status": "active",
                        "isLatest": False,
                    }
                },
            },
            {
                "server": {"name": "owner/server", "version": "2.0.0"},
                "_meta": {
                    "io.modelcontextprotocol.registry/official": {
                        "status": "active",
                        "isLatest": True,
                    }
                },
            },
            {
                "server": {"name": "owner/yanked", "version": "1.0.0"},
                "_meta": {
                    "io.modelcontextprotocol.registry/official": {
                        "status": "deleted",
                        "isLatest": True,
                    }
                },
            },
            {"not-a-server": True},
        ]
        parsed = MCPMarketService._parse_servers(entries)
        assert [(item.name, item.version) for item in parsed] == [
            ("owner/server", "2.0.0")
        ]


class TestRemoteConfig:
    def test_prefers_streamable_http_and_collects_secret_templates(
        self,
        service: MCPMarketService,
    ) -> None:
        server = _server(
            remotes=[
                {"type": "sse", "url": "https://fallback.test/sse"},
                {
                    "type": "streamable-http",
                    "url": "https://{tenant}.example.test/mcp",
                    "headers": [
                        {
                            "name": "Authorization",
                            "value": "Bearer {api_key}",
                            "description": "API token",
                            "isRequired": True,
                            "isSecret": True,
                        }
                    ],
                },
            ]
        )
        plan = service.create_install_plan(server)
        assert plan.kind == "remote"
        assert plan.option_index == 1
        inputs = {item.key: item for item in plan.inputs}
        assert inputs["remote.variable.tenant"].required is True
        assert inputs["remote.header.Authorization.variable.api_key"].secret is True

        config = service.build_config(
            server,
            plan,
            {
                "remote.variable.tenant": "acme",
                "remote.header.Authorization.variable.api_key": "secret",
            },
        )
        assert config == {
            "type": "http",
            "url": "https://acme.example.test/mcp",
            "headers": {"Authorization": "Bearer secret"},
        }

    def test_requires_unresolved_template_values(self, service: MCPMarketService) -> None:
        server = _server(
            remotes=[{"type": "streamable-http", "url": "https://{tenant}.test/mcp"}]
        )
        plan = service.create_install_plan(server)
        with pytest.raises(ValueError, match="tenant"):
            service.build_config(server, plan)

    def test_uses_variable_defaults_and_direct_header_input(
        self,
        service: MCPMarketService,
    ) -> None:
        server = _server(
            remotes=[
                {
                    "type": "sse",
                    "url": "https://example.test/{workspace}/sse",
                    "variables": {"workspace": {"default": "main"}},
                    "headers": [
                        {"name": "X-API-Key", "isRequired": True, "isSecret": True}
                    ],
                }
            ]
        )
        plan = service.create_install_plan(server)
        config = service.build_config(
            server,
            plan,
            {"remote.header.X-API-Key": "token"},
        )
        assert config == {
            "type": "sse",
            "url": "https://example.test/main/sse",
            "headers": {"X-API-Key": "token"},
        }

    def test_ignores_unsupported_remote_and_falls_back_to_package(
        self,
        service: MCPMarketService,
    ) -> None:
        server = _server(
            remotes=[{"type": "websocket", "url": "wss://example.test"}],
            packages=[
                {
                    "registryType": "pypi",
                    "identifier": "example-mcp",
                    "version": "1.0.0",
                    "transport": {"type": "stdio"},
                }
            ],
        )
        assert service.create_install_plan(server).kind == "package"


class TestPackageConfig:
    def test_builds_npm_stdio_config(self, service: MCPMarketService) -> None:
        server = _server(
            packages=[
                {
                    "registryType": "npm",
                    "identifier": "@owner/example-mcp",
                    "version": "1.2.3",
                    "runtimeHint": "npx",
                    "transport": {"type": "stdio"},
                    "runtimeArguments": [{"type": "positional", "value": "-y"}],
                    "environmentVariables": [
                        {"name": "API_KEY", "isRequired": True, "isSecret": True},
                        {"name": "MODE", "default": "safe"},
                    ],
                    "packageArguments": [
                        {"type": "named", "name": "--read-only", "default": "true"},
                        {"type": "named", "name": "--region"},
                    ],
                }
            ]
        )
        plan = service.create_install_plan(server)
        input_map = {item.key: item for item in plan.inputs}
        assert input_map["package.env.API_KEY"].secret is True
        config = service.build_config(
            server,
            plan,
            {
                "package.env.API_KEY": "token",
                "package.packageArguments.1": "eu",
            },
        )
        assert config == {
            "type": "stdio",
            "command": "npx",
            "args": [
                "-y",
                "@owner/example-mcp@1.2.3",
                "--read-only",
                "--region",
                "eu",
            ],
            "env": {"API_KEY": "token", "MODE": "safe"},
        }

    def test_builds_pypi_uvx_config(self, service: MCPMarketService) -> None:
        server = _server(
            packages=[
                {
                    "registryType": "pypi",
                    "identifier": "example-mcp",
                    "version": "2.0.0",
                    "transport": {"type": "stdio"},
                }
            ]
        )
        plan = service.create_install_plan(server)
        assert service.build_config(server, plan) == {
            "type": "stdio",
            "command": "uvx",
            "args": ["example-mcp==2.0.0"],
        }

    def test_resolves_nested_environment_and_argument_variables(
        self,
        service: MCPMarketService,
    ) -> None:
        server = _server(
            packages=[
                {
                    "registryType": "npm",
                    "identifier": "example-mcp",
                    "version": "1.0.0",
                    "transport": {"type": "stdio"},
                    "environmentVariables": [
                        {
                            "name": "AUTHORIZATION",
                            "value": "Bearer {token}",
                            "variables": {
                                "token": {
                                    "description": "API token",
                                    "isRequired": True,
                                    "isSecret": True,
                                }
                            },
                        }
                    ],
                    "packageArguments": [
                        {
                            "type": "positional",
                            "value": "{directory}",
                            "variables": {"directory": {"default": "/workspace"}},
                        }
                    ],
                }
            ]
        )
        plan = service.create_install_plan(server)
        input_map = {item.key: item for item in plan.inputs}
        token_key = "package.env.AUTHORIZATION.variable.token"
        directory_key = "package.packageArguments.0.variable.directory"
        assert input_map[token_key].secret is True
        assert input_map[directory_key].default == "/workspace"

        config = service.build_config(server, plan, {token_key: "secret"})
        assert config["env"] == {"AUTHORIZATION": "Bearer secret"}
        assert config["args"] == ["-y", "example-mcp@1.0.0", "/workspace"]

    def test_rejects_required_package_values(self, service: MCPMarketService) -> None:
        server = _server(
            packages=[
                {
                    "registryType": "npm",
                    "identifier": "example-mcp",
                    "transport": {"type": "stdio"},
                    "environmentVariables": [{"name": "TOKEN", "isRequired": True}],
                }
            ]
        )
        plan = service.create_install_plan(server)
        with pytest.raises(ValueError, match="TOKEN"):
            service.build_config(server, plan)

    @pytest.mark.parametrize(
        "packages",
        [
            [],
            [{"registryType": "oci", "identifier": "image", "transport": {"type": "stdio"}}],
            [{"registryType": "npm", "identifier": "pkg", "transport": {"type": "sse"}}],
            [
                {
                    "registryType": "npm",
                    "identifier": "pkg",
                    "runtimeHint": "powershell",
                    "transport": {"type": "stdio"},
                }
            ],
        ],
    )
    def test_rejects_unsupported_packages(
        self,
        service: MCPMarketService,
        packages: list[dict],
    ) -> None:
        with pytest.raises(ValueError, match="No supported"):
            service.create_install_plan(_server(packages=packages))


class TestDefensiveValidation:
    def test_config_name_is_sanitized(self, service: MCPMarketService) -> None:
        plan = service.create_install_plan(
            _server(
                name="io.github.Owner/My Fancy MCP!",
                remotes=[{"type": "sse", "url": "https://example.test/sse"}],
            )
        )
        assert plan.server_name == "my-fancy-mcp"

    def test_rejects_stale_plan_index(self, service: MCPMarketService) -> None:
        server = _server(remotes=[])
        plan = MCPInstallPlan("example", "remote", 3, ())
        with pytest.raises(ValueError, match="no longer available"):
            service.build_config(server, plan)

    def test_rejects_invalid_remote_url(self, service: MCPMarketService) -> None:
        server = _server(remotes=[{"type": "sse", "url": "file:///tmp/socket"}])
        plan = MCPInstallPlan("example", "remote", 0, ())
        with pytest.raises(ValueError, match="invalid remote URL"):
            service.build_config(server, plan)

    def test_http_json_validation(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps([]).encode()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch(
            "misaka.services.mcp.mcp_market_service.urlopen",
            return_value=response,
        ), pytest.raises(RuntimeError, match="invalid response"):
            MCPMarketService._http_get_json("https://example.test")
