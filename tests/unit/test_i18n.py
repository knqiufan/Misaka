"""
Tests for the i18n (internationalization) module.
"""

from __future__ import annotations

import misaka.i18n as i18n


class TestI18n:

    def setup_method(self) -> None:
        """Reset i18n state before each test."""
        i18n.init("en")

    def test_init_loads_translations(self) -> None:
        """init() should load translation files without error."""
        i18n.init("en")
        assert i18n.get_locale() == "en"

    def test_init_with_invalid_locale_falls_back(self) -> None:
        """init() with an unsupported locale should fall back to default."""
        i18n.init("xx-XX")
        assert i18n.get_locale() == i18n.DEFAULT_LOCALE

    def test_basic_translation_en(self) -> None:
        """t() should return the English translation for a known key."""
        assert i18n.t("nav.chat") == "Chat"

    def test_basic_translation_zh_cn(self) -> None:
        """t() should return the Chinese translation after switching locale."""
        i18n.set_locale("zh-CN")
        assert i18n.t("nav.chat") == "聊天"

    def test_basic_translation_zh_tw(self) -> None:
        """t() should return the Traditional Chinese translation."""
        i18n.set_locale("zh-TW")
        assert i18n.t("nav.settings") == "設定"

    def test_fallback_to_key(self) -> None:
        """t() should return the key itself if not found in any locale."""
        assert i18n.t("nonexistent.key") == "nonexistent.key"

    def test_fallback_to_english(self) -> None:
        """t() should fall back to English if key missing in current locale."""
        # All locales have the same keys in our test data,
        # so we test the fallback mechanism by checking that English is used
        # when a key exists in English but the current locale dict is empty.
        # We simulate this by manually removing a key from zh-CN.
        original = i18n._translations.get("zh-CN", {}).copy()
        i18n._translations["zh-CN"] = {
            k: v for k, v in original.items() if k != "nav.chat"
        }
        i18n.set_locale("zh-CN")
        # Should fall back to English "Chat"
        assert i18n.t("nav.chat") == "Chat"
        # Restore
        i18n._translations["zh-CN"] = original

    def test_placeholder_substitution(self) -> None:
        """t() should substitute placeholders in the translation string."""
        result = i18n.t("update.available", version="1.1.0", current="1.0.25")
        assert "1.1.0" in result
        assert "1.0.25" in result

    def test_placeholder_missing_kwarg(self) -> None:
        """t() should not crash if a placeholder kwarg is missing."""
        # The template has {version} and {current} placeholders
        result = i18n.t("update.available")
        # Should return the template string with unresolved placeholders
        assert "version" in result or "update.available" in result

    def test_locale_switch(self) -> None:
        """set_locale() should switch the active locale."""
        i18n.set_locale("zh-CN")
        assert i18n.t("nav.chat") == "聊天"
        i18n.set_locale("en")
        assert i18n.t("nav.chat") == "Chat"

    def test_set_locale_ignores_invalid(self) -> None:
        """set_locale() should ignore unsupported locale codes."""
        i18n.set_locale("en")
        i18n.set_locale("invalid-locale")
        assert i18n.get_locale() == "en"

    def test_get_locale(self) -> None:
        """get_locale() should return the current locale."""
        i18n.set_locale("zh-TW")
        assert i18n.get_locale() == "zh-TW"

    def test_get_available_locales(self) -> None:
        """get_available_locales() should return the supported locales tuple."""
        locales = i18n.get_available_locales()
        assert "en" in locales
        assert "zh-CN" in locales
        assert "zh-TW" in locales

    def test_flatten_dict_simple(self) -> None:
        """_flatten_dict should flatten a simple nested dict."""
        result = i18n._flatten_dict({"a": {"b": "value"}})
        assert result == {"a.b": "value"}

    def test_flatten_dict_deep(self) -> None:
        """_flatten_dict should flatten deeply nested dicts."""
        result = i18n._flatten_dict({"a": {"b": {"c": "value"}}})
        assert result == {"a.b.c": "value"}

    def test_flatten_dict_multiple_keys(self) -> None:
        """_flatten_dict should handle multiple sibling keys."""
        result = i18n._flatten_dict({"a": {"x": "1", "y": "2"}, "b": "3"})
        assert result == {"a.x": "1", "a.y": "2", "b": "3"}

    def test_flatten_dict_empty(self) -> None:
        """_flatten_dict should return empty dict for empty input."""
        result = i18n._flatten_dict({})
        assert result == {}

    def test_nested_key_access(self) -> None:
        """t() should correctly access deeply nested translation keys."""
        assert i18n.t("settings.api_providers") == "API Providers"
        assert i18n.t("common.ok") == "OK"
        assert i18n.t("env_check.title") == "Environment Setup"

    def test_all_locales_have_same_keys(self) -> None:
        """All locale files should have the same set of translation keys."""
        i18n.init("en")
        en_keys = set(i18n._translations.get("en", {}).keys())
        zh_cn_keys = set(i18n._translations.get("zh-CN", {}).keys())
        zh_tw_keys = set(i18n._translations.get("zh-TW", {}).keys())

        assert en_keys == zh_cn_keys, (
            f"Key mismatch between en and zh-CN: "
            f"missing in zh-CN: {en_keys - zh_cn_keys}, "
            f"extra in zh-CN: {zh_cn_keys - en_keys}"
        )
        assert en_keys == zh_tw_keys, (
            f"Key mismatch between en and zh-TW: "
            f"missing in zh-TW: {en_keys - zh_tw_keys}, "
            f"extra in zh-TW: {zh_tw_keys - en_keys}"
        )

    def test_no_empty_translation_values(self) -> None:
        """No translation value should be empty string."""
        i18n.init("en")
        for locale in i18n.SUPPORTED_LOCALES:
            translations = i18n._translations.get(locale, {})
            for key, value in translations.items():
                assert value.strip() != "", (
                    f"Empty translation for key '{key}' in locale '{locale}'"
                )

    def test_placeholder_consistency(self) -> None:
        """Placeholders should be the same across all locales."""
        import re
        placeholder_re = re.compile(r"\{(\w+)\}")
        i18n.init("en")
        en_translations = i18n._translations.get("en", {})

        for locale in ("zh-CN", "zh-TW"):
            locale_translations = i18n._translations.get(locale, {})
            for key in en_translations:
                en_placeholders = set(placeholder_re.findall(en_translations[key]))
                if not en_placeholders:
                    continue
                locale_placeholders = set(
                    placeholder_re.findall(locale_translations.get(key, ""))
                )
                assert en_placeholders == locale_placeholders, (
                    f"Placeholder mismatch for key '{key}' in '{locale}': "
                    f"en has {en_placeholders}, {locale} has {locale_placeholders}"
                )

    def test_init_handles_malformed_json_file(self) -> None:
        """init() should handle a malformed JSON translation file gracefully."""
        import json
        from unittest.mock import patch, mock_open

        # Simulate a JSONDecodeError during file loading by patching json.load
        original_json_load = json.load
        call_count = 0

        def mock_json_load(f):
            nonlocal call_count
            call_count += 1
            # Let the third file (zh-TW) raise JSONDecodeError
            if call_count == 3:
                raise json.JSONDecodeError("bad json", "", 0)
            return original_json_load(f)

        with patch("json.load", side_effect=mock_json_load):
            i18n.init("en")

        # en and zh-CN should have loaded, zh-TW should be empty
        assert len(i18n._translations.get("en", {})) > 0
        assert len(i18n._translations.get("zh-CN", {})) > 0
        assert i18n._translations.get("zh-TW", {}) == {}

        # Re-init properly to not break other tests
        i18n.init("en")

    def test_t_with_non_string_format_value(self) -> None:
        """t() should handle non-string placeholder values."""
        result = i18n.t("update.available", version=123, current=456)
        assert "123" in result
        assert "456" in result

    def test_reinit_changes_locale(self) -> None:
        """Calling init() multiple times should update the locale."""
        i18n.init("en")
        assert i18n.get_locale() == "en"
        assert i18n.t("nav.chat") == "Chat"

        i18n.init("zh-CN")
        assert i18n.get_locale() == "zh-CN"
        assert i18n.t("nav.chat") == "聊天"

    def test_flatten_dict_non_string_values(self) -> None:
        """_flatten_dict should convert non-string values to strings."""
        result = i18n._flatten_dict({"a": {"b": 42, "c": True}})
        assert result == {"a.b": "42", "a.c": "True"}
