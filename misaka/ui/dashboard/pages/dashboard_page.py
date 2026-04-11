"""
Unified dashboard page.

Aggregates environment status, MCP server health, session/skill statistics,
and cumulative token usage into a single overview page with card layout.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    ERROR_RED,
    RADIUS_LG,
    RADIUS_MD,
    SUCCESS_GREEN,
    WARNING_AMBER,
    make_badge,
    make_icon_button,
    make_outlined_button,
    make_section_card,
)

if TYPE_CHECKING:
    from misaka.services.dashboard.dashboard_service import (
        SessionStats,
        SkillStats,
        TokenUsageSummary,
    )
    from misaka.state import AppState

logger = logging.getLogger(__name__)


def _fmt_number(n: int) -> str:
    """Format an integer with thousand separators."""
    return f"{n:,}"


def _fmt_cost(cost: float) -> str:
    """Format a USD cost value."""
    return f"${cost:,.4f}"


class DashboardPage(ft.Column):
    """Unified dashboard with env, MCP, session, skill, and token cards."""

    def __init__(self, state: AppState) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._session_stats: SessionStats | None = None
        self._token_summary: TokenUsageSummary | None = None
        self._skill_stats: SkillStats | None = None
        self._cli_session_count: int = 0
        self._mcp_health: dict[str, bool] | None = None
        self._mcp_checking = False
        self._loading = False
        self._sections_column: ft.Column | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # Top-level layout (matches Settings / Plugins page structure)
    # ------------------------------------------------------------------

    def _build_sections(self) -> list[ft.Control]:
        return [
            self._wrap_card(self._build_session_section()),
            self._wrap_card(self._build_token_section()),
            self._wrap_card(self._build_skill_section()),
            self._wrap_card(self._build_env_section()),
            self._wrap_card(self._build_mcp_section()),
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
                    color=ft.Colors.with_opacity(
                        0.08, ft.Colors.BLACK,
                    ),
                    offset=ft.Offset(0, 4),
                ),
                ft.BoxShadow(
                    blur_radius=12,
                    spread_radius=-2,
                    color=ft.Colors.with_opacity(
                        0.04, ft.Colors.BLACK,
                    ),
                    offset=ft.Offset(0, 2),
                ),
            ],
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        self.controls = [main_card]

    def _build_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(
                            ft.Icons.DASHBOARD,
                            size=24,
                            color=ft.Colors.PRIMARY,
                        ),
                        width=44,
                        height=44,
                        border_radius=RADIUS_LG,
                        bgcolor=ft.Colors.with_opacity(
                            0.12, ft.Colors.PRIMARY,
                        ),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                t("dashboard.title"),
                                size=20,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                t("dashboard.description"),
                                size=12,
                                opacity=0.65,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    make_icon_button(
                        ft.Icons.REFRESH,
                        tooltip=t("dashboard.refresh"),
                        on_click=self._on_refresh,
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
    # Session statistics section
    # ------------------------------------------------------------------

    def _build_session_section(self) -> ft.Control:
        stats = self._session_stats

        if stats:
            row1 = [
                self._stat_chip(
                    _fmt_number(stats.total_sessions),
                    t("dashboard.total_sessions"),
                    ft.Icons.CHAT_BUBBLE_OUTLINE,
                ),
                self._stat_chip(
                    _fmt_number(stats.active_sessions),
                    t("dashboard.active_sessions"),
                    ft.Icons.CIRCLE,
                ),
                self._stat_chip(
                    _fmt_number(stats.archived_sessions),
                    t("dashboard.archived_sessions"),
                    ft.Icons.ARCHIVE_OUTLINED,
                ),
            ]
            row2 = [
                self._stat_chip(
                    _fmt_number(stats.total_messages),
                    t("dashboard.total_messages"),
                    ft.Icons.MESSAGE_OUTLINED,
                ),
            ]
            if self._cli_session_count > 0:
                row2.append(
                    self._stat_chip(
                        _fmt_number(self._cli_session_count),
                        t("dashboard.cli_sessions"),
                        ft.Icons.TERMINAL,
                    ),
                )
            body: ft.Control = ft.Column(
                controls=[
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(
                                col={"xs": 4, "md": 4}, content=c,
                            )
                            for c in row1
                        ],
                        spacing=8,
                        run_spacing=8,
                    ),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(
                                col={"xs": 6, "md": 6}, content=c,
                            )
                            for c in row2
                        ],
                        spacing=8,
                        run_spacing=8,
                    ),
                ],
                spacing=8,
            )
        else:
            body = ft.Text(
                t("dashboard.no_data"),
                size=12, italic=True, opacity=0.5,
            )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        t("dashboard.session_stats"),
                        size=16, weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        t("dashboard.session_stats_desc"),
                        size=12, opacity=0.6,
                    ),
                    body,
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    # ------------------------------------------------------------------
    # Token usage section
    # ------------------------------------------------------------------

    def _build_token_section(self) -> ft.Control:
        summary = self._token_summary

        if summary:
            stat_items = [
                self._stat_chip(
                    _fmt_number(summary.total_input_tokens),
                    t("dashboard.total_input"),
                    ft.Icons.INPUT,
                ),
                self._stat_chip(
                    _fmt_number(summary.total_output_tokens),
                    t("dashboard.total_output"),
                    ft.Icons.OUTPUT,
                ),
                self._stat_chip(
                    _fmt_number(summary.total_cache_read_tokens),
                    t("dashboard.total_cache"),
                    ft.Icons.CACHED,
                ),
                self._stat_chip(
                    _fmt_cost(summary.total_cost_usd),
                    t("dashboard.total_cost"),
                    ft.Icons.ATTACH_MONEY,
                ),
            ]
            body: ft.Control = ft.ResponsiveRow(
                controls=[
                    ft.Container(col={"xs": 6, "md": 3}, content=c)
                    for c in stat_items
                ],
                spacing=8,
                run_spacing=8,
            )
        else:
            body = ft.Text(
                t("dashboard.no_data"),
                size=12, italic=True, opacity=0.5,
            )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        t("dashboard.token_usage"),
                        size=16, weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        t("dashboard.token_usage_desc"),
                        size=12, opacity=0.6,
                    ),
                    body,
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    # ------------------------------------------------------------------
    # Skill statistics section
    # ------------------------------------------------------------------

    def _build_skill_section(self) -> ft.Control:
        stats = self._skill_stats

        if stats:
            stat_items = [
                self._stat_chip(
                    _fmt_number(stats.total),
                    t("dashboard.skills_total"),
                    ft.Icons.CODE,
                ),
                self._stat_chip(
                    _fmt_number(stats.global_count),
                    t("extensions.source_global"),
                    ft.Icons.PUBLIC,
                ),
                self._stat_chip(
                    _fmt_number(stats.project_count),
                    t("extensions.source_project"),
                    ft.Icons.FOLDER_OUTLINED,
                ),
                self._stat_chip(
                    _fmt_number(stats.installed_count),
                    t("extensions.source_installed"),
                    ft.Icons.DOWNLOAD_DONE,
                ),
                self._stat_chip(
                    _fmt_number(stats.plugin_count),
                    t("extensions.source_plugin"),
                    ft.Icons.EXTENSION,
                ),
            ]
            row1 = stat_items[:3]
            row2 = stat_items[3:]
            body: ft.Control = ft.Column(
                controls=[
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(
                                col={"xs": 4, "md": 4}, content=c,
                            )
                            for c in row1
                        ],
                        spacing=8,
                        run_spacing=8,
                    ),
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(
                                col={"xs": 6, "md": 6}, content=c,
                            )
                            for c in row2
                        ],
                        spacing=8,
                        run_spacing=8,
                    ),
                ],
                spacing=8,
            )
        else:
            body = ft.Text(
                t("dashboard.no_data"),
                size=12, italic=True, opacity=0.5,
            )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        t("dashboard.skill_stats"),
                        size=16, weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        t("dashboard.skill_stats_desc"),
                        size=12, opacity=0.6,
                    ),
                    body,
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    # ------------------------------------------------------------------
    # Environment status section
    # ------------------------------------------------------------------

    def _build_env_section(self) -> ft.Control:
        env_result = self.state.env_check_result
        tool_rows: list[ft.Control] = []

        if env_result and hasattr(env_result, "tools"):
            for tool in env_result.tools:
                tool_rows.append(self._build_tool_row(tool))
        else:
            tool_rows.append(
                ft.Text(
                    t("dashboard.not_checked"),
                    size=12, italic=True, opacity=0.5,
                )
            )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        t("dashboard.env_status"),
                        size=16, weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        t("dashboard.env_status_desc"),
                        size=12, opacity=0.6,
                    ),
                    ft.Column(controls=tool_rows, spacing=8),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    @staticmethod
    def _build_tool_row(tool) -> ft.Control:
        has_version = tool.version is not None
        is_installed = tool.is_installed

        if has_version:
            status_icon = ft.Icon(
                ft.Icons.CHECK_CIRCLE,
                color=SUCCESS_GREEN, size=22,
            )
            version_text = f"v{tool.version}"
            badge = make_badge(
                t("dashboard.healthy"), bgcolor=SUCCESS_GREEN,
            )
            border_color = SUCCESS_GREEN
        elif is_installed:
            status_icon = ft.Icon(
                ft.Icons.CHECK_CIRCLE,
                color=WARNING_AMBER, size=22,
            )
            version_text = t("dashboard.version_unknown")
            badge = make_badge(
                t("dashboard.healthy"), bgcolor=WARNING_AMBER,
            )
            border_color = WARNING_AMBER
        else:
            status_icon = ft.Icon(
                ft.Icons.CANCEL,
                color=ERROR_RED, size=22,
            )
            version_text = t("dashboard.unhealthy")
            badge = make_badge(
                t("dashboard.unhealthy"), bgcolor=ERROR_RED,
            )
            border_color = ft.Colors.with_opacity(
                0.06, ft.Colors.ON_SURFACE,
            )

        return ft.Container(
            content=ft.Row(
                controls=[
                    status_icon,
                    ft.Column(
                        controls=[
                            ft.Text(
                                tool.name, size=13,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                version_text, size=11, opacity=0.6,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    badge,
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=RADIUS_LG,
            border=ft.Border.all(1, border_color),
            bgcolor=ft.Colors.with_opacity(
                0.02, ft.Colors.ON_SURFACE,
            ),
        )

    # ------------------------------------------------------------------
    # MCP server status section
    # ------------------------------------------------------------------

    def _build_mcp_section(self) -> ft.Control:
        mcp_configs = self.state.mcp_servers_sdk
        server_rows: list[ft.Control] = []

        if mcp_configs:
            for name in mcp_configs:
                health = (
                    self._mcp_health.get(name)
                    if self._mcp_health is not None
                    else None
                )
                server_rows.append(
                    self._build_server_row(
                        name, mcp_configs[name], health,
                    )
                )
        else:
            server_rows.append(
                ft.Text(
                    t("dashboard.no_servers"),
                    size=12, italic=True, opacity=0.5,
                )
            )

        server_count = len(mcp_configs) if mcp_configs else 0
        count_text = (
            f" ({server_count})" if server_count else ""
        )

        if self._mcp_checking:
            action_widget: ft.Control = ft.Row(
                controls=[
                    ft.ProgressRing(
                        width=14, height=14, stroke_width=2,
                    ),
                    ft.Text(
                        t("dashboard.checking"),
                        size=12, opacity=0.7,
                    ),
                ],
                spacing=6,
            )
        else:
            action_widget = make_outlined_button(
                t("dashboard.check_health"),
                icon=ft.Icons.HEALTH_AND_SAFETY,
                on_click=self._on_check_mcp_health,
            )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                t("dashboard.mcp_status"),
                                size=16,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                t("dashboard.configured") + count_text
                                if server_count else "",
                                size=11, opacity=0.5,
                            ),
                            ft.Container(expand=True),
                            action_widget,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    ft.Text(
                        t("dashboard.mcp_status_desc"),
                        size=12, opacity=0.6,
                    ),
                    ft.Column(controls=server_rows, spacing=8),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

    @staticmethod
    def _build_server_row(
        name: str,
        cfg: dict | object,
        health: bool | None,
    ) -> ft.Control:
        transport = (
            cfg.get("type", "stdio")
            if isinstance(cfg, dict) else "stdio"
        )

        if health is True:
            badge = make_badge(
                t("dashboard.healthy"), bgcolor=SUCCESS_GREEN,
            )
        elif health is False:
            badge = make_badge(
                t("dashboard.unhealthy"), bgcolor=WARNING_AMBER,
            )
        else:
            badge = make_badge(
                t("dashboard.not_checked"),
                bgcolor=ft.Colors.with_opacity(
                    0.3, ft.Colors.ON_SURFACE_VARIANT,
                ),
            )

        transport_badge = ft.Container(
            content=ft.Text(
                transport, size=9,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(
                    0.15, ft.Colors.ON_SURFACE,
                ),
            ),
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=5, vertical=1),
        )

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.EXTENSION, size=22,
                        color=ft.Colors.PRIMARY, opacity=0.7,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                name, size=13,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Row(
                                controls=[transport_badge],
                                spacing=4,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    badge,
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=RADIUS_LG,
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(
                    0.06, ft.Colors.ON_SURFACE,
                ),
            ),
            bgcolor=ft.Colors.with_opacity(
                0.02, ft.Colors.ON_SURFACE,
            ),
        )

    # ------------------------------------------------------------------
    # Stat chip (reusable metric display)
    # ------------------------------------------------------------------

    @staticmethod
    def _stat_chip(
        value: str, label: str, icon: str,
    ) -> ft.Control:
        """Metric card: bordered container with icon, value, label."""
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        icon, size=18,
                        color=ft.Colors.PRIMARY, opacity=0.6,
                    ),
                    ft.Text(
                        value,
                        size=20,
                        weight=ft.FontWeight.W_700,
                        color=ft.Colors.ON_SURFACE,
                    ),
                    ft.Text(
                        label,
                        size=11,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=14),
            border_radius=RADIUS_LG,
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(
                    0.06, ft.Colors.ON_SURFACE,
                ),
            ),
            bgcolor=ft.Colors.with_opacity(
                0.02, ft.Colors.ON_SURFACE,
            ),
            alignment=ft.Alignment.CENTER,
        )

    # ------------------------------------------------------------------
    # Refresh / MCP health check logic
    # ------------------------------------------------------------------

    def _on_refresh(self, e: ft.ControlEvent | None = None) -> None:
        if self.state.page:
            self.state.page.run_task(self._load_data)

    def _on_check_mcp_health(
        self, e: ft.ControlEvent | None = None,
    ) -> None:
        if self.state.page:
            self.state.page.run_task(self._do_mcp_health_check)

    async def _do_mcp_health_check(self) -> None:
        """Start all configured MCP servers and check health."""
        self._mcp_checking = True
        self._build_ui()
        self.state.update()

        try:
            mcp_svc = self.state.get_service("mcp_service")
            if not mcp_svc:
                return

            mcp_configs = self.state.mcp_servers_sdk
            if not mcp_configs:
                return

            mcp_raw = mcp_svc.load_mcp_servers()
            for name, cfg in mcp_raw.items():
                await mcp_svc.start_server(name, cfg)

            self._mcp_health = await mcp_svc.check_health()
        except Exception:
            logger.exception("MCP health check failed")
        finally:
            self._mcp_checking = False
            self._build_ui()
            self.state.update()

    async def _load_data(self) -> None:
        """Load dashboard data from services on the main thread."""
        if self._loading:
            return
        self._loading = True

        try:
            dashboard_svc = self.state.get_service("dashboard_service")
            if dashboard_svc:
                self._session_stats = (
                    dashboard_svc.get_session_stats()
                )
                self._token_summary = (
                    dashboard_svc.get_token_usage_summary()
                )
                self._skill_stats = (
                    dashboard_svc.get_skill_stats()
                )
                self._cli_session_count = (
                    dashboard_svc.get_cli_session_count()
                )

            self._build_ui()
            self.state.update()
        except Exception:
            logger.exception("Failed to load dashboard data")
        finally:
            self._loading = False

    def refresh(self) -> None:
        """Called by AppShell when navigating to this page."""
        self._on_refresh()
