"""Tests for the Claude Code Router settings section."""

from __future__ import annotations

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
