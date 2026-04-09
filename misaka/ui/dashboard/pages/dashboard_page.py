"""
Unified dashboard page.

Aggregates environment status, MCP server health, session statistics,
and cumulative token usage into a single overview page with card layout.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    ERROR_RED,
    SUCCESS_GREEN,
    WARNING_AMBER,
    make_card,
    make_icon_button,
)

if TYPE_CHECKING:
    from misaka.services.dashboard.dashboard_service import (
        SessionStats,
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


def _stat_tile(label: str, value: str, icon: str) -> ft.Control:
    """Build a compact stat display: icon + value + label."""
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(
                            icon, size=14,
                            color=ft.Colors.PRIMARY, opacity=0.7,
                        ),
                        ft.Text(
                            value,
                            size=20,
                            weight=ft.FontWeight.W_700,
                            color=ft.Colors.ON_SURFACE,
                        ),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                ),
                ft.Text(
                    label,
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=2,
        ),
        expand=True,
        padding=ft.Padding.symmetric(horizontal=4, vertical=2),
    )


class DashboardPage(ft.Column):
    """Unified dashboard with environment, MCP, session, and token cards."""

    def __init__(self, state: AppState) -> None:
        super().__init__(spacing=0, expand=True, scroll=ft.ScrollMode.AUTO)
        self.state = state
        self._session_stats: SessionStats | None = None
        self._token_summary: TokenUsageSummary | None = None
        self._loading = False
        self._build_ui()

    def _build_ui(self) -> None:
        self.controls = [
            ft.Container(
                content=ft.Column(
                    controls=[
                        self._build_header(),
                        self._build_cards(),
                        ft.Container(height=24),
                    ],
                    spacing=16,
                ),
                padding=ft.Padding.only(
                    left=32, right=32, top=20, bottom=16,
                ),
            ),
        ]

    def _build_header(self) -> ft.Control:
        return ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.DASHBOARD, size=22,
                    color=ft.Colors.PRIMARY,
                ),
                ft.Text(
                    t("dashboard.title"),
                    size=20,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Container(expand=True),
                make_icon_button(
                    ft.Icons.REFRESH,
                    tooltip=t("dashboard.refresh"),
                    on_click=self._on_refresh,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _build_cards(self) -> ft.Control:
        return ft.ResponsiveRow(
            controls=[
                ft.Container(
                    col={"xs": 12, "md": 6},
                    content=self._build_env_card(),
                ),
                ft.Container(
                    col={"xs": 12, "md": 6},
                    content=self._build_mcp_card(),
                ),
                ft.Container(
                    col={"xs": 12, "md": 6},
                    content=self._build_session_card(),
                ),
                ft.Container(
                    col={"xs": 12, "md": 6},
                    content=self._build_token_card(),
                ),
            ],
            spacing=12,
            run_spacing=12,
        )

    # ------------------------------------------------------------------
    # Environment status card
    # ------------------------------------------------------------------

    def _build_env_card(self) -> ft.Control:
        env_result = self.state.env_check_result
        rows: list[ft.Control] = []

        if env_result and hasattr(env_result, "tools"):
            for tool in env_result.tools:
                status_icon = ft.Icon(
                    ft.Icons.CHECK_CIRCLE,
                    size=14,
                    color=SUCCESS_GREEN,
                ) if tool.is_installed else ft.Icon(
                    ft.Icons.CANCEL,
                    size=14,
                    color=ERROR_RED,
                )
                version_text = (
                    tool.version or t("dashboard.not_checked")
                )
                rows.append(
                    ft.Row(
                        controls=[
                            ft.Text(
                                tool.name, size=12,
                                weight=ft.FontWeight.W_500,
                                expand=True,
                            ),
                            ft.Text(
                                version_text,
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            status_icon,
                        ],
                        spacing=8,
                    )
                )
        else:
            rows.append(
                ft.Text(
                    t("dashboard.not_checked"),
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                )
            )

        return self._wrap_card(
            title=t("dashboard.env_status"),
            icon=ft.Icons.BUILD_CIRCLE_OUTLINED,
            content=ft.Column(controls=rows, spacing=8, tight=True),
        )

    # ------------------------------------------------------------------
    # MCP server status card
    # ------------------------------------------------------------------

    def _build_mcp_card(self) -> ft.Control:
        mcp_configs = self.state.mcp_servers_sdk
        rows: list[ft.Control] = []

        if mcp_configs:
            mcp_svc = self.state.get_service("mcp_service")
            server_status = (
                mcp_svc.get_server_status() if mcp_svc else {}
            )

            for name in mcp_configs:
                info = server_status.get(name)
                if info:
                    healthy = info.get("is_healthy", False)
                    transport = info.get("transport", "stdio")
                    status_icon = ft.Icon(
                        ft.Icons.CHECK_CIRCLE,
                        size=14, color=SUCCESS_GREEN,
                    ) if healthy else ft.Icon(
                        ft.Icons.WARNING_AMBER,
                        size=14, color=WARNING_AMBER,
                    )
                else:
                    cfg = mcp_configs[name]
                    transport = (
                        cfg.get("type", "stdio")
                        if isinstance(cfg, dict) else "stdio"
                    )
                    status_icon = ft.Icon(
                        ft.Icons.CIRCLE_OUTLINED, size=14,
                        color=ft.Colors.ON_SURFACE_VARIANT,
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
                    padding=ft.Padding.symmetric(
                        horizontal=5, vertical=1,
                    ),
                )

                rows.append(
                    ft.Row(
                        controls=[
                            ft.Text(
                                name, size=12,
                                weight=ft.FontWeight.W_500,
                                expand=True,
                            ),
                            transport_badge,
                            status_icon,
                        ],
                        spacing=8,
                    )
                )
        else:
            rows.append(
                ft.Text(
                    t("dashboard.no_servers"),
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                )
            )

        server_count = len(mcp_configs) if mcp_configs else 0
        subtitle = (
            t("dashboard.configured") + f" ({server_count})"
            if server_count else None
        )

        return self._wrap_card(
            title=t("dashboard.mcp_status"),
            icon=ft.Icons.EXTENSION_OUTLINED,
            subtitle=subtitle,
            content=ft.Column(controls=rows, spacing=8, tight=True),
        )

    # ------------------------------------------------------------------
    # Session statistics card
    # ------------------------------------------------------------------

    def _build_session_card(self) -> ft.Control:
        stats = self._session_stats

        if stats:
            content = ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            _stat_tile(
                                t("dashboard.total_sessions"),
                                _fmt_number(stats.total_sessions),
                                ft.Icons.CHAT_BUBBLE_OUTLINE,
                            ),
                            _stat_tile(
                                t("dashboard.active_sessions"),
                                _fmt_number(stats.active_sessions),
                                ft.Icons.CIRCLE,
                            ),
                        ],
                    ),
                    ft.Row(
                        controls=[
                            _stat_tile(
                                t("dashboard.archived_sessions"),
                                _fmt_number(
                                    stats.archived_sessions,
                                ),
                                ft.Icons.ARCHIVE_OUTLINED,
                            ),
                            _stat_tile(
                                t("dashboard.total_messages"),
                                _fmt_number(stats.total_messages),
                                ft.Icons.MESSAGE_OUTLINED,
                            ),
                        ],
                    ),
                ],
                spacing=12,
                tight=True,
            )
        else:
            content = ft.Text(
                t("dashboard.no_data"),
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            )

        return self._wrap_card(
            title=t("dashboard.session_stats"),
            icon=ft.Icons.ANALYTICS_OUTLINED,
            content=content,
        )

    # ------------------------------------------------------------------
    # Token usage card
    # ------------------------------------------------------------------

    def _build_token_card(self) -> ft.Control:
        summary = self._token_summary

        if summary:
            content = ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            _stat_tile(
                                t("dashboard.total_input"),
                                _fmt_number(
                                    summary.total_input_tokens,
                                ),
                                ft.Icons.INPUT,
                            ),
                            _stat_tile(
                                t("dashboard.total_output"),
                                _fmt_number(
                                    summary.total_output_tokens,
                                ),
                                ft.Icons.OUTPUT,
                            ),
                        ],
                    ),
                    ft.Row(
                        controls=[
                            _stat_tile(
                                t("dashboard.total_cache"),
                                _fmt_number(
                                    summary.total_cache_read_tokens,
                                ),
                                ft.Icons.CACHED,
                            ),
                            _stat_tile(
                                t("dashboard.total_cost"),
                                _fmt_cost(summary.total_cost_usd),
                                ft.Icons.ATTACH_MONEY,
                            ),
                        ],
                    ),
                ],
                spacing=12,
                tight=True,
            )
        else:
            content = ft.Text(
                t("dashboard.no_data"),
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            )

        return self._wrap_card(
            title=t("dashboard.token_usage"),
            icon=ft.Icons.TOKEN_OUTLINED,
            content=content,
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _wrap_card(
        self,
        *,
        title: str,
        icon: str,
        content: ft.Control,
        subtitle: str | None = None,
    ) -> ft.Control:
        """Wrap card content with a consistent header."""
        header_controls: list[ft.Control] = [
            ft.Icon(icon, size=16, color=ft.Colors.PRIMARY),
            ft.Text(title, size=14, weight=ft.FontWeight.W_600),
        ]
        if subtitle:
            header_controls.append(
                ft.Text(
                    subtitle, size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )

        return make_card(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=header_controls, spacing=8,
                        ),
                        ft.Divider(
                            height=1,
                            color=ft.Colors.with_opacity(
                                0.06, ft.Colors.ON_SURFACE,
                            ),
                        ),
                        content,
                    ],
                    spacing=10,
                    tight=True,
                ),
                padding=ft.Padding.all(16),
            ),
            margin=ft.Margin.all(0),
        )

    # ------------------------------------------------------------------
    # Refresh logic
    # ------------------------------------------------------------------

    def _on_refresh(self, e: ft.ControlEvent | None = None) -> None:
        if self.state.page:
            self.state.page.run_task(self._load_data)

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

            self._build_ui()
            self.state.update()
        except Exception:
            logger.exception("Failed to load dashboard data")
        finally:
            self._loading = False

    def refresh(self) -> None:
        """Called by AppShell when navigating to this page."""
        self._on_refresh()
