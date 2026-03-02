"""Plugins page.

MCP server management interface. Lists configured MCP servers,
allows adding/editing/removing them, and shows their status.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    MONO_FONT_FAMILY,
    make_badge,
    make_button,
    make_dialog,
    make_divider,
    make_icon_button,
    make_text_button,
)

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState


class PluginsPage(ft.Column):
    """MCP plugins management page."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend | None = None,
    ) -> None:
        super().__init__(
            spacing=0,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
        self.state = state
        self.db = db
        self._mcp_configs: dict[str, Any] = {}
        self._server_list: ft.Column | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        # Load MCP config
        self._load_mcp_config()

        header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        t("plugins.title"),
                        size=22,
                        weight=ft.FontWeight.W_600,
                        expand=True,
                    ),
                    make_button(
                        t("plugins.add_server"),
                        icon=ft.Icons.ADD,
                        on_click=self._show_add_dialog,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=24, right=24, top=20, bottom=8),
        )

        description = ft.Container(
            content=ft.Text(
                t("plugins.description"),
                size=12,
                opacity=0.6,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=4),
        )

        self._server_list = ft.Column(spacing=8)
        self._refresh_server_list()

        server_container = ft.Container(
            content=self._server_list,
            padding=ft.Padding.symmetric(horizontal=24, vertical=12),
        )

        # Config file info
        config_info = ft.Container(
            content=ft.Column(
                controls=[
                    make_divider(),
                    ft.Text(
                        t("plugins.config_files"),
                        size=14,
                        weight=ft.FontWeight.W_500,
                    ),
                    ft.Text(
                        t("plugins.config_files_desc"),
                        size=12,
                        opacity=0.6,
                        font_family=MONO_FONT_FAMILY,
                    ),
                    make_button(
                        t("plugins.reload_config"),
                        icon=ft.Icons.REFRESH,
                        on_click=self._reload_config,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=16),
        )

        self.controls = [header, description, ft.Divider(height=1), server_container, config_info]

    def _load_mcp_config(self) -> None:
        """Load MCP server configurations from settings files."""
        from pathlib import Path

        home = Path.home()
        config_paths = [
            home / ".claude.json",
            home / ".claude" / "settings.json",
        ]

        self._mcp_configs = {}
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, encoding="utf-8") as f:
                        data = json.load(f)
                    servers = data.get("mcpServers", {})
                    if isinstance(servers, dict):
                        self._mcp_configs.update(servers)
                except (json.JSONDecodeError, OSError):
                    pass

    def _refresh_server_list(self) -> None:
        if not self._server_list:
            return

        if not self._mcp_configs:
            self._server_list.controls = [
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.EXTENSION_OFF, size=40, opacity=0.3),
                            ft.Text(
                                t("plugins.no_servers"),
                                size=14,
                                opacity=0.5,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Text(
                                t("plugins.no_servers_hint"),
                                size=12,
                                opacity=0.3,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=32,
                )
            ]
            return

        self._server_list.controls = [
            self._build_server_card(name, config)
            for name, config in self._mcp_configs.items()
        ]

    def _build_server_card(self, name: str, config: dict) -> ft.Control:
        server_type = config.get("type", "stdio")
        command = config.get("command", "")
        args = config.get("args", [])
        url = config.get("url", "")

        # Build detail text
        if server_type == "stdio":
            detail = f"Command: {command} {' '.join(args)}"
        elif server_type in ("sse", "http"):
            detail = f"URL: {url}"
        else:
            detail = f"Type: {server_type}"

        type_colors = {
            "stdio": "#2563eb",
            "sse": "#f59e0b",
            "http": "#10b981",
        }

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.EXTENSION, size=20, color=ft.Colors.PRIMARY),
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        name,
                                        size=14,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    make_badge(
                                        server_type.upper(),
                                        bgcolor=type_colors.get(server_type, "#6b7280"),
                                        size=9,
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Text(
                                detail,
                                size=11,
                                opacity=0.6,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    make_icon_button(
                        ft.Icons.DELETE_OUTLINE,
                        tooltip=t("plugins.remove"),
                        on_click=lambda e, n=name: self._remove_server(n),
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=14,
            border_radius=12,
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
        )

    def _show_add_dialog(self, e: ft.ControlEvent) -> None:
        if not e.page:
            return

        from misaka.ui.common.theme import make_dropdown as _mdd
        from misaka.ui.common.theme import make_text_field as _mtf
        name_field = _mtf(label=t("plugins.server_name"), autofocus=True)
        type_dropdown = _mdd(
            label=t("plugins.transport_type"),
            value="stdio",
            options=[
                ft.dropdown.Option("stdio"),
                ft.dropdown.Option("sse"),
                ft.dropdown.Option("http"),
            ],
        )
        command_field = _mtf(label=t("plugins.command"))
        args_field = _mtf(label=t("plugins.arguments"))
        url_field = _mtf(label=t("plugins.url"))

        def save(ev):
            name = (name_field.value or "").strip()
            if not name:
                return

            server_type = type_dropdown.value or "stdio"
            config: dict[str, Any] = {"type": server_type}

            if server_type == "stdio":
                config["command"] = command_field.value or ""
                config["args"] = (args_field.value or "").split()
            else:
                config["url"] = url_field.value or ""

            self._mcp_configs[name] = config
            self._save_mcp_config()
            self._refresh_server_list()
            e.page.pop_dialog()
            self.state.update()

        dialog = make_dialog(
            title=t("plugins.add_mcp_server"),
            content=ft.Column(
                controls=[name_field, type_dropdown, command_field, args_field, url_field],
                spacing=12,
                tight=True,
                width=400,
            ),
            actions=[
                make_text_button(
                    t("common.cancel"), on_click=lambda ev: e.page.pop_dialog(),
                ),
                make_button(t("plugins.add"), on_click=save),
            ],
        )
        e.page.show_dialog(dialog)

    def _remove_server(self, name: str) -> None:
        if name in self._mcp_configs:
            del self._mcp_configs[name]
            self._save_mcp_config()
            self._refresh_server_list()
            self.state.update()

    def _save_mcp_config(self) -> None:
        """Save MCP config back to ~/.claude.json."""
        from pathlib import Path

        config_path = Path.home() / ".claude.json"
        data = {}
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        data["mcpServers"] = self._mcp_configs
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def _reload_config(self, e: ft.ControlEvent) -> None:
        self._load_mcp_config()
        self._refresh_server_list()
        self.state.update()

    def refresh(self) -> None:
        """Rebuild the plugins page."""
        self._build_ui()
