"""File tree component.

Renders a hierarchical file tree using nested ExpansionTile controls
for directories and clickable items for files. Uses colorful modern
icons to distinguish file types at a glance.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from misaka.i18n import t
from misaka.db.models import FileTreeNode


# (icon, color) per extension — modern colorful style
_EXT_STYLE: dict[str, tuple[str, str]] = {
    # Python
    ".py":   (ft.Icons.CODE,            "#3b82f6"),   # blue
    # JavaScript / TypeScript
    ".js":   (ft.Icons.JAVASCRIPT,      "#f59e0b"),   # amber
    ".ts":   (ft.Icons.JAVASCRIPT,      "#3b82f6"),   # blue
    ".tsx":  (ft.Icons.JAVASCRIPT,      "#06b6d4"),   # cyan
    ".jsx":  (ft.Icons.JAVASCRIPT,      "#f59e0b"),   # amber
    # Web
    ".html": (ft.Icons.WEB,             "#f97316"),   # orange
    ".css":  (ft.Icons.STYLE,           "#8b5cf6"),   # purple
    ".scss": (ft.Icons.STYLE,           "#ec4899"),   # pink
    ".less": (ft.Icons.STYLE,           "#8b5cf6"),   # purple
    # Data / Config
    ".json": (ft.Icons.DATA_OBJECT,     "#10b981"),   # emerald
    ".yml":  (ft.Icons.SETTINGS,        "#6366f1"),   # indigo
    ".yaml": (ft.Icons.SETTINGS,        "#6366f1"),   # indigo
    ".toml": (ft.Icons.SETTINGS,        "#6366f1"),   # indigo
    ".cfg":  (ft.Icons.TUNE,            "#64748b"),   # slate
    ".ini":  (ft.Icons.TUNE,            "#64748b"),   # slate
    ".env":  (ft.Icons.LOCK,            "#f59e0b"),   # amber
    # Docs
    ".md":   (ft.Icons.ARTICLE,         "#6366f1"),   # indigo
    ".txt":  (ft.Icons.TEXT_SNIPPET,    "#94a3b8"),   # slate-400
    ".pdf":  (ft.Icons.PICTURE_AS_PDF,  "#ef4444"),   # red
    # Shell
    ".sh":   (ft.Icons.TERMINAL,        "#22c55e"),   # green
    ".bat":  (ft.Icons.TERMINAL,        "#22c55e"),   # green
    ".ps1":  (ft.Icons.TERMINAL,        "#3b82f6"),   # blue
    # Images
    ".png":  (ft.Icons.IMAGE,           "#ec4899"),   # pink
    ".jpg":  (ft.Icons.IMAGE,           "#ec4899"),   # pink
    ".jpeg": (ft.Icons.IMAGE,           "#ec4899"),   # pink
    ".gif":  (ft.Icons.IMAGE,           "#f59e0b"),   # amber
    ".svg":  (ft.Icons.IMAGE,           "#8b5cf6"),   # purple
    ".ico":  (ft.Icons.IMAGE,           "#64748b"),   # slate
    # Archives
    ".zip":  (ft.Icons.FOLDER_ZIP,      "#f59e0b"),   # amber
    ".gz":   (ft.Icons.FOLDER_ZIP,      "#f59e0b"),   # amber
    ".tar":  (ft.Icons.FOLDER_ZIP,      "#f59e0b"),   # amber
    # Rust / Go / Java / C
    ".rs":   (ft.Icons.CODE,            "#f97316"),   # orange
    ".go":   (ft.Icons.CODE,            "#06b6d4"),   # cyan
    ".java": (ft.Icons.CODE,            "#ef4444"),   # red
    ".kt":   (ft.Icons.CODE,            "#8b5cf6"),   # purple
    ".c":    (ft.Icons.CODE,            "#64748b"),   # slate
    ".cpp":  (ft.Icons.CODE,            "#3b82f6"),   # blue
    ".h":    (ft.Icons.CODE,            "#94a3b8"),   # slate-400
    # Lock / package
    ".lock": (ft.Icons.LOCK_OUTLINE,    "#94a3b8"),   # slate-400
}

_DEFAULT_FILE_STYLE = (ft.Icons.INSERT_DRIVE_FILE, "#94a3b8")

# Folder colors by depth
_FOLDER_COLORS = ["#f59e0b", "#fb923c", "#fbbf24", "#fcd34d"]


def _folder_color(depth: int) -> str:
    return _FOLDER_COLORS[min(depth, len(_FOLDER_COLORS) - 1)]


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
        )
        self.controls = [tree_view]

    def _build_node(self, node: FileTreeNode, depth: int) -> ft.Control:
        if node.type == "directory":
            return self._build_directory_node(node, depth)
        return self._build_file_node(node, depth)

    def _build_directory_node(self, node: FileTreeNode, depth: int) -> ft.Control:
        children = [self._build_node(c, depth + 1) for c in node.children]
        color = _folder_color(depth)

        no_border = ft.RoundedRectangleBorder(
            side=ft.BorderSide(0, ft.Colors.TRANSPARENT),
            radius=0,
        )

        folder_icon = ft.Stack(
            controls=[
                ft.Icon(ft.Icons.FOLDER, size=16, color=color),
            ],
            width=16,
            height=16,
        )

        return ft.Container(
            content=ft.ExpansionTile(
                leading=folder_icon,
                title=ft.Text(
                    node.name,
                    size=13,
                    weight=ft.FontWeight.W_500,
                ),
                controls=children if children else [
                    ft.Container(
                        content=ft.Text("(empty)", size=11, italic=True, opacity=0.3),
                        padding=ft.Padding.only(left=24, top=2, bottom=2),
                    )
                ],
                expanded=depth == 0,
                tile_padding=ft.Padding.only(left=depth * 12, right=4),
                controls_padding=ft.Padding.all(0),
                dense=True,
                shape=no_border,
                collapsed_shape=no_border,
            ),
        )

    def _build_file_node(self, node: FileTreeNode, depth: int) -> ft.Control:
        ext = (node.extension or "").lower()
        icon_name, icon_color = _EXT_STYLE.get(ext, _DEFAULT_FILE_STYLE)

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon_name, size=14, color=icon_color),
                    ft.Text(
                        node.name,
                        size=12,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                        color=ft.Colors.ON_SURFACE,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(
                left=20 + depth * 12,
                top=3,
                bottom=3,
                right=8,
            ),
            on_click=lambda e, p=node.path: self._handle_click(p),
            ink=True,
            border_radius=4,
        )

    def _handle_click(self, path: str) -> None:
        if self._on_file_click:
            self._on_file_click(path)

    def set_nodes(self, nodes: list[FileTreeNode]) -> None:
        self._nodes = nodes
        self._build_ui()
