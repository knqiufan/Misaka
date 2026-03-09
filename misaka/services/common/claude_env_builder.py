"""
Claude CLI environment builder.

Constructs the subprocess environment dictionary for the Claude CLI,
including PATH expansion, Git Bash discovery, and router-based
credential injection.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from misaka.config import IS_WINDOWS, get_expanded_path
from misaka.utils.platform import find_git_bash

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import RouterConfig


_CLAUDE_ENV_KEYS = (
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
)


def _sanitize_env_value(value: str) -> str:
    """Remove null bytes and control characters that cause spawn errors."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)


def _sanitize_env(env: dict[str, str]) -> dict[str, str]:
    """Sanitize all values in an env dict for subprocess safety."""
    return {
        k: _sanitize_env_value(v)
        for k, v in env.items()
        if isinstance(v, str)
    }


def build_claude_env(db: DatabaseBackend) -> dict[str, str]:
    """Build the subprocess environment for the Claude CLI."""
    env: dict[str, str] = {k: v for k, v in os.environ.items() if isinstance(v, str)}

    home = str(Path.home())
    env.setdefault("HOME", home)
    env.setdefault("USERPROFILE", home)
    env["PATH"] = get_expanded_path()

    # Skip SDK version check to avoid spawning an extra subprocess
    # (which flashes a console window on Windows when packaged as GUI exe).
    # Must also set in os.environ because the SDK checks os.environ directly,
    # not the env dict passed via options.
    os.environ.setdefault("CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK", "1")
    env.setdefault("CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK", "1")

    if IS_WINDOWS and "CLAUDE_CODE_GIT_BASH_PATH" not in env:
        git_bash = find_git_bash()
        if git_bash:
            env["CLAUDE_CODE_GIT_BASH_PATH"] = git_bash

    active_router = db.get_active_router_config()
    _clear_claude_env(env)
    if active_router:
        _apply_router_env(env, active_router)
    else:
        _apply_legacy_env(env, db)

    return _sanitize_env(env)


def _clear_claude_env(env: dict[str, str]) -> None:
    """Remove Claude-specific env keys before applying active config."""
    for key in _CLAUDE_ENV_KEYS:
        env.pop(key, None)


def _parse_router_env(config_json: str) -> dict[str, str]:
    """Extract the env mapping from router config JSON."""
    try:
        data = json.loads(config_json)
    except (json.JSONDecodeError, TypeError):
        return {}

    raw_env = data.get("env", {}) if isinstance(data, dict) else {}
    if not isinstance(raw_env, dict):
        return {}
    return {k: v for k, v in raw_env.items() if isinstance(k, str) and isinstance(v, str)}


def _apply_router_env(env: dict[str, str], router: RouterConfig) -> None:
    """Overlay active router configuration onto *env*."""
    router_env = _parse_router_env(router.config_json)
    for key, value in router_env.items():
        if value == "":
            env.pop(key, None)
        else:
            env[key] = value

    token = env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY") or router.api_key
    if token:
        env["ANTHROPIC_AUTH_TOKEN"] = token
        env["ANTHROPIC_API_KEY"] = token

    _set_if_missing(env, "ANTHROPIC_BASE_URL", router.base_url)
    _set_if_missing(env, "ANTHROPIC_MODEL", router.main_model)
    _set_if_missing(env, "ANTHROPIC_DEFAULT_HAIKU_MODEL", router.haiku_model)
    _set_if_missing(env, "ANTHROPIC_DEFAULT_OPUS_MODEL", router.opus_model)
    _set_if_missing(env, "ANTHROPIC_DEFAULT_SONNET_MODEL", router.sonnet_model)
    if "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" not in env and router.agent_team:
        env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"


def _set_if_missing(env: dict[str, str], key: str, value: Any) -> None:
    """Set an env key when it is currently missing and value is non-empty."""
    if key not in env and isinstance(value, str) and value:
        env[key] = value


def _apply_legacy_env(env: dict[str, str], db: DatabaseBackend) -> None:
    """Apply legacy API token settings when no router config is active."""
    legacy_token = db.get_setting("anthropic_auth_token")
    legacy_base = db.get_setting("anthropic_base_url")
    if legacy_token:
        env["ANTHROPIC_AUTH_TOKEN"] = legacy_token
        env["ANTHROPIC_API_KEY"] = legacy_token
    if legacy_base:
        env["ANTHROPIC_BASE_URL"] = legacy_base


def resolve_script_from_cmd(cmd_path: str) -> str | None:
    """Parse a Windows .cmd wrapper to extract the real .js script path.

    npm installs CLI tools as .cmd wrappers on Windows that cannot be
    spawned without ``shell=True``. This extracts the underlying .js
    script path so it can be passed to the SDK directly.
    """
    try:
        content = Path(cmd_path).read_text(encoding="utf-8", errors="ignore")
        cmd_dir = str(Path(cmd_path).parent)

        patterns = [
            r'"%~dp0\\([^"]*claude[^"]*\.js)"',
            r"%~dp0\\(\S*claude\S*\.js)",
            r'"%dp0%\\([^"]*claude[^"]*\.js)"',
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                resolved = os.path.normpath(os.path.join(cmd_dir, match.group(1)))
                if os.path.isfile(resolved):
                    return resolved
    except OSError:
        pass
    return None
