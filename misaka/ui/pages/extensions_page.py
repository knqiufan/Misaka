"""Extensions page — Skills Manager.

Full skills management UI with a left panel showing skill list grouped
by source (Global/Project/Installed/Plugin), and a right panel showing
a skill editor. Supports CRUD operations on skill files.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.theme import (
    make_badge,
    make_button,
    make_danger_button,
    make_dialog,
    make_divider,
    make_outlined_button,
    make_text_button,
    make_text_field,
)

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)


class ExtensionsPage(ft.Column):
    """Extensions and skills management page."""

    def __init__(self, state: AppState) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._skills: list = []
        self._filtered_skills: list = []
        self._selected_skill = None
        self._search_query = ""
        self._skill_list: ft.ListView | None = None
        self._editor_field: ft.TextField | None = None
        self._editor_panel: ft.Container | None = None
        self._build_ui()

    def _get_skill_service(self):
        if hasattr(self.state, "services") and self.state.services:
            return getattr(self.state.services, "skill_service", None)
        return None

    def _load_skills(self) -> None:
        svc = self._get_skill_service()
        if svc:
            try:
                self._skills = svc.list_skills()
            except Exception as exc:
                logger.warning("Failed to load skills: %s", exc)
                self._skills = []
        else:
            self._skills = []
        self._apply_filter()

    def _apply_filter(self) -> None:
        if not self._search_query:
            self._filtered_skills = list(self._skills)
        else:
            q = self._search_query.lower()
            self._filtered_skills = [
                s for s in self._skills
                if q in s.name.lower() or q in (s.description or "").lower()
            ]

    def _build_ui(self) -> None:
        self._load_skills()

        # --- Header ---
        header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        t("extensions.title"),
                        size=22,
                        weight=ft.FontWeight.W_600,
                        expand=True,
                    ),
                    make_outlined_button(
                        t("extensions.refresh_skills"),
                        icon=ft.Icons.REFRESH,
                        on_click=self._refresh_all_skills,
                    ),
                    make_button(
                        t("extensions.install_from_zip"),
                        icon=ft.Icons.UPLOAD_FILE,
                        on_click=self._pick_zip_and_install,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=24, right=24, top=20, bottom=8),
        )

        description = ft.Container(
            content=ft.Text(
                t("extensions.description"),
                size=12,
                opacity=0.6,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=4),
        )

        search_field = make_text_field(
            hint_text=t("extensions.search_skills"),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=12,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            on_change=self._on_search,
        )

        # --- Left panel: skill list ---
        self._skill_list = ft.ListView(
            expand=True,
            spacing=2,
            padding=ft.Padding.symmetric(horizontal=4, vertical=4),
        )
        self._refresh_skill_list()

        left_panel = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=search_field,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=8),
                    ),
                    self._skill_list,
                ],
                spacing=0,
                expand=True,
            ),
            width=260,
            border=ft.Border(
                right=ft.BorderSide(
                    1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
                ),
            ),
        )

        self._editor_field = make_text_field(
            multiline=True,
            min_lines=20,
            max_lines=40,
            expand=True,
            border_radius=12,
        )

        self._editor_panel = ft.Container(
            content=self._build_editor_content(),
            expand=True,
            padding=ft.Padding.all(16),
        )

        # --- Main content ---
        main_content = ft.Row(
            controls=[
                left_panel,
                self._editor_panel,
            ],
            spacing=0,
            expand=True,
        )

        self.controls = [
            header,
            description,
            ft.Divider(height=1),
            main_content,
        ]

    def _build_editor_content(self) -> ft.Control:
        """Build the right-side editor panel content."""
        if not self._selected_skill:
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

        skill = self._selected_skill
        is_readonly = skill.source in ("installed", "plugin")

        if self._editor_field:
            self._editor_field.value = skill.content
            self._editor_field.read_only = is_readonly

        # Source badge
        source_labels = {
            "global": t("extensions.source_global"),
            "project": t("extensions.source_project"),
            "installed": t("extensions.source_installed"),
            "plugin": t("extensions.source_plugin"),
        }
        source_colors = {
            "global": "#2563eb",
            "project": "#10b981",
            "installed": "#f59e0b",
            "plugin": "#7c3aed",
        }

        badge = make_badge(
            source_labels.get(skill.source, skill.source),
            bgcolor=source_colors.get(skill.source, "#6b7280"),
        )

        # Header
        editor_header = ft.Row(
            controls=[
                ft.Text(
                    skill.name,
                    size=16,
                    weight=ft.FontWeight.W_600,
                ),
                badge,
                ft.Container(expand=True),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Description
        desc_row = ft.Container(height=0)
        if skill.description:
            desc_row = ft.Text(
                skill.description,
                size=12,
                opacity=0.6,
            )

        # File path
        path_row = ft.Text(
            skill.file_path,
            size=11,
            opacity=0.4,
        )

        # Action buttons
        action_buttons: list[ft.Control] = []
        if not is_readonly:
            action_buttons.append(
                make_button(
                    t("extensions.save_skill"),
                    icon=ft.Icons.SAVE,
                    on_click=self._save_skill,
                )
            )
            action_buttons.append(
                make_danger_button(
                    t("extensions.delete_skill"),
                    icon=ft.Icons.DELETE,
                    on_click=self._confirm_delete_skill,
                )
            )
        else:
            action_buttons.append(
                ft.Text(
                    t("extensions.readonly_skill"),
                    size=12,
                    italic=True,
                    opacity=0.5,
                )
            )

        return ft.Column(
            controls=[
                editor_header,
                desc_row,
                path_row,
                make_divider(),
                self._editor_field,
                ft.Row(
                    controls=action_buttons,
                    spacing=8,
                ),
            ],
            spacing=8,
            expand=True,
        )

    def _refresh_skill_list(self) -> None:
        """Rebuild the skill list grouped by source."""
        if not self._skill_list:
            return

        if not self._filtered_skills:
            msg = (
                t("extensions.no_matching_skills")
                if self._search_query
                else t("extensions.no_skills")
            )
            self._skill_list.controls = [
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.CODE_OFF, size=32, opacity=0.3),
                            ft.Text(
                                msg,
                                italic=True,
                                size=12,
                                opacity=0.5,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=24,
                )
            ]
            return

        # Group by source
        groups: dict[str, list] = {}
        for skill in self._filtered_skills:
            groups.setdefault(skill.source, []).append(skill)

        source_order = ["project", "global", "installed", "plugin"]
        source_labels = {
            "global": t("extensions.source_global"),
            "project": t("extensions.source_project"),
            "installed": t("extensions.source_installed"),
            "plugin": t("extensions.source_plugin"),
        }

        controls: list[ft.Control] = []
        for source in source_order:
            skills = groups.get(source, [])
            if not skills:
                continue

            # Group header
            controls.append(
                ft.Container(
                    content=ft.Text(
                        source_labels.get(source, source),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        opacity=0.6,
                    ),
                    padding=ft.Padding.only(left=8, top=8, bottom=4),
                )
            )

            for skill in sorted(skills, key=lambda s: s.name):
                is_selected = (
                    self._selected_skill is not None
                    and self._selected_skill.name == skill.name
                    and self._selected_skill.source == skill.source
                )
                controls.append(self._build_skill_item(skill, is_selected))

        self._skill_list.controls = controls

    def _build_skill_item(self, skill, is_selected: bool) -> ft.Control:
        """Build a single skill list item."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        width=3,
                        height=32,
                        border_radius=2,
                        bgcolor=ft.Colors.PRIMARY if is_selected else ft.Colors.TRANSPARENT,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                skill.name,
                                size=13,
                                weight=ft.FontWeight.W_500 if is_selected else ft.FontWeight.NORMAL,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                skill.description or skill.file_path,
                                size=10,
                                opacity=0.5,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=6, vertical=5),
            border_radius=8,
            bgcolor=(
                ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY)
                if is_selected
                else ft.Colors.TRANSPARENT
            ),
            on_click=lambda e, s=skill: self._select_skill(s),
            ink=True,
        )

    def _select_skill(self, skill) -> None:
        self._selected_skill = skill
        if self._editor_panel:
            self._editor_panel.content = self._build_editor_content()
        self._refresh_skill_list()
        self.state.update()

    def _on_search(self, e: ft.ControlEvent) -> None:
        self._search_query = (e.data or "").strip()
        self._apply_filter()
        self._refresh_skill_list()
        if self._skill_list:
            self._skill_list.update()

    def _refresh_all_skills(self, e: ft.ControlEvent) -> None:
        """Reload all skills from disk and refresh the UI."""
        self._selected_skill = None
        self._load_skills()
        self._refresh_skill_list()
        if self._editor_panel:
            self._editor_panel.content = self._build_editor_content()
        self.state.update()
        if e.page:
            self._show_snackbar(e.page, t("extensions.skills_refreshed"))

    def _pick_zip_and_install(self, e: ft.ControlEvent) -> None:
        if not e.page:
            return
        page = e.page
        result, zip_path = self._pick_zip_file_path()
        if result == "selected" and zip_path:
            self._install_skill_from_zip_path(page, zip_path)
            return
        if result == "cancelled":
            return

        self._show_zip_path_dialog(page)

    @staticmethod
    def _pick_zip_file_path() -> tuple[str, str | None]:
        """Open native file dialog and return (status, zip_path).

        Status values:
        - "selected": user picked a file
        - "cancelled": dialog opened, but user cancelled/closed it
        - "unavailable": native picker is not available
        """
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception:
            return "unavailable", None

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            selected = filedialog.askopenfilename(
                title="Select skill ZIP",
                filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
            )
            if selected:
                return "selected", selected
            return "cancelled", None
        finally:
            root.destroy()

    def _show_zip_path_dialog(self, page: ft.Page) -> None:
        zip_path_field = make_text_field(
            label=t("extensions.zip_path_label"),
            hint_text=t("extensions.zip_path_hint"),
            autofocus=True,
            dense=True,
        )

        def do_install(_ev: ft.ControlEvent) -> None:
            zip_path = (zip_path_field.value or "").strip()
            if not zip_path:
                return
            page.pop_dialog()
            self._install_skill_from_zip_path(page, zip_path)

        dialog = make_dialog(
            title=t("extensions.install_from_zip"),
            content=ft.Column(
                controls=[
                    ft.Text(t("extensions.install_zip_manual_notice"), size=12, opacity=0.7),
                    zip_path_field,
                ],
                spacing=12,
                tight=True,
                width=420,
            ),
            actions=[
                make_text_button(
                    t("common.cancel"), on_click=lambda ev: page.pop_dialog(),
                ),
                make_button(t("common.confirm"), on_click=do_install),
            ],
        )
        page.show_dialog(dialog)

    def _install_skill_from_zip_path(self, page: ft.Page, zip_path: str) -> None:
        svc = self._get_skill_service()
        if not svc:
            return

        try:
            installed = svc.install_skills_from_zip(zip_path)
        except Exception as exc:
            logger.error("Failed to install skill zip: %s", exc)
            self._show_snackbar(page, t("extensions.install_zip_failed", error=str(exc)))
            return

        self._selected_skill = None
        self._load_skills()
        self._refresh_skill_list()
        if self._editor_panel:
            self._editor_panel.content = self._build_editor_content()
        self.state.update()
        self._show_snackbar(
            page,
            t("extensions.install_zip_success", count=str(len(installed))),
        )

    def _save_skill(self, e: ft.ControlEvent) -> None:
        svc = self._get_skill_service()
        if not svc or not self._selected_skill or not self._editor_field:
            return
        try:
            svc.update_skill(
                self._selected_skill.name,
                self._editor_field.value or "",
                source=self._selected_skill.source,
            )
            self._show_snackbar(e.page, t("extensions.skill_saved"))
            self._load_skills()
            # Re-select the updated skill
            for s in self._skills:
                if s.name == self._selected_skill.name and s.source == self._selected_skill.source:
                    self._selected_skill = s
                    break
            self._refresh_skill_list()
            if self._editor_panel:
                self._editor_panel.content = self._build_editor_content()
            self.state.update()
        except Exception as exc:
            logger.error("Failed to save skill: %s", exc)

    def _confirm_delete_skill(self, e: ft.ControlEvent) -> None:
        if not e.page or not self._selected_skill:
            return

        page = e.page
        skill = self._selected_skill

        def do_delete(ev):
            page.pop_dialog()
            svc = self._get_skill_service()
            if svc:
                try:
                    svc.delete_skill(skill.name, source=skill.source)
                    self._show_snackbar(page, t("extensions.skill_deleted"))
                    self._selected_skill = None
                    self._load_skills()
                    self._refresh_skill_list()
                    if self._editor_panel:
                        self._editor_panel.content = self._build_editor_content()
                    self.state.update()
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
    def _show_snackbar(page: ft.Page, message: str) -> None:
        snackbar = ft.SnackBar(content=ft.Text(message))
        page.show_dialog(snackbar)

    def refresh(self) -> None:
        """Rebuild the extensions page."""
        self._build_ui()
