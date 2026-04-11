"""Settings page.

Application settings including API provider management,
theme selection, permission mode, language selector,
default model configuration, and runtime log viewer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.config import SettingKeys, get_assets_path
from misaka.i18n import t
from misaka.ui.common.theme import (
    ERROR_RED,
    MONO_FONT_FAMILY,
    RADIUS_LG,
    RADIUS_MD,
    SUCCESS_GREEN,
    WARNING_AMBER,
    make_badge,
    make_button,
    make_outlined_button,
    make_section_card,
    show_snackbar,
)
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
from misaka.utils.log_buffer import get_ring_handler

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState

_PERMISSION_MODES = [
    ("default", "settings.perm_default", "settings.perm_default_desc"),
    ("acceptEdits", "settings.perm_accept_edits", "settings.perm_accept_edits_desc"),
    ("bypassPermissions", "settings.perm_bypass", "settings.perm_bypass_desc"),
]


def _log_level_color(level: str) -> str:
    if level in ("ERROR", "CRITICAL"):
        return ERROR_RED
    if level == "WARNING":
        return WARNING_AMBER
    if level == "DEBUG":
        return ft.Colors.ON_SURFACE_VARIANT
    return ft.Colors.ON_SURFACE


def _log_level_bg(level: str) -> str:
    if level in ("ERROR", "CRITICAL"):
        return ft.Colors.with_opacity(0.12, ERROR_RED)
    if level == "WARNING":
        return ft.Colors.with_opacity(0.12, WARNING_AMBER)
    if level == "DEBUG":
        return ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)
    return ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY)


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
        )
        self.state = state
        self.db = db
        self._on_theme_change = on_theme_change
        self._on_locale_change = on_locale_change
        self._router_list: ft.Column | None = None
        self._sections_column: ft.Column | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_sections(self) -> list[ft.Control]:
        """Build all section cards for the settings page."""
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
        log_viewer_section = self._build_log_viewer_section()
        language_section = build_language_section(
            self.state,
            on_language_click=self._change_language,
        )
        about_section = self._build_about_section()

        return [
            self._wrap_card(appearance_section),
            self._wrap_card(permission_section),
            self._wrap_card(cli_settings_section),
            self._wrap_card(claude_update_section),
            self._wrap_card(misaka_update_section),
            self._wrap_card(env_status_section),
            self._wrap_card(log_viewer_section),
            self._wrap_card(language_section),
            self._wrap_card(about_section),
            ft.Container(height=16),
        ]

    def _build_ui(self) -> None:
        sections = self._build_sections()

        if self._sections_column is not None:
            self._sections_column.controls = sections
            return

        header = self._build_header()

        self._sections_column = ft.Column(
            controls=sections,
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        sections_container = ft.Container(
            content=self._sections_column,
            expand=True,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        inner = ft.Column(
            controls=[header, sections_container],
            spacing=0,
            expand=True,
        )

        main_card = ft.Container(
            content=inner,
            margin=ft.Margin.symmetric(horizontal=10, vertical=10),
            padding=ft.Padding.all(10),
            expand=True,
            border_radius=RADIUS_MD,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            ),
            shadow=[
                ft.BoxShadow(
                    blur_radius=24,
                    spread_radius=-4,
                    color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK),
                    offset=ft.Offset(0, 4),
                ),
                ft.BoxShadow(
                    blur_radius=12,
                    spread_radius=-2,
                    color=ft.Colors.with_opacity(0.04, ft.Colors.BLACK),
                    offset=ft.Offset(0, 2),
                ),
            ],
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        self.controls = [main_card]

    def _build_header(self) -> ft.Container:
        """Build page header with icon, title and description."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(
                            ft.Icons.SETTINGS,
                            size=24,
                            color=ft.Colors.PRIMARY,
                        ),
                        width=44,
                        height=44,
                        border_radius=RADIUS_LG,
                        bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                t("settings.title"),
                                size=20,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                t("settings.description"),
                                size=12,
                                opacity=0.65,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
            padding=ft.Padding.only(bottom=20),
        )

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
        if tool.version:
            version_text = f"v{tool.version}"
        elif tool.is_installed:
            version_text = t("settings.env_version_unknown")
        else:
            version_text = t("env_check.not_installed")
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
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=RADIUS_LG,
            border=ft.Border.all(
                1,
                SUCCESS_GREEN if is_installed
                else ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
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

        async def _install_task() -> None:
            await self._do_env_install(tool_name)

        page.run_task(_install_task)

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

    # GitHub releases URL: /releases/latest redirects to the latest release page
    _MISAKA_RELEASES_URL = "https://github.com/knqiufan/Misaka/releases/latest"

    def _build_misaka_update_section(self) -> ft.Control:
        from misaka import __version__

        # NOTE: 检查更新功能已注释，改为直接跳转 GitHub Release 页面供用户自行下载
        # make_outlined_button(
        #     t("settings.check_update"),
        #     icon=ft.Icons.REFRESH,
        #     on_click=self._handle_misaka_update_check,
        # ),
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
                                t("settings.misaka_open_releases"),
                                icon=ft.Icons.OPEN_IN_NEW,
                                on_click=self._handle_open_misaka_releases,
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

    # def _handle_misaka_update_check(self, e: ft.ControlEvent) -> None:
    #     """原检查更新逻辑：显示未配置提示。已弃用，改为跳转 Release 页面。"""
    #     if not e.page:
    #         return
    #     e.page.show_dialog(
    #         ft.SnackBar(
    #             content=ft.Text(t("settings.update_not_configured")),
    #             duration=3000,
    #         )
    #     )

    def _handle_open_misaka_releases(self, e: ft.ControlEvent) -> None:
        """打开 GitHub 最新 Release 页面，供用户自行下载更新。"""
        page = e.page
        if not page:
            return

        async def _launch() -> None:
            await page.launch_url(self._MISAKA_RELEASES_URL)

        page.run_task(_launch)

    # ------------------------------------------------------------------
    # Log viewer section
    # ------------------------------------------------------------------

    _LOG_LEVELS = ("All", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

    def _build_log_viewer_section(self) -> ft.Control:
        handler = get_ring_handler()
        selected_level: str = getattr(self, "_log_level_filter", "All")
        level_filter = None if selected_level == "All" else selected_level
        entries = handler.get_entries(level_filter=level_filter)

        level_chips: list[ft.Control] = []
        for lvl in self._LOG_LEVELS:
            label = t("settings.log_viewer_all") if lvl == "All" else lvl
            is_selected = selected_level == lvl
            level_chips.append(
                ft.Container(
                    content=ft.Text(
                        label,
                        size=11,
                        weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.W_400,
                        color=(
                            ft.Colors.ON_PRIMARY
                            if is_selected
                            else ft.Colors.ON_SURFACE_VARIANT
                        ),
                    ),
                    bgcolor=(
                        ft.Colors.PRIMARY if is_selected
                        else ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)
                    ),
                    border_radius=12,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    on_click=lambda e, lv=lvl: self._set_log_level_filter(lv),
                    ink=True,
                ),
            )

        count_text = t("settings.log_viewer_entries").format(count=len(entries))

        if entries:
            log_rows: list[ft.Control] = []
            for i, entry in enumerate(entries):
                log_rows.append(self._build_log_entry_row(entry, i))
            log_content: ft.Control = ft.ListView(
                controls=log_rows,
                spacing=2,
                padding=ft.Padding.symmetric(horizontal=4, vertical=4),
                auto_scroll=True,
            )
        else:
            log_content = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.ARTICLE_OUTLINED, size=32, opacity=0.15),
                        ft.Text(
                            t("settings.log_viewer_empty"),
                            size=12, italic=True, opacity=0.4,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=8,
                ),
                expand=True,
                alignment=ft.Alignment.CENTER,
            )

        log_container = ft.Container(
            content=log_content,
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
            border_radius=RADIUS_LG,
            height=320,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                t("settings.log_viewer"),
                                size=16, weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(count_text, size=11, opacity=0.5),
                            ft.Container(expand=True),
                            make_outlined_button(
                                t("settings.log_viewer_copy"),
                                icon=ft.Icons.COPY,
                                on_click=self._handle_copy_logs,
                            ),
                            make_outlined_button(
                                t("settings.log_viewer_clear"),
                                icon=ft.Icons.DELETE_OUTLINE,
                                on_click=self._handle_clear_logs,
                            ),
                            make_outlined_button(
                                t("settings.log_viewer_refresh"),
                                icon=ft.Icons.REFRESH,
                                on_click=self._handle_refresh_logs,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    ft.Text(t("settings.log_viewer_desc"), size=12, opacity=0.6),
                    ft.Row(controls=level_chips, spacing=6, wrap=True),
                    log_container,
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    @staticmethod
    def _build_log_entry_row(entry, index: int) -> ft.Control:
        """Build a single structured log entry row."""
        level = entry.level
        level_color = _log_level_color(level)
        level_bg = _log_level_bg(level)

        level_badge = ft.Container(
            content=ft.Text(
                level[:4],
                size=9,
                weight=ft.FontWeight.W_700,
                color=level_color,
                font_family=MONO_FONT_FAMILY,
            ),
            bgcolor=level_bg,
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=5, vertical=1),
            width=42,
            alignment=ft.Alignment.CENTER,
        )

        timestamp_text = ft.Text(
            entry.timestamp,
            size=10,
            font_family=MONO_FONT_FAMILY,
            opacity=0.45,
            no_wrap=True,
        )

        logger_text = ft.Text(
            entry.logger_name,
            size=10,
            font_family=MONO_FONT_FAMILY,
            opacity=0.5,
            color=ft.Colors.PRIMARY,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        msg_text = ft.Text(
            entry.message,
            size=11,
            font_family=MONO_FONT_FAMILY,
            selectable=True,
            max_lines=3,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        row_bg = (
            ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE)
            if index % 2 == 0
            else None
        )

        return ft.Container(
            content=ft.Row(
                controls=[
                    level_badge,
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[timestamp_text, logger_text],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            msg_text,
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=5),
            border_radius=6,
            bgcolor=row_bg,
        )

    def _set_log_level_filter(self, level: str) -> None:
        self._log_level_filter = level
        self._build_ui()
        self.state.update()

    def _handle_refresh_logs(self, e: ft.ControlEvent) -> None:
        self._build_ui()
        self.state.update()

    def _handle_clear_logs(self, e: ft.ControlEvent) -> None:
        handler = get_ring_handler()
        handler.clear()
        self._build_ui()
        self.state.update()
        page = e.page
        if page:
            show_snackbar(page, t("settings.log_viewer_cleared"))

    def _handle_copy_logs(self, e: ft.ControlEvent) -> None:
        page = e.page
        if not page:
            return
        handler = get_ring_handler()
        selected_level: str = getattr(self, "_log_level_filter", "All")
        level_filter = None if selected_level == "All" else selected_level
        entries = handler.get_entries(level_filter=level_filter)
        text = "\n".join(entry.format_line() for entry in entries)
        page.set_clipboard(text)
        show_snackbar(page, t("settings.log_viewer_copied"))

    # ------------------------------------------------------------------
    # About section
    # ------------------------------------------------------------------

    def _build_about_section(self) -> ft.Control:
        github_icon_path = str(get_assets_path() / "GitHub.png")
        github_btn = ft.IconButton(
            icon=ft.Image(
                src=github_icon_path,
                width=18,
                height=18,
                fit=ft.BoxFit.CONTAIN,
            ),
            tooltip=t("settings.about_github"),
            on_click=self._open_github,
            style=ft.ButtonStyle(padding=6, shape=ft.CircleBorder()),
        )
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text(t("settings.about"), size=16, weight=ft.FontWeight.W_600),
                            ft.Text(t("settings.about_app"), size=13),
                            ft.Text(t("settings.about_desc"), size=12, opacity=0.6),
                            ft.Row(
                                controls=[
                                    ft.Text(t("settings.about_author"), size=12, opacity=0.7),
                                    github_btn,
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=8,
                        expand=True,
                    ),
                ],
                expand=True,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    def _open_github(self, e: ft.ControlEvent) -> None:
        page = e.page
        if not page:
            return

        async def _launch() -> None:
            await page.launch_url("https://github.com/knqiufan/Misaka")

        page.run_task(_launch)

    def refresh(self) -> None:
        """Rebuild the settings page."""
        self._build_ui()
