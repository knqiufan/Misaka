"""Online MCP server discovery backed by the official MCP Registry."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_REGISTRY_BASE_URL = "https://registry.modelcontextprotocol.io/v0.1"
_HTTP_TIMEOUT = 15
_TEMPLATE_RE = re.compile(r"\{([A-Za-z0-9_.-]+)\}")


@dataclass(frozen=True)
class MCPMarketInput:
    """A value that must be supplied before a registry entry can be installed."""

    key: str
    label: str
    description: str = ""
    default: str = ""
    required: bool = False
    secret: bool = False


@dataclass
class MarketMCPServer:
    """Installable MCP server metadata returned by the official registry."""

    name: str
    title: str
    description: str
    version: str
    repository_url: str = ""
    remotes: list[dict[str, Any]] = field(default_factory=list)
    packages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.title or self.name


@dataclass(frozen=True)
class MCPInstallPlan:
    """Selected registry transport and its user-configurable inputs."""

    server_name: str
    kind: str
    option_index: int
    inputs: tuple[MCPMarketInput, ...]


@dataclass
class MCPMarketSearchResult:
    """Result of an MCP Registry search."""

    query: str
    servers: list[MarketMCPServer]
    total: int = 0
    error: str | None = None


class MCPMarketService:
    """Search the official MCP Registry and build Claude-compatible configs."""

    def __init__(self, base_url: str = _REGISTRY_BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")

    async def search(self, query: str = "", limit: int = 30) -> MCPMarketSearchResult:
        """Search active, latest MCP servers in the public registry."""
        limit = max(1, min(100, limit))
        params: dict[str, str | int] = {"limit": limit, "version": "latest"}
        normalized_query = query.strip()
        if normalized_query:
            params["search"] = normalized_query
        url = f"{self._base_url}/servers?{urlencode(params)}"

        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(self._http_get_json, url),
                timeout=_HTTP_TIMEOUT + 5,
            )
        except asyncio.TimeoutError:
            logger.warning("MCP Registry search timed out for %r", query)
            return MCPMarketSearchResult(query, [], error="timeout")
        except Exception as exc:
            logger.warning("MCP Registry search failed: %s", exc)
            return MCPMarketSearchResult(query, [], error=str(exc))

        servers = self._parse_servers(data.get("servers", []))
        metadata = data.get("metadata") or {}
        total = metadata.get("count", len(servers))
        return MCPMarketSearchResult(
            query=normalized_query,
            servers=servers,
            total=total if isinstance(total, int) else len(servers),
        )

    def create_install_plan(self, server: MarketMCPServer) -> MCPInstallPlan:
        """Choose the safest supported transport and describe required inputs."""
        indexed_remotes = [
            (index, remote)
            for index, remote in enumerate(server.remotes)
            if remote.get("type") in {"streamable-http", "sse"}
            and remote.get("url")
        ]
        if indexed_remotes:
            indexed_remotes.sort(
                key=lambda item: 0
                if item[1].get("type") == "streamable-http"
                else 1
            )
            option_index, remote = indexed_remotes[0]
            return MCPInstallPlan(
                server_name=self._config_name(server),
                kind="remote",
                option_index=option_index,
                inputs=tuple(self._remote_inputs(remote)),
            )

        for index, package in enumerate(server.packages):
            if self._is_supported_package(package):
                return MCPInstallPlan(
                    server_name=self._config_name(server),
                    kind="package",
                    option_index=index,
                    inputs=tuple(self._package_inputs(package)),
                )

        raise ValueError("No supported HTTP, SSE, npm, or PyPI transport")

    def build_config(
        self,
        server: MarketMCPServer,
        plan: MCPInstallPlan,
        values: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Resolve an install plan into a Claude ``mcpServers`` entry."""
        values = values or {}
        self._validate_inputs(plan.inputs, values)
        if plan.kind == "remote":
            try:
                remote = server.remotes[plan.option_index]
            except IndexError as exc:
                raise ValueError("Registry remote transport is no longer available") from exc
            return self._build_remote_config(remote, values)
        if plan.kind == "package":
            try:
                package = server.packages[plan.option_index]
            except IndexError as exc:
                raise ValueError("Registry package transport is no longer available") from exc
            return self._build_package_config(package, values)
        raise ValueError(f"Unsupported MCP install plan: {plan.kind}")

    @staticmethod
    def _http_get_json(url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "Misaka/1.0"},
        )
        try:
            with urlopen(request, timeout=_HTTP_TIMEOUT) as response:
                data = json.loads(response.read())
        except (URLError, json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"HTTP request failed: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Registry returned an invalid response")
        return data

    @classmethod
    def _parse_servers(cls, entries: list[Any]) -> list[MarketMCPServer]:
        latest: dict[str, MarketMCPServer] = {}
        latest_flags: dict[str, bool] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            raw = entry.get("server")
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            official = (entry.get("_meta") or {}).get(
                "io.modelcontextprotocol.registry/official",
                {},
            )
            if official.get("status") not in (None, "active"):
                continue
            server = cls._parse_server(raw)
            is_latest = bool(official.get("isLatest"))
            if server.name not in latest or (is_latest and not latest_flags[server.name]):
                latest[server.name] = server
                latest_flags[server.name] = is_latest
        return list(latest.values())

    @staticmethod
    def _parse_server(raw: dict[str, Any]) -> MarketMCPServer:
        repository = raw.get("repository") or {}
        remotes = raw.get("remotes") or []
        packages = raw.get("packages") or []
        return MarketMCPServer(
            name=str(raw.get("name") or ""),
            title=str(raw.get("title") or ""),
            description=str(raw.get("description") or ""),
            version=str(raw.get("version") or ""),
            repository_url=str(repository.get("url") or ""),
            remotes=[item for item in remotes if isinstance(item, dict)],
            packages=[item for item in packages if isinstance(item, dict)],
        )

    @staticmethod
    def _config_name(server: MarketMCPServer) -> str:
        raw = server.name.rsplit("/", 1)[-1] or server.display_name
        normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-").lower()
        return normalized or "mcp-server"

    @staticmethod
    def _is_supported_package(package: dict[str, Any]) -> bool:
        transport = package.get("transport") or {}
        registry_type = package.get("registryType")
        runtime_hint = package.get("runtimeHint")
        supported_runtime = (
            registry_type == "npm" and runtime_hint in (None, "", "npx")
        ) or (
            registry_type == "pypi" and runtime_hint in (None, "", "uvx")
        )
        return (
            supported_runtime
            and transport.get("type") == "stdio"
            and bool(package.get("identifier"))
        )

    @classmethod
    def _remote_inputs(cls, remote: dict[str, Any]) -> list[MCPMarketInput]:
        inputs: dict[str, MCPMarketInput] = {}
        variables = remote.get("variables") or {}
        if isinstance(variables, dict):
            for name, spec in variables.items():
                if isinstance(spec, dict) and "value" not in spec:
                    key = f"remote.variable.{name}"
                    inputs[key] = cls._input_from_spec(key, name, spec)

        def add_url_template_input(
            name: str,
            spec: dict[str, Any] | None = None,
        ) -> None:
            key = f"remote.variable.{name}"
            spec = spec or {}
            if "value" in spec:
                return
            current = inputs.get(key)
            inputs[key] = MCPMarketInput(
                key=key,
                label=current.label if current else name,
                description=(
                    current.description
                    if current and current.description
                    else str(spec.get("description") or spec.get("placeholder") or "")
                ),
                default=current.default if current else str(spec.get("default") or ""),
                required=True,
                secret=bool(spec.get("isSecret")) or bool(current and current.secret),
            )

        for name in _TEMPLATE_RE.findall(str(remote.get("url") or "")):
            spec = variables.get(name) if isinstance(variables, dict) else None
            add_url_template_input(name, spec if isinstance(spec, dict) else None)

        for header in remote.get("headers") or []:
            if not isinstance(header, dict):
                continue
            name = str(header.get("name") or "")
            if not name:
                continue
            key = f"remote.header.{name}"
            if "value" not in header:
                inputs[key] = cls._input_from_spec(key, name, header)
            else:
                for item in cls._templated_value_inputs(key, header):
                    inputs[item.key] = item
        return list(inputs.values())

    @classmethod
    def _package_inputs(cls, package: dict[str, Any]) -> list[MCPMarketInput]:
        inputs: list[MCPMarketInput] = []
        for env_var in package.get("environmentVariables") or []:
            if not isinstance(env_var, dict) or not env_var.get("name"):
                continue
            name = str(env_var["name"])
            key = f"package.env.{name}"
            if "value" in env_var:
                inputs.extend(cls._templated_value_inputs(key, env_var))
            else:
                inputs.append(cls._input_from_spec(key, name, env_var))

        for group_name in ("runtimeArguments", "packageArguments"):
            for index, argument in enumerate(package.get(group_name) or []):
                if not isinstance(argument, dict):
                    continue
                label = str(
                    argument.get("valueHint")
                    or argument.get("name")
                    or f"Argument {index + 1}"
                )
                key = f"package.{group_name}.{index}"
                if "value" in argument:
                    inputs.extend(cls._templated_value_inputs(key, argument))
                else:
                    inputs.append(cls._input_from_spec(key, label, argument))
        return inputs

    @classmethod
    def _templated_value_inputs(
        cls,
        key_prefix: str,
        spec: dict[str, Any],
    ) -> list[MCPMarketInput]:
        variables = spec.get("variables") or {}
        result: list[MCPMarketInput] = []
        for name in dict.fromkeys(_TEMPLATE_RE.findall(str(spec.get("value") or ""))):
            variable_spec = variables.get(name) if isinstance(variables, dict) else None
            if isinstance(variable_spec, dict) and "value" in variable_spec:
                continue
            input_spec = variable_spec if isinstance(variable_spec, dict) else spec
            key = f"{key_prefix}.variable.{name}"
            item = cls._input_from_spec(key, name, input_spec)
            result.append(
                MCPMarketInput(
                    key=item.key,
                    label=item.label,
                    description=item.description,
                    default=item.default,
                    required=True,
                    secret=item.secret,
                )
            )
        return result

    @staticmethod
    def _input_from_spec(key: str, label: str, spec: dict[str, Any]) -> MCPMarketInput:
        return MCPMarketInput(
            key=key,
            label=label,
            description=str(spec.get("description") or spec.get("placeholder") or ""),
            default=str(spec.get("default") or ""),
            required=bool(spec.get("isRequired")),
            secret=bool(spec.get("isSecret")),
        )

    @staticmethod
    def _validate_inputs(
        inputs: tuple[MCPMarketInput, ...],
        values: dict[str, str],
    ) -> None:
        missing = [
            item.label
            for item in inputs
            if item.required and not (values.get(item.key) or item.default).strip()
        ]
        if missing:
            raise ValueError(f"Required values are missing: {', '.join(missing)}")

    @classmethod
    def _build_remote_config(
        cls,
        remote: dict[str, Any],
        values: dict[str, str],
    ) -> dict[str, Any]:
        variables = remote.get("variables") or {}
        resolved_variables: dict[str, str] = {}
        if isinstance(variables, dict):
            for name, spec in variables.items():
                if not isinstance(spec, dict):
                    continue
                resolved_variables[name] = cls._resolve_spec_value(
                    spec,
                    values,
                    f"remote.variable.{name}",
                )

        for name in _TEMPLATE_RE.findall(str(remote.get("url") or "")):
            resolved_variables.setdefault(name, values.get(f"remote.variable.{name}", ""))

        url = cls._substitute(str(remote.get("url") or ""), resolved_variables)
        if not url.startswith(("http://", "https://")):
            raise ValueError("Registry returned an invalid remote URL")
        config: dict[str, Any] = {
            "type": "http" if remote.get("type") == "streamable-http" else "sse",
            "url": url,
        }

        headers: dict[str, str] = {}
        for header in remote.get("headers") or []:
            if not isinstance(header, dict) or not header.get("name"):
                continue
            name = str(header["name"])
            raw_value = cls._resolve_spec_value(
                header,
                values,
                f"remote.header.{name}",
            )
            value = cls._substitute(raw_value, resolved_variables)
            if value:
                headers[name] = value
        if headers:
            config["headers"] = headers
        return config

    @classmethod
    def _build_package_config(
        cls,
        package: dict[str, Any],
        values: dict[str, str],
    ) -> dict[str, Any]:
        registry_type = str(package.get("registryType") or "")
        command = "npx" if registry_type == "npm" else "uvx"

        args = cls._resolve_arguments(package, "runtimeArguments", values)
        if registry_type == "npm" and command == "npx" and "-y" not in args:
            args.insert(0, "-y")
        args.append(cls._package_identifier(package, registry_type))
        args.extend(cls._resolve_arguments(package, "packageArguments", values))

        config: dict[str, Any] = {"type": "stdio", "command": command, "args": args}
        env: dict[str, str] = {}
        for env_var in package.get("environmentVariables") or []:
            if not isinstance(env_var, dict) or not env_var.get("name"):
                continue
            name = str(env_var["name"])
            value = cls._resolve_spec_value(
                env_var,
                values,
                f"package.env.{name}",
            )
            if value:
                env[name] = value
        if env:
            config["env"] = env
        return config

    @classmethod
    def _resolve_arguments(
        cls,
        package: dict[str, Any],
        group_name: str,
        values: dict[str, str],
    ) -> list[str]:
        result: list[str] = []
        for index, argument in enumerate(package.get(group_name) or []):
            if not isinstance(argument, dict):
                continue
            value = cls._resolve_spec_value(
                argument,
                values,
                f"package.{group_name}.{index}",
            )
            if argument.get("type") == "named" and argument.get("name"):
                name = str(argument["name"])
                if value.lower() == "false":
                    continue
                result.append(name)
                if value and value.lower() != "true":
                    result.append(value)
            elif value:
                result.append(value)
        return result

    @classmethod
    def _resolve_spec_value(
        cls,
        spec: dict[str, Any],
        values: dict[str, str],
        key: str,
    ) -> str:
        if "value" in spec:
            raw_value = str(spec.get("value") or "")
            variables = spec.get("variables") or {}
            resolved: dict[str, str] = {}
            for name in _TEMPLATE_RE.findall(raw_value):
                variable_spec = (
                    variables.get(name) if isinstance(variables, dict) else None
                )
                if isinstance(variable_spec, dict) and "value" in variable_spec:
                    resolved[name] = str(variable_spec.get("value") or "")
                elif isinstance(variable_spec, dict):
                    resolved[name] = str(
                        values.get(f"{key}.variable.{name}")
                        or variable_spec.get("default")
                        or ""
                    )
                else:
                    resolved[name] = values.get(f"{key}.variable.{name}", "")
            return cls._substitute(raw_value, resolved)
        return str(values.get(key) or spec.get("default") or "")

    @staticmethod
    def _package_identifier(package: dict[str, Any], registry_type: str) -> str:
        identifier = str(package.get("identifier") or "")
        version = str(package.get("version") or "")
        if not version:
            return identifier
        separator = "@" if registry_type == "npm" else "=="
        suffix = f"{separator}{version}"
        return identifier if identifier.endswith(suffix) else f"{identifier}{suffix}"

    @staticmethod
    def _substitute(template: str, values: dict[str, str]) -> str:
        return _TEMPLATE_RE.sub(lambda match: values.get(match.group(1), match.group(0)), template)
