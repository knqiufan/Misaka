"""Skill editor panel — right-side detail/editor for a single skill.

Displays skill metadata (name, source, description, file path),
a multiline content editor, and save/delete actions.
Read-only skills (installed/plugin) show the content without edit controls.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    RADIUS_LG,
    make_badge,
    make_button,
    make_danger_button,
    make_dialog,
    make_divider,
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
        self._editor_field: ft.TextField = make_text_field(
            multiline=True,
            min_lines=20,
            max_lines=40,
            expand=True,
            border_radius=12,
        )

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
        self.content = self._build_content()

    def clear(self) -> None:
        """Deselect the current skill and show the empty state."""
        self._selected_skill = None
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
        folder_section = self._build_folder_files_section(skill)
        action_buttons = self._build_action_buttons(is_readonly)

        controls = [
            header,
            desc_row,
            path_row,
            folder_section,
            make_divider(),
            self._editor_field,
            ft.Row(controls=action_buttons, spacing=8),
        ]

        return ft.Column(
            controls=controls,
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

    def _build_folder_files_section(self, skill) -> ft.Control:
        """Build a collapsible section listing files in the skill's folder."""
        folder = Path(skill.file_path).parent
        try:
            entries = sorted(folder.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
            files = [e for e in entries if e.is_file()]
        except (OSError, PermissionError):
            files = []

        if not files:
            return ft.Container(height=0)

        # Collapsed by default if only 1 file (the skill itself)
        initially_open = len(files) > 1

        def _icon_for_file(name: str) -> str:
            lower = name.lower()
            if lower.endswith(".md"):
                return ft.Icons.DESCRIPTION_OUTLINED
            if lower.endswith((".json", ".yaml", ".yml", ".toml")):
                return ft.Icons.SETTINGS_OUTLINED
            if lower.endswith((".py", ".js", ".ts", ".sh")):
                return ft.Icons.CODE
            return ft.Icons.INSERT_DRIVE_FILE_OUTLINED

        def _format_size(size: int) -> str:
            if size < 1024:
                return f"{size} B"
            if size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            return f"{size / (1024 * 1024):.1f} MB"

        file_rows: list[ft.Control] = []
        for f in files:
            try:
                fsize = f.stat().st_size
            except OSError:
                fsize = 0
            is_current = str(f) == skill.file_path
            file_rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                _icon_for_file(f.name),
                                size=14,
                                color=(
                                    ft.Colors.PRIMARY
                                    if is_current
                                    else ft.Colors.ON_SURFACE_VARIANT
                                ),
                            ),
                            ft.Text(
                                f.name,
                                size=11,
                                weight=ft.FontWeight.W_600 if is_current else ft.FontWeight.W_400,
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
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    border_radius=6,
                    ink=True,
                    on_click=lambda _, p=str(f): open_in_file_manager(p),
                    tooltip=t("extensions.open_file"),
                )
            )

        return ft.Container(
            content=ft.ExpansionTile(
                title=ft.Text(
                    t("extensions.folder_files"),
                    size=12,
                    weight=ft.FontWeight.W_500,
                ),
                expanded=initially_open,
                tile_padding=ft.Padding.symmetric(horizontal=4, vertical=0),
                controls_padding=ft.Padding.only(left=4, right=4, bottom=4),
                controls=file_rows,
                dense=True,
            ),
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)),
            padding=0,
        )

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
