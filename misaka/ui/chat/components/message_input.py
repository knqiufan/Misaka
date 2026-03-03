"""Message input component.

Multi-line text input area with send button, file attachment support,
slash-command menu, @ file picker overlay, and keyboard shortcut handling.
Supports Shift+Enter for newline and Enter to send.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.commands import SlashCommand, filter_commands
from misaka.db.models import FileTreeNode
from misaka.i18n import t
from misaka.ui.common.theme import MONO_FONT_FAMILY

if TYPE_CHECKING:
    from misaka.state import AppState

_FOLDER_COLOR = "#f59e0b"
_MAX_FILE_RESULTS = 15


class MessageInput(ft.Container):
    """Message input area with send/stop button, file attachment, and slash commands."""

    def __init__(
        self,
        state: AppState,
        on_send: Callable[[str], None] | None = None,
        on_abort: Callable[[], None] | None = None,
        on_command: Callable[[str], None] | None = None,
        on_model_change: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self._on_send = on_send
        self._on_abort = on_abort
        self._on_command = on_command
        self._on_model_change = on_model_change
        self._text_field: ft.TextField | None = None
        self._send_btn: ft.IconButton | None = None
        self._command_menu: ft.Column | None = None
        self._command_menu_container: ft.Container | None = None
        self._input_shell: ft.Container | None = None
        self._badge_container: ft.Container | None = None
        self._model_indicator: ft.Container | None = None
        self._active_badge: SlashCommand | None = None
        self._file_menu: ft.Column | None = None
        self._file_menu_container: ft.Container | None = None
        self._at_start_pos: int = -1
        self._file_menu_active: bool = False
        self._suppress_focus_close: bool = False
        self._build_ui()

    async def _do_focus(self) -> None:
        """Async focus on text field. Used by _schedule_focus."""
        if self._text_field:
            await self._text_field.focus()

    def _schedule_focus(self, page: ft.Page | None = None) -> None:
        """Schedule async focus on text field. Safe to call from sync handlers."""
        if not self._text_field:
            return
        p = page or getattr(self, "page", None)
        if p:
            p.run_task(self._do_focus)

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        from misaka.ui.common.theme import make_text_field as _mtf
        self._text_field = _mtf(
            hint_text=t("chat.type_message"),
            expand=True,
            multiline=True,
            min_lines=1,
            max_lines=6,
            shift_enter=True,
            on_submit=self._handle_send,
            on_change=self._handle_text_change,
            on_focus=self._handle_focus,
            border=ft.InputBorder.NONE,
            border_radius=0,
            border_width=0,
            filled=False,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=10),
            text_size=13,
        )

        is_streaming = self.state.is_streaming

        self._send_btn = ft.IconButton(
            icon=(
                ft.Icons.STOP_CIRCLE_ROUNDED
                if is_streaming
                else ft.Icons.SEND_ROUNDED
            ),
            tooltip=t("chat.stop") if is_streaming else t("chat.send"),
            on_click=self._handle_action,
            icon_color=ft.Colors.WHITE,
            bgcolor=ft.Colors.ERROR if is_streaming else ft.Colors.PRIMARY,
            icon_size=20,
            style=ft.ButtonStyle(shape=ft.CircleBorder(), padding=8),
        )

        attach_btn = self._build_utility_button(
            icon=ft.Icons.ATTACH_FILE_ROUNDED,
            tooltip=t("chat.attach_file"),
            on_click=self._handle_attach,
        )

        command_btn = self._build_utility_button(
            icon=ft.Icons.TERMINAL_ROUNDED,
            tooltip=t("chat.command_menu"),
            on_click=self._toggle_command_menu,
        )

        self._command_menu = ft.Column(spacing=0, tight=True)
        self._command_menu_container = ft.Container(
            content=self._command_menu,
            visible=False,
            border_radius=14,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE)),
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            padding=ft.Padding.symmetric(vertical=6),
            width=360,
            margin=ft.Margin.only(left=52, bottom=8),
            shadow=ft.BoxShadow(
                blur_radius=16,
                spread_radius=-2,
                offset=ft.Offset(0, 6),
                color=ft.Colors.with_opacity(0.16, ft.Colors.BLACK),
            ),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        # File menu for @ file picking
        self._file_menu = ft.Column(spacing=0, tight=True)
        self._file_menu_container = ft.Container(
            content=self._file_menu,
            visible=False,
            border_radius=14,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE)),
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            padding=ft.Padding.symmetric(vertical=6),
            width=360,
            margin=ft.Margin.only(left=52, bottom=8),
            shadow=ft.BoxShadow(
                blur_radius=16,
                spread_radius=-2,
                offset=ft.Offset(0, 6),
                color=ft.Colors.with_opacity(0.16, ft.Colors.BLACK),
            ),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        self._badge_container = ft.Container(visible=False)

        self._model_indicator = self._build_model_indicator()

        input_row = ft.Row(
            controls=[attach_btn, command_btn, self._model_indicator,
                      self._badge_container, self._text_field, self._send_btn],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._input_shell = ft.Container(
            content=input_row,
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=18,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.10, ft.Colors.ON_SURFACE)),
            on_click=self._handle_shell_click,
        )

        self.content = ft.Column(
            controls=[self._command_menu_container, self._file_menu_container, self._input_shell],
            spacing=0,
            tight=True,
        )
        self.padding = ft.Padding.symmetric(horizontal=12, vertical=8)

    @staticmethod
    def _build_utility_button(
        *,
        icon: str,
        tooltip: str,
        on_click: object,
    ) -> ft.Container:
        """Build modern utility icon button for input tools."""
        return ft.Container(
            content=ft.IconButton(
                icon=icon,
                tooltip=tooltip,
                on_click=on_click,
                icon_size=16,
                style=ft.ButtonStyle(
                    shape=ft.CircleBorder(),
                    padding=6,
                    overlay_color=ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY),
                ),
            ),
            width=36,
            height=36,
            alignment=ft.Alignment.CENTER,
            border_radius=20,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
        )

    # ------------------------------------------------------------------
    # Slash-command menu
    # ------------------------------------------------------------------

    def _handle_text_change(self, e: ft.ControlEvent) -> None:
        """Detect '/' prefix or '@' for commands and file picking."""
        value = e.data or ""

        self._detect_at_file_picker(value)

        if value.startswith("/"):
            matches = filter_commands(value[1:])
            self._show_command_menu(matches)
        else:
            self._hide_command_menu()

    def _handle_focus(self, e: ft.ControlEvent) -> None:
        """Close file menu when the text field regains focus (e.g. user clicks inside)."""
        if self._suppress_focus_close:
            self._suppress_focus_close = False
            return
        if self._file_menu_active:
            self._hide_file_menu()

    def _handle_shell_click(self, e: ft.ControlEvent) -> None:
        """Close file menu when the input shell area is clicked."""
        if self._file_menu_active:
            self._hide_file_menu()

    def _show_command_menu(self, commands: list[SlashCommand]) -> None:
        if not self._command_menu or not self._command_menu_container:
            return
        if not commands:
            self._hide_command_menu()
            return

        items: list[ft.Control] = []
        for cmd in commands:
            items.append(self._build_command_item(cmd))

        self._command_menu.controls = items
        self._command_menu_container.visible = True
        self._command_menu_container.update()

    def _toggle_command_menu(self, e: ft.ControlEvent) -> None:
        """Toggle command menu when clicking the command button."""
        if self._command_menu_container and self._command_menu_container.visible:
            self._hide_command_menu()
            return
        self._show_command_menu(filter_commands(""))
        self._schedule_focus(e.page if e else None)

    def _hide_command_menu(self) -> None:
        if self._command_menu_container and self._command_menu_container.visible:
            self._command_menu_container.visible = False
            self._command_menu_container.update()

    def _build_command_item(self, cmd: SlashCommand) -> ft.Control:
        """Build a single command row for the popup menu."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(cmd.icon, size=15, opacity=0.5),
                    ft.Text(
                        f"/{cmd.name}",
                        size=12,
                        weight=ft.FontWeight.W_500,
                        font_family=MONO_FONT_FAMILY,
                    ),
                    ft.Text(
                        cmd.description,
                        size=11,
                        opacity=0.4,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            on_click=lambda e, c=cmd: self._select_command(c),
            ink=True,
        )

    def _select_command(self, cmd: SlashCommand) -> None:
        """Handle selection of a slash command from the menu."""
        self._hide_command_menu()

        if cmd.name == "model":
            if self._text_field:
                self._text_field.value = ""
                self._text_field.update()
            self._show_model_menu()
            return

        if cmd.immediate:
            if self._text_field:
                self._text_field.value = ""
                self._text_field.update()
            if self._on_command:
                self._on_command(f"/{cmd.name}")
        else:
            self._set_badge(cmd)
            if self._text_field:
                self._text_field.value = ""
                self._text_field.update()
                self._schedule_focus()

    # ------------------------------------------------------------------
    # File menu (@ file picking)
    # ------------------------------------------------------------------

    def _detect_at_file_picker(self, value: str) -> None:
        """Detect @ token and show/hide the file picker overlay."""
        at_pos = self._find_active_at(value)
        if at_pos < 0:
            if self._file_menu_active:
                self._hide_file_menu()
            return

        query = value[at_pos + 1:]
        if " " in query or "\n" in query:
            if self._file_menu_active:
                self._hide_file_menu()
            return

        self._at_start_pos = at_pos
        self._file_menu_active = True
        self._show_file_menu(query)

    @staticmethod
    def _find_active_at(text: str) -> int:
        """Find the position of the last valid @ trigger in *text*.

        A valid @ is either at position 0 or preceded by whitespace.
        Returns -1 if none found.
        """
        pos = len(text)
        while pos > 0:
            pos = text.rfind("@", 0, pos)
            if pos < 0:
                return -1
            if pos == 0 or text[pos - 1] in " \n\t":
                return pos
        return -1

    def _show_file_menu(self, query: str) -> None:
        """Show the file picking overlay with filtered results."""
        if not self._file_menu or not self._file_menu_container:
            return

        nodes = self._resolve_file_nodes(query)
        if nodes is None:
            self._render_file_menu_items([])
            return
        self._render_file_menu_items(nodes)

    def _resolve_file_nodes(self, query: str) -> list[FileTreeNode] | None:
        """Resolve visible file nodes based on the query path.

        Supports incremental navigation:
        - "" → show top-level nodes
        - "mis" → filter top-level nodes by "mis"
        - "misaka\\" → show children of "misaka" folder
        - "misaka\\ui\\" → show children of misaka/ui folder
        - "misaka\\ui\\ch" → filter children of misaka/ui by "ch"
        """
        root_nodes = self._get_root_nodes()
        if not root_nodes:
            return None

        normalized = query.replace("/", "\\")
        segments = normalized.split("\\")

        current_nodes = root_nodes
        for i, segment in enumerate(segments):
            is_last = i == len(segments) - 1
            if is_last:
                return self._filter_nodes_by_name(current_nodes, segment)
            matched_dir = self._find_directory_node(current_nodes, segment)
            if matched_dir is None:
                return []
            current_nodes = matched_dir.children or []
        return current_nodes

    def _get_root_nodes(self) -> list[FileTreeNode]:
        """Get the top-level file tree nodes from state."""
        raw_nodes = self.state.file_tree_nodes or []
        result: list[FileTreeNode] = []
        for node in raw_nodes:
            if isinstance(node, FileTreeNode):
                result.append(node)
        return result

    @staticmethod
    def _filter_nodes_by_name(
        nodes: list[FileTreeNode],
        fragment: str,
    ) -> list[FileTreeNode]:
        """Filter nodes whose name contains *fragment* (case-insensitive)."""
        if not fragment:
            return nodes[:_MAX_FILE_RESULTS]
        frag_lower = fragment.lower()
        return [n for n in nodes if frag_lower in n.name.lower()][:_MAX_FILE_RESULTS]

    @staticmethod
    def _find_directory_node(
        nodes: list[FileTreeNode],
        name: str,
    ) -> FileTreeNode | None:
        """Find a directory node by exact name (case-insensitive)."""
        name_lower = name.lower()
        for n in nodes:
            if n.type == "directory" and n.name.lower() == name_lower:
                return n
        return None

    def _render_file_menu_items(self, nodes: list[FileTreeNode]) -> None:
        """Render file items into the overlay menu."""
        if not self._file_menu or not self._file_menu_container:
            return
        if not nodes:
            self._file_menu.controls = [
                ft.Container(
                    content=ft.Text(
                        t("right_panel.no_files"), size=12, opacity=0.5,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                )
            ]
        else:
            self._file_menu.controls = [
                self._build_file_item(n) for n in nodes
            ]
        self._file_menu_container.visible = True
        self._file_menu_container.update()
        if self._text_field:
            self._suppress_focus_close = True
            self._schedule_focus()

    def _build_file_item(self, node: FileTreeNode) -> ft.Control:
        """Build a single file row for the popup menu."""
        is_dir = node.type == "directory"
        icon = ft.Icons.FOLDER_ROUNDED if is_dir else ft.Icons.DESCRIPTION_OUTLINED
        icon_color = _FOLDER_COLOR if is_dir else "#94a3b8"

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, size=15, color=icon_color),
                    ft.Text(
                        node.name,
                        size=12,
                        weight=ft.FontWeight.W_500,
                        expand=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Icon(
                        ft.Icons.CHEVRON_RIGHT,
                        size=14,
                        opacity=0.3,
                        visible=is_dir,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            on_click=lambda e, n=node: self._select_file_node(n),
            ink=True,
        )

    def _select_file_node(self, node: FileTreeNode) -> None:
        """Handle file/folder selection from the file menu."""
        if not self._text_field:
            return
        text = self._text_field.value or ""

        if self._at_start_pos < 0 or self._at_start_pos >= len(text):
            return

        before = text[:self._at_start_pos]
        old_query = text[self._at_start_pos + 1:]

        if node.type == "directory":
            new_query = self._build_dir_query(old_query, node.name)
            self._text_field.value = f"{before}@{new_query}"
            self._text_field.update()
            self._suppress_focus_close = True
            self._schedule_focus()
            self._show_file_menu(new_query)
            return

        self._text_field.value = f"{before}@{node.path} "
        self._text_field.update()
        self._schedule_focus()
        self._hide_file_menu()

    @staticmethod
    def _build_dir_query(old_query: str, dir_name: str) -> str:
        """Build the new query string after selecting a directory.

        Examples:
            old_query="mis", dir_name="misaka" → "misaka\\"
            old_query="misaka\\u", dir_name="ui" → "misaka\\ui\\"
        """
        normalized = old_query.replace("/", "\\")
        parts = normalized.split("\\")
        parts[-1] = dir_name
        return "\\".join(parts) + "\\"

    def _hide_file_menu(self) -> None:
        """Hide the file picker overlay and reset state."""
        self._file_menu_active = False
        self._at_start_pos = -1
        if self._file_menu_container and self._file_menu_container.visible:
            self._file_menu_container.visible = False
            self._file_menu_container.update()

    # ------------------------------------------------------------------
    # Insert file path from external source (right-click menu)
    # ------------------------------------------------------------------

    def insert_at_symbol(self, path: str) -> None:
        """Insert a file path prefixed with @ into the input field.

        Trailing space prevents the @ file picker from re-activating.
        """
        if not self._text_field:
            return

        current = self._text_field.value or ""
        separator = " " if current and not current.endswith((" ", "\n")) else ""
        self._text_field.value = f"{current}{separator}@{path} "
        self._text_field.update()
        self._suppress_focus_close = True
        self._schedule_focus()

    # ------------------------------------------------------------------
    # Model sub-menu
    # ------------------------------------------------------------------

    def _get_model_options(self) -> list[tuple[str, str]]:
        """Read model names from settings and build option list."""
        options: list[tuple[str, str]] = [("default", "Default")]
        cli_svc = self.state.get_service("cli_settings_service")
        if cli_svc:
            settings = cli_svc.read_settings()
            env = settings.get("env", {})
            sonnet = env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "Sonnet")
            opus = env.get("ANTHROPIC_DEFAULT_OPUS_MODEL", "Opus")
            haiku = env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "Haiku")
            main = env.get("ANTHROPIC_MODEL", "")
            if main and main != options[0][1]:
                options[0] = ("default", f"Default ({main})")
            options.append(("sonnet", sonnet if sonnet != "Sonnet" else "Sonnet"))
            options.append(("opus", opus if opus != "Opus" else "Opus"))
            options.append(("haiku", haiku if haiku != "Haiku" else "Haiku"))
            return options
        options.extend([("sonnet", "Sonnet"), ("opus", "Opus"), ("haiku", "Haiku")])
        return options

    def _show_model_menu(self) -> None:
        """Show a second-level menu for model selection."""
        if not self._command_menu or not self._command_menu_container:
            return

        options = self._get_model_options()
        current = self.state.selected_model

        items: list[ft.Control] = []
        for value, label in options:
            is_selected = value == current
            items.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.CHECK_ROUNDED if is_selected else ft.Icons.CIRCLE,
                                size=13,
                                opacity=1.0 if is_selected else 0.2,
                                color=ft.Colors.PRIMARY if is_selected else None,
                            ),
                            ft.Text(
                                label,
                                size=12,
                                weight=(
                                    ft.FontWeight.W_500
                                    if is_selected
                                    else ft.FontWeight.NORMAL
                                ),
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                    on_click=lambda e, v=value: self._select_model(v),
                    ink=True,
                )
            )

        self._command_menu.controls = items
        self._command_menu_container.visible = True
        self._command_menu_container.update()

    def _select_model(self, model: str) -> None:
        """Handle model selection from the sub-menu."""
        self._hide_command_menu()
        self.state.selected_model = model
        self._refresh_model_indicator()
        if self._on_model_change:
            self._on_model_change(model)

    def _build_model_indicator(self) -> ft.Container:
        """Build a small badge showing the currently selected model."""
        model = self.state.selected_model
        if model == "default":
            return ft.Container(visible=False)

        label = model.capitalize()
        return ft.Container(
            content=ft.Text(
                label,
                size=10,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.PRIMARY,
            ),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.PRIMARY)),
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        )

    def _refresh_model_indicator(self) -> None:
        """Update the model indicator badge."""
        if not self._model_indicator:
            return
        model = self.state.selected_model
        if model == "default":
            self._model_indicator.visible = False
            self._model_indicator.content = None
        else:
            self._model_indicator.visible = True
            self._model_indicator.content = ft.Text(
                model.capitalize(),
                size=10,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.PRIMARY,
            )
            self._model_indicator.border = ft.Border.all(
                1, ft.Colors.with_opacity(0.2, ft.Colors.PRIMARY),
            )
            self._model_indicator.border_radius = 6
            self._model_indicator.padding = ft.Padding.symmetric(
                horizontal=6, vertical=2
            )
        with contextlib.suppress(Exception):
            self._model_indicator.update()

    # ------------------------------------------------------------------
    # Badge (non-immediate commands)
    # ------------------------------------------------------------------

    def _set_badge(self, cmd: SlashCommand) -> None:
        """Show a command badge before the input field."""
        self._active_badge = cmd
        if not self._badge_container:
            return
        self._badge_container.content = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(cmd.icon, size=13, color=ft.Colors.WHITE),
                    ft.Text(
                        f"/{cmd.name}",
                        size=11,
                        weight=ft.FontWeight.W_500,
                        color=ft.Colors.WHITE,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE_ROUNDED,
                        icon_size=12,
                        icon_color=ft.Colors.WHITE,
                        on_click=lambda e: self._remove_badge(),
                        style=ft.ButtonStyle(padding=0),
                    ),
                ],
                spacing=4,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=ft.Colors.PRIMARY,
            border_radius=8,
            padding=ft.Padding.only(left=8, right=2, top=4, bottom=4),
        )
        self._badge_container.visible = True
        self._badge_container.update()

    def _remove_badge(self) -> None:
        """Remove the active command badge."""
        self._active_badge = None
        if self._badge_container:
            self._badge_container.visible = False
            self._badge_container.content = ft.Container()
            self._badge_container.update()

    # ------------------------------------------------------------------
    # Send / action handling
    # ------------------------------------------------------------------

    def _handle_action(self, e: ft.ControlEvent) -> None:
        if self.state.is_streaming:
            if self._on_abort:
                self._on_abort()
        else:
            self._handle_send(e)

    def _handle_send(self, e: ft.ControlEvent) -> None:
        if not self._text_field:
            return

        user_text = (self._text_field.value or "").strip()

        if self._active_badge:
            badge = self._active_badge
            self._remove_badge()
            prompt = badge.prompt
            if user_text:
                prompt = f"{prompt}\n\nUser context: {user_text}"
            self._text_field.value = ""
            self._text_field.update()
            if self._on_send and prompt:
                self._on_send(prompt)
            return

        if not user_text:
            return

        self._text_field.value = ""
        self._text_field.update()
        self._hide_command_menu()
        self._hide_file_menu()
        if self._on_send:
            self._on_send(user_text)

    def _handle_attach(self, e: ft.ControlEvent) -> None:
        """Open a manual file-path dialog (stable fallback UX)."""
        page = getattr(self.state, "page", None)
        if not page:
            return

        from misaka.ui.common.theme import make_button, make_dialog, make_text_button

        path_field = ft.TextField(
            label=t("chat.attach_file"),
            hint_text="C:/path/to/file.txt\nD:/path/to/image.png",
            multiline=True,
            min_lines=3,
            max_lines=6,
            autofocus=True,
        )

        def do_confirm(ev: ft.ControlEvent) -> None:
            raw = (path_field.value or "").strip()
            if not raw:
                return
            parts = raw.replace(";", "\n").splitlines()
            paths = [p.strip().strip('"') for p in parts if p.strip()]
            self._append_file_paths(paths)
            page.pop_dialog()
            self._schedule_focus(page)

        dialog = make_dialog(
            title=t("chat.attach_file"),
            content=ft.Column(
                controls=[
                    ft.Text("输入文件绝对路径，可多行粘贴或使用分号分隔。", size=12, opacity=0.7),
                    path_field,
                ],
                spacing=12,
                tight=True,
                width=460,
            ),
            actions=[
                make_text_button(t("common.cancel"), on_click=lambda ev: page.pop_dialog()),
                make_button(t("common.confirm"), on_click=do_confirm),
            ],
            modal=True,
        )
        page.show_dialog(dialog)

    def _append_file_paths(self, paths: list[str]) -> None:
        """Append selected file markers into input box."""
        if not paths or not self._text_field:
            return
        for path in paths:
            current = self._text_field.value or ""
            separator = "\n" if current else ""
            self._text_field.value = f"{current}{separator}[File: {path}]"
        self._text_field.update()

    # ------------------------------------------------------------------
    # Refresh / focus
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        if self._send_btn:
            is_streaming = self.state.is_streaming
            self._send_btn.icon = (
                ft.Icons.STOP_CIRCLE_ROUNDED if is_streaming else ft.Icons.SEND_ROUNDED
            )
            self._send_btn.tooltip = t("chat.stop") if is_streaming else t("chat.send")
            self._send_btn.bgcolor = ft.Colors.ERROR if is_streaming else ft.Colors.PRIMARY

    def focus(self) -> None:
        self._schedule_focus()
