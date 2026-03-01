"""Settings page.

Application settings including API provider management,
theme selection, permission mode, language selector, and
default model configuration.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

import misaka.i18n as i18n
from misaka.i18n import t
from misaka.ui.theme import (
    ERROR_RED,
    SUCCESS_GREEN,
    WARNING_AMBER,
    apply_theme,
    make_badge,
    make_button,
    make_form_dialog,
    make_icon_button,
    make_outlined_button,
    make_section_card,
    make_text_button,
    make_text_field,
)

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import RouterConfig
    from misaka.state import AppState


# Available permission modes (keys for i18n)
_PERMISSION_MODES = [
    ("default", "settings.perm_default", "settings.perm_default_desc"),
    ("acceptEdits", "settings.perm_accept_edits", "settings.perm_accept_edits_desc"),
    ("bypassPermissions", "settings.perm_bypass", "settings.perm_bypass_desc"),
]

# Available themes (keys for i18n)
_THEME_MODES = [
    ("system", "settings.theme_system", ft.Icons.BRIGHTNESS_AUTO),
    ("light", "settings.theme_light", ft.Icons.LIGHT_MODE),
    ("dark", "settings.theme_dark", ft.Icons.DARK_MODE),
]

# Available languages
_LANGUAGES = [
    ("zh-CN", "\u7b80\u4f53\u4e2d\u6587"),
    ("zh-TW", "\u7e41\u9ad4\u4e2d\u6587"),
    ("en", "English"),
]


class SettingsPage(ft.Column):
    """Application settings page with provider management, theme, and CLI settings."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend | None = None,
        on_theme_change: Callable[[str], None] | None = None,
        on_locale_change: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(
            spacing=0,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
        self.state = state
        self.db = db
        self._on_theme_change = on_theme_change
        self._on_locale_change = on_locale_change
        self._router_list: ft.Column | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        # Page header
        header = ft.Container(
            content=ft.Text(
                t("settings.title"),
                size=22,
                weight=ft.FontWeight.W_600,
            ),
            padding=ft.Padding.only(left=24, top=20, bottom=12),
        )

        # --- Appearance section ---
        appearance_section = self._build_appearance_section()

        # --- Permission mode section ---
        permission_section = self._build_permission_section()

        # --- Claude CLI Settings (settings.json) section ---
        cli_settings_section = self._build_cli_settings_section()

        # --- Claude Code update section ---
        claude_update_section = self._build_claude_update_section()

        # --- Misaka update section ---
        misaka_update_section = self._build_misaka_update_section()

        # --- Environment status section ---
        env_status_section = self._build_env_status_section()

        # --- Language section ---
        language_section = self._build_language_section()

        # --- About section ---
        about_section = self._build_about_section()

        self.controls = [
            header,
            self._wrap_card(appearance_section),
            self._wrap_card(permission_section),
            self._wrap_card(cli_settings_section),
            self._wrap_card(claude_update_section),
            self._wrap_card(misaka_update_section),
            self._wrap_card(env_status_section),
            self._wrap_card(language_section),
            self._wrap_card(about_section),
            ft.Container(height=16),
        ]

    @staticmethod
    def _wrap_card(content: ft.Control) -> ft.Control:
        """Wrap a section in a card-like container that fills the available width."""
        return make_section_card(content)

    @staticmethod
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

    @staticmethod
    def _make_compact_field(**kwargs) -> ft.TextField:
        """Create compact form field for dialog usage."""
        defaults = {
            "dense": True,
            "text_size": 12,
            "content_padding": ft.Padding.symmetric(horizontal=12, vertical=10),
        }
        defaults.update(kwargs)
        return make_text_field(**defaults)

    # ---------------------------------------------------------------
    # Appearance section
    # ---------------------------------------------------------------

    def _build_appearance_section(self) -> ft.Control:
        theme_buttons: list[ft.Control] = []
        use_white_active_text = self.state.theme_mode == "light"
        for mode, label_key, icon in _THEME_MODES:
            is_active = self.state.theme_mode == mode
            active_text_color = ft.Colors.WHITE if is_active and use_white_active_text else None
            btn = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(icon, size=18, color=active_text_color),
                        ft.Text(t(label_key), size=13, color=active_text_color),
                    ],
                    spacing=6,
                ),
                bgcolor=ft.Colors.PRIMARY if is_active else ft.Colors.TRANSPARENT,
                border=ft.Border.all(
                    1,
                    ft.Colors.PRIMARY if is_active else ft.Colors.OUTLINE,
                ),
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                on_click=lambda e, m=mode: self._change_theme(m),
                ink=True,
            )
            theme_buttons.append(btn)

        # --- Accent color selector ---
        accent_colors = [
            ("#6366f1", "Indigo"),
            ("#3b82f6", "Blue"),
            ("#10b981", "Emerald"),
            ("#f43f5e", "Rose"),
            ("#f59e0b", "Amber"),
            ("#8b5cf6", "Purple"),
            ("#14b8a6", "Teal"),
        ]
        current_accent = getattr(self.state, "accent_color", "#6366f1")
        color_circles: list[ft.Control] = []
        for hex_color, color_name in accent_colors:
            is_selected = current_accent == hex_color
            circle = ft.Container(
                width=28,
                height=28,
                bgcolor=hex_color,
                border_radius=14,
                border=ft.Border.all(
                    3 if is_selected else 1,
                    ft.Colors.ON_SURFACE if is_selected
                    else ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
                ),
                tooltip=color_name,
                on_click=lambda e, c=hex_color: self._change_accent_color(c),
                ink=True,
            )
            color_circles.append(circle)

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("settings.appearance"), size=16, weight=ft.FontWeight.W_600),
                    ft.Text(t("settings.appearance_desc"), size=12, opacity=0.6),
                    ft.Row(controls=theme_buttons, spacing=8),
                    ft.Text(t("settings.accent_color"), size=14, weight=ft.FontWeight.W_500),
                    ft.Text(t("settings.accent_color_desc"), size=12, opacity=0.6),
                    ft.Row(controls=color_circles, spacing=8),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _change_theme(self, mode: str) -> None:
        self.state.theme_mode = mode
        apply_theme(self.state.page, mode, self.state.accent_color)
        if self._on_theme_change:
            self._on_theme_change(mode)
        self._build_ui()
        self.state.update()

    def _change_accent_color(self, color: str) -> None:
        self.state.accent_color = color
        if self.db:
            self.db.set_setting("accent_color", color)
        apply_theme(self.state.page, self.state.theme_mode, color)
        self._build_ui()
        self.state.update()

    # ---------------------------------------------------------------
    # Permission section
    # ---------------------------------------------------------------

    def _build_permission_section(self) -> ft.Control:
        # Read current permission mode from settings
        current_mode = "default"
        if self.db:
            saved = self.db.get_setting("permission_mode")
            if saved:
                current_mode = saved

        mode_options: list[ft.Control] = []
        for mode_id, label_key, desc_key in _PERMISSION_MODES:
            tile = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Radio(value=mode_id, label=""),
                        ft.Column(
                            controls=[
                                ft.Text(t(label_key), size=13, weight=ft.FontWeight.W_500),
                                ft.Text(t(desc_key), size=11, opacity=0.6),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=0,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            )
            mode_options.append(tile)

        radio_group = ft.RadioGroup(
            value=current_mode,
            content=ft.Column(controls=mode_options, spacing=4),
            on_change=self._change_permission_mode,
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("settings.permission_mode"), size=16, weight=ft.FontWeight.W_600),
                    ft.Text(
                        t("settings.permission_mode_desc"),
                        size=12,
                        opacity=0.6,
                    ),
                    radio_group,
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _change_permission_mode(self, e: ft.ControlEvent) -> None:
        mode = e.data or e.control.value
        if mode and self.db:
            self.db.set_setting("permission_mode", mode)

    # ---------------------------------------------------------------
    # Claude Code Router section
    # ---------------------------------------------------------------

    def _build_cli_settings_section(self) -> ft.Control:
        """Build the Claude Code Router configuration section."""
        self._router_list = ft.Column(spacing=4)
        self._refresh_router_list()

        add_btn = make_button(
            t("settings.router_add"),
            icon=ft.Icons.ADD,
            on_click=self._show_add_router_dialog,
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
                    self._router_list,
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _get_router_service(self):
        if hasattr(self.state, "services") and self.state.services:
            return getattr(self.state.services, "router_config_service", None)
        return None

    def _refresh_router_list(self) -> None:
        if not hasattr(self, "_router_list") or not self._router_list:
            return
        svc = self._get_router_service()
        if not svc:
            return

        configs = svc.get_all()
        if not configs:
            self._router_list.controls = [
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

        self._router_list.controls = [
            self._build_router_card(c) for c in configs
        ]

    def _build_router_card(self, config: RouterConfig) -> ft.Control:
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
                                on_click=lambda e, cid=config.id: (
                                    self._activate_router(cid)
                                ),
                                visible=not is_active,
                            ) if not is_active else ft.Container(width=0),
                            make_icon_button(
                                ft.Icons.EDIT,
                                tooltip=t("common.edit"),
                                on_click=lambda e, c=config: (
                                    self._show_edit_router_dialog(c)
                                ),
                                icon_size=20,
                            ),
                            make_icon_button(
                                ft.Icons.DELETE,
                                tooltip=t("common.delete"),
                                icon_color=ERROR_RED,
                                on_click=lambda e, cid=config.id: (
                                    self._delete_router(cid)
                                ),
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

    def _show_add_router_dialog(self, e: ft.ControlEvent) -> None:
        self._show_router_form(e.page, config=None)

    def _show_edit_router_dialog(self, config: RouterConfig) -> None:
        if self.state.page:
            self._show_router_form(self.state.page, config=config)

    def _show_router_form(
        self, page: ft.Page, config: RouterConfig | None
    ) -> None:
        is_edit = config is not None
        svc = self._get_router_service()

        # Parse form values from config_json if editing
        form_vals: dict[str, str | bool] = {}
        if is_edit and config and svc:
            form_vals = svc.sync_json_to_form(config.config_json)

        # Default JSON for add mode: load current settings with env={}
        if not is_edit:
            cli_svc = getattr(self.state.services, "cli_settings_service", None) \
                if self.state.services else None
            if cli_svc:
                default_data = cli_svc.read_settings()
                default_data["env"] = {}
                default_json = json.dumps(default_data, indent=2, ensure_ascii=False)
            else:
                default_json = "{}"
        else:
            default_json = config.config_json if config else "{}"

        name_field = self._make_compact_field(
            label=t("settings.router_name"),
            value=config.name if config else "",
            autofocus=True,
        )
        api_key_field = self._make_compact_field(
            label=t("settings.router_api_key"),
            value=(
                str(form_vals.get("api_key", ""))
                or (config.api_key if config else "")
            ),
            password=True,
            can_reveal_password=True,
        )
        base_url_field = self._make_compact_field(
            label=t("settings.router_base_url"),
            value=(
                str(form_vals.get("base_url", ""))
                or (config.base_url if config else "")
            ),
        )
        main_model_field = self._make_compact_field(
            label=t("settings.router_main_model"),
            value=str(form_vals.get("main_model", "")),
        )
        haiku_model_field = self._make_compact_field(
            label=t("settings.router_haiku_model"),
            value=str(form_vals.get("haiku_model", "")),
        )
        opus_model_field = self._make_compact_field(
            label=t("settings.router_opus_model"),
            value=str(form_vals.get("opus_model", "")),
        )
        sonnet_model_field = self._make_compact_field(
            label=t("settings.router_sonnet_model"),
            value=str(form_vals.get("sonnet_model", "")),
        )
        agent_team_switch = ft.Switch(
            label=t("settings.router_agent_team"),
            value=bool(form_vals.get("agent_team", False)),
        )
        config_json_field = self._make_compact_field(
            hint_text=t("settings.router_config_json"),
            value=default_json,
            multiline=True,
            min_lines=4,
            max_lines=10,
            text_size=12,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        )

        model_fields = {
            "main_model": main_model_field,
            "haiku_model": haiku_model_field,
            "opus_model": opus_model_field,
            "sonnet_model": sonnet_model_field,
        }

        def on_model_field_change(field_name: str):
            def handler(e: ft.ControlEvent):
                if not svc:
                    return
                current_json = config_json_field.value or "{}"
                updated = svc.sync_form_to_json(
                    current_json, field_name, e.data or ""
                )
                config_json_field.value = updated
                config_json_field.update()
            return handler

        for fname, fld in model_fields.items():
            fld.on_change = on_model_field_change(fname)

        def on_api_key_change(e: ft.ControlEvent):
            if not svc:
                return
            current_json = config_json_field.value or "{}"
            updated = svc.sync_form_to_json(
                current_json, "api_key", e.data or ""
            )
            config_json_field.value = updated
            config_json_field.update()

        def on_base_url_change(e: ft.ControlEvent):
            if not svc:
                return
            current_json = config_json_field.value or "{}"
            updated = svc.sync_form_to_json(
                current_json, "base_url", e.data or ""
            )
            config_json_field.value = updated
            config_json_field.update()

        api_key_field.on_change = on_api_key_change
        base_url_field.on_change = on_base_url_change

        def on_agent_team_change(e: ft.ControlEvent):
            if not svc:
                return
            current_json = config_json_field.value or "{}"
            updated = svc.sync_form_to_json(
                current_json, "agent_team", agent_team_switch.value
            )
            config_json_field.value = updated
            config_json_field.update()

        agent_team_switch.on_change = on_agent_team_change

        def on_json_change(e: ft.ControlEvent):
            if not svc:
                return
            raw = config_json_field.value or "{}"
            vals = svc.sync_json_to_form(raw)
            for fname, fld in model_fields.items():
                new_val = str(vals.get(fname, ""))
                if fld.value != new_val:
                    fld.value = new_val
                    fld.update()
            new_agent = bool(vals.get("agent_team", False))
            if agent_team_switch.value != new_agent:
                agent_team_switch.value = new_agent
                agent_team_switch.update()
            new_api_key = str(vals.get("api_key", ""))
            if api_key_field.value != new_api_key:
                api_key_field.value = new_api_key
                api_key_field.update()
            new_base_url = str(vals.get("base_url", ""))
            if base_url_field.value != new_base_url:
                base_url_field.value = new_base_url
                base_url_field.update()

        config_json_field.on_blur = on_json_change

        def save(ev):
            name = (name_field.value or "").strip()
            if not name:
                return

            kwargs = {
                "api_key": api_key_field.value or "",
                "base_url": base_url_field.value or "",
                "main_model": main_model_field.value or "",
                "haiku_model": haiku_model_field.value or "",
                "opus_model": opus_model_field.value or "",
                "sonnet_model": sonnet_model_field.value or "",
                "agent_team": agent_team_switch.value or False,
                "config_json": config_json_field.value or "{}",
            }

            if is_edit and config and svc:
                svc.update(config.id, name=name, **kwargs)
            elif svc:
                svc.create(name, **kwargs)

            self._refresh_router_list()
            page.pop_dialog()
            self.state.update()

        form_groups = [
            self._build_form_group(
                t("settings.router_title"),
                [name_field, api_key_field, base_url_field],
            ),
            self._build_form_group(
                t("settings.default_model"),
                [
                    main_model_field,
                    sonnet_model_field,
                    opus_model_field,
                    haiku_model_field,
                    agent_team_switch,
                ],
            ),
            self._build_form_group(
                t("settings.router_config_json"),
                [config_json_field],
            ),
        ]

        dialog = make_form_dialog(
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
                height=430,
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
        page.show_dialog(dialog)

    def _activate_router(self, config_id: str) -> None:
        svc = self._get_router_service()
        if not svc:
            return
        svc.activate(config_id)
        self._refresh_router_list()
        self.state.update()

    def _delete_router(self, config_id: str) -> None:
        svc = self._get_router_service()
        if not svc:
            return
        svc.delete(config_id)
        self._refresh_router_list()
        self.state.update()

    # ---------------------------------------------------------------
    # Language section
    # ---------------------------------------------------------------

    def _build_language_section(self) -> ft.Control:
        current_locale = getattr(self.state, "locale", "zh-CN")
        use_white_active_text = self.state.theme_mode == "light"

        lang_buttons: list[ft.Control] = []
        for locale_code, locale_label in _LANGUAGES:
            is_active = current_locale == locale_code
            active_text_color = ft.Colors.WHITE if is_active and use_white_active_text else None
            btn = ft.Container(
                content=ft.Text(locale_label, size=13, color=active_text_color),
                bgcolor=ft.Colors.PRIMARY if is_active else ft.Colors.TRANSPARENT,
                border=ft.Border.all(
                    1,
                    ft.Colors.PRIMARY if is_active else ft.Colors.OUTLINE,
                ),
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                on_click=lambda e, loc=locale_code: self._change_language(loc),
                ink=True,
            )
            lang_buttons.append(btn)

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("settings.language"), size=16, weight=ft.FontWeight.W_600),
                    ft.Text(t("settings.language_desc"), size=12, opacity=0.6),
                    ft.Row(controls=lang_buttons, spacing=8),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _change_language(self, locale: str) -> None:
        """Handle language selection change."""
        # Persist preference
        if self.db:
            self.db.set_setting("language", locale)
        # Update i18n
        i18n.set_locale(locale)
        # Update state
        self.state.locale = locale
        # Notify app shell to rebuild
        if self._on_locale_change:
            self._on_locale_change(locale)
        else:
            # Fallback: rebuild just this page
            self._build_ui()
            self.state.update()

    # ---------------------------------------------------------------
    # Claude Code update section
    # ---------------------------------------------------------------

    def _build_claude_update_section(self) -> ft.Control:
        """Build the Claude Code version check & update section."""
        result = self.state.update_check_result
        is_checking = getattr(self, "_update_checking", False)
        is_updating = self.state.update_in_progress
        update_msg = getattr(self, "_update_progress_msg", "")

        current = result.current_version if result else None
        latest = result.latest_version if result else None
        has_update = result.update_available if result else False

        version_rows = self._build_version_info_rows(
            current, latest, has_update, update_msg,
        )
        action_btn = self._build_update_action_button(
            is_checking, is_updating, has_update,
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                t("settings.claude_update"),
                                size=16,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Container(expand=True),
                            action_btn,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        t("settings.claude_update_desc"),
                        size=12,
                        opacity=0.6,
                    ),
                    *version_rows,
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _build_version_info_rows(
        self,
        current: str | None,
        latest: str | None,
        has_update: bool,
        update_msg: str,
    ) -> list[ft.Control]:
        """Build rows showing current/latest version and status badge."""
        rows: list[ft.Control] = []

        if current:
            rows.append(
                ft.Text(
                    f"{t('settings.current_version')}: {current}",
                    size=13,
                    opacity=0.8,
                ),
            )

        if latest:
            status_badge = self._make_version_status_badge(has_update)
            rows.append(
                ft.Row(
                    controls=[
                        ft.Text(
                            f"{t('settings.latest_version')}: {latest}",
                            size=13,
                            opacity=0.8,
                        ),
                        status_badge,
                    ],
                    spacing=8,
                ),
            )

        if update_msg:
            rows.append(ft.Text(update_msg, size=12, opacity=0.6))

        return rows

    @staticmethod
    def _make_version_status_badge(has_update: bool) -> ft.Control:
        if has_update:
            return make_badge(
                t("settings.update_available"),
                bgcolor=WARNING_AMBER,
            )
        return make_badge(
            t("settings.up_to_date"),
            bgcolor=SUCCESS_GREEN,
            icon=ft.Icons.CHECK_CIRCLE,
        )

    def _build_update_action_button(
        self,
        is_checking: bool,
        is_updating: bool,
        has_update: bool,
    ) -> ft.Control:
        """Build the check/update action button with loading state."""
        if is_checking or is_updating:
            label = t("settings.checking") if is_checking else t("update.updating")
            return ft.Row(
                controls=[
                    ft.ProgressRing(width=16, height=16, stroke_width=2),
                    ft.Text(label, size=12, opacity=0.7),
                ],
                spacing=6,
            )

        if has_update:
            return make_button(
                t("update.update_now"),
                icon=ft.Icons.SYSTEM_UPDATE,
                on_click=self._handle_perform_update,
            )

        return make_outlined_button(
            t("settings.check_update"),
            icon=ft.Icons.REFRESH,
            on_click=self._handle_check_update,
        )

    def _handle_check_update(self, e: ft.ControlEvent) -> None:
        """Trigger async update check via page.run_task."""
        if not e.page:
            return
        self._update_checking = True
        self._build_ui()
        self.state.update()
        e.page.run_task(self._do_check_update)

    async def _do_check_update(self) -> None:
        svc = self._get_update_service()
        if svc:
            self.state.update_check_result = await svc.check_for_update()
        self._update_checking = False
        self._build_ui()
        self.state.update()

    def _handle_perform_update(self, e: ft.ControlEvent) -> None:
        if not e.page:
            return
        self.state.update_in_progress = True
        self._update_progress_msg = ""
        self._build_ui()
        self.state.update()
        e.page.run_task(self._do_perform_update)

    async def _do_perform_update(self) -> None:
        svc = self._get_update_service()
        if not svc:
            self.state.update_in_progress = False
            self._build_ui()
            self.state.update()
            return

        def on_progress(msg: str) -> None:
            self._update_progress_msg = msg

        success = await svc.perform_update(on_progress=on_progress)
        self.state.update_in_progress = False
        if success:
            self.state.update_check_result = await svc.check_for_update()
        self._build_ui()
        self.state.update()

    def _get_update_service(self):
        if hasattr(self.state, "services") and self.state.services:
            return getattr(self.state.services, "update_check_service", None)
        return None

    # ---------------------------------------------------------------
    # Environment status section
    # ---------------------------------------------------------------

    def _build_env_status_section(self) -> ft.Control:
        """Build the environment status check section."""
        result = self.state.env_check_result
        is_checking = getattr(self, "_env_checking", False)

        tool_rows = self._build_tool_status_rows(result)
        header_btn = self._build_env_header_button(is_checking)

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                t("settings.env_status"),
                                size=16,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Container(expand=True),
                            header_btn,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        t("settings.env_status_desc"),
                        size=12,
                        opacity=0.6,
                    ),
                    ft.Column(controls=tool_rows, spacing=8),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _build_env_header_button(self, is_checking: bool) -> ft.Control:
        if is_checking:
            return ft.Row(
                controls=[
                    ft.ProgressRing(width=16, height=16, stroke_width=2),
                    ft.Text(t("settings.checking"), size=12, opacity=0.7),
                ],
                spacing=6,
            )
        return make_outlined_button(
            t("settings.recheck"),
            icon=ft.Icons.REFRESH,
            on_click=self._handle_env_recheck,
        )

    def _build_tool_status_rows(self, result) -> list[ft.Control]:
        if not result:
            return [
                ft.Text(
                    t("settings.checking"),
                    size=12,
                    italic=True,
                    opacity=0.5,
                )
            ]

        rows: list[ft.Control] = []
        for tool in result.tools:
            rows.append(self._build_tool_status_card(tool))
        return rows

    def _build_tool_status_card(self, tool) -> ft.Control:
        """Build a single tool status row with icon, name, version, and action."""
        is_installed = tool.is_installed
        installing_tool = getattr(self, "_env_installing_tool", None)
        is_installing = installing_tool == tool.name

        status_icon = ft.Icon(
            ft.Icons.CHECK_CIRCLE if is_installed else ft.Icons.CANCEL,
            color=SUCCESS_GREEN if is_installed else ERROR_RED,
            size=22,
        )

        version_text = f"v{tool.version}" if tool.version else t("env_check.not_installed")

        right_widget = self._build_tool_action_widget(
            tool, is_installed, is_installing,
        )

        return ft.Container(
            content=ft.Row(
                controls=[
                    status_icon,
                    ft.Column(
                        controls=[
                            ft.Text(
                                tool.name,
                                size=13,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(version_text, size=11, opacity=0.6),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    right_widget,
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=12,
            border=ft.Border.all(
                1,
                SUCCESS_GREEN if is_installed
                else ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
        )

    def _build_tool_action_widget(
        self, tool, is_installed: bool, is_installing: bool,
    ) -> ft.Control:
        if is_installed:
            return make_badge(t("env_check.installed"), bgcolor=SUCCESS_GREEN)
        if is_installing:
            return ft.Row(
                controls=[
                    ft.ProgressRing(width=14, height=14, stroke_width=2),
                    ft.Text(t("env_check.installing"), size=11, opacity=0.7),
                ],
                spacing=6,
            )
        return make_button(
            t("env_check.install"),
            icon=ft.Icons.DOWNLOAD,
            on_click=lambda e, name=tool.name: self._handle_env_install(e, name),
        )

    def _handle_env_recheck(self, e: ft.ControlEvent) -> None:
        if not e.page:
            return
        self._env_checking = True
        self._build_ui()
        self.state.update()
        e.page.run_task(self._do_env_recheck)

    async def _do_env_recheck(self) -> None:
        svc = self._get_env_service()
        if svc:
            self.state.env_check_result = await svc.check_all()
        self._env_checking = False
        self._build_ui()
        self.state.update()

    def _handle_env_install(self, e: ft.ControlEvent, tool_name: str) -> None:
        if not e.page:
            return
        self._env_installing_tool = tool_name
        self._build_ui()
        self.state.update()
        e.page.run_task(lambda: self._do_env_install(tool_name))

    async def _do_env_install(self, tool_name: str) -> None:
        svc = self._get_env_service()
        if svc:
            await svc.install_tool(tool_name)
            self.state.env_check_result = await svc.check_all()
        self._env_installing_tool = None
        self._build_ui()
        self.state.update()

    def _get_env_service(self):
        if hasattr(self.state, "services") and self.state.services:
            return getattr(self.state.services, "env_check_service", None)
        return None

    # ---------------------------------------------------------------
    # Misaka update section
    # ---------------------------------------------------------------

    def _build_misaka_update_section(self) -> ft.Control:
        """Build the Misaka version info and update check section."""
        from misaka import __version__

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                t("settings.misaka_update"),
                                size=16,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Container(expand=True),
                            make_outlined_button(
                                t("settings.check_update"),
                                icon=ft.Icons.REFRESH,
                                on_click=self._handle_misaka_update_check,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        t("settings.misaka_update_desc"),
                        size=12,
                        opacity=0.6,
                    ),
                    ft.Text(
                        f"{t('settings.misaka_version')}: {__version__}",
                        size=13,
                        opacity=0.8,
                    ),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _handle_misaka_update_check(self, e: ft.ControlEvent) -> None:
        """Show a placeholder snackbar for Misaka update check."""
        if not e.page:
            return
        e.page.open(
            ft.SnackBar(
                content=ft.Text(t("settings.update_not_configured")),
                duration=3000,
            )
        )

    # ---------------------------------------------------------------
    # About section
    # ---------------------------------------------------------------

    def _build_about_section(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("settings.about"), size=16, weight=ft.FontWeight.W_600),
                    ft.Text(
                        t("settings.about_app"),
                        size=13,
                    ),
                    ft.Text(
                        t("settings.about_desc"),
                        size=12,
                        opacity=0.6,
                    ),
                ],
                spacing=8,
                expand=True,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
            expand=True,
        )

    def refresh(self) -> None:
        """Rebuild the settings page."""
        self._build_ui()
