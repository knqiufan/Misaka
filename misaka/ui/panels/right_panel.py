"""Right panel component.

Collapsible panel on the right side containing file tree and task list,
toggled via tab buttons. Supports dynamic content switching and
file preview display.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.file.components.file_preview import FilePreview
from misaka.ui.file.components.file_tree import FileTree
from misaka.ui.task.components.task_list import TaskList

if TYPE_CHECKING:
    from misaka.db.models import FilePreview as FilePreviewModel
    from misaka.state import AppState


class RightPanel(ft.Column):
    """Right sidebar with file tree, file preview, and task list tabs."""

    def __init__(
        self,
        state: AppState,
        on_file_click: Callable[[str], None] | None = None,
        on_file_select: Callable[[str], None] | None = None,
        on_task_status_change: Callable[[str, str], None] | None = None,
        on_task_create: Callable[[str], None] | None = None,
        on_task_delete: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._on_file_click = on_file_click
        self._on_file_select = on_file_select
        self._on_task_status_change = on_task_status_change
        self._on_task_create = on_task_create
        self._on_task_delete = on_task_delete

        self._file_tree: FileTree | None = None
        self._file_preview: FilePreview | None = None
        self._task_list: TaskList | None = None
        self._current_preview: FilePreviewModel | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        # Tab buttons
        is_files = self.state.right_panel_tab == "files"
        session = self.state.current_session
        working_dir = (
            self.state.file_tree_root
            or (session.working_directory if session else "")
        )

        files_btn = self._build_tab_button(
            label=t("right_panel.files"),
            tab_key="files",
            is_active=is_files,
        )
        tasks_btn = self._build_tab_button(
            label=t("right_panel.tasks"),
            tab_key="tasks",
            is_active=not is_files,
        )

        tab_bar = ft.Container(
            content=ft.Row(
                controls=[files_btn, tasks_btn],
                spacing=6,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            margin=ft.Margin.only(left=8, right=8, top=6, bottom=4),
            # bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
            border_radius=12,
        )

        # Content area
        if is_files:
            # Parse file tree nodes from state
            file_nodes = self._parse_file_tree_nodes()
            self._file_tree = FileTree(
                nodes=file_nodes,
                on_file_click=self._handle_file_click,
                on_file_select=self._handle_file_select,
            )
            self._file_preview = FilePreview(preview=self._current_preview)

            if self._current_preview:
                from misaka.ui.common.theme import make_icon_button
                back_btn = ft.Container(
                    content=ft.Row(
                        controls=[
                            make_icon_button(
                                ft.Icons.ARROW_BACK_ROUNDED,
                                on_click=self._close_preview,
                                tooltip=t("right_panel.back_to_tree"),
                            ),
                            ft.Text(
                                t("right_panel.file_preview"),
                                size=12,
                                weight=ft.FontWeight.W_500,
                            ),
                        ],
                        spacing=4,
                    ),
                    padding=ft.Padding.only(left=4, bottom=4),
                )
                content = ft.Column(
                    controls=[back_btn, self._file_preview],
                    spacing=0,
                    expand=True,
                )
            else:
                content = self._file_tree
        else:
            self._task_list = TaskList(
                tasks=self.state.tasks,
                on_status_change=self._on_task_status_change,
                on_create=self._on_task_create,
                on_delete=self._on_task_delete,
            )
            content = self._task_list

        dir_display = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.FOLDER_OPEN_ROUNDED,
                        size=14,
                        color=ft.Colors.PRIMARY,
                        opacity=0.6,
                    ),
                    ft.Text(
                        working_dir or t("right_panel.no_files"),
                        size=11,
                        opacity=0.5,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                ],
                spacing=5,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=10, right=10, top=1, bottom=4),
            visible=is_files,
        )

        self.controls = [
            tab_bar,
            dir_display,
            ft.Container(content=content, expand=True),
        ]

    def _build_tab_button(self, label: str, tab_key: str, is_active: bool) -> ft.Control:
        """Build right-panel tab with clear active/inactive separation."""
        text_color = ft.Colors.PRIMARY if is_active else ft.Colors.with_opacity(0.68, ft.Colors.ON_SURFACE)
        return ft.Container(
            content=ft.Text(
                label,
                size=13,
                weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_500,
                color=text_color,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border_radius=10,
            bgcolor=(
                ft.Colors.with_opacity(0.14, ft.Colors.PRIMARY)
                if is_active
                else ft.Colors.TRANSPARENT
            ),
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.24, ft.Colors.PRIMARY)
                if is_active
                else ft.Colors.TRANSPARENT,
            ),
            on_click=lambda e, key=tab_key: self._switch_tab(key),
            ink=True,
        )

    def _parse_file_tree_nodes(self):
        """Parse file tree nodes from state."""
        from misaka.db.models import FileTreeNode
        nodes = self.state.file_tree_nodes
        if not nodes:
            return []
        # If already FileTreeNode objects, return directly
        if nodes and isinstance(nodes[0], FileTreeNode):
            return nodes
        # Otherwise try to parse from dicts
        result = []
        for item in nodes:
            if isinstance(item, dict):
                result.append(self._dict_to_node(item))
        return result

    def _dict_to_node(self, d: dict) -> object:
        """Convert a dict to a FileTreeNode."""
        from misaka.db.models import FileTreeNode
        children = [self._dict_to_node(c) for c in d.get("children", [])]
        return FileTreeNode(
            name=d.get("name", ""),
            path=d.get("path", ""),
            type=d.get("type", "file"),
            children=children,
            size=d.get("size"),
            extension=d.get("extension"),
        )

    def _switch_tab(self, tab: str) -> None:
        self.state.right_panel_tab = tab
        self._current_preview = None
        self._build_ui()
        self.update()

    def _handle_file_click(self, path: str) -> None:
        if self._on_file_click:
            self._on_file_click(path)

    def _handle_file_select(self, path: str) -> None:
        if self._on_file_select:
            self._on_file_select(path)

    def _close_preview(self, e: ft.ControlEvent) -> None:
        self._current_preview = None
        self._build_ui()
        self.update()

    def show_file_preview(self, preview) -> None:
        """Display a file preview in the panel."""
        self._current_preview = preview
        self.state.right_panel_tab = "files"
        self._build_ui()

    def refresh(self) -> None:
        """Rebuild panel content from current state."""
        self._build_ui()
