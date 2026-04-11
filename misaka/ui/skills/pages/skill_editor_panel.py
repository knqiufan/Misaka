"""Skill editor panel — right-side detail/editor for a single skill.

Displays skill metadata (name, source, description, file path),
a multiline content editor, and save/delete actions.
Read-only skills (installed/plugin) show the content without edit controls.

Layout: header + description on top, then a two-pane area —
left pane is the SKILL.md editor, right pane is the folder file browser.
Clicking a text file shows its content inline; binary files open externally.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    RADIUS_MD,
    make_badge,
    make_button,
    make_danger_button,
    make_dialog,
    make_divider,
    make_icon_button,
    make_text_button,
    make_text_field,
)
from misaka.utils.platform import open_in_file_manager

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)

_SOURCE_LABEL_KEYS: dict[str, str] = {
    "global": "extensions.source_global",
    "project": "extensions.source_project",
    "installed": "extensions.source_installed",
    "plugin": "extensions.source_plugin",
}

_SOURCE_COLORS: dict[str, str] = {
    "global": "#2563eb",
    "project": "#10b981",
    "installed": "#f59e0b",
    "plugin": "#7c3aed",
}

_TEXT_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".txt", ".py", ".js", ".ts", ".jsx", ".tsx", ".sh", ".bash",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".html", ".htm", ".css",
    ".scss", ".less", ".csv", ".cfg", ".ini", ".conf", ".env", ".log",
    ".rst", ".tex", ".sql", ".r", ".rb", ".go", ".rs", ".java", ".kt",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".lua", ".pl", ".php",
    ".bat", ".cmd", ".ps1", ".psm1", ".psd1", ".makefile", ".dockerfile",
    ".gitignore", ".gitattributes", ".editorconfig", ".prettierrc",
    ".eslintrc", ".babelrc", ".npmrc", ".env.example", ".env.local",
})

_MAX_PREVIEW_SIZE = 512 * 1024  # 512 KB


def _is_text_file(path: Path) -> bool:
    """Heuristic check: is this file likely viewable as text?"""
    suffix = path.suffix.lower()
    if suffix in _TEXT_EXTENSIONS:
        return True
    name_lower = path.name.lower()
    if name_lower in (
        "makefile", "dockerfile", "license", "readme",
        "changelog", "authors", "contributors", "todo",
        ".gitignore", ".gitattributes", ".editorconfig",
        ".prettierrc", ".eslintrc", ".babelrc", ".npmrc",
    ):
        return True
    if not suffix:
        try:
            with open(path, "rb") as f:
                chunk = f.read(1024)
            return b"\x00" not in chunk
        except OSError:
            return False
    return False


def _icon_for_entry(entry: Path) -> str:
    if entry.is_dir():
        return ft.Icons.FOLDER_OUTLINED
    lower = entry.name.lower()
    if lower.endswith(".md"):
        return ft.Icons.DESCRIPTION_OUTLINED
    if lower.endswith((".json", ".yaml", ".yml", ".toml")):
        return ft.Icons.SETTINGS_OUTLINED
    if lower.endswith((".py", ".js", ".ts", ".jsx", ".tsx", ".sh", ".go", ".rs")):
        return ft.Icons.CODE
    if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico")):
        return ft.Icons.IMAGE_OUTLINED
    if lower.endswith((".zip", ".tar", ".gz", ".bz2", ".7z", ".rar")):
        return ft.Icons.ARCHIVE_OUTLINED
    return ft.Icons.INSERT_DRIVE_FILE_OUTLINED


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


class SkillEditorPanel(ft.Container):
    """Editable detail panel for a single skill.

    Parameters
    ----------
    state:
        Application state — used both for ``state.update()`` and to
        dynamically look up the ``SkillService`` via
        ``state.get_service("skill_service")``.
    on_skill_saved:
        Callback invoked after a skill is saved successfully.
        Receives ``(skill_name: str, skill_source: str)`` so the parent
        can reload and re-select.
    on_skill_deleted:
        Callback invoked after a skill is deleted successfully.
        Receives ``(skill_name: str, skill_source: str)`` of the deleted skill.
    """

    def __init__(
        self,
        state: AppState,
        *,
        on_skill_saved: Callable[[str, str], None] | None = None,
        on_skill_deleted: Callable[[str, str], None] | None = None,
    ) -> None:
        self._state = state
        self._on_skill_saved = on_skill_saved
        self._on_skill_deleted = on_skill_deleted

        self._selected_skill = None
        self._viewing_file: str | None = None
        self._editor_field: ft.TextField = make_text_field(
            multiline=True,
            min_lines=20,
            max_lines=40,
            expand=True,
            border_radius=12,
        )
        self._file_viewer_field: ft.TextField = make_text_field(
            multiline=True,
            min_lines=20,
            max_lines=40,
            expand=True,
            read_only=True,
            border_radius=12,
        )
        self._file_viewer_title = ft.Text("", size=13, weight=ft.FontWeight.W_500)
        self._file_viewer_container: ft.Container | None = None

        super().__init__(
            content=self._build_content(),
            expand=True,
            padding=ft.Padding.all(16),
        )

    def _get_skill_service(self):
        """Dynamically fetch SkillService from state every time it's needed."""
        return self._state.get_service("skill_service")

    @property
    def selected_skill(self):
        return self._selected_skill

    def set_skill(self, skill) -> None:
        """Set the currently-displayed skill and rebuild the panel."""
        self._selected_skill = skill
        self._viewing_file = None
        self.content = self._build_content()

    def clear(self) -> None:
        """Deselect the current skill and show the empty state."""
        self._selected_skill = None
        self._viewing_file = None
        self.content = self._build_content()

    def _build_content(self) -> ft.Control:
        """Build the panel content based on current selection."""
        if not self._selected_skill:
            return self._build_empty_state()
        return self._build_skill_detail()

    def _build_empty_state(self) -> ft.Control:
        return ft.Column(
            controls=[
                ft.Icon(ft.Icons.CODE, size=48, opacity=0.2),
                ft.Text(
                    t("extensions.no_skills_desc"),
                    size=14,
                    opacity=0.4,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )

    def _build_skill_detail(self) -> ft.Control:
        skill = self._selected_skill
        is_readonly = skill.source in ("installed", "plugin")

        self._editor_field.value = skill.content
        self._editor_field.read_only = is_readonly

        header = self._build_header(skill)
        desc_row = self._build_description(skill)
        path_row = ft.Text(skill.file_path, size=11, opacity=0.4)
        action_buttons = self._build_action_buttons(is_readonly)

        editor_pane = ft.Column(
            controls=[
                self._editor_field,
                ft.Row(controls=action_buttons, spacing=8),
            ],
            spacing=8,
            expand=True,
        )

        folder_section = self._build_folder_files_section(skill)
        file_viewer = self._build_file_viewer()

        right_pane = ft.Column(
            controls=[folder_section, file_viewer],
            spacing=0,
            expand=True,
        )

        two_pane = ft.Row(
            controls=[
                ft.Container(content=editor_pane, expand=3),
                ft.Container(
                    content=right_pane,
                    expand=2,
                    padding=ft.Padding.only(left=12),
                ),
            ],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        return ft.Column(
            controls=[
                header,
                desc_row,
                path_row,
                make_divider(),
                two_pane,
            ],
            spacing=8,
            expand=True,
        )

    @staticmethod
    def _build_header(skill) -> ft.Row:
        source_label = t(_SOURCE_LABEL_KEYS.get(skill.source, skill.source))
        if skill.source not in _SOURCE_LABEL_KEYS:
            source_label = skill.source

        badge = make_badge(
            source_label,
            bgcolor=_SOURCE_COLORS.get(skill.source, "#6b7280"),
        )
        return ft.Row(
            controls=[
                ft.Text(skill.name, size=16, weight=ft.FontWeight.W_600),
                badge,
                ft.Container(expand=True),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    @staticmethod
    def _build_description(skill) -> ft.Control:
        if skill.description:
            return ft.Text(skill.description, size=12, opacity=0.6)
        return ft.Container(height=0)

    # ------------------------------------------------------------------
    # Folder file browser (recursive tree)
    # ------------------------------------------------------------------

    def _build_folder_files_section(self, skill) -> ft.Control:
        """Build a tree listing all files/subdirectories in the skill's folder."""
        folder = Path(skill.file_path).parent
        tree_controls = self._build_dir_tree(folder, skill.file_path, depth=0)

        if not tree_controls:
            return ft.Container(height=0)

        folder_header = ft.Row(
            controls=[
                ft.Icon(ft.Icons.FOLDER_OPEN, size=16, color=ft.Colors.PRIMARY),
                ft.Text(
                    t("extensions.folder_files"),
                    size=12,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Container(expand=True),
                make_icon_button(
                    ft.Icons.FOLDER_OPEN_OUTLINED,
                    tooltip=t("extensions.open_folder"),
                    on_click=lambda _: open_in_file_manager(str(folder)),
                    icon_size=16,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        file_list = ft.ListView(
            controls=tree_controls,
            spacing=2,
            expand=True,
            padding=ft.Padding.only(top=4),
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=folder_header,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    ),
                    ft.Container(
                        content=file_list,
                        expand=True,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            border_radius=RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)),
            expand=True,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

    def _build_dir_tree(
        self, folder: Path, current_file: str, depth: int,
    ) -> list[ft.Control]:
        """Recursively build a flat list of controls representing the tree."""
        try:
            entries = sorted(
                folder.iterdir(),
                key=lambda e: (e.is_file(), e.name.lower()),
            )
        except (OSError, PermissionError):
            return []

        controls: list[ft.Control] = []
        for entry in entries:
            try:
                is_dir = entry.is_dir()
            except OSError:
                continue

            if is_dir:
                controls.append(self._build_dir_row(entry, depth))
                children = self._build_dir_tree(entry, current_file, depth + 1)
                controls.extend(children)
            else:
                controls.append(
                    self._build_file_row(entry, current_file, depth)
                )
        return controls

    @staticmethod
    def _build_dir_row(entry: Path, depth: int) -> ft.Control:
        indent = depth * 16
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.FOLDER_OUTLINED,
                        size=14,
                        color=ft.Colors.PRIMARY,
                        opacity=0.7,
                    ),
                    ft.Text(
                        entry.name,
                        size=11,
                        weight=ft.FontWeight.W_500,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=8 + indent, right=8, top=3, bottom=3),
            border_radius=4,
        )

    def _build_file_row(
        self, entry: Path, current_file: str, depth: int,
    ) -> ft.Control:
        indent = depth * 16
        is_current = str(entry) == current_file
        is_text = _is_text_file(entry)
        is_viewing = self._viewing_file == str(entry)

        try:
            fsize = entry.stat().st_size
        except OSError:
            fsize = 0

        highlighted = is_current or is_viewing
        icon_color = ft.Colors.PRIMARY if highlighted else ft.Colors.ON_SURFACE_VARIANT
        name_weight = ft.FontWeight.W_600 if highlighted else ft.FontWeight.W_400

        bg = None
        if is_viewing:
            bg = ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY)
        elif is_current:
            bg = ft.Colors.with_opacity(0.04, ft.Colors.PRIMARY)

        entry_str = str(entry)

        def _on_click_view(_, p=entry_str):
            self._on_view_file(p)

        def _on_click_open(_, p=entry_str):
            open_in_file_manager(p)

        if is_text:
            on_click = _on_click_view
            tooltip = t("extensions.view_file")
        else:
            on_click = _on_click_open
            tooltip = t("extensions.open_file")

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        _icon_for_entry(entry),
                        size=14,
                        color=icon_color,
                    ),
                    ft.Text(
                        entry.name,
                        size=11,
                        weight=name_weight,
                        expand=True,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        _format_size(fsize),
                        size=10,
                        opacity=0.4,
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=8 + indent, right=8, top=3, bottom=3),
            border_radius=4,
            bgcolor=bg,
            ink=True,
            on_click=on_click,
            tooltip=tooltip,
        )

    # ------------------------------------------------------------------
    # Inline file viewer
    # ------------------------------------------------------------------

    def _build_file_viewer(self) -> ft.Control:
        """Build the inline file content viewer below the folder tree."""
        if not self._viewing_file:
            self._file_viewer_container = ft.Container(height=0)
            return self._file_viewer_container

        path = Path(self._viewing_file)
        filename = path.name
        self._file_viewer_title.value = filename

        try:
            fsize = path.stat().st_size
        except OSError:
            fsize = 0

        if fsize > _MAX_PREVIEW_SIZE:
            content_text = t("extensions.file_too_large")
            self._file_viewer_field.value = content_text
        else:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                self._file_viewer_field.value = text
            except OSError:
                self._file_viewer_field.value = t("extensions.file_read_error")

        viewer_header = ft.Row(
            controls=[
                ft.Icon(
                    _icon_for_entry(path),
                    size=14,
                    color=ft.Colors.PRIMARY,
                ),
                self._file_viewer_title,
                ft.Container(expand=True),
                make_icon_button(
                    ft.Icons.CLOSE,
                    tooltip=t("common.close"),
                    on_click=lambda _: self._close_file_viewer(),
                    icon_size=16,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._file_viewer_container = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=viewer_header,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        border=ft.Border(
                            bottom=ft.BorderSide(
                                1,
                                ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                            ),
                        ),
                    ),
                    ft.Container(
                        content=self._file_viewer_field,
                        expand=True,
                        padding=ft.Padding.only(left=4, right=4, bottom=4),
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            border_radius=RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
            expand=2,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            margin=ft.Margin.only(top=8),
        )
        return self._file_viewer_container

    def _on_view_file(self, file_path: str) -> None:
        """Open a text file in the inline viewer."""
        self._viewing_file = file_path
        self.content = self._build_content()
        self._state.update()

    def _close_file_viewer(self) -> None:
        """Close the inline file viewer."""
        self._viewing_file = None
        self.content = self._build_content()
        self._state.update()

    # ------------------------------------------------------------------
    # Action buttons
    # ------------------------------------------------------------------

    def _build_action_buttons(self, is_readonly: bool) -> list[ft.Control]:
        if is_readonly:
            return [
                ft.Text(
                    t("extensions.readonly_skill"),
                    size=12,
                    italic=True,
                    opacity=0.5,
                )
            ]
        return [
            make_button(
                t("extensions.save_skill"),
                icon=ft.Icons.SAVE,
                on_click=self._on_save_click,
            ),
            make_danger_button(
                t("extensions.delete_skill"),
                icon=ft.Icons.DELETE,
                on_click=self._on_delete_click,
            ),
        ]

    def _on_save_click(self, e: ft.ControlEvent) -> None:
        svc = self._get_skill_service()
        skill = self._selected_skill
        if not svc or not skill:
            return
        try:
            svc.update_skill(
                skill.name,
                self._editor_field.value or "",
                source=skill.source,
            )
            self._show_snackbar(e.page, t("extensions.skill_saved"))
            if self._on_skill_saved:
                self._on_skill_saved(skill.name, skill.source)
        except Exception as exc:
            logger.error("Failed to save skill: %s", exc)

    def _on_delete_click(self, e: ft.ControlEvent) -> None:
        if not e.page or not self._selected_skill:
            return
        page = e.page
        skill = self._selected_skill

        del_name, del_source = skill.name, skill.source

        def do_delete(_ev: ft.ControlEvent) -> None:
            page.pop_dialog()
            svc = self._get_skill_service()
            if not svc:
                return
            try:
                svc.delete_skill(del_name, source=del_source)
                self._show_snackbar(page, t("extensions.skill_deleted"))
                if self._on_skill_deleted:
                    self._on_skill_deleted(del_name, del_source)
            except Exception as exc:
                logger.error("Failed to delete skill: %s", exc)

        dialog = make_dialog(
            title=t("extensions.delete_skill_title"),
            content=ft.Text(t("extensions.delete_skill_confirm")),
            actions=[
                make_text_button(
                    t("common.cancel"),
                    on_click=lambda ev: page.pop_dialog(),
                ),
                make_danger_button(t("common.delete"), on_click=do_delete),
            ],
        )
        page.show_dialog(dialog)

    @staticmethod
    def _show_snackbar(page: ft.Page | None, message: str) -> None:
        if page:
            snackbar = ft.SnackBar(content=ft.Text(message))
            page.show_dialog(snackbar)
