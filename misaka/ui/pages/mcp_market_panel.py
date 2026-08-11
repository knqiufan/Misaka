"""MCP Registry browser and configuration installer."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    RADIUS_LG,
    make_badge,
    make_button,
    make_dialog,
    make_empty_state,
    make_outlined_button,
    make_text_button,
    make_text_field,
    show_snackbar,
)

if TYPE_CHECKING:
    from misaka.services.mcp.mcp_market_service import MarketMCPServer, MCPInstallPlan
    from misaka.state import AppState

logger = logging.getLogger(__name__)

InstallCallback = Callable[
    [str, "MarketMCPServer", dict[str, Any]],
    tuple[bool, str],
]


class MCPMarketPanel(ft.Column):
    """Search and install entries from the official MCP Registry."""

    def __init__(self, state: AppState, on_install: InstallCallback) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._on_install = on_install
        self._results: list[MarketMCPServer] = []
        self._selected_server: MarketMCPServer | None = None
        self._is_searching = False
        self._is_installing = False
        self._query = ""
        self._search_field = make_text_field(
            hint_text=t("plugins.market_search"),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            on_submit=self._handle_search,
        )
        self._result_list = ft.ListView(
            expand=True,
            spacing=6,
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
        )
        self._preview = ft.Container(expand=True)
        self._build_ui()

    def _get_service(self):
        return self.state.get_service("mcp_market_service")

    def _build_ui(self) -> None:
        search_row = ft.Row(
            controls=[
                ft.Container(content=self._search_field, expand=True),
                make_button(
                    t("plugins.market_search_btn"),
                    icon=ft.Icons.SEARCH,
                    on_click=self._handle_search,
                ),
                make_outlined_button(
                    t("plugins.market_browse"),
                    icon=ft.Icons.PUBLIC,
                    on_click=self._handle_browse,
                ),
            ],
            spacing=8,
        )
        self._result_list.controls = [self._empty_results()]
        self._preview.content = self._empty_preview()

        results_panel = ft.Container(
            content=self._result_list,
            width=330,
            expand=False,
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)),
            margin=ft.Margin.only(right=20),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        self._preview.border_radius = RADIUS_LG
        self._preview.bgcolor = ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE)
        self._preview.border = ft.Border.all(
            1,
            ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        )
        self._preview.padding = ft.Padding.all(18)
        self.controls = [
            ft.Container(content=search_row, padding=ft.Padding.only(bottom=12)),
            ft.Row(
                controls=[results_panel, self._preview],
                spacing=0,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        ]

    @staticmethod
    def _empty_preview() -> ft.Control:
        return make_empty_state(
            ft.Icons.HUB_OUTLINED,
            t("plugins.market_hint"),
            icon_size=48,
            icon_opacity=0.22,
        )

    def _empty_results(self) -> ft.Control:
        message = (
            t("plugins.market_no_results")
            if self._query
            else t("plugins.market_hint")
        )
        return ft.Container(
            content=make_empty_state(
                ft.Icons.SEARCH_OFF if self._query else ft.Icons.PUBLIC,
                message,
                hint=t("plugins.market_no_results_desc") if self._query else None,
                icon_size=42,
                icon_opacity=0.25,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=32),
        )

    def _rebuild_results(self) -> None:
        if not self._results:
            self._result_list.controls = [self._empty_results()]
            return
        self._result_list.controls = [
            self._server_card(server)
            for server in self._results
        ]

    def _server_card(self, server: MarketMCPServer) -> ft.Control:
        selected = self._selected_server is server
        transports: list[str] = []
        if server.remotes:
            transports.append("HTTP")
        if server.packages:
            transports.append("STDIO")
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        server.display_name,
                        size=13,
                        weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_500,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        server.description or server.name,
                        size=10,
                        opacity=0.6,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        f"v{server.version} · {' / '.join(transports)}",
                        size=9,
                        opacity=0.42,
                    ),
                ],
                spacing=4,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border_radius=RADIUS_LG,
            bgcolor=(
                ft.Colors.with_opacity(0.09, ft.Colors.PRIMARY)
                if selected
                else ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE)
            ),
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(
                    0.14 if selected else 0.06,
                    ft.Colors.PRIMARY if selected else ft.Colors.ON_SURFACE,
                ),
            ),
            on_click=lambda e, item=server: self._select_server(item),
            ink=True,
        )

    def _build_preview(self, server: MarketMCPServer) -> ft.Control:
        badges: list[ft.Control] = [make_badge(f"v{server.version}", bgcolor="#2563eb")]
        if server.remotes:
            badges.append(make_badge("HTTP", bgcolor="#059669"))
        if server.packages:
            badges.append(make_badge("STDIO", bgcolor="#7c3aed"))

        actions: list[ft.Control] = [
            make_button(
                t("plugins.market_install"),
                icon=ft.Icons.DOWNLOAD,
                on_click=lambda e, item=server: self._handle_install(e, item),
                disabled=self._is_installing,
            )
        ]
        if server.repository_url:
            actions.append(
                ft.TextButton(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.OPEN_IN_NEW, size=14),
                            ft.Text(t("plugins.market_repository"), size=12),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    url=server.repository_url,
                )
            )
        return ft.Column(
            controls=[
                ft.Text(server.display_name, size=20, weight=ft.FontWeight.W_600),
                ft.Row(controls=badges, spacing=6),
                ft.Text(server.name, size=11, opacity=0.5),
                ft.Divider(height=1, opacity=0.1),
                ft.Text(server.description or t("plugins.market_no_description"), size=13),
                ft.Container(expand=True),
                ft.Row(controls=actions, spacing=8),
            ],
            spacing=10,
            expand=True,
        )

    def _handle_search(self, e: ft.ControlEvent) -> None:
        query = (self._search_field.value or "").strip()
        if query:
            self._start_search(query)

    def _handle_browse(self, e: ft.ControlEvent) -> None:
        self._search_field.value = ""
        self._start_search("")

    def _start_search(self, query: str) -> None:
        if self._is_searching or not self.page:
            return
        service = self._get_service()
        if not service:
            return
        page = self.page
        self._query = query
        self._is_searching = True
        self._result_list.controls = [
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.ProgressRing(width=20, height=20, stroke_width=2),
                        ft.Text(t("plugins.market_searching"), size=13),
                    ],
                    spacing=10,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(vertical=40),
            )
        ]
        self.state.update()

        async def run_search() -> None:
            result = await service.search(query, limit=30)
            self._is_searching = False
            self._results = result.servers
            self._selected_server = None
            self._preview.content = self._empty_preview()
            self._rebuild_results()
            if result.error:
                show_snackbar(
                    page,
                    t("plugins.market_search_error", error=result.error),
                )
            self.state.update()

        page.run_task(run_search)

    def _select_server(self, server: MarketMCPServer) -> None:
        self._selected_server = server
        self._rebuild_results()
        self._preview.content = self._build_preview(server)
        self.state.update()

    def _handle_install(self, e: ft.ControlEvent, server: MarketMCPServer) -> None:
        page = e.page
        service = self._get_service()
        if not page or not service or self._is_installing:
            return
        try:
            plan = service.create_install_plan(server)
        except ValueError as exc:
            show_snackbar(page, t("plugins.market_install_failed", error=str(exc)))
            return
        if plan.inputs:
            self._show_configuration_dialog(page, server, plan)
        else:
            self._finish_install(page, server, plan, {})

    def _show_configuration_dialog(
        self,
        page: ft.Page,
        server: MarketMCPServer,
        plan: MCPInstallPlan,
    ) -> None:
        fields: dict[str, ft.TextField] = {}
        controls: list[ft.Control] = [
            ft.Text(t("plugins.market_configure_desc"), size=12, opacity=0.65)
        ]
        for item in plan.inputs:
            field = make_text_field(
                label=item.label,
                value=item.default,
                hint_text=item.description or None,
                password=item.secret,
                can_reveal_password=item.secret,
            )
            fields[item.key] = field
            controls.append(field)

        def install(ev: ft.ControlEvent) -> None:
            values = {key: (field.value or "").strip() for key, field in fields.items()}
            missing = False
            for item in plan.inputs:
                fields[item.key].error_text = None
                if item.required and not values[item.key]:
                    fields[item.key].error_text = t("plugins.market_required")
                    missing = True
            if missing:
                page.update()
                return
            page.pop_dialog()
            self._finish_install(page, server, plan, values)

        dialog = make_dialog(
            title=t("plugins.market_configure", name=server.display_name),
            content=ft.Column(
                controls=controls,
                spacing=10,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                width=520,
                height=min(520, 90 + len(controls) * 72),
            ),
            actions=[
                make_text_button(t("common.cancel"), on_click=lambda e: page.pop_dialog()),
                make_button(
                    t("plugins.market_install"),
                    icon=ft.Icons.DOWNLOAD,
                    on_click=install,
                ),
            ],
        )
        page.show_dialog(dialog)

    def _finish_install(
        self,
        page: ft.Page,
        server: MarketMCPServer,
        plan: MCPInstallPlan,
        values: dict[str, str],
    ) -> None:
        service = self._get_service()
        if not service:
            return
        self._is_installing = True
        try:
            config = service.build_config(server, plan, values)
            success, message = self._on_install(plan.server_name, server, config)
        except Exception as exc:
            logger.warning("MCP market install failed: %s", exc)
            success = False
            message = t("plugins.market_install_failed", error=str(exc))
        finally:
            self._is_installing = False
        show_snackbar(page, message, bgcolor=ft.Colors.GREEN if success else None)
        if self._selected_server is server:
            self._preview.content = self._build_preview(server)
        self.state.update()
