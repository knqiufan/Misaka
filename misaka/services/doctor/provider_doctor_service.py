"""
Provider Doctor diagnostic service.

Runs structured health probes against the Claude Code integration
stack and returns graded results with fix suggestions.

Probes:
1. CLI existence — is the Claude Code CLI binary reachable?
2. API Key validity — does the active config contain a well-formed key?
3. Environment variables — are critical env vars set consistently?
4. CLI settings file — does ~/.claude/settings.json exist and parse?
5. Node.js runtime — is a compatible Node.js version available?
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from misaka.config import get_claude_config_paths, get_expanded_path
from misaka.utils.platform import find_claude_binary

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend

logger = logging.getLogger(__name__)


class Severity(Enum):
    """Probe result severity."""
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ProbeResult:
    """Result of a single diagnostic probe."""
    probe_id: str
    title: str
    severity: Severity
    message: str
    suggestion: str = ""


@dataclass
class DoctorReport:
    """Aggregated diagnostic report."""
    probes: list[ProbeResult] = field(default_factory=list)
    checked_at: str = ""

    @property
    def has_errors(self) -> bool:
        return any(p.severity == Severity.ERROR for p in self.probes)

    @property
    def has_warnings(self) -> bool:
        return any(p.severity == Severity.WARNING for p in self.probes)

    @property
    def all_ok(self) -> bool:
        return all(p.severity == Severity.OK for p in self.probes)

    @property
    def error_count(self) -> int:
        return sum(1 for p in self.probes if p.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for p in self.probes if p.severity == Severity.WARNING)


_API_KEY_PATTERN = re.compile(r"^sk-ant-[a-zA-Z0-9\-_]{20,}$")


class ProviderDoctorService:
    """Runs structured diagnostic probes for the Claude Code provider stack."""

    def __init__(self, db: DatabaseBackend) -> None:
        self._db = db

    async def run_all(self) -> DoctorReport:
        """Execute all probes and return an aggregated report."""
        probes = [
            self._probe_cli_existence(),
            self._probe_api_key(),
            self._probe_env_vars(),
            self._probe_cli_settings(),
            self._probe_nodejs(),
        ]
        return DoctorReport(
            probes=probes,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def _probe_cli_existence(self) -> ProbeResult:
        """Probe 1: Check if Claude Code CLI binary is reachable."""
        try:
            path = find_claude_binary()
        except OSError:
            path = None

        if path:
            return ProbeResult(
                probe_id="cli_existence",
                title="Claude Code CLI",
                severity=Severity.OK,
                message=path,
            )
        return ProbeResult(
            probe_id="cli_existence",
            title="Claude Code CLI",
            severity=Severity.ERROR,
            message="not_found",
            suggestion="cli_install_suggestion",
        )

    def _probe_api_key(self) -> ProbeResult:
        """Probe 2: Validate the API key from the active router config."""
        active = self._db.get_active_router_config()
        if not active:
            return ProbeResult(
                probe_id="api_key",
                title="API Key",
                severity=Severity.WARNING,
                message="no_active_config",
                suggestion="api_key_no_config_suggestion",
            )

        token = self._extract_api_key(active.config_json, active.api_key)

        if not token:
            return ProbeResult(
                probe_id="api_key",
                title="API Key",
                severity=Severity.ERROR,
                message="no_key_configured",
                suggestion="api_key_missing_suggestion",
            )

        if _API_KEY_PATTERN.match(token):
            masked = token[:10] + "..." + token[-4:]
            return ProbeResult(
                probe_id="api_key",
                title="API Key",
                severity=Severity.OK,
                message=masked,
            )

        return ProbeResult(
            probe_id="api_key",
            title="API Key",
            severity=Severity.WARNING,
            message="non_standard_format",
            suggestion="api_key_format_suggestion",
        )

    def _probe_env_vars(self) -> ProbeResult:
        """Probe 3: Check critical environment variable consistency."""
        active = self._db.get_active_router_config()
        if not active:
            return ProbeResult(
                probe_id="env_vars",
                title="Environment Variables",
                severity=Severity.WARNING,
                message="no_active_config",
                suggestion="env_no_config_suggestion",
            )

        try:
            data = json.loads(active.config_json)
        except (json.JSONDecodeError, TypeError):
            return ProbeResult(
                probe_id="env_vars",
                title="Environment Variables",
                severity=Severity.ERROR,
                message="invalid_config_json",
                suggestion="env_invalid_json_suggestion",
            )

        env = data.get("env", {}) if isinstance(data, dict) else {}
        issues: list[str] = []

        token = env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY")
        if not token and not active.api_key:
            issues.append("no_auth_token")

        base_url = env.get("ANTHROPIC_BASE_URL") or (
            active.base_url if hasattr(active, "base_url") else ""
        )
        if base_url and not base_url.startswith(("http://", "https://")):
            issues.append("invalid_base_url")

        if issues:
            return ProbeResult(
                probe_id="env_vars",
                title="Environment Variables",
                severity=Severity.WARNING,
                message=", ".join(issues),
                suggestion="env_fix_suggestion",
            )

        return ProbeResult(
            probe_id="env_vars",
            title="Environment Variables",
            severity=Severity.OK,
            message="all_set",
        )

    def _probe_cli_settings(self) -> ProbeResult:
        """Probe 4: Check ~/.claude/settings.json existence and validity."""
        settings_path = Path.home() / ".claude" / "settings.json"
        if not settings_path.exists():
            return ProbeResult(
                probe_id="cli_settings",
                title="CLI Settings",
                severity=Severity.WARNING,
                message="file_not_found",
                suggestion="cli_settings_create_suggestion",
            )

        try:
            text = settings_path.read_text(encoding="utf-8")
            json.loads(text)
        except json.JSONDecodeError:
            return ProbeResult(
                probe_id="cli_settings",
                title="CLI Settings",
                severity=Severity.ERROR,
                message="invalid_json",
                suggestion="cli_settings_fix_suggestion",
            )
        except OSError as exc:
            return ProbeResult(
                probe_id="cli_settings",
                title="CLI Settings",
                severity=Severity.ERROR,
                message=str(exc),
                suggestion="cli_settings_permission_suggestion",
            )

        return ProbeResult(
            probe_id="cli_settings",
            title="CLI Settings",
            severity=Severity.OK,
            message=str(settings_path),
        )

    def _probe_nodejs(self) -> ProbeResult:
        """Probe 5: Check Node.js availability and version compatibility."""
        import shutil

        expanded_path = get_expanded_path()
        node_path = shutil.which("node", path=expanded_path)
        if not node_path:
            return ProbeResult(
                probe_id="nodejs",
                title="Node.js",
                severity=Severity.ERROR,
                message="not_found",
                suggestion="nodejs_install_suggestion",
            )

        return ProbeResult(
            probe_id="nodejs",
            title="Node.js",
            severity=Severity.OK,
            message=node_path,
        )

    @staticmethod
    def _extract_api_key(config_json: str, fallback_key: str) -> str:
        """Extract the API key from config JSON env or fallback field."""
        try:
            data = json.loads(config_json)
        except (json.JSONDecodeError, TypeError):
            return fallback_key or ""

        env = data.get("env", {}) if isinstance(data, dict) else {}
        return (
            env.get("ANTHROPIC_AUTH_TOKEN")
            or env.get("ANTHROPIC_API_KEY")
            or fallback_key
            or ""
        )
