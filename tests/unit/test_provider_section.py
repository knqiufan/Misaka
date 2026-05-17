"""Tests for the Claude Code Router settings section."""

from __future__ import annotations

import json
from types import SimpleNamespace

import flet as ft

from misaka.ui.settings.pages import provider_section


class _RouterService:
    def __init__(self) -> None:
        self.deleted_ids: list[str] = []

    def get_all(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                id="router-1",
                name="Test Router",
                main_model="claude-test",
                is_active=0,
            ),
        ]

    def delete(self, config_id: str) -> None:
        self.deleted_ids.append(config_id)


class _Page:
    def __init__(self) -> None:
        self.dialogs: list[ft.Control] = []

    def show_dialog(self, dialog: ft.Control) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        pass


class _State:
    def __init__(self, service: _RouterService, page: _Page) -> None:
        self.page = page
        self.updated = False
        self._service = service

    def get_service(self, name: str) -> _RouterService | None:
        if name == "router_config_service":
            return self._service
        return None

    def update(self) -> None:
        self.updated = True


class _SyncService:
    _env_keys = {
        "main_model": "ANTHROPIC_MODEL",
        "haiku_model": "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "opus_model": "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "sonnet_model": "ANTHROPIC_DEFAULT_SONNET_MODEL",
    }

    def sync_form_to_json(self, current_json: str, field_name: str, value: object) -> str:
        data = json.loads(current_json)
        env = data.setdefault("env", {})
        if field_name in self._env_keys:
            env[self._env_keys[field_name]] = str(value)
        return json.dumps(data)

    def sync_json_to_form(self, current_json: str) -> dict[str, str]:
        data = json.loads(current_json)
        env = data.get("env", {})
        return {
            field_name: env.get(env_key, "")
            for field_name, env_key in self._env_keys.items()
        }


def test_router_delete_click_opens_confirm_dialog_without_deleting() -> None:
    service = _RouterService()
    page = _Page()
    state = _State(service, page)
    router_list = ft.Column()

    provider_section.refresh_router_list(state, router_list)

    delete_button = _find_delete_button(router_list)
    assert delete_button is not None

    delete_button.on_click(SimpleNamespace())

    assert service.deleted_ids == []
    assert len(page.dialogs) == 1


def test_default_model_controls_allow_manual_text_input() -> None:
    fields = provider_section._create_form_fields(
        None,
        {"main_model": "manual-model"},
        "{}",
    )

    assert isinstance(fields.main_model, ft.TextField)
    assert fields.main_model.value == "manual-model"


def test_detected_llm_fills_active_model_field_and_syncs_json() -> None:
    service = _SyncService()
    fields = provider_section._create_form_fields(None, {}, '{"env": {}}')
    provider_section._wire_field_sync(service, fields)
    fields.active_model_field = "sonnet_model"

    provider_section._fill_active_model_field(service, fields, "custom-llm")

    assert fields.sonnet_model.value == "custom-llm"
    config_json = json.loads(fields.config_json.value or "{}")
    assert config_json["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "custom-llm"


def _find_delete_button(control: ft.Control) -> ft.IconButton | None:
    if isinstance(control, ft.IconButton) and control.icon == ft.Icons.DELETE:
        return control

    children = getattr(control, "controls", None)
    if children:
        for child in children:
            found = _find_delete_button(child)
            if found:
                return found

    content = getattr(control, "content", None)
    if content:
        return _find_delete_button(content)

    return None
