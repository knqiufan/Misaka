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
    RADIUS_LG,
    RADIUS_XL,
    make_badge,
    make_button,
    make_dialog,
    make_divider,
    make_empty_state,
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

        header = self._build_header()
        self._server_list = ft.Column(spacing=10)
        self._refresh_server_list()
        server_container = self._build_server_container()
        config_info = self._build_config_info()

        inner = ft.Column(
            controls=[header, make_divider(), server_container, config_info],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        main_card = ft.Container(
            content=inner,
            margin=ft.Margin.symmetric(horizontal=20, vertical=16),
            padding=ft.Padding.all(28),
            expand=True,
            border_radius=RADIUS_XL,
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
        """Build page header with title and add button."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(
                            ft.Icons.EXTENSION,
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
                                t("plugins.title"),
                                size=20,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                t("plugins.description"),
                                size=12,
                                opacity=0.65,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    make_button(
                        t("plugins.add_server"),
                        icon=ft.Icons.ADD,
                        on_click=self._show_add_dialog,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
            padding=ft.Padding.only(bottom=20),
        )

    def _build_server_container(self) -> ft.Container:
        """Build server list container."""
        return ft.Container(
            content=self._server_list,
            padding=ft.Padding.symmetric(vertical=16),
        )

    def _build_config_info(self) -> ft.Container:
        """Build config files info block with card style."""
        config_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.FOLDER_OPEN,
                                size=18,
                                color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE),
                            ),
                            ft.Text(
                                t("plugins.config_files"),
                                size=13,
                                weight=ft.FontWeight.W_500,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Container(
                        content=ft.Text(
                            t("plugins.config_files_desc"),
                            size=11,
                            opacity=0.6,
                            font_family=MONO_FONT_FAMILY,
                        ),
                        padding=ft.Padding.only(top=6),
                    ),
                    ft.Container(
                        content=make_button(
                            t("plugins.reload_config"),
                            icon=ft.Icons.REFRESH,
                            on_click=self._reload_config,
                        ),
                        padding=ft.Padding.only(top=12),
                    ),
                ],
                spacing=0,
            ),
            padding=ft.Padding.all(16),
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
        )
        return ft.Container(content=config_content, padding=ft.Padding.only(top=8))

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
            empty = make_empty_state(
                ft.Icons.EXTENSION_OFF,
                t("plugins.no_servers"),
                hint=t("plugins.no_servers_hint"),
                icon_size=48,
                icon_opacity=0.25,
            )
            self._server_list.controls = [
                ft.Container(
                    content=empty,
                    padding=ft.Padding.symmetric(vertical=40, horizontal=24),
                    border_radius=RADIUS_LG,
                    bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
                    border=ft.Border.all(
                        1,
                        ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
                    ),
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

        card_content = ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(ft.Icons.EXTENSION, size=22, color=ft.Colors.PRIMARY),
                    width=40,
                    height=40,
                    border_radius=RADIUS_LG,
                    bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text(
                                    name,
                                    size=14,
                                    weight=ft.FontWeight.W_600,
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
                            opacity=0.65,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=4,
                    expand=True,
                ),
                make_icon_button(
                    ft.Icons.EDIT_OUTLINED,
                    tooltip=t("plugins.edit"),
                    on_click=lambda e, n=name: self._show_edit_dialog(n),
                ),
                make_icon_button(
                    ft.Icons.DELETE_OUTLINE,
                    tooltip=t("plugins.remove"),
                    on_click=lambda e, n=name: self._remove_server(n),
                ),
            ],
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Container(
            content=card_content,
            padding=ft.Padding.symmetric(horizontal=16, vertical=14),
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            ),
            shadow=[
                ft.BoxShadow(
                    blur_radius=12,
                    spread_radius=-2,
                    color=ft.Colors.with_opacity(0.05, ft.Colors.BLACK),
                    offset=ft.Offset(0, 2),
                ),
            ],
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

    def _show_edit_dialog(self, name: str) -> None:
        """Show edit dialog for an existing MCP server."""
        if not self.state.page:
            return

        config = self._mcp_configs.get(name)
        if not config:
            return

        from misaka.ui.common.theme import make_dropdown as _mdd
        from misaka.ui.common.theme import make_text_field as _mtf
        name_field = _mtf(label=t("plugins.server_name"), value=name, autofocus=True)
        type_dropdown = _mdd(
            label=t("plugins.transport_type"),
            value=config.get("type", "stdio"),
            options=[
                ft.dropdown.Option("stdio"),
                ft.dropdown.Option("sse"),
                ft.dropdown.Option("http"),
            ],
        )
        command_field = _mtf(label=t("plugins.command"), value=config.get("command", ""))
        args_field = _mtf(label=t("plugins.arguments"), value=" ".join(config.get("args", [])))
        url_field = _mtf(label=t("plugins.url"), value=config.get("url", ""))

        def save(ev):
            new_name = (name_field.value or "").strip()
            if not new_name:
                return

            server_type = type_dropdown.value or "stdio"
            new_config: dict[str, Any] = {"type": server_type}

            if server_type == "stdio":
                new_config["command"] = command_field.value or ""
                new_config["args"] = (args_field.value or "").split()
            else:
                new_config["url"] = url_field.value or ""

            # Remove old entry if name changed
            if new_name != name:
                del self._mcp_configs[name]
            self._mcp_configs[new_name] = new_config
            self._save_mcp_config()
            self._refresh_server_list()
            self.state.page.pop_dialog()
            self.state.update()

        dialog = make_dialog(
            title=t("plugins.edit_mcp_server"),
            content=ft.Column(
                controls=[name_field, type_dropdown, command_field, args_field, url_field],
                spacing=12,
                tight=True,
                width=400,
            ),
            actions=[
                make_text_button(
                    t("common.cancel"), on_click=lambda ev: self.state.page.pop_dialog(),
                ),
                make_button(t("common.save"), on_click=save),
            ],
        )
        self.state.page.show_dialog(dialog)

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
