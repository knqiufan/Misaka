"""
Claude CLI environment builder.

Constructs the subprocess environment dictionary for the Claude CLI,
including PATH expansion, Git Bash discovery, and API provider
credential injection.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from misaka.config import IS_WINDOWS, get_expanded_path
from misaka.utils.platform import find_git_bash

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import ApiProvider


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


def build_claude_env(
    db: DatabaseBackend,
    provider: ApiProvider | None = None,
) -> dict[str, str]:
    """Build the subprocess environment for the Claude CLI.

    Starts with ``os.environ``, overlays provider config, and expands PATH.
    """
    env: dict[str, str] = {k: v for k, v in os.environ.items() if isinstance(v, str)}

    home = str(Path.home())
    env.setdefault("HOME", home)
    env.setdefault("USERPROFILE", home)
    env["PATH"] = get_expanded_path()

    if IS_WINDOWS and "CLAUDE_CODE_GIT_BASH_PATH" not in env:
        git_bash = find_git_bash()
        if git_bash:
            env["CLAUDE_CODE_GIT_BASH_PATH"] = git_bash

    if provider and provider.api_key:
        _apply_provider_env(env, provider)
    else:
        _apply_legacy_env(env, db)

    return _sanitize_env(env)


def _apply_provider_env(env: dict[str, str], provider: ApiProvider) -> None:
    """Overlay provider credentials onto *env*."""
    for key in [k for k in env if k.startswith("ANTHROPIC_")]:
        del env[key]

    env["ANTHROPIC_AUTH_TOKEN"] = provider.api_key
    env["ANTHROPIC_API_KEY"] = provider.api_key
    if provider.base_url:
        env["ANTHROPIC_BASE_URL"] = provider.base_url

    for key, value in provider.parse_extra_env().items():
        if value == "":
            env.pop(key, None)
        else:
            env[key] = value


def _apply_legacy_env(env: dict[str, str], db: DatabaseBackend) -> None:
    """Apply legacy API token settings when no provider is active."""
    legacy_token = db.get_setting("anthropic_auth_token")
    legacy_base = db.get_setting("anthropic_base_url")
    if legacy_token:
        env["ANTHROPIC_AUTH_TOKEN"] = legacy_token
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
