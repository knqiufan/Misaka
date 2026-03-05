"""Settings page.

Application settings including API provider management,
theme selection, permission mode, language selector, and
default model configuration.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.config import SettingKeys
from misaka.ui.settings.pages.appearance_section import (
    build_appearance_section,
    build_language_section,
    change_accent_color,
    change_language,
    change_theme,
)
from misaka.ui.settings.pages.provider_section import (
    build_router_section,
    show_router_form,
)
from misaka.ui.common.theme import (
    ERROR_RED,
    SUCCESS_GREEN,
    WARNING_AMBER,
    make_badge,
    make_button,
    make_outlined_button,
    make_section_card,
)

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState

_PERMISSION_MODES = [
    ("default", "settings.perm_default", "settings.perm_default_desc"),
    ("acceptEdits", "settings.perm_accept_edits", "settings.perm_accept_edits_desc"),
    ("bypassPermissions", "settings.perm_bypass", "settings.perm_bypass_desc"),
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

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        header = ft.Container(
            content=ft.Text(
                t("settings.title"),
                size=22,
                weight=ft.FontWeight.W_600,
            ),
            padding=ft.Padding.only(left=24, top=20, bottom=12),
        )

        appearance_section = build_appearance_section(
            self.state,
            on_theme_click=self._change_theme,
            on_accent_click=self._change_accent_color,
        )
        permission_section = self._build_permission_section()
        cli_settings_section = self._build_cli_settings_section()
        claude_update_section = self._build_claude_update_section()
        misaka_update_section = self._build_misaka_update_section()
        env_status_section = self._build_env_status_section()
        language_section = build_language_section(
            self.state,
            on_language_click=self._change_language,
        )
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
        return make_section_card(content)

    # ------------------------------------------------------------------
    # Delegated callbacks (appearance / language / router)
    # ------------------------------------------------------------------

    def _change_theme(self, mode: str) -> None:
        change_theme(self.state, mode, self._on_theme_change, self._build_ui)

    def _change_accent_color(self, color: str) -> None:
        change_accent_color(self.state, color, self.db, self._build_ui)

    def _change_language(self, locale: str) -> None:
        change_language(
            self.state, locale, self.db,
            self._on_locale_change, self._build_ui,
        )

    def _build_cli_settings_section(self) -> ft.Control:
        self._router_list = ft.Column(spacing=4)
        return build_router_section(
            self.state,
            self._router_list,
            on_add_click=self._show_add_router_dialog,
        )

    def _show_add_router_dialog(self, e: ft.ControlEvent) -> None:
        if self._router_list:
            show_router_form(self.state, e.page, config=None, router_list=self._router_list)

    # ------------------------------------------------------------------
    # Permission section
    # ------------------------------------------------------------------

    def _build_permission_section(self) -> ft.Control:
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
                    ft.Text(t("settings.permission_mode_desc"), size=12, opacity=0.6),
                    radio_group,
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _change_permission_mode(self, e: ft.ControlEvent) -> None:
        mode = e.data or e.control.value
        if mode:
            settings_svc = self.state.get_service("settings_service")
            if settings_svc:
                settings_svc.set(SettingKeys.PERMISSION_MODE, mode)
            elif self.db:
                self.db.set_setting(SettingKeys.PERMISSION_MODE, mode)

    # ------------------------------------------------------------------
    # Claude Code update section
    # ------------------------------------------------------------------

    def _build_claude_update_section(self) -> ft.Control:
        result = self.state.update_check_result
        is_checking = getattr(self, "_update_checking", False)
        is_updating = self.state.update_in_progress
        update_msg = getattr(self, "_update_progress_msg", "")

        current = result.current_version if result else None
        latest = result.latest_version if result else None
        has_update = result.update_available if result else False

        version_rows = self._build_version_info_rows(current, latest, has_update, update_msg)
        action_btn = self._build_update_action_button(is_checking, is_updating, has_update)

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                t("settings.claude_update"),
                                size=16, weight=ft.FontWeight.W_600,
                            ),
                            ft.Container(expand=True),
                            action_btn,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(t("settings.claude_update_desc"), size=12, opacity=0.6),
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
        rows: list[ft.Control] = []
        if current:
            rows.append(
                ft.Text(
                    f"{t('settings.current_version')}: {current}",
                    size=13, opacity=0.8,
                ),
            )
        if latest:
            status_badge = self._make_version_status_badge(has_update)
            rows.append(
                ft.Row(
                    controls=[
                        ft.Text(
                            f"{t('settings.latest_version')}: {latest}",
                            size=13, opacity=0.8,
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
            return make_badge(t("settings.update_available"), bgcolor=WARNING_AMBER)
        return make_badge(
            t("settings.up_to_date"),
            bgcolor=SUCCESS_GREEN,
            icon=ft.Icons.CHECK_CIRCLE,
        )

    def _build_update_action_button(
        self, is_checking: bool, is_updating: bool, has_update: bool,
    ) -> ft.Control:
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
        page = e.page
        if not page:
            return
        self._update_checking = True
        self._build_ui()
        self.state.update()
        page.run_task(self._do_check_update)

    async def _do_check_update(self) -> None:
        svc = self._get_update_service()
        if svc:
            self.state.update_check_result = await svc.check_for_update()
        self._update_checking = False
        self._build_ui()
        self.state.update()

    def _handle_perform_update(self, e: ft.ControlEvent) -> None:
        page = e.page
        if not page:
            return
        self.state.update_in_progress = True
        self._update_progress_msg = ""
        self._build_ui()
        self.state.update()
        page.run_task(self._do_perform_update)

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
        return self.state.get_service("update_check_service")

    # ------------------------------------------------------------------
    # Environment status section
    # ------------------------------------------------------------------

    def _build_env_status_section(self) -> ft.Control:
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
                                size=16, weight=ft.FontWeight.W_600,
                            ),
                            ft.Container(expand=True),
                            header_btn,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(t("settings.env_status_desc"), size=12, opacity=0.6),
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
                ft.Text(t("settings.checking"), size=12, italic=True, opacity=0.5)
            ]
        return [self._build_tool_status_card(tool) for tool in result.tools]

    def _build_tool_status_card(self, tool) -> ft.Control:
        is_installed = tool.is_installed
        installing_tool = getattr(self, "_env_installing_tool", None)
        is_installing = installing_tool == tool.name

        status_icon = ft.Icon(
            ft.Icons.CHECK_CIRCLE if is_installed else ft.Icons.CANCEL,
            color=SUCCESS_GREEN if is_installed else ERROR_RED,
            size=22,
        )
        version_text = f"v{tool.version}" if tool.version else t("env_check.not_installed")
        right_widget = self._build_tool_action_widget(tool, is_installed, is_installing)

        return ft.Container(
            content=ft.Row(
                controls=[
                    status_icon,
                    ft.Column(
                        controls=[
                            ft.Text(tool.name, size=13, weight=ft.FontWeight.W_500),
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
        page = e.page
        if not page:
            return
        self._env_checking = True
        self._build_ui()
        self.state.update()
        page.run_task(self._do_env_recheck)

    async def _do_env_recheck(self) -> None:
        svc = self._get_env_service()
        if svc:
            self.state.env_check_result = await svc.check_all()
        self._env_checking = False
        self._build_ui()
        self.state.update()

    def _handle_env_install(self, e: ft.ControlEvent, tool_name: str) -> None:
        page = e.page
        if not page:
            return
        self._env_installing_tool = tool_name
        self._build_ui()
        self.state.update()
        page.run_task(lambda: self._do_env_install(tool_name))

    async def _do_env_install(self, tool_name: str) -> None:
        svc = self._get_env_service()
        if svc:
            await svc.install_tool(tool_name)
            self.state.env_check_result = await svc.check_all()
        self._env_installing_tool = None
        self._build_ui()
        self.state.update()

    def _get_env_service(self):
        return self.state.get_service("env_check_service")

    # ------------------------------------------------------------------
    # Misaka update section
    # ------------------------------------------------------------------

    def _build_misaka_update_section(self) -> ft.Control:
        from misaka import __version__

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                t("settings.misaka_update"),
                                size=16, weight=ft.FontWeight.W_600,
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
                    ft.Text(t("settings.misaka_update_desc"), size=12, opacity=0.6),
                    ft.Text(
                        f"{t('settings.misaka_version')}: {__version__}",
                        size=13, opacity=0.8,
                    ),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _handle_misaka_update_check(self, e: ft.ControlEvent) -> None:
        if not e.page:
            return
        e.page.show_dialog(
            ft.SnackBar(
                content=ft.Text(t("settings.update_not_configured")),
                duration=3000,
            )
        )

    # ------------------------------------------------------------------
    # About section
    # ------------------------------------------------------------------

    def _build_about_section(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("settings.about"), size=16, weight=ft.FontWeight.W_600),
                    ft.Text(t("settings.about_app"), size=13),
                    ft.Text(t("settings.about_desc"), size=12, opacity=0.6),
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
