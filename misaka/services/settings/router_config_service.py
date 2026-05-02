"""Router configuration service.

Manages multiple Claude Code Router configurations with
bidirectional binding between form fields and config JSON,
activation (writing to ~/.claude/settings.json), default
config initialization, and API model detection.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import httpx

from misaka.db.models import ModelDetectionResult

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import ModelInfo, RouterConfig, RouterModel
    from misaka.services.settings.cli_settings_service import CliSettingsService

logger = logging.getLogger(__name__)

_DETECT_TIMEOUT = 15
_EMBED_KEYWORDS = ("embed",)
_RERANK_KEYWORDS = ("rerank", "ranker")

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
        elif field_name == "api_key":
            if value:
                env["ANTHROPIC_AUTH_TOKEN"] = str(value)
            else:
                env.pop("ANTHROPIC_AUTH_TOKEN", None)
        elif field_name == "base_url":
            if value:
                env["ANTHROPIC_BASE_URL"] = str(value)
            else:
                env.pop("ANTHROPIC_BASE_URL", None)
        elif field_name == "high_effort":
            if value:
                data["effortLevel"] = "high"
            else:
                data.pop("effortLevel", None)
        elif field_name == "disable_autoupdater":
            if value:
                env["DISABLE_AUTOUPDATER"] = "1"
            else:
                env.pop("DISABLE_AUTOUPDATER", None)
        elif field_name == "hide_attribution":
            if value:
                data["attribution"] = {"commit": "", "pr": ""}
            else:
                data.pop("attribution", None)
        elif field_name == "enable_tool_search":
            if value:
                env["ENABLE_TOOL_SEARCH"] = "true"
            else:
                env.pop("ENABLE_TOOL_SEARCH", None)
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
        result["api_key"] = env.get("ANTHROPIC_AUTH_TOKEN", "")
        result["base_url"] = env.get("ANTHROPIC_BASE_URL", "")
        result["high_effort"] = data.get("effortLevel") == "high"
        result["disable_autoupdater"] = env.get("DISABLE_AUTOUPDATER") == "1"
        result["hide_attribution"] = isinstance(data.get("attribution"), dict)
        result["enable_tool_search"] = env.get("ENABLE_TOOL_SEARCH") == "true"
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

    # ------------------------------------------------------------------
    # Model detection & management
    # ------------------------------------------------------------------

    async def detect_models(
        self, base_url: str, api_key: str,
    ) -> ModelDetectionResult:
        """Probe ``GET /v1/models`` and classify results by heuristic."""
        url = base_url.rstrip("/") + "/v1/models"
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with httpx.AsyncClient(timeout=_DETECT_TIMEOUT) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
        except httpx.TimeoutException:
            return ModelDetectionResult(error=f"Request timed out ({_DETECT_TIMEOUT}s)")
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code == 401:
                return ModelDetectionResult(
                    error="Authentication failed (401). Check your API key.",
                )
            if code == 403:
                return ModelDetectionResult(
                    error="Access forbidden (403). Check your API key permissions.",
                )
            return ModelDetectionResult(
                error=f"HTTP {code}: {exc.response.reason_phrase}",
            )
        except Exception as exc:  # noqa: BLE001
            return ModelDetectionResult(error=str(exc))

        raw_models: list[dict[str, Any]] = payload.get("data", [])
        return self._classify_models(raw_models)

    @staticmethod
    def _classify_models(raw_models: list[dict[str, Any]]) -> ModelDetectionResult:
        llm: list[str] = []
        embedding: list[str] = []
        reranker: list[str] = []

        for m in raw_models:
            model_id: str = m.get("id", "")
            if not model_id:
                continue
            lower_id = model_id.lower()
            if any(kw in lower_id for kw in _RERANK_KEYWORDS):
                reranker.append(model_id)
            elif any(kw in lower_id for kw in _EMBED_KEYWORDS):
                embedding.append(model_id)
            else:
                llm.append(model_id)

        llm.sort()
        embedding.sort()
        reranker.sort()
        return ModelDetectionResult(
            llm=llm, embedding=embedding, reranker=reranker,
            raw_models=raw_models,
        )

    def save_detected_models(
        self, config_id: str, models: list[dict[str, Any]],
    ) -> None:
        """Replace detected models for a router config (idempotent)."""
        self._db.save_router_models(config_id, models)

    def update_model_selection(
        self, model_id: str, is_selected: bool,
    ) -> None:
        self._db.update_router_model_selection(model_id, is_selected)

    def get_models_by_config(self, config_id: str) -> list[RouterModel]:
        return self._db.get_router_models(config_id)

    def get_available_embedding_models(self) -> list[ModelInfo]:
        return self._db.get_all_selected_models_by_type("embedding")

    def get_available_reranker_models(self) -> list[ModelInfo]:
        return self._db.get_all_selected_models_by_type("reranker")
