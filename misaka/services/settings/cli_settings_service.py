"""Claude CLI settings service.

Reads and writes the ~/.claude/settings.json configuration file
used by the Claude Code CLI.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CliSettingsService:
    """Service for reading and writing ~/.claude/settings.json."""

    SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

    def read_settings(self) -> dict:
        """Read and return the current CLI settings.

        Returns an empty dict if the file doesn't exist or is invalid.
        """
        try:
            if not self.SETTINGS_PATH.exists():
                return {}
            text = self.SETTINGS_PATH.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            return {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read CLI settings: %s", exc)
            return {}

    def write_settings(self, data: dict) -> None:
        """Write settings to ~/.claude/settings.json.

        Creates the parent directory if it doesn't exist.

        Args:
            data: The settings dict to write.

        Raises:
            OSError: If the file cannot be written.
            TypeError: If data is not JSON-serializable.
        """
        self.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, indent=2, ensure_ascii=False)
        self.SETTINGS_PATH.write_text(text, encoding="utf-8")
        logger.info("CLI settings written to %s", self.SETTINGS_PATH)

    def get_value(self, key: str, default=None):
        """Get a specific setting value by key."""
        settings = self.read_settings()
        return settings.get(key, default)

    def set_value(self, key: str, value) -> None:
        """Set a specific setting value by key."""
        settings = self.read_settings()
        settings[key] = value
        self.write_settings(settings)

    def get_model_display_name(self, model_key: str) -> str:
        """Resolve model key (default/sonnet/opus/haiku) to display name.

        Reads from ~/.claude/settings.json env section. Returns 'Claude'
        when model_key is empty or unknown.
        """
        if not model_key:
            return "Claude"
        settings = self.read_settings()
        env = settings.get("env", {})
        if model_key == "default":
            main = env.get("ANTHROPIC_MODEL", "")
            return f"Default ({main})" if main else "Default"
        mapping = {
            "sonnet": str(env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "Sonnet")),
            "opus": str(env.get("ANTHROPIC_DEFAULT_OPUS_MODEL", "Opus")),
            "haiku": str(env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "Haiku")),
        }
        return mapping.get(model_key, "Claude")
