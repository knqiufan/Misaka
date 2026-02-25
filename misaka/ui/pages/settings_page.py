"""Settings page.

Application settings including API provider management,
theme selection, permission mode, language selector, and
default model configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import flet as ft

import misaka.i18n as i18n
from misaka.i18n import t
from misaka.ui.theme import make_text_field, make_dropdown

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import ApiProvider
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
        self._providers: list[ApiProvider] = []
        self._provider_list: ft.Column | None = None
        self._cli_json_field: ft.TextField | None = None
        self._cli_settings_original: dict = {}
        self._build_ui()

    def _build_ui(self) -> None:
        # Load providers from DB
        if self.db:
            self._providers = self.db.get_all_providers()

        # Page header
        header = ft.Container(
            content=ft.Text(t("settings.title"), size=24, weight=ft.FontWeight.BOLD),
            padding=ft.Padding.only(left=24, top=20, bottom=12),
        )

        # --- API Providers section ---
        provider_section = self._build_provider_section()

        # --- Appearance section ---
        appearance_section = self._build_appearance_section()

        # --- Permission mode section ---
        permission_section = self._build_permission_section()

        # --- Claude Code CLI section ---
        cli_section = self._build_cli_section()

        # --- Claude CLI Settings (settings.json) section ---
        cli_settings_section = self._build_cli_settings_section()

        # --- Claude Code update section ---
        claude_update_section = self._build_claude_update_section()

        # --- Environment status section ---
        env_status_section = self._build_env_status_section()

        # --- Language section ---
        language_section = self._build_language_section()

        # --- About section ---
        about_section = self._build_about_section()

        self.controls = [
            header,
            self._wrap_card(provider_section),
            self._wrap_card(appearance_section),
            self._wrap_card(permission_section),
            self._wrap_card(cli_section),
            self._wrap_card(cli_settings_section),
            self._wrap_card(claude_update_section),
            self._wrap_card(env_status_section),
            self._wrap_card(language_section),
            self._wrap_card(about_section),
            ft.Container(height=16),
        ]

    @staticmethod
    def _wrap_card(content: ft.Control) -> ft.Control:
        """Wrap a section in a card-like container that fills the available width."""
        return ft.Container(
            content=content,
            margin=ft.Margin.symmetric(horizontal=16, vertical=4),
            border_radius=8,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
        )

    # ---------------------------------------------------------------
    # Provider section
    # ---------------------------------------------------------------

    def _build_provider_section(self) -> ft.Control:
        self._provider_list = ft.Column(spacing=4)
        self._refresh_provider_list()

        add_btn = ft.Button(
            content=t("settings.add_provider"),
            icon=ft.Icons.ADD,
            on_click=self._show_add_provider_dialog,
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                t("settings.api_providers"),
                                size=18,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Container(expand=True),
                            add_btn,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        t("settings.api_providers_desc"),
                        size=12,
                        opacity=0.6,
                    ),
                    self._provider_list,
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _refresh_provider_list(self) -> None:
        if not self._provider_list:
            return
        if not self._providers:
            self._provider_list.controls = [
                ft.Container(
                    content=ft.Text(
                        t("settings.no_providers"),
                        italic=True,
                        size=12,
                        opacity=0.5,
                    ),
                    padding=12,
                )
            ]
            return

        self._provider_list.controls = [
            self._build_provider_card(p) for p in self._providers
        ]

    def _build_provider_card(self, provider: ApiProvider) -> ft.Control:
        is_active = provider.is_active == 1

        status_badge = ft.Container(
            content=ft.Text(
                t("settings.active") if is_active else t("settings.inactive"),
                size=10,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE if is_active else ft.Colors.ON_SURFACE_VARIANT,
            ),
            bgcolor=ft.Colors.GREEN if is_active else ft.Colors.GREY,
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        )

        # Mask API key
        masked_key = ""
        if provider.api_key:
            if len(provider.api_key) > 8:
                masked_key = provider.api_key[:4] + "..." + provider.api_key[-4:]
            else:
                masked_key = "***"

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        provider.name,
                                        size=14,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    status_badge,
                                ],
                                spacing=8,
                            ),
                            ft.Text(
                                f"{provider.provider_type} | {masked_key or t('common.no_key')}",
                                size=11,
                                opacity=0.6,
                            ),
                            ft.Text(
                                provider.base_url or t("common.default_url"),
                                size=11,
                                opacity=0.4,
                            ) if provider.base_url else ft.Container(height=0),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.POWER_SETTINGS_NEW,
                                icon_color=ft.Colors.GREEN if not is_active else ft.Colors.GREY,
                                tooltip=t("settings.activate") if not is_active else t("settings.deactivate"),
                                on_click=lambda e, pid=provider.id: self._toggle_provider(pid),
                                icon_size=20,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.EDIT,
                                tooltip=t("settings.edit"),
                                on_click=lambda e, p=provider: self._show_edit_provider_dialog(p),
                                icon_size=20,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE,
                                tooltip=t("settings.delete"),
                                icon_color=ft.Colors.ERROR,
                                on_click=lambda e, pid=provider.id: self._delete_provider(pid),
                                icon_size=20,
                            ),
                        ],
                        spacing=0,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=8,
            border=ft.Border.all(1, ft.Colors.OUTLINE),
        )

    def _show_add_provider_dialog(self, e: ft.ControlEvent) -> None:
        self._show_provider_form(e.page, provider=None)

    def _show_edit_provider_dialog(self, provider: ApiProvider) -> None:
        if self.state.page:
            self._show_provider_form(self.state.page, provider=provider)

    def _show_provider_form(self, page: ft.Page, provider: ApiProvider | None) -> None:
        is_edit = provider is not None

        name_field = make_text_field(
            label=t("settings.provider_name"),
            value=provider.name if provider else "",
            autofocus=True,
        )
        type_field = make_dropdown(
            label=t("settings.provider_type"),
            value=provider.provider_type if provider else "anthropic",
            options=[
                ft.dropdown.Option("anthropic"),
                ft.dropdown.Option("openrouter"),
                ft.dropdown.Option("bedrock"),
                ft.dropdown.Option("vertex"),
                ft.dropdown.Option("custom"),
            ],
        )
        key_field = make_text_field(
            label=t("settings.api_key"),
            value=provider.api_key if provider else "",
            password=True,
            can_reveal_password=True,
        )
        url_field = make_text_field(
            label=t("settings.base_url"),
            value=provider.base_url if provider else "",
        )
        env_field = make_text_field(
            label=t("settings.extra_env"),
            value=provider.extra_env if provider and provider.extra_env != "{}" else "",
            multiline=True,
            min_lines=2,
            max_lines=4,
        )
        notes_field = make_text_field(
            label=t("settings.notes"),
            value=provider.notes if provider else "",
        )

        def save(ev):
            name = (name_field.value or "").strip()
            if not name:
                return

            kwargs = {
                "provider_type": type_field.value or "anthropic",
                "api_key": key_field.value or "",
                "base_url": url_field.value or "",
                "extra_env": env_field.value or "{}",
                "notes": notes_field.value or "",
            }

            if is_edit and provider and self.db:
                self.db.update_provider(provider.id, name=name, **kwargs)
            elif self.db:
                self.db.create_provider(name=name, **kwargs)

            # Reload
            if self.db:
                self._providers = self.db.get_all_providers()
            self._refresh_provider_list()
            page.pop_dialog()
            self.state.update()

        dialog = ft.AlertDialog(
            title=ft.Text(t("settings.edit_provider") if is_edit else t("settings.add_provider")),
            content=ft.Column(
                controls=[name_field, type_field, key_field, url_field, env_field, notes_field],
                spacing=12,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                width=400,
            ),
            actions=[
                ft.TextButton(t("settings.cancel"), on_click=lambda ev: page.pop_dialog()),
                ft.Button(t("settings.save"), on_click=save),
            ],
        )
        page.show_dialog(dialog)

    def _toggle_provider(self, provider_id: str) -> None:
        if not self.db:
            return
        provider = self.db.get_provider(provider_id)
        if provider and provider.is_active == 1:
            self.db.deactivate_all_providers()
        else:
            self.db.activate_provider(provider_id)
        self._providers = self.db.get_all_providers()
        self._refresh_provider_list()
        self.state.update()

    def _delete_provider(self, provider_id: str) -> None:
        if not self.db:
            return
        self.db.delete_provider(provider_id)
        self._providers = self.db.get_all_providers()
        self._refresh_provider_list()
        self.state.update()

    # ---------------------------------------------------------------
    # Appearance section
    # ---------------------------------------------------------------

    def _build_appearance_section(self) -> ft.Control:
        theme_buttons: list[ft.Control] = []
        for mode, label_key, icon in _THEME_MODES:
            is_active = self.state.theme_mode == mode
            btn = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(icon, size=18),
                        ft.Text(t(label_key), size=13),
                    ],
                    spacing=6,
                ),
                bgcolor=ft.Colors.PRIMARY if is_active else ft.Colors.TRANSPARENT,
                border=ft.Border.all(
                    1,
                    ft.Colors.PRIMARY if is_active else ft.Colors.OUTLINE,
                ),
                border_radius=8,
                padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                on_click=lambda e, m=mode: self._change_theme(m),
                ink=True,
            )
            theme_buttons.append(btn)

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("settings.appearance"), size=18, weight=ft.FontWeight.W_500),
                    ft.Text(t("settings.appearance_desc"), size=12, opacity=0.6),
                    ft.Row(controls=theme_buttons, spacing=8),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _change_theme(self, mode: str) -> None:
        self.state.theme_mode = mode
        if self._on_theme_change:
            self._on_theme_change(mode)
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
                    ft.Text(t("settings.permission_mode"), size=18, weight=ft.FontWeight.W_500),
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
    # CLI section
    # ---------------------------------------------------------------

    def _build_cli_section(self) -> ft.Control:
        # Default working directory
        current_dir = ""
        if self.db:
            current_dir = self.db.get_setting("default_working_directory") or ""

        dir_field = make_text_field(
            label=t("settings.default_working_dir"),
            value=current_dir,
            hint_text=t("settings.default_working_dir_hint"),
            on_change=self._save_working_dir,
        )

        # Default model
        current_model = ""
        if self.db:
            current_model = self.db.get_setting("default_model") or ""

        model_dropdown = make_dropdown(
            label=t("settings.default_model"),
            value=current_model or "sonnet",
            options=[
                ft.dropdown.Option(key="sonnet", text="Sonnet 4.5"),
                ft.dropdown.Option(key="opus", text="Opus 4.6"),
                ft.dropdown.Option(key="haiku", text="Haiku 4.5"),
            ],
            on_select=self._save_default_model,
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("settings.claude_code"), size=18, weight=ft.FontWeight.W_500),
                    ft.Text(
                        t("settings.claude_code_desc"),
                        size=12,
                        opacity=0.6,
                    ),
                    dir_field,
                    model_dropdown,
                ],
                spacing=12,
                expand=True,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
            expand=True,
        )

    def _save_working_dir(self, e: ft.ControlEvent) -> None:
        if self.db and e.data is not None:
            self.db.set_setting("default_working_directory", e.data)

    def _save_default_model(self, e: ft.ControlEvent) -> None:
        model = e.data or e.control.value
        if self.db and model:
            self.db.set_setting("default_model", model)

    # ---------------------------------------------------------------
    # CLI Settings section (~/.claude/settings.json)
    # ---------------------------------------------------------------

    def _build_cli_settings_section(self) -> ft.Control:
        """Build the Claude CLI settings.json editor section."""
        import json

        cli_svc = None
        if hasattr(self.state, "services") and self.state.services:
            cli_svc = getattr(self.state.services, "cli_settings_service", None)

        settings_data = cli_svc.read_settings() if cli_svc else {}
        self._cli_settings_original = dict(settings_data)

        # JSON editor
        self._cli_json_field = make_text_field(
            value=json.dumps(settings_data, indent=2, ensure_ascii=False) if settings_data else "",
            multiline=True,
            min_lines=8,
            max_lines=20,
            text_size=12,
            expand=True,
        )

        if not settings_data:
            empty_notice = ft.Text(
                t("settings.cli_settings_empty"),
                size=12, italic=True, opacity=0.5,
            )
        else:
            empty_notice = ft.Container(height=0)

        format_btn = ft.OutlinedButton(
            t("settings.cli_settings_format"),
            icon=ft.Icons.FORMAT_ALIGN_LEFT,
            on_click=self._format_cli_json,
        )

        reset_btn = ft.OutlinedButton(
            t("settings.cli_settings_reset"),
            icon=ft.Icons.RESTORE,
            on_click=self._reset_cli_settings,
        )

        save_btn = ft.Button(
            t("common.save"),
            icon=ft.Icons.SAVE,
            on_click=self._save_cli_settings,
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("settings.cli_settings"), size=18, weight=ft.FontWeight.W_500),
                    ft.Text(t("settings.cli_settings_desc"), size=12, opacity=0.6),
                    empty_notice,
                    self._cli_json_field,
                    ft.Row(
                        controls=[format_btn, reset_btn, ft.Container(expand=True), save_btn],
                        spacing=8,
                    ),
                ],
                spacing=12,
                expand=True,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
            expand=True,
        )

    def _format_cli_json(self, e: ft.ControlEvent) -> None:
        import json
        if self._cli_json_field:
            try:
                data = json.loads(self._cli_json_field.value or "{}")
                self._cli_json_field.value = json.dumps(data, indent=2, ensure_ascii=False)
                self._cli_json_field.update()
            except json.JSONDecodeError:
                pass

    def _reset_cli_settings(self, e: ft.ControlEvent) -> None:
        import json
        if self._cli_json_field:
            self._cli_json_field.value = json.dumps(
                self._cli_settings_original, indent=2, ensure_ascii=False
            )
            self._cli_json_field.update()

    def _save_cli_settings(self, e: ft.ControlEvent) -> None:
        import json
        if not e.page:
            return

        page = e.page
        cli_svc = None
        if hasattr(self.state, "services") and self.state.services:
            cli_svc = getattr(self.state.services, "cli_settings_service", None)

        if not cli_svc or not self._cli_json_field:
            return

        try:
            data = json.loads(self._cli_json_field.value or "{}")
        except json.JSONDecodeError:
            page.show_dialog(ft.SnackBar(content=ft.Text("Invalid JSON"), bgcolor=ft.Colors.ERROR))
            return

        def do_save(ev):
            page.pop_dialog()
            cli_svc.write_settings(data)
            self._cli_settings_original = dict(data)
            page.show_dialog(ft.SnackBar(content=ft.Text(t("settings.cli_settings_saved"))))

        dialog = ft.AlertDialog(
            title=ft.Text(t("settings.cli_settings_save_confirm_title")),
            content=ft.Text(t("settings.cli_settings_save_confirm")),
            actions=[
                ft.TextButton(t("common.cancel"), on_click=lambda ev: page.pop_dialog()),
                ft.Button(t("common.save"), on_click=do_save),
            ],
        )
        page.show_dialog(dialog)

    # ---------------------------------------------------------------
    # Language section
    # ---------------------------------------------------------------

    def _build_language_section(self) -> ft.Control:
        current_locale = getattr(self.state, "locale", "zh-CN")

        lang_buttons: list[ft.Control] = []
        for locale_code, locale_label in _LANGUAGES:
            is_active = current_locale == locale_code
            btn = ft.Container(
                content=ft.Text(locale_label, size=13),
                bgcolor=ft.Colors.PRIMARY if is_active else ft.Colors.TRANSPARENT,
                border=ft.Border.all(
                    1,
                    ft.Colors.PRIMARY if is_active else ft.Colors.OUTLINE,
                ),
                border_radius=8,
                padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                on_click=lambda e, loc=locale_code: self._change_language(loc),
                ink=True,
            )
            lang_buttons.append(btn)

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("settings.language"), size=18, weight=ft.FontWeight.W_500),
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
                                size=18,
                                weight=ft.FontWeight.W_500,
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
            return ft.Container(
                content=ft.Text(
                    t("settings.update_available"),
                    size=10,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.WHITE,
                ),
                bgcolor=ft.Colors.ORANGE,
                border_radius=4,
                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
            )
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=14),
                    ft.Text(
                        t("settings.up_to_date"),
                        size=10,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREEN,
                    ),
                ],
                spacing=4,
            ),
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
            return ft.Button(
                t("update.update_now"),
                icon=ft.Icons.SYSTEM_UPDATE,
                on_click=self._handle_perform_update,
            )

        return ft.OutlinedButton(
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
                                size=18,
                                weight=ft.FontWeight.W_500,
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
        return ft.OutlinedButton(
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
            color=ft.Colors.GREEN if is_installed else ft.Colors.ERROR,
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
            border_radius=8,
            border=ft.Border.all(
                1,
                ft.Colors.GREEN if is_installed else ft.Colors.OUTLINE,
            ),
        )

    def _build_tool_action_widget(
        self, tool, is_installed: bool, is_installing: bool,
    ) -> ft.Control:
        if is_installed:
            return ft.Container(
                content=ft.Text(
                    t("env_check.installed"),
                    size=10,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.WHITE,
                ),
                bgcolor=ft.Colors.GREEN,
                border_radius=4,
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            )
        if is_installing:
            return ft.Row(
                controls=[
                    ft.ProgressRing(width=14, height=14, stroke_width=2),
                    ft.Text(t("env_check.installing"), size=11, opacity=0.7),
                ],
                spacing=6,
            )
        return ft.Button(
            t("env_check.install"),
            icon=ft.Icons.DOWNLOAD,
            on_click=lambda e, name=tool.name: self._handle_env_install(e, name),
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.PRIMARY,
                color=ft.Colors.ON_PRIMARY,
            ),
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
    # About section
    # ---------------------------------------------------------------

    def _build_about_section(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("settings.about"), size=18, weight=ft.FontWeight.W_500),
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
