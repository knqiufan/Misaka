"""File tree component.

Renders a hierarchical file tree using nested ExpansionTile controls
for directories and clickable items for files. Uses colorful modern
icons to distinguish file types at a glance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import flet as ft

from misaka.db.models import FileTreeNode
from misaka.i18n import t


# Compact layout tokens (kept centralized for consistent spacing)
_ROW_HEIGHT = 26
_BASE_LEFT_PADDING = 6
_DEPTH_INDENT = 10
_FILE_ICON_SIZE = 15
_FOLDER_ICON_SIZE = 16
_SELECTED_BG = ft.Colors.with_opacity(0.14, ft.Colors.PRIMARY)


# (icon, color) per extension — modernized and less noisy
_EXT_STYLE: dict[str, tuple[str, str]] = {
    ".py": (ft.Icons.CODE, "#4f46e5"),
    ".js": (ft.Icons.JAVASCRIPT, "#f59e0b"),
    ".ts": (ft.Icons.JAVASCRIPT, "#2563eb"),
    ".tsx": (ft.Icons.JAVASCRIPT, "#0891b2"),
    ".jsx": (ft.Icons.JAVASCRIPT, "#d97706"),
    ".html": (ft.Icons.LANGUAGE_ROUNDED, "#f97316"),
    ".css": (ft.Icons.STYLE, "#7c3aed"),
    ".scss": (ft.Icons.STYLE, "#be185d"),
    ".less": (ft.Icons.STYLE, "#7c3aed"),
    ".json": (ft.Icons.DATA_OBJECT, "#10b981"),
    ".yml": (ft.Icons.TUNE, "#4f46e5"),
    ".yaml": (ft.Icons.TUNE, "#4f46e5"),
    ".toml": (ft.Icons.TUNE, "#4f46e5"),
    ".cfg": (ft.Icons.TUNE, "#64748b"),
    ".ini": (ft.Icons.TUNE, "#64748b"),
    ".env": (ft.Icons.LOCK, "#d97706"),
    ".md": (ft.Icons.ARTICLE, "#4f46e5"),
    ".txt": (ft.Icons.DESCRIPTION_OUTLINED, "#94a3b8"),
    ".pdf": (ft.Icons.PICTURE_AS_PDF_ROUNDED, "#ef4444"),
    ".sh": (ft.Icons.TERMINAL_ROUNDED, "#16a34a"),
    ".bat": (ft.Icons.TERMINAL_ROUNDED, "#16a34a"),
    ".ps1": (ft.Icons.TERMINAL_ROUNDED, "#2563eb"),
    ".png": (ft.Icons.IMAGE, "#db2777"),
    ".jpg": (ft.Icons.IMAGE, "#db2777"),
    ".jpeg": (ft.Icons.IMAGE, "#db2777"),
    ".gif": (ft.Icons.IMAGE, "#d97706"),
    ".svg": (ft.Icons.IMAGE, "#7c3aed"),
    ".ico": (ft.Icons.IMAGE, "#64748b"),
    ".zip": (ft.Icons.FOLDER_ZIP, "#d97706"),
    ".gz": (ft.Icons.FOLDER_ZIP, "#d97706"),
    ".tar": (ft.Icons.FOLDER_ZIP, "#d97706"),
    ".rs": (ft.Icons.CODE, "#f97316"),
    ".go": (ft.Icons.CODE, "#0891b2"),
    ".java": (ft.Icons.CODE, "#ef4444"),
    ".kt": (ft.Icons.CODE, "#7c3aed"),
    ".c": (ft.Icons.CODE, "#64748b"),
    ".cpp": (ft.Icons.CODE, "#2563eb"),
    ".h": (ft.Icons.CODE, "#94a3b8"),
    ".lock": (ft.Icons.LOCK_OUTLINE, "#94a3b8"),
}

_DEFAULT_FILE_STYLE = (ft.Icons.DESCRIPTION_OUTLINED, "#94a3b8")
_FOLDER_COLOR = "#f59e0b"
_NAME_STYLE: dict[str, tuple[str, str]] = {
    "readme": (ft.Icons.ARTICLE, "#4f46e5"),
    "readme_cn": (ft.Icons.ARTICLE, "#4f46e5"),
    "license": (ft.Icons.GAVEL, "#64748b"),
    "dockerfile": (ft.Icons.INVENTORY_2, "#0ea5e9"),
    "makefile": (ft.Icons.BUILD, "#64748b"),
}


class FileTree(ft.Column):
    """Hierarchical file tree display with expand/collapse support."""

    def __init__(
        self,
        nodes: list[FileTreeNode] | None = None,
        on_file_click: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self._nodes = nodes or []
        self._on_file_click = on_file_click
        self._selected_file_path: str | None = None
        self._selected_file_row: ft.Container | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        if not self._nodes:
            self.controls = [
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.FOLDER_OPEN, size=28, opacity=0.25),
                            ft.Text(
                                t("right_panel.no_files"),
                                italic=True,
                                size=12,
                                opacity=0.4,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    padding=24,
                    alignment=ft.Alignment.CENTER,
                )
            ]
            return

        tree_view = ft.ListView(
            controls=[self._build_node(n, 0) for n in self._nodes],
            expand=True,
            spacing=0,
            padding=ft.Padding.only(left=4, right=4, top=2, bottom=4),
        )
        self.controls = [tree_view]

    def _build_node(self, node: FileTreeNode, depth: int) -> ft.Control:
        if node.type == "directory":
            return self._build_directory_node(node, depth)
        return self._build_file_node(node, depth)

    def _build_directory_node(self, node: FileTreeNode, depth: int) -> ft.Control:
        children = [self._build_node(c, depth + 1) for c in node.children]
        left_padding = _BASE_LEFT_PADDING + depth * _DEPTH_INDENT

        no_border = ft.RoundedRectangleBorder(
            side=ft.BorderSide(0, ft.Colors.TRANSPARENT),
            radius=0,
        )

        title_container = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.FOLDER_ROUNDED,
                        size=_FOLDER_ICON_SIZE,
                        color=_FOLDER_COLOR,
                    ),
                    ft.Text(
                        node.name,
                        size=12,
                        weight=ft.FontWeight.W_500,
                        tooltip=node.name,
                        expand=True,
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=6, vertical=4),
            bgcolor=ft.Colors.TRANSPARENT,
        )

        return ft.ExpansionTile(
            title=title_container,
            leading=None,
            controls=children if children else [
                ft.Container(
                    content=ft.Text("(empty)", size=11, italic=True, opacity=0.3),
                    padding=ft.Padding.only(left=left_padding + 18, top=1, bottom=1),
                )
            ],
            expanded=depth == 0,
            tile_padding=ft.Padding.only(left=left_padding, right=2),
            controls_padding=ft.Padding.all(0),
            dense=True,
            shape=no_border,
            collapsed_shape=no_border,
        )

    def _build_file_node(self, node: FileTreeNode, depth: int) -> ft.Control:
        icon_name, icon_color = self._resolve_file_style(node)

        row = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon_name, size=_FILE_ICON_SIZE, color=icon_color),
                    ft.Text(
                        node.name,
                        size=12,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                        color=ft.Colors.ON_SURFACE,
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(
                left=_BASE_LEFT_PADDING + 12 + depth * _DEPTH_INDENT,
                top=2,
                bottom=2,
                right=6,
            ),
            ink=True,
            border_radius=8,
            height=_ROW_HEIGHT,
            bgcolor=(
                _SELECTED_BG
                if self._selected_file_path is not None and self._selected_file_path == node.path
                else ft.Colors.TRANSPARENT
            ),
            data=node.path,
        )
        row.on_click = lambda e, p=node.path, c=row: self._handle_click(p, c)
        if self._selected_file_path is not None and self._selected_file_path == node.path:
            self._selected_file_row = row
        return row

    @staticmethod
    def _resolve_file_style(node: FileTreeNode) -> tuple[str, str]:
        ext = (node.extension or "").strip().lower().lstrip(".")
        if not ext:
            ext = Path(node.name).suffix.lower().lstrip(".")

        if ext:
            style = _EXT_STYLE.get(f".{ext}")
            if style:
                return style

        stem = Path(node.name).stem.lower()
        return _NAME_STYLE.get(stem, _DEFAULT_FILE_STYLE)

    def _handle_click(self, path: str, row: ft.Container) -> None:
        if self._selected_file_row is not None and self._selected_file_row is not row:
            self._selected_file_row.bgcolor = ft.Colors.TRANSPARENT
            self._selected_file_row.update()

        self._selected_file_path = path
        self._selected_file_row = row
        row.bgcolor = _SELECTED_BG
        row.update()

        if self._on_file_click:
            self._on_file_click(path)

    def set_nodes(self, nodes: list[FileTreeNode]) -> None:
        self._nodes = nodes
        self._build_ui()
