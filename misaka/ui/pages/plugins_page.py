"""Plugins page.

MCP server management interface. Lists configured MCP servers,
allows adding/editing/removing them, and shows their status.
"""

from __future__ import annotations

import json
from pathlib import Path
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
    show_snackbar,
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
        self._mcp_config_sources: dict[str, Path] = {}
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
        home = Path.home()
        config_paths = [
            home / ".claude.json",
            home / ".claude" / "settings.json",
        ]

        self._mcp_configs = {}
        self._mcp_config_sources = {}
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, encoding="utf-8") as f:
                        data = json.load(f)
                    servers = data.get("mcpServers", {})
                    if isinstance(servers, dict):
                        for name, config in servers.items():
                            self._mcp_configs[name] = config
                            self._mcp_config_sources[name] = config_path
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

    def _is_sensitive_header(self, key: str) -> bool:
        """Check if a header key is sensitive and should be masked."""
        sensitive_keys = {
            "authorization",
            "x-api-key",
            "api-key",
            "apikey",
            "token",
            "secret",
            "cookie",
            "x-auth-token",
            "x-access-token",
        }
        return key.lower() in sensitive_keys

    def _build_header_row(
        self,
        key: str = "",
        value: str = "",
        on_delete: callable | None = None,
        on_change: callable | None = None,
    ) -> ft.Container:
        """Build a single header key-value row with delete button."""
        from misaka.ui.common.theme import make_text_field as _mtf

        key_field = _mtf(
            label=t("plugins.header_name"),
            value=key,
            expand=True,
            on_change=on_change,
        )

        is_sensitive = self._is_sensitive_header(key) if key else False
        value_field = _mtf(
            label=t("plugins.header_value"),
            value=value,
            expand=True,
            password=is_sensitive,
            can_reveal_password=is_sensitive,
            on_change=on_change,
        )

        delete_btn = make_icon_button(
            ft.Icons.DELETE_OUTLINE,
            tooltip=t("plugins.remove_header"),
            on_click=on_delete if on_delete else lambda e: None,
        )

        row = ft.Row(
            controls=[key_field, value_field, delete_btn],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Store references for later retrieval
        row.data = {"key_field": key_field, "value_field": value_field}

        return ft.Container(
            content=row,
            padding=ft.Padding.symmetric(vertical=4),
        )

    def _build_server_card(self, name: str, config: dict) -> ft.Control:
        server_type = config.get("type", "stdio")
        command = config.get("command", "")
        args = config.get("args", [])
        url = config.get("url", "")
        headers = config.get("headers", {})
        source_path = self._mcp_config_sources.get(name)

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

        badges = [
            make_badge(
                server_type.upper(),
                bgcolor=type_colors.get(server_type, "#6b7280"),
                size=9,
            ),
        ]

        if server_type in ("sse", "http") and headers:
            badges.append(
                make_badge(
                    t("plugins.header_count", count=len(headers)),
                    bgcolor="#8b5cf6",
                    size=9,
                ),
            )

        source_text = None
        if source_path is not None:
            source_text = source_path.name

        info_controls: list[ft.Control] = [
            ft.Row(
                controls=[
                    ft.Text(
                        name,
                        size=14,
                        weight=ft.FontWeight.W_600,
                    ),
                    *badges,
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
        ]
        if source_text:
            info_controls.append(
                ft.Text(
                    source_text,
                    size=10,
                    opacity=0.45,
                    italic=True,
                ),
            )

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
                    controls=info_controls,
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

        self._show_server_dialog(e.page, mode="add")

    def _show_server_dialog(
        self,
        page: ft.Page,
        mode: str = "add",
        existing_name: str = "",
        existing_config: dict[str, Any] | None = None,
    ) -> None:
        """Show add or edit dialog for MCP server with headers support."""
        from misaka.ui.common.theme import make_text_field as _mtf

        is_edit = mode == "edit"
        config = existing_config or {}
        initial_type = config.get("type", "stdio")
        if initial_type not in ("stdio", "sse", "http"):
            initial_type = "stdio"

        # Basic fields
        name_field = _mtf(
            label=t("plugins.server_name"),
            value=existing_name if is_edit else "",
            autofocus=True,
        )
        type_selector = ft.SegmentedButton(
            selected=[initial_type],
            allow_multiple_selection=False,
            segments=[
                ft.Segment(value="stdio", label=ft.Text("stdio")),
                ft.Segment(value="sse", label=ft.Text("sse")),
                ft.Segment(value="http", label=ft.Text("http")),
            ],
        )

        # Connection fields
        command_field = _mtf(label=t("plugins.command"), value=config.get("command", ""))
        args_field = _mtf(
            label=t("plugins.arguments"),
            value=" ".join(config.get("args", [])),
        )
        url_field = _mtf(label=t("plugins.url"), value=config.get("url", ""))

        # Headers section
        headers_container = ft.Column(spacing=8, visible=False)
        header_rows: list[ft.Container] = []
        error_text = ft.Text(color=ft.Colors.ERROR, size=11, visible=False)

        def add_header_row(key: str = "", value: str = ""):
            def on_delete(e):
                if row_container in header_rows:
                    header_rows.remove(row_container)
                    headers_container.controls.remove(row_container)
                    if page:
                        page.update()

            def on_change(e):
                # Update password field when key changes
                key_field = row_container.content.data["key_field"]
                value_field = row_container.content.data["value_field"]
                current_key = key_field.value or ""
                is_sensitive = self._is_sensitive_header(current_key)
                value_field.password = is_sensitive
                value_field.can_reveal_password = is_sensitive
                if page:
                    page.update()

            row_container = self._build_header_row(key, value, on_delete, on_change)
            header_rows.append(row_container)
            headers_container.controls.append(row_container)
            if page:
                page.update()

        def add_new_header(e):
            add_header_row()

        # Initialize existing headers
        for key, value in config.get("headers", {}).items():
            add_header_row(key, value)
        if not header_rows and initial_type in ("sse", "http"):
            add_header_row()

        add_header_btn = make_text_button(
            t("plugins.add_header"),
            icon=ft.Icons.ADD,
            on_click=add_new_header,
        )

        # Build sectioned form
        def show_error(message: str) -> None:
            error_text.value = message
            error_text.visible = True
            page.update()

        basic_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("plugins.basic_info"), size=13, weight=ft.FontWeight.W_600),
                    name_field,
                    ft.Text(t("plugins.transport_type"), size=12, opacity=0.8),
                    type_selector,
                ],
                spacing=12,
            ),
            padding=ft.Padding.only(bottom=16),
        )

        connection_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(t("plugins.connection_info"), size=13, weight=ft.FontWeight.W_600),
                    command_field,
                    args_field,
                    url_field,
                ],
                spacing=12,
            ),
            padding=ft.Padding.only(bottom=16),
        )

        headers_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(t("plugins.request_headers"), size=13, weight=ft.FontWeight.W_600),
                            ft.Container(expand=True),
                            add_header_btn,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    headers_container,
                ],
                spacing=12,
            ),
            visible=False,
        )

        # Update headers section visibility based on type
        dialog_ref: list[ft.AlertDialog | None] = [None]

        def update_sections_visibility(e=None):
            # SegmentedButton.selected 为列表，取第一个
            sel = type_selector.selected
            server_type = (sel[0] if sel else "stdio").strip()
            is_remote = server_type in ("sse", "http")
            command_field.visible = not is_remote
            args_field.visible = not is_remote
            url_field.visible = is_remote
            headers_section.visible = is_remote
            headers_container.visible = is_remote
            if is_remote and not header_rows:
                add_header_row()
            if page:
                # 显式更新对话框，确保 overlay 中的内容正确刷新
                if dialog_ref[0]:
                    page.update(dialog_ref[0])
                else:
                    page.update()

        type_selector.on_change = update_sections_visibility
        update_sections_visibility()

        def save(ev):
            error_text.visible = False
            name = (name_field.value or "").strip()
            if not name:
                show_error(t("plugins.validation_name_required"))
                return

            sel = type_selector.selected
            server_type = sel[0] if sel else "stdio"
            new_config: dict[str, Any] = {"type": server_type}

            if server_type == "stdio":
                command = (command_field.value or "").strip()
                if not command:
                    show_error(t("plugins.validation_command_required"))
                    return
                new_config["command"] = command
                args_text = args_field.value or ""
                new_config["args"] = args_text.split() if args_text.strip() else []
            else:
                url = (url_field.value or "").strip()
                if not url:
                    show_error(t("plugins.validation_url_required"))
                    return
                new_config["url"] = url

                headers: dict[str, str] = {}
                for row_container in header_rows:
                    key_field = row_container.content.data["key_field"]
                    value_field = row_container.content.data["value_field"]
                    key = (key_field.value or "").strip()
                    value = (value_field.value or "").strip()
                    if key:
                        headers[key] = value

                if headers:
                    new_config["headers"] = headers

            previous_configs = dict(self._mcp_configs)
            previous_sources = dict(self._mcp_config_sources)

            if is_edit and name != existing_name:
                self._mcp_configs.pop(existing_name, None)
                self._mcp_config_sources.pop(existing_name, None)

            self._mcp_configs[name] = new_config
            if is_edit and existing_name in previous_sources:
                self._mcp_config_sources[name] = previous_sources[existing_name]
            elif name not in self._mcp_config_sources:
                self._mcp_config_sources[name] = Path.home() / ".claude.json"

            success = self._save_and_verify_mcp_config(name)

            if success:
                show_snackbar(page, t("plugins.save_success"), bgcolor=ft.Colors.GREEN)
                page.pop_dialog()
                self.state.update()
                return

            self._mcp_configs = previous_configs
            self._mcp_config_sources = previous_sources
            show_error(t("plugins.save_failed"))

        dialog = make_dialog(
            title=t("plugins.edit_mcp_server") if is_edit else t("plugins.add_mcp_server"),
            content=ft.Column(
                controls=[basic_section, connection_section, headers_section, error_text],
                spacing=0,
                tight=True,
                width=500,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                make_text_button(
                    t("common.cancel"),
                    on_click=lambda ev: page.pop_dialog(),
                ),
                make_button(
                    t("common.save") if is_edit else t("plugins.add"),
                    on_click=save,
                ),
            ],
        )
        dialog_ref[0] = dialog
        page.show_dialog(dialog)

    def _show_edit_dialog(self, name: str) -> None:
        """Show edit dialog for an existing MCP server."""
        if not self.state.page:
            return

        config = self._mcp_configs.get(name)
        if not config:
            return

        self._show_server_dialog(
            self.state.page,
            mode="edit",
            existing_name=name,
            existing_config=config,
        )

    def _remove_server(self, name: str) -> None:
        if name in self._mcp_configs:
            target_path = self._mcp_config_sources.get(name, Path.home() / ".claude.json")
            del self._mcp_configs[name]
            self._mcp_config_sources.pop(name, None)
            self._save_mcp_config(target_path)
            self._load_mcp_config()
            self._refresh_server_list()
            self.state.update()

    def _save_mcp_config(self, target_path: Path | None = None) -> None:
        """Save MCP config back to the target Claude config file."""
        config_path = target_path or (Path.home() / ".claude.json")
        data = {}
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        else:
            config_path.parent.mkdir(parents=True, exist_ok=True)

        current_data = data.get("mcpServers", {}) if isinstance(data.get("mcpServers", {}), dict) else {}
        owned_servers = {
            name: config
            for name, config in self._mcp_configs.items()
            if self._mcp_config_sources.get(name, Path.home() / ".claude.json") == config_path
        }
        data["mcpServers"] = {**current_data, **owned_servers}
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def _save_and_verify_mcp_config(self, server_name: str) -> bool:
        """Save MCP config, reload from file, and verify the server exists."""
        target_path = self._mcp_config_sources.get(server_name, Path.home() / ".claude.json")
        expected_config = self._mcp_configs.get(server_name)
        if expected_config is None:
            return False

        self._save_mcp_config(target_path)
        self._load_mcp_config()

        reloaded_config = self._mcp_configs.get(server_name)
        if reloaded_config != expected_config:
            return False
        if self._mcp_config_sources.get(server_name) != target_path:
            return False

        self._refresh_server_list()
        return True

    def _reload_config(self, e: ft.ControlEvent) -> None:
        self._load_mcp_config()
        self._refresh_server_list()
        self.state.update()

    def refresh(self) -> None:
        """Rebuild the plugins page."""
        self._build_ui()
