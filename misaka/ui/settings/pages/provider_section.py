"""Router / provider configuration section for the Settings page."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    ERROR_RED,
    SUCCESS_GREEN,
    make_badge,
    make_button,
    make_form_dialog,
    make_icon_button,
    make_outlined_button,
    make_text_button,
    make_text_field,
)

if TYPE_CHECKING:
    from misaka.db.models import RouterConfig
    from misaka.state import AppState


def _make_compact_field(**kwargs) -> ft.TextField:
    """Create compact form field for dialog usage."""
    defaults = {
        "dense": True,
        "text_size": 12,
        "content_padding": ft.Padding.symmetric(horizontal=12, vertical=10),
    }
    defaults.update(kwargs)
    return make_text_field(**defaults)


def _build_form_group(title: str, controls: list[ft.Control]) -> ft.Control:
    """Build a soft card group used inside modern form dialogs."""
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(title, size=12, weight=ft.FontWeight.W_600, opacity=0.78),
                ft.Column(
                    controls=controls,
                    spacing=8,
                    tight=False,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ],
            spacing=8,
            tight=True,
        ),
        width=None,
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border_radius=12,
        bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
    )


def _get_router_service(state: AppState):
    return state.get_service("router_config_service")


def build_router_section(
    state: AppState,
    router_list: ft.Column,
    on_add_click: Callable[[ft.ControlEvent], None],
) -> ft.Control:
    """Build the Claude Code Router configuration section."""
    refresh_router_list(state, router_list)

    add_btn = make_button(
        t("settings.router_add"),
        icon=ft.Icons.ADD,
        on_click=on_add_click,
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            t("settings.router_title"),
                            size=16,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Container(expand=True),
                        add_btn,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    t("settings.router_desc"),
                    size=12,
                    opacity=0.6,
                ),
                router_list,
            ],
            spacing=12,
        ),
        padding=ft.Padding.symmetric(horizontal=24, vertical=16),
    )


def refresh_router_list(state: AppState, router_list: ft.Column) -> None:
    """Reload all router configs into the list column."""
    svc = _get_router_service(state)
    if not svc:
        return

    configs = svc.get_all()
    if not configs:
        router_list.controls = [
            ft.Container(
                content=ft.Text(
                    t("settings.router_no_configs"),
                    italic=True,
                    size=12,
                    opacity=0.5,
                ),
                padding=12,
            )
        ]
        return

    router_list.controls = [
        _build_router_card(
            config,
            on_activate=lambda cid: activate_router(state, cid, router_list),
            on_edit=lambda c: show_edit_router_dialog(state, c, router_list),
            on_delete=lambda cid: delete_router(state, cid, router_list),
        )
        for config in configs
    ]


def _build_router_card(
    config: RouterConfig,
    on_activate: Callable[[str], None],
    on_edit: Callable[[RouterConfig], None],
    on_delete: Callable[[str], None],
) -> ft.Control:
    is_active = config.is_active == 1

    status_badge = make_badge(
        t("settings.router_in_use"),
        bgcolor=SUCCESS_GREEN,
    ) if is_active else ft.Container(width=0, height=0)

    model_info = config.main_model or ""
    if model_info:
        model_info = f"Model: {model_info}"

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text(
                                    config.name,
                                    size=14,
                                    weight=ft.FontWeight.W_500,
                                ),
                                status_badge,
                            ],
                            spacing=8,
                        ),
                        ft.Text(
                            model_info if model_info else config.name,
                            size=11,
                            opacity=0.6,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Row(
                    controls=[
                        make_outlined_button(
                            t("settings.router_enable"),
                            on_click=lambda e, cid=config.id: on_activate(cid),
                            visible=not is_active,
                        ) if not is_active else ft.Container(width=0),
                        make_icon_button(
                            ft.Icons.EDIT,
                            tooltip=t("common.edit"),
                            on_click=lambda e, c=config: on_edit(c),
                            icon_size=20,
                        ),
                        make_icon_button(
                            ft.Icons.DELETE,
                            tooltip=t("common.delete"),
                            icon_color=ERROR_RED,
                            on_click=lambda e, cid=config.id: on_delete(cid),
                            icon_size=20,
                        ),
                    ],
                    spacing=0,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=14,
        border_radius=12,
        border=ft.Border.all(
            1,
            SUCCESS_GREEN if is_active
            else ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        ),
    )


# ------------------------------------------------------------------
# Router CRUD helpers
# ------------------------------------------------------------------

def activate_router(
    state: AppState, config_id: str, router_list: ft.Column,
) -> None:
    svc = _get_router_service(state)
    if not svc:
        return
    svc.activate(config_id)
    refresh_router_list(state, router_list)
    state.update()


def delete_router(
    state: AppState, config_id: str, router_list: ft.Column,
) -> None:
    svc = _get_router_service(state)
    if not svc:
        return
    svc.delete(config_id)
    refresh_router_list(state, router_list)
    state.update()


def show_edit_router_dialog(
    state: AppState,
    config: RouterConfig,
    router_list: ft.Column,
) -> None:
    if state.page:
        show_router_form(state, state.page, config, router_list)


def show_router_form(
    state: AppState,
    page: ft.Page,
    config: RouterConfig | None,
    router_list: ft.Column,
) -> None:
    """Show the add/edit router dialog."""
    is_edit = config is not None
    svc = _get_router_service(state)

    form_vals = _parse_form_values(svc, config, is_edit)
    default_json = _get_default_json(state, config, is_edit)

    fields = _create_form_fields(config, form_vals, default_json)
    _wire_field_sync(svc, fields)

    def save(ev):
        _save_router(
            svc, config, is_edit,
            fields=fields,
            page=page,
            state=state,
            router_list=router_list,
        )

    form_groups = _build_dialog_form_groups(fields)
    dialog = _build_router_dialog(is_edit, form_groups, page, save)
    page.show_dialog(dialog)


# ------------------------------------------------------------------
# Internal helpers for show_router_form
# ------------------------------------------------------------------

class _FormFields:
    """Simple container for the form field references."""

    __slots__ = (
        "name", "api_key", "base_url",
        "main_model", "haiku_model", "opus_model", "sonnet_model",
        "agent_team_switch", "high_effort_switch",
        "disable_autoupdater_switch", "hide_attribution_switch",
        "enable_tool_search_switch", "config_json",
    )


def _parse_form_values(svc, config, is_edit: bool) -> dict:
    if is_edit and config and svc:
        return svc.sync_json_to_form(config.config_json)
    return {}


def _get_default_json(state: AppState, config, is_edit: bool) -> str:
    if not is_edit:
        cli_svc = state.get_service("cli_settings_service")
        if cli_svc:
            default_data = cli_svc.read_settings()
            default_data["env"] = {}
            return json.dumps(default_data, indent=2, ensure_ascii=False)
        return "{}"
    return config.config_json if config else "{}"


def _create_form_fields(config, form_vals: dict, default_json: str) -> _FormFields:
    f = _FormFields()
    f.name = _make_compact_field(
        label=t("settings.router_name"),
        value=config.name if config else "",
        autofocus=True,
    )
    f.api_key = _make_compact_field(
        label=t("settings.router_api_key"),
        value=(
            str(form_vals.get("api_key", ""))
            or (config.api_key if config else "")
        ),
        password=True,
        can_reveal_password=True,
    )
    f.base_url = _make_compact_field(
        label=t("settings.router_base_url"),
        value=(
            str(form_vals.get("base_url", ""))
            or (config.base_url if config else "")
        ),
    )
    f.main_model = _make_compact_field(
        label=t("settings.router_main_model"),
        value=str(form_vals.get("main_model", "")),
    )
    f.haiku_model = _make_compact_field(
        label=t("settings.router_haiku_model"),
        value=str(form_vals.get("haiku_model", "")),
    )
    f.opus_model = _make_compact_field(
        label=t("settings.router_opus_model"),
        value=str(form_vals.get("opus_model", "")),
    )
    f.sonnet_model = _make_compact_field(
        label=t("settings.router_sonnet_model"),
        value=str(form_vals.get("sonnet_model", "")),
    )
    f.agent_team_switch = ft.Switch(
        value=bool(form_vals.get("agent_team", False)),
        scale=0.7,
    )
    f.high_effort_switch = ft.Switch(
        value=bool(form_vals.get("high_effort", False)),
        scale=0.7,
    )
    f.disable_autoupdater_switch = ft.Switch(
        value=bool(form_vals.get("disable_autoupdater", False)),
        scale=0.7,
    )
    f.hide_attribution_switch = ft.Switch(
        value=bool(form_vals.get("hide_attribution", False)),
        scale=0.7,
    )
    f.enable_tool_search_switch = ft.Switch(
        value=bool(form_vals.get("enable_tool_search", False)),
        scale=0.7,
    )
    f.config_json = _make_compact_field(
        hint_text=t("settings.router_config_json"),
        value=default_json,
        multiline=True,
        min_lines=4,
        max_lines=10,
        text_size=12,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
    )
    return f


def _wire_field_sync(svc, fields: _FormFields) -> None:
    """Wire bi-directional sync between form fields and the JSON textarea."""
    model_fields = {
        "main_model": fields.main_model,
        "haiku_model": fields.haiku_model,
        "opus_model": fields.opus_model,
        "sonnet_model": fields.sonnet_model,
    }

    def on_model_field_change(field_name: str):
        def handler(e: ft.ControlEvent):
            if not svc:
                return
            current_json = fields.config_json.value or "{}"
            updated = svc.sync_form_to_json(current_json, field_name, e.data or "")
            fields.config_json.value = updated
            fields.config_json.update()
        return handler

    for fname, fld in model_fields.items():
        fld.on_change = on_model_field_change(fname)

    def on_api_key_change(e: ft.ControlEvent):
        if not svc:
            return
        current_json = fields.config_json.value or "{}"
        updated = svc.sync_form_to_json(current_json, "api_key", e.data or "")
        fields.config_json.value = updated
        fields.config_json.update()

    def on_base_url_change(e: ft.ControlEvent):
        if not svc:
            return
        current_json = fields.config_json.value or "{}"
        updated = svc.sync_form_to_json(current_json, "base_url", e.data or "")
        fields.config_json.value = updated
        fields.config_json.update()

    fields.api_key.on_change = on_api_key_change
    fields.base_url.on_change = on_base_url_change

    def on_agent_team_change(e: ft.ControlEvent):
        if not svc:
            return
        current_json = fields.config_json.value or "{}"
        updated = svc.sync_form_to_json(
            current_json, "agent_team", fields.agent_team_switch.value,
        )
        fields.config_json.value = updated
        fields.config_json.update()

    fields.agent_team_switch.on_change = on_agent_team_change

    switch_field_bindings = {
        "high_effort": fields.high_effort_switch,
        "disable_autoupdater": fields.disable_autoupdater_switch,
        "hide_attribution": fields.hide_attribution_switch,
        "enable_tool_search": fields.enable_tool_search_switch,
    }

    def on_switch_change(field_name: str, switch: ft.Switch):
        def handler(e: ft.ControlEvent):
            if not svc:
                return
            current_json = fields.config_json.value or "{}"
            updated = svc.sync_form_to_json(
                current_json, field_name, switch.value,
            )
            fields.config_json.value = updated
            fields.config_json.update()
        return handler

    for sw_name, sw_ctrl in switch_field_bindings.items():
        sw_ctrl.on_change = on_switch_change(sw_name, sw_ctrl)

    def on_json_change(e: ft.ControlEvent):
        if not svc:
            return
        raw = fields.config_json.value or "{}"
        vals = svc.sync_json_to_form(raw)
        for fname, fld in model_fields.items():
            new_val = str(vals.get(fname, ""))
            if fld.value != new_val:
                fld.value = new_val
                fld.update()
        new_agent = bool(vals.get("agent_team", False))
        if fields.agent_team_switch.value != new_agent:
            fields.agent_team_switch.value = new_agent
            fields.agent_team_switch.update()
        new_api_key = str(vals.get("api_key", ""))
        if fields.api_key.value != new_api_key:
            fields.api_key.value = new_api_key
            fields.api_key.update()
        new_base_url = str(vals.get("base_url", ""))
        if fields.base_url.value != new_base_url:
            fields.base_url.value = new_base_url
            fields.base_url.update()
        for sw_name, sw_ctrl in switch_field_bindings.items():
            new_sw = bool(vals.get(sw_name, False))
            if sw_ctrl.value != new_sw:
                sw_ctrl.value = new_sw
                sw_ctrl.update()

    fields.config_json.on_blur = on_json_change


def _save_router(
    svc,
    config,
    is_edit: bool,
    *,
    fields: _FormFields,
    page: ft.Page,
    state: AppState,
    router_list: ft.Column,
) -> None:
    name = (fields.name.value or "").strip()
    if not name:
        return

    kwargs = {
        "api_key": fields.api_key.value or "",
        "base_url": fields.base_url.value or "",
        "main_model": fields.main_model.value or "",
        "haiku_model": fields.haiku_model.value or "",
        "opus_model": fields.opus_model.value or "",
        "sonnet_model": fields.sonnet_model.value or "",
        "agent_team": fields.agent_team_switch.value or False,
        "config_json": fields.config_json.value or "{}",
    }

    if is_edit and config and svc:
        svc.update(config.id, name=name, **kwargs)
    elif svc:
        svc.create(name, **kwargs)

    refresh_router_list(state, router_list)
    page.pop_dialog()
    state.update()


def _make_switch_tile(label: str, switch: ft.Switch) -> ft.Container:
    """Build a compact clickable tile: label on the left, mini switch on the right."""
    def _toggle(e: ft.ControlEvent):
        switch.value = not switch.value
        switch.update()
        if switch.on_change:
            switch.on_change(e)

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Text(label, size=12, expand=True, no_wrap=True),
                switch,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=8,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)),
        bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
        on_click=_toggle,
    )


def _build_switch_grid(switch_items: list[tuple[str, ft.Switch]]) -> ft.Control:
    """Lay out switch tiles in a responsive wrap of fixed-width chips."""
    tiles = [_make_switch_tile(label, sw) for label, sw in switch_items]

    rows: list[ft.Control] = []
    for i in range(0, len(tiles), 2):
        pair = tiles[i:i + 2]
        row_controls = [ft.Container(content=tile, expand=True) for tile in pair]
        if len(row_controls) == 1:
            row_controls.append(ft.Container(expand=True))
        rows.append(ft.Row(controls=row_controls, spacing=8))

    return ft.Column(controls=rows, spacing=6, tight=True)


def _build_dialog_form_groups(fields: _FormFields) -> list[ft.Control]:
    switch_items: list[tuple[str, ft.Switch]] = [
        (t("settings.router_agent_team"), fields.agent_team_switch),
        (t("settings.router_high_effort"), fields.high_effort_switch),
        (t("settings.router_disable_autoupdater"), fields.disable_autoupdater_switch),
        (t("settings.router_hide_attribution"), fields.hide_attribution_switch),
        (t("settings.router_enable_tool_search"), fields.enable_tool_search_switch),
    ]

    return [
        _build_form_group(
            t("settings.router_title"),
            [fields.name, fields.api_key, fields.base_url],
        ),
        _build_form_group(
            t("settings.default_model"),
            [
                fields.main_model,
                fields.sonnet_model,
                fields.opus_model,
                fields.haiku_model,
            ],
        ),
        _build_form_group(
            t("settings.router_advanced_options"),
            [_build_switch_grid(switch_items)],
        ),
        _build_form_group(
            t("settings.router_config_json"),
            [fields.config_json],
        ),
    ]


def _build_router_dialog(
    is_edit: bool,
    form_groups: list[ft.Control],
    page: ft.Page,
    save: Callable,
) -> ft.Control:
    return make_form_dialog(
        title=(
            t("settings.router_edit") if is_edit
            else t("settings.router_add")
        ),
        content=ft.Column(
            controls=form_groups,
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            tight=False,
            height=500,
        ),
        subtitle=t("settings.router_desc"),
        icon=ft.Icons.ROUTE_ROUNDED,
        width=640,
        actions=[
            make_text_button(
                t("common.cancel"),
                on_click=lambda ev: page.pop_dialog(),
            ),
            make_button(t("common.save"), on_click=save),
        ],
    )
