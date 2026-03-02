"""Skill editor panel — right-side detail/editor for a single skill.

Displays skill metadata (name, source, description, file path),
a multiline content editor, and save/delete actions.
Read-only skills (installed/plugin) show the content without edit controls.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    make_badge,
    make_button,
    make_danger_button,
    make_dialog,
    make_divider,
    make_text_button,
    make_text_field,
)

if TYPE_CHECKING:
    from misaka.services.skills.skill_service import SkillService
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
        Application state (used for ``state.update()``).
    skill_service:
        Reference to the ``SkillService`` instance (may be ``None``).
    on_skill_saved:
        Callback invoked after a skill is saved successfully.
        Receives ``(skill_name: str, skill_source: str)`` so the parent
        can reload and re-select.
    on_skill_deleted:
        Callback invoked after a skill is deleted successfully.
    """

    def __init__(
        self,
        state: AppState,
        skill_service: SkillService | None,
        *,
        on_skill_saved: Callable[[str, str], None] | None = None,
        on_skill_deleted: Callable[[], None] | None = None,
    ) -> None:
        self._state = state
        self._skill_service = skill_service
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
        action_buttons = self._build_action_buttons(is_readonly)

        return ft.Column(
            controls=[
                header,
                desc_row,
                path_row,
                make_divider(),
                self._editor_field,
                ft.Row(controls=action_buttons, spacing=8),
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
        svc = self._skill_service
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

        def do_delete(_ev: ft.ControlEvent) -> None:
            page.pop_dialog()
            svc = self._skill_service
            if not svc:
                return
            try:
                svc.delete_skill(skill.name, source=skill.source)
                self._show_snackbar(page, t("extensions.skill_deleted"))
                if self._on_skill_deleted:
                    self._on_skill_deleted()
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
