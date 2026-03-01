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
from misaka.ui.components.file_preview import FilePreview
from misaka.ui.components.file_tree import FileTree
from misaka.ui.components.task_list import TaskList

if TYPE_CHECKING:
    from misaka.db.models import FilePreview as FilePreviewModel
    from misaka.state import AppState


class RightPanel(ft.Column):
    """Right sidebar with file tree, file preview, and task list tabs."""

    def __init__(
        self,
        state: AppState,
        on_file_click: Callable[[str], None] | None = None,
        on_task_status_change: Callable[[str, str], None] | None = None,
        on_task_create: Callable[[str], None] | None = None,
        on_task_delete: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._on_file_click = on_file_click
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

        files_btn = ft.TextButton(
            content=t("right_panel.files"),
            icon=ft.Icons.FOLDER_ROUNDED if is_files else ft.Icons.FOLDER_OUTLINED,
            on_click=lambda e: self._switch_tab("files"),
            style=ft.ButtonStyle(
                color=ft.Colors.PRIMARY if is_files else ft.Colors.ON_SURFACE_VARIANT,
            ),
        )

        tasks_btn = ft.TextButton(
            content=t("right_panel.tasks"),
            icon=(
                ft.Icons.CHECKLIST_ROUNDED
                if not is_files
                else ft.Icons.CHECKLIST_RTL_ROUNDED
            ),
            on_click=lambda e: self._switch_tab("tasks"),
            style=ft.ButtonStyle(
                color=ft.Colors.PRIMARY if not is_files else ft.Colors.ON_SURFACE_VARIANT,
            ),
        )

        tab_bar = ft.Container(
            content=ft.Row(
                controls=[files_btn, tasks_btn],
                spacing=2,
            ),
            padding=ft.Padding.only(left=6, right=6, top=6, bottom=4),
        )

        # Content area
        if is_files:
            # Parse file tree nodes from state
            file_nodes = self._parse_file_tree_nodes()
            self._file_tree = FileTree(
                nodes=file_nodes,
                on_file_click=self._handle_file_click,
            )
            self._file_preview = FilePreview(preview=self._current_preview)

            if self._current_preview:
                # Show preview with back button
                back_btn = ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK_ROUNDED,
                                icon_size=18,
                                on_click=self._close_preview,
                                tooltip=t("right_panel.back_to_tree"),
                                style=ft.ButtonStyle(padding=4),
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
