"""Message input component.

Multi-line text input area with send button, file attachment support,
slash-command menu, @ file picker overlay, and keyboard shortcut handling.
Supports Shift+Enter for newline and Enter to send.
Supports image upload via file picker and clipboard paste (Ctrl+V).
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.commands import SlashCommand, filter_commands
from misaka.db.models import FileTreeNode, PendingImage
from misaka.i18n import t
from misaka.ui.chat.components.image_preview_bar import ImagePreviewBar
from misaka.ui.common.theme import MONO_FONT_FAMILY

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)

_FOLDER_COLOR = "#f59e0b"
_MAX_FILE_RESULTS = 15

# Claude 多模态模型支持的附件格式（图片、文档、表格、演示）
# 参考: https://docs.anthropic.com/en/docs/build-with-claude/file-support
_CLAUDE_ATTACH_EXTENSIONS = [
    "jpg", "jpeg", "png", "gif", "webp",  # 图片
    "pdf", "docx", "txt", "rtf", "odt", "html", "epub", "json", "md",  # 文档
    "csv", "tsv", "xlsx",  # 表格
    "pptx",  # 演示
]

# Image formats that should be processed as image attachments
_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


@dataclasses.dataclass
class FileRef:
    """Mapping between a short display tag and an absolute file path."""

    display: str
    abs_path: str
    is_dir: bool


class MessageInput(ft.Container):
    """Message input area with send/stop button, file attachment, and slash commands.

    Supports image upload via file picker and clipboard paste (Ctrl+V).
    Images are displayed in a preview bar above the input field before sending.
    """

    def __init__(
        self,
        state: AppState,
        on_send: Callable[[str, list[PendingImage]], None] | None = None,
        on_abort: Callable[[], None] | None = None,
        on_command: Callable[[str], None] | None = None,
        on_model_change: Callable[[str], None] | None = None,
        on_view_image: Callable[[PendingImage], None] | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self._on_send = on_send
        self._on_abort = on_abort
        self._on_command = on_command
        self._on_model_change = on_model_change
        self._on_view_image = on_view_image
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
        self._model_options_cache: list[tuple[str, str]] | None = None
        # Image preview bar
        self._image_preview_bar: ImagePreviewBar | None = None
        self._pending_images: list[PendingImage] = []
        # Keyboard modifier tracking for Ctrl+V
        self._ctrl_pressed: bool = False
        # File reference tags: display text -> FileRef mapping
        self._file_references: dict[str, FileRef] = {}
        self._prev_text: str = ""
        self._guard_in_progress: bool = False
        self._file_hint_row: ft.Row | None = None
        self._file_hint_container: ft.Container | None = None
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
                else ft.Icons.KEYBOARD_RETURN_ROUNDED
            ),
            tooltip=t("chat.stop") if is_streaming else t("chat.send"),
            on_click=self._handle_action,
            icon_color=ft.Colors.WHITE,
            bgcolor=ft.Colors.ERROR if is_streaming else ft.Colors.PRIMARY,
            icon_size=15,
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

        # Image preview bar (above input, hidden by default)
        self._image_preview_bar = ImagePreviewBar(
            on_delete_image=self._handle_delete_image,
            on_view_image=self._handle_view_image,
        )

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

        # File reference hint bar (above input, below image preview)
        self._file_hint_row = ft.Row(
            controls=[],
            spacing=4,
            wrap=True,
            run_spacing=4,
        )
        self._file_hint_container = ft.Container(
            content=self._file_hint_row,
            visible=False,
            padding=ft.Padding.only(left=14, right=14, top=2, bottom=4),
        )

        # Content column: menus, image preview bar, file hints, input shell
        content_column = ft.Column(
            controls=[
                self._command_menu_container,
                self._file_menu_container,
                self._image_preview_bar,
                self._file_hint_container,
                self._input_shell,
            ],
            spacing=0,
            tight=True,
        )

        # Keyboard listener for Ctrl+V paste (wraps the content)
        self.content = ft.KeyboardListener(
            content=content_column,
            on_key_down=self._handle_key_down,
            on_key_up=self._handle_key_up,
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
        """Detect '/' prefix or '@' for commands and file picking.

        Also enforces atomic integrity of file-reference tags: if a user
        partially deletes a tag, the remaining fragment is removed
        automatically.
        """
        value = e.data or ""

        if self._guard_in_progress:
            self._prev_text = value
            return

        fixed = self._guard_file_references(value)
        if fixed is not None:
            self._guard_in_progress = True
            self._text_field.value = fixed  # type: ignore[union-attr]
            self._prev_text = fixed
            self._text_field.update()  # type: ignore[union-attr]
            self._guard_in_progress = False
            self._refresh_file_hints()
            return

        self._prev_text = value

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
            self._clear_file_references()
            self._show_model_menu()
            return

        if cmd.immediate:
            if self._text_field:
                self._text_field.value = ""
                self._text_field.update()
            self._clear_file_references()
            if self._on_command:
                self._on_command(f"/{cmd.name}")
        elif cmd.prompt and self._on_send:
            if self._text_field:
                self._text_field.value = ""
                self._text_field.update()
            self._clear_file_references()
            self._on_send(cmd.prompt, [])
        else:
            self._set_badge(cmd)
            if self._text_field:
                self._text_field.value = ""
                self._text_field.update()
                self._schedule_focus()
            self._clear_file_references()

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

        # Replace the @query with a short file-reference tag
        display = self._make_unique_display(node.path)
        self._file_references[display] = FileRef(
            display=display,
            abs_path=node.path,
            is_dir=False,
        )
        new_value = f"{before}{display} "
        self._text_field.value = new_value
        self._prev_text = new_value
        self._text_field.update()
        self._schedule_focus()
        self._hide_file_menu()
        self._refresh_file_hints()

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
    # File reference tag helpers
    # ------------------------------------------------------------------

    def _make_unique_display(self, path: str) -> str:
        """Generate a unique short display tag like ``[@filename.ext]``.

        If a tag with the same basename already maps to a *different* path,
        disambiguate by prepending the parent directory name.
        """
        basename = os.path.basename(path.rstrip("\\/"))
        if os.path.isdir(path):
            candidate = f"[@{basename}/]"
        else:
            candidate = f"[@{basename}]"

        existing = self._file_references.get(candidate)
        if existing is None or existing.abs_path == path:
            return candidate

        parent = os.path.basename(os.path.dirname(path.rstrip("\\/")))
        if parent:
            if os.path.isdir(path):
                return f"[@{parent}/{basename}/]"
            return f"[@{parent}/{basename}]"
        return candidate

    def _insert_file_tag(self, path: str) -> None:
        """Create a file-reference tag and insert it at the current cursor."""
        if not self._text_field:
            return

        display = self._make_unique_display(path)
        if display in self._file_references:
            if self._file_references[display].abs_path == path:
                pass  # same file selected again, still insert a second occurrence
            # different path collision already handled by _make_unique_display
        self._file_references[display] = FileRef(
            display=display,
            abs_path=path,
            is_dir=os.path.isdir(path),
        )

        self._insert_text_at_cursor(f"{display} ")
        self._refresh_file_hints()

    def _insert_text_at_cursor(self, text: str) -> None:
        """Insert *text* at the current cursor position in the TextField."""
        if not self._text_field:
            return

        current = self._text_field.value or ""
        cursor_pos = len(current)

        sel = self._text_field.selection
        if sel is not None and sel.is_valid:
            start, end = sel.start, sel.end
            before = current[:start]
            after = current[end:]
            new_value = f"{before}{text}{after}"
            cursor_pos = start + len(text)
        else:
            separator = " " if current and not current.endswith((" ", "\n")) else ""
            new_value = f"{current}{separator}{text}"
            cursor_pos = len(new_value)

        self._text_field.value = new_value
        self._text_field.selection = ft.TextSelection(
            base_offset=cursor_pos, extent_offset=cursor_pos,
        )
        self._prev_text = new_value
        self._text_field.update()

    # ------------------------------------------------------------------
    # Atomic integrity guard for file-reference tags
    # ------------------------------------------------------------------

    def _guard_file_references(self, new_text: str) -> str | None:
        """If any registered tag was partially edited, remove the remnant.

        Returns the corrected text when a fix was applied, or ``None``
        when nothing changed.
        """
        if not self._file_references:
            return None

        damaged = [d for d in self._file_references if d not in new_text]
        if not damaged:
            return None

        fixed = self._remove_damaged_tags(new_text, damaged)
        for d in damaged:
            del self._file_references[d]
        return fixed

    def _remove_damaged_tags(self, new_text: str, damaged: list[str]) -> str:
        """Remove remnant characters of *damaged* tags from *new_text*.

        Strategy: rebuild ``new_text`` from ``_prev_text`` by removing
        every damaged tag entirely, then replaying the user's edit.
        """
        old = self._prev_text
        prefix, old_end, new_end = self._diff_bounds(old, new_text)
        user_inserted = new_text[prefix:new_end]

        cleaned_old = old
        for display in damaged:
            tag_pos = cleaned_old.find(display)
            if tag_pos < 0:
                continue

            remove_start = tag_pos
            remove_end = tag_pos + len(display)

            # Also consume a trailing space that was auto-inserted with the tag
            if remove_end < len(cleaned_old) and cleaned_old[remove_end] == " ":
                remove_end += 1

            removed_len = remove_end - remove_start
            cleaned_old = cleaned_old[:remove_start] + cleaned_old[remove_end:]

            removed_before_edit = 0
            if remove_start < prefix:
                removed_before_edit = min(remove_end, prefix) - remove_start
            prefix -= removed_before_edit
            old_end -= removed_len

        # Clamp edit boundaries after removals
        prefix = max(0, min(prefix, len(cleaned_old)))
        old_end = max(prefix, min(old_end, len(cleaned_old)))

        result = cleaned_old[:prefix] + user_inserted + cleaned_old[old_end:]
        return result

    @staticmethod
    def _diff_bounds(old: str, new: str) -> tuple[int, int, int]:
        """Return *(common_prefix_len, old_change_end, new_change_end)*.

        ``old[prefix:old_change_end]`` was replaced by
        ``new[prefix:new_change_end]``.
        """
        i = 0
        while i < len(old) and i < len(new) and old[i] == new[i]:
            i += 1
        j_old, j_new = len(old), len(new)
        while j_old > i and j_new > i and old[j_old - 1] == new[j_new - 1]:
            j_old -= 1
            j_new -= 1
        return i, j_old, j_new

    # ------------------------------------------------------------------
    # Insert file path from external source (right-click menu)
    # ------------------------------------------------------------------

    def insert_at_symbol(self, path: str) -> None:
        """Insert a file-reference tag into the input field.

        Shows a short ``[@filename.ext]`` placeholder instead of the full
        absolute path.  The placeholder is resolved back to the real path
        on send.
        """
        self._insert_file_tag(path)
        self._suppress_focus_close = True
        self._schedule_focus()

    # ------------------------------------------------------------------
    # Model sub-menu
    # ------------------------------------------------------------------

    def _get_model_options(self) -> list[tuple[str, str]]:
        """Read model names from settings and build option list. Cached."""
        if self._model_options_cache is not None:
            return self._model_options_cache
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
            self._model_options_cache = options
            return options
        options.extend([("sonnet", "Sonnet"), ("opus", "Opus"), ("haiku", "Haiku")])
        self._model_options_cache = options
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

    def _resolve_file_tags(self, text: str) -> str:
        """Replace all ``[@filename]`` placeholders with ``@absolute_path``."""
        for display, ref in self._file_references.items():
            text = text.replace(display, f"@{ref.abs_path}")
        return text

    def _clear_file_references(self) -> None:
        """Reset file-reference state (after send / session switch)."""
        self._file_references.clear()
        self._prev_text = ""
        self._refresh_file_hints()

    # ------------------------------------------------------------------
    # File reference hint bar
    # ------------------------------------------------------------------

    def _refresh_file_hints(self) -> None:
        """Re-render the hint bar showing full paths of referenced files."""
        if not self._file_hint_row or not self._file_hint_container:
            return

        if not self._file_references:
            if self._file_hint_container.visible:
                self._file_hint_container.visible = False
                with contextlib.suppress(Exception):
                    self._file_hint_container.update()
            return

        chips: list[ft.Control] = []
        for display, ref in self._file_references.items():
            chips.append(self._build_hint_chip(display, ref))

        self._file_hint_row.controls = chips
        self._file_hint_container.visible = True
        with contextlib.suppress(Exception):
            self._file_hint_container.update()

    def _build_hint_chip(self, display: str, ref: FileRef) -> ft.Control:
        """Build a compact chip: icon + filename + close. Hover shows full path."""
        icon = ft.Icons.FOLDER_ROUNDED if ref.is_dir else ft.Icons.DESCRIPTION_OUTLINED
        icon_color = _FOLDER_COLOR if ref.is_dir else "#94a3b8"
        basename = os.path.basename(ref.abs_path.rstrip("\\/"))

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, size=11, color=icon_color),
                    ft.Text(
                        basename,
                        size=10,
                        weight=ft.FontWeight.W_500,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Container(
                        content=ft.Icon(
                            ft.Icons.CLOSE_ROUNDED,
                            size=10,
                            color=ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE),
                        ),
                        on_click=lambda _, d=display: self._remove_file_tag(d),
                        width=14,
                        height=14,
                        alignment=ft.Alignment.CENTER,
                        border_radius=7,
                        ink=True,
                    ),
                ],
                spacing=4,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            tooltip=ref.abs_path,
            padding=ft.Padding.only(left=6, right=4, top=2, bottom=2),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            ),
        )

    def _remove_file_tag(self, display: str) -> None:
        """Remove a file-reference tag via the hint-bar close button."""
        if display not in self._file_references:
            return

        del self._file_references[display]

        if self._text_field:
            current = self._text_field.value or ""
            if display in current:
                new_value = current.replace(display, "")
                new_value = new_value.replace("  ", " ")
                self._text_field.value = new_value
                self._prev_text = new_value
                self._text_field.update()

        self._refresh_file_hints()

    def _handle_send(self, e: ft.ControlEvent) -> None:
        if not self._text_field:
            return

        user_text = (self._text_field.value or "").strip()

        if self._active_badge:
            badge = self._active_badge
            self._remove_badge()
            prompt = badge.prompt
            if user_text:
                user_text = self._resolve_file_tags(user_text)
                prompt = f"{prompt}\n\nUser context: {user_text}"
            self._text_field.value = ""
            self._text_field.update()
            self._clear_file_references()
            if self._on_send and prompt:
                self._on_send(prompt, [])
            return

        user_text = self._resolve_file_tags(user_text)

        has_text = bool(user_text)
        has_images = bool(self._pending_images)

        if not has_text and not has_images:
            return

        images_to_send = list(self._pending_images)

        self._text_field.value = ""
        self._text_field.update()
        self._hide_command_menu()
        self._hide_file_menu()
        self._clear_file_references()

        if self._image_preview_bar:
            self._image_preview_bar.clear()
        self._pending_images = []

        if self._on_send:
            self._on_send(user_text, images_to_send)

    def _handle_attach(self, e: ft.ControlEvent) -> None:
        """Open file picker for attachments. Images are added to preview bar."""
        page = e.page if e and e.page else getattr(self.state, "page", None)
        if not page:
            return
        paths = self._pick_attach_files_native()
        if paths:
            self._process_selected_files(paths)
        self._schedule_focus(page)

    @staticmethod
    def _pick_attach_files_native() -> list[str]:
        """使用系统原生文件选择器选择附件，返回选中文件路径列表。"""
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError:
            return []

        patterns = " ".join(f"*.{ext}" for ext in _CLAUDE_ATTACH_EXTENSIONS)
        filetypes = [
            (t("chat.attach_file"), patterns),
            ("All files", "*.*"),
        ]
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected = filedialog.askopenfilenames(
                title=t("chat.select_files"),
                filetypes=filetypes,
            )
            return list(selected) if selected else []
        finally:
            root.destroy()

    def _process_selected_files(self, paths: list[str]) -> None:
        """Process selected files: images go to preview bar, others as text markers."""
        if not paths:
            return

        image_paths = []
        other_paths = []

        for path in paths:
            ext = os.path.splitext(path)[1].lower().lstrip(".")
            if ext in _IMAGE_EXTENSIONS:
                image_paths.append(path)
            else:
                other_paths.append(path)

        # Process images
        if image_paths:
            self._add_images_from_paths(image_paths)

        # Add non-image files as text markers
        if other_paths and self._text_field:
            for path in other_paths:
                current = self._text_field.value or ""
                separator = "\n" if current else ""
                self._text_field.value = f"{current}{separator}[File: {path}]"
            self._text_field.update()

    def _add_images_from_paths(self, paths: list[str]) -> None:
        """Add images from file paths to the preview bar."""
        image_service = self.state.get_service("image_service")
        if not image_service:
            return

        for path in paths:
            pending = image_service.create_pending_image(path)
            if pending:
                self._pending_images.append(pending)

        if self._image_preview_bar:
            self._image_preview_bar.update_images(self._pending_images)

    @staticmethod
    def _is_image_file(path: str) -> bool:
        """Check if a file path points to a supported image file."""
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        return ext in _IMAGE_EXTENSIONS

    def _handle_delete_image(self, image_id: str) -> None:
        """Handle deletion of an image from the preview bar."""
        # Find and remove the image
        for i, img in enumerate(self._pending_images):
            if img.id == image_id:
                # Delete temp file
                image_service = self.state.get_service("image_service")
                if image_service:
                    image_service.delete_pending_image(img)
                self._pending_images.pop(i)
                break

        # Update preview bar
        if self._image_preview_bar:
            self._image_preview_bar.update_images(self._pending_images)

    def _handle_view_image(self, pending: PendingImage) -> None:
        """Handle click to view full-size image."""
        from misaka.ui.components.image_overlay import show_image_overlay

        image_src = pending.temp_path
        if self.page and image_src:
            show_image_overlay(self.page, image_src)
            return

        if self._on_view_image:
            self._on_view_image(pending)

    # ------------------------------------------------------------------
    # Keyboard handling for clipboard paste
    # ------------------------------------------------------------------

    def _handle_key_down(self, e: ft.KeyDownEvent) -> None:
        """Handle key down events for tracking modifiers and paste."""
        # Track Ctrl key
        if e.key == "Control" or e.key == "Control Left" or e.key == "Control Right":
            self._ctrl_pressed = True

        # Check for Ctrl+V
        if e.key == "V" and self._ctrl_pressed:
            self._try_paste_clipboard_image()

    def _handle_key_up(self, e: ft.KeyUpEvent) -> None:
        """Handle key up events for tracking modifiers."""
        # Track Ctrl key release
        if e.key == "Control" or e.key == "Control Left" or e.key == "Control Right":
            self._ctrl_pressed = False

    def _try_paste_clipboard_image(self) -> None:
        """Try to paste an image from the system clipboard.

        Uses PIL.ImageGrab.grabclipboard() which works on Windows and macOS.
        """
        try:
            from PIL import ImageGrab
        except ImportError:
            logger.warning("PIL not available for clipboard access")
            return

        try:
            # grabclipboard returns:
            # - None: clipboard is empty or doesn't contain image
            # - PIL.Image: clipboard contains an image
            # - list: clipboard contains file paths
            # - str: clipboard contains text (on some platforms)
            clipboard_data = ImageGrab.grabclipboard()

            if clipboard_data is None:
                return

            # Case 1: Clipboard contains an image
            if hasattr(clipboard_data, "save"):
                # It's a PIL Image
                self._process_pil_image(clipboard_data)
                return

            # Case 2: Clipboard contains file paths (e.g., copied image file)
            if isinstance(clipboard_data, list):
                for path in clipboard_data:
                    if isinstance(path, str) and self._is_image_file(path):
                        self._add_images_from_paths([path])
                return

        except Exception as exc:
            logger.error("Failed to read clipboard: %s", exc)

    def _process_pil_image(self, image) -> None:
        """Process a PIL Image from clipboard and add to preview."""
        import io

        image_service = self.state.get_service("image_service")
        if not image_service:
            return

        # Convert PIL Image to bytes
        buffer = io.BytesIO()

        # Determine format based on image mode
        if image.mode == "RGBA":
            format_name = "PNG"
        elif image.mode == "P":
            # Palette mode - convert to RGBA for transparency support
            image = image.convert("RGBA")
            format_name = "PNG"
        else:
            # Convert to RGB for JPEG (smaller size)
            if image.mode != "RGB":
                image = image.convert("RGB")
            format_name = "JPEG"

        image.save(buffer, format=format_name)
        image_bytes = buffer.getvalue()

        # Create pending image
        pending = image_service.create_pending_from_clipboard(
            image_bytes, format_hint=format_name.lower()
        )
        if pending:
            self._pending_images.append(pending)
            if self._image_preview_bar:
                self._image_preview_bar.update_images(self._pending_images)

    def handle_clipboard_image(self, image_data: bytes) -> None:
        """Handle image paste from clipboard.

        Called externally when clipboard contains image data.

        Args:
            image_data: Raw image bytes from clipboard.
        """
        if not image_data:
            return

        image_service = self.state.get_service("image_service")
        if not image_service:
            return

        pending = image_service.create_pending_from_clipboard(image_data)
        if pending:
            self._pending_images.append(pending)
            if self._image_preview_bar:
                self._image_preview_bar.update_images(self._pending_images)

    def get_pending_images(self) -> list[PendingImage]:
        """Return the current list of pending images."""
        return list(self._pending_images)

    def clear_pending_images(self) -> None:
        """Clear all pending images."""
        image_service = self.state.get_service("image_service")
        if image_service:
            for img in self._pending_images:
                image_service.delete_pending_image(img)
        self._pending_images = []
        if self._image_preview_bar:
            self._image_preview_bar.clear()

    # ------------------------------------------------------------------
    # Refresh / focus
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Update send/stop button appearance based on streaming state."""
        if self._send_btn:
            is_streaming = self.state.is_streaming
            self._send_btn.icon = (
                ft.Icons.STOP_CIRCLE_ROUNDED if is_streaming else ft.Icons.SEND_ROUNDED
            )
            self._send_btn.tooltip = t("chat.stop") if is_streaming else t("chat.send")
            self._send_btn.bgcolor = ft.Colors.ERROR if is_streaming else ft.Colors.PRIMARY
            self._send_btn.update()

    def focus(self) -> None:
        self._schedule_focus()
