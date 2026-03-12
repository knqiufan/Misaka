from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

from misaka.i18n import init, set_locale, t
from misaka.ui.pages.plugins_page import PluginsPage


def make_page(monkeypatch):
    monkeypatch.setattr(PluginsPage, "_build_ui", lambda self: None)
    return PluginsPage(state=SimpleNamespace(update=lambda: None), db=None)


class DummyPage:
    def __init__(self) -> None:
        self.dialog = None
        self.update_calls = 0

    def show_dialog(self, dialog) -> None:
        self.dialog = dialog

    def pop_dialog(self) -> None:
        self.dialog = None

    def update(self, *controls) -> None:
        self.update_calls += 1


def test_save_and_verify_mcp_config_writes_back_to_original_source(monkeypatch, tmp_path: Path) -> None:
    init("en")
    page = make_page(monkeypatch)
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings_path = settings_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote-api": {
                        "type": "http",
                        "url": "https://old.example.com/mcp",
                        "headers": {"Authorization": "Bearer old-token"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    page._mcp_configs = {
        "remote-api": {
            "type": "http",
            "url": "https://new.example.com/mcp",
            "headers": {"Authorization": "Bearer new-token"},
        }
    }
    page._mcp_config_sources = {"remote-api": settings_path}
    with patch("pathlib.Path.home", return_value=tmp_path):
        assert page._save_and_verify_mcp_config("remote-api") is True

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["mcpServers"]["remote-api"]["url"] == "https://new.example.com/mcp"
    assert saved["mcpServers"]["remote-api"]["headers"]["Authorization"] == "Bearer new-token"


def test_save_and_verify_mcp_config_fails_when_reloaded_config_differs(monkeypatch, tmp_path: Path) -> None:
    init("en")
    page = make_page(monkeypatch)
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings_path = settings_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote-api": {
                        "type": "http",
                        "url": "https://stale.example.com/mcp",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    page._mcp_configs = {
        "remote-api": {
            "type": "http",
            "url": "https://fresh.example.com/mcp",
        }
    }
    with patch("pathlib.Path.home", return_value=tmp_path):
        assert page._save_and_verify_mcp_config("remote-api") is False


def test_header_count_badge_is_localized(monkeypatch) -> None:
    init("en")
    page = make_page(monkeypatch)
    card = page._build_server_card(
        "remote-api",
        {
            "type": "http",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer t", "X-API-Key": "k"},
        },
    )

    title_row = card.content.controls[1].controls[0]
    badge_texts = []
    for control in title_row.controls[1:]:
        text = getattr(getattr(control, "content", None), "value", None)
        if text is None:
            nested_content = getattr(getattr(control, "content", None), "controls", [])
            for nested in nested_content:
                nested_text = getattr(nested, "value", None)
                if nested_text:
                    badge_texts.append(nested_text)
        else:
            badge_texts.append(text)

    assert "2 Headers" in badge_texts


def test_show_server_dialog_shows_headers_when_http_selected_from_event(monkeypatch) -> None:
    init("en")
    page = make_page(monkeypatch)
    dummy_page = DummyPage()

    page._show_server_dialog(dummy_page, mode="add")

    assert dummy_page.dialog is not None
    dialog_content = dummy_page.dialog.content
    basic_section, _, headers_section, _ = dialog_content.controls
    type_selector = basic_section.content.controls[3]  # Text, name_field, label, SegmentedButton
    headers_container = headers_section.content.controls[1]

    assert headers_section.visible is False
    assert headers_container.visible is False

    type_selector.selected = ["http"]
    type_selector.on_change(SimpleNamespace(control=type_selector, page=dummy_page))

    assert headers_section.visible is True
    assert headers_container.visible is True
    assert len(headers_container.controls) == 1


def test_is_sensitive_header_matches_authorization_prefix(monkeypatch) -> None:
    page = make_page(monkeypatch)

    assert page._is_sensitive_header("Authorization") is True
    assert page._is_sensitive_header("X-API-Key") is True
    assert page._is_sensitive_header("X-Custom-Header") is False


def test_plugins_translations_include_header_count_label() -> None:
    init("en")
    set_locale("en")

    assert t("plugins.header_count", count=2) == "2 Headers"
