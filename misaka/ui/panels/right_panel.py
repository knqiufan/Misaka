"""Right panel component.

Collapsible panel on the right side containing file tree and file preview.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import make_icon_button
from misaka.ui.file.components.file_preview import FilePreview
from misaka.ui.file.components.file_tree import FileTree

if TYPE_CHECKING:
    from misaka.db.models import FilePreview as FilePreviewModel
    from misaka.state import AppState


class RightPanel(ft.Column):
    """Right sidebar with file tree and file preview."""

    def __init__(
        self,
        state: AppState,
        on_file_click: Callable[[str], None] | None = None,
        on_file_select: Callable[[str], None] | None = None,
        on_refresh_file_tree: Callable[[], None] | None = None,
        on_load_folder_children: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._on_file_click = on_file_click
        self._on_file_select = on_file_select
        self._on_refresh_file_tree = on_refresh_file_tree
        self._on_load_folder_children = on_load_folder_children

        self._file_tree: FileTree | None = None
        self._file_preview: FilePreview | None = None
        self._current_preview: FilePreviewModel | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        session = self.state.current_session
        working_dir = (
            self.state.file_tree_root
            or (session.working_directory if session else "")
        )

        # Content area
        if self.state.file_tree_loading:
            loading_indicator = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.ProgressRing(width=20, height=20),
                        ft.Text(
                            t("right_panel.scanning"),
                            size=11,
                            opacity=0.5,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
            content = loading_indicator
        else:
            file_nodes = self._parse_file_tree_nodes()
            self._file_tree = FileTree(
                nodes=file_nodes,
                on_file_click=self._handle_file_click,
                on_file_select=self._handle_file_select,
                on_load_children=self._on_load_folder_children,
                expanded_paths=getattr(
                    self.state, "file_tree_expanded_paths", set()
                ),
                loading_paths=getattr(
                    self.state, "file_tree_loading_paths", set()
                ),
            )
            self._file_preview = FilePreview(preview=self._current_preview)

            if self._current_preview:
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

        icon_pill = ft.Container(
            content=ft.Icon(
                ft.Icons.FOLDER_OPEN_ROUNDED,
                size=14,
                color=ft.Colors.with_opacity(0.35, ft.Colors.PRIMARY),
            ),
            padding=ft.Padding.symmetric(horizontal=4, vertical=4),
            border_radius=999,
            bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        )
        dir_display = ft.Container(
            content=ft.Row(
                controls=[
                    icon_pill,
                    ft.Text(
                        working_dir or t("right_panel.no_files"),
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                    make_icon_button(
                        ft.Icons.REFRESH_ROUNDED,
                        on_click=self._handle_refresh,
                        tooltip=t("right_panel.refresh"),
                        icon_size=14,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            margin=ft.Margin.only(left=8, right=8, bottom=4),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
        )

        self.controls = [
            ft.Container(
                content=ft.Text(t("right_panel.files"), size=13, weight=ft.FontWeight.W_600),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                margin=ft.Margin.only(left=8, right=8, top=6, bottom=4),
            ),
            dir_display,
            ft.Container(content=content, expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE),
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

    def _handle_file_click(self, path: str) -> None:
        if self._on_file_click:
            self._on_file_click(path)

    def _handle_file_select(self, path: str) -> None:
        if self._on_file_select:
            self._on_file_select(path)

    def _handle_refresh(self, e: ft.ControlEvent) -> None:
        if self._on_refresh_file_tree:
            self._on_refresh_file_tree()

    def _close_preview(self, e: ft.ControlEvent) -> None:
        self._current_preview = None
        self._build_ui()
        self.update()

    def show_file_preview(self, preview) -> None:
        """Display a file preview in the panel."""
        self._current_preview = preview
        self._build_ui()

    def clear_preview(self) -> None:
        """Clear the active file preview when session context changes."""
        self._current_preview = None
        self._build_ui()
        self.update()

    def refresh(self) -> None:
        """Rebuild panel content from current state."""
        self._build_ui()
        self.update()
