"""
Internationalization (i18n) module for Misaka.

Provides a simple, synchronous translation lookup system.
Translation files are JSON dictionaries with dotted key paths.
"""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Supported locales
SUPPORTED_LOCALES = ("en", "zh-CN", "zh-TW")
DEFAULT_LOCALE = "zh-CN"

# Module-level singleton state
_current_locale: str = DEFAULT_LOCALE
_translations: dict[str, dict[str, str]] = {}
_fallback_translations: dict[str, str] = {}


def init(locale: str = DEFAULT_LOCALE) -> None:
    """Initialize the i18n system by loading translation files.

    Should be called once at startup, after reading the user's
    language preference from settings.

    Args:
        locale: The locale code to use ("en", "zh-CN", "zh-TW").
    """
    global _current_locale, _translations, _fallback_translations
    _current_locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE

    i18n_dir = Path(__file__).parent

    # Load all locale files
    for loc in SUPPORTED_LOCALES:
        file_name = loc.replace("-", "_") + ".json"  # "zh-CN" -> "zh_CN.json"
        file_path = i18n_dir / file_name
        if file_path.exists():
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                _translations[loc] = _flatten_dict(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load i18n file %s: %s", file_path, exc)
                _translations[loc] = {}
        else:
            _translations[loc] = {}

    # Set fallback to English
    _fallback_translations = _translations.get("en", {})


def set_locale(locale: str) -> None:
    """Change the current locale at runtime.

    Does NOT reload files; assumes init() was already called.
    """
    global _current_locale
    if locale in SUPPORTED_LOCALES:
        _current_locale = locale


def get_locale() -> str:
    """Return the current locale code."""
    return _current_locale


def get_available_locales() -> tuple[str, ...]:
    """Return the tuple of supported locale codes."""
    return SUPPORTED_LOCALES


def t(key: str, **kwargs: Any) -> str:
    """Translate a key to the current locale.

    Supports placeholder substitution: t("hello", name="World") ->
    "Hello, {name}" becomes "Hello, World"

    Falls back to English if key not found in current locale.
    Falls back to the key itself if not found in any locale.

    Args:
        key: Dotted key path, e.g. "nav.chat", "settings.title"
        **kwargs: Placeholder values for string formatting
    """
    translations = _translations.get(_current_locale, {})
    text = translations.get(key) or _fallback_translations.get(key) or key

    if kwargs:
        with contextlib.suppress(KeyError, IndexError):
            text = text.format(**kwargs)

    return text


def _flatten_dict(d: dict, prefix: str = "") -> dict[str, str]:
    """Flatten a nested dict into dotted key paths.

    {"nav": {"chat": "Chat"}} -> {"nav.chat": "Chat"}
    """
    result: dict[str, str] = {}
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten_dict(v, full_key))
        else:
            result[full_key] = str(v)
    return result
