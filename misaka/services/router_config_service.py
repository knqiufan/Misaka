"""Router configuration service.

Manages multiple Claude Code Router configurations with
bidirectional binding between form fields and config JSON,
activation (writing to ~/.claude/settings.json), and
default config initialization.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import RouterConfig
    from misaka.services.cli_settings_service import CliSettingsService

logger = logging.getLogger(__name__)

# Mapping: form field name -> env var key in config_json
_FIELD_TO_ENV_KEY: dict[str, str] = {
    "main_model": "ANTHROPIC_MODEL",
    "haiku_model": "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "opus_model": "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "sonnet_model": "ANTHROPIC_DEFAULT_SONNET_MODEL",
}

_AGENT_TEAM_ENV_KEY = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"


class RouterConfigService:
    """Service for managing Claude Code Router configurations."""

    def __init__(
        self, db: DatabaseBackend, cli_settings_service: CliSettingsService
    ) -> None:
        self._db = db
        self._cli = cli_settings_service

    def get_all(self) -> list[RouterConfig]:
        return self._db.get_all_router_configs()

    def get(self, config_id: str) -> RouterConfig | None:
        return self._db.get_router_config(config_id)

    def get_active(self) -> RouterConfig | None:
        return self._db.get_active_router_config()

    def create(self, name: str, **kwargs: object) -> RouterConfig:
        return self._db.create_router_config(name, **kwargs)

    def update(self, config_id: str, **kwargs: object) -> RouterConfig | None:
        return self._db.update_router_config(config_id, **kwargs)

    def delete(self, config_id: str) -> bool:
        return self._db.delete_router_config(config_id)

    def activate(self, config_id: str) -> bool:
        """Activate a router config: write its config_json to settings.json."""
        config = self._db.get_router_config(config_id)
        if not config:
            return False

        try:
            data = json.loads(config.config_json)
        except (json.JSONDecodeError, TypeError):
            data = {}

        self._cli.write_settings(data)
        return self._db.activate_router_config(config_id)

    def sync_form_to_json(
        self, config_json: str, field_name: str, value: str | bool
    ) -> str:
        """Update config_json when a form field changes.

        Returns the updated config_json string.
        """
        try:
            data = json.loads(config_json)
        except (json.JSONDecodeError, TypeError):
            data = {}

        env = data.setdefault("env", {})

        if field_name == "agent_team":
            if value:
                env[_AGENT_TEAM_ENV_KEY] = "1"
            else:
                env.pop(_AGENT_TEAM_ENV_KEY, None)
        elif field_name in _FIELD_TO_ENV_KEY:
            env_key = _FIELD_TO_ENV_KEY[field_name]
            if value:
                env[env_key] = str(value)
            else:
                env.pop(env_key, None)

        return json.dumps(data, indent=2, ensure_ascii=False)

    def sync_json_to_form(self, config_json: str) -> dict[str, str | bool]:
        """Extract form field values from config JSON env section.

        Returns a dict with keys: main_model, haiku_model, opus_model,
        sonnet_model, agent_team.
        """
        try:
            data = json.loads(config_json)
        except (json.JSONDecodeError, TypeError):
            data = {}

        env = data.get("env", {})

        result: dict[str, str | bool] = {}
        for field_name, env_key in _FIELD_TO_ENV_KEY.items():
            result[field_name] = env.get(env_key, "")

        result["agent_team"] = env.get(_AGENT_TEAM_ENV_KEY) == "1"
        return result

    def ensure_default_config(self) -> None:
        """On first launch, create a Default config from current settings.json."""
        configs = self._db.get_all_router_configs()
        if configs:
            return

        settings = self._cli.read_settings()
        config_json = json.dumps(settings, indent=2, ensure_ascii=False) if settings else "{}"

        # Extract form fields from the existing settings
        form_vals = self.sync_json_to_form(config_json)

        self._db.create_router_config(
            name="Default",
            main_model=form_vals.get("main_model", ""),
            haiku_model=form_vals.get("haiku_model", ""),
            opus_model=form_vals.get("opus_model", ""),
            sonnet_model=form_vals.get("sonnet_model", ""),
            agent_team=form_vals.get("agent_team", False),
            config_json=config_json,
            is_active=1,
        )
        logger.info("Created default router config from ~/.claude/settings.json")
