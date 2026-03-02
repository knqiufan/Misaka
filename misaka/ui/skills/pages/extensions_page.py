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
from misaka.ui.skills.pages.skill_editor_panel import SkillEditorPanel
from misaka.ui.common.theme import (
    make_button,
    make_dialog,
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
        self._editor_panel: SkillEditorPanel | None = None
        self._build_ui()

    def _get_skill_service(self):
        return self.state.get_service("skill_service")

    # ------------------------------------------------------------------
    # Skill loading & filtering
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._load_skills()

        header = self._build_header()
        description = self._build_description()

        search_field = make_text_field(
            hint_text=t("extensions.search_skills"),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=12,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            on_change=self._on_search,
        )

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

        self._editor_panel = SkillEditorPanel(
            self.state,
            self._get_skill_service(),
            on_skill_saved=self._handle_skill_saved,
            on_skill_deleted=self._handle_skill_deleted,
        )

        main_content = ft.Row(
            controls=[left_panel, self._editor_panel],
            spacing=0,
            expand=True,
        )

        self.controls = [
            header,
            description,
            ft.Divider(height=1),
            main_content,
        ]

    def _build_header(self) -> ft.Container:
        return ft.Container(
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

    @staticmethod
    def _build_description() -> ft.Container:
        return ft.Container(
            content=ft.Text(
                t("extensions.description"),
                size=12,
                opacity=0.6,
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=4),
        )

    # ------------------------------------------------------------------
    # Skill list
    # ------------------------------------------------------------------

    def _refresh_skill_list(self) -> None:
        """Rebuild the skill list grouped by source."""
        if not self._skill_list:
            return

        if not self._filtered_skills:
            self._skill_list.controls = [self._build_empty_list_indicator()]
            return

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
            controls.append(self._build_group_header(source_labels.get(source, source)))
            for skill in sorted(skills, key=lambda s: s.name):
                is_selected = self._is_skill_selected(skill)
                controls.append(self._build_skill_item(skill, is_selected))

        self._skill_list.controls = controls

    def _build_empty_list_indicator(self) -> ft.Container:
        msg = (
            t("extensions.no_matching_skills")
            if self._search_query
            else t("extensions.no_skills")
        )
        return ft.Container(
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

    @staticmethod
    def _build_group_header(label: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(
                label,
                size=11,
                weight=ft.FontWeight.BOLD,
                opacity=0.6,
            ),
            padding=ft.Padding.only(left=8, top=8, bottom=4),
        )

    def _is_skill_selected(self, skill) -> bool:
        return (
            self._selected_skill is not None
            and self._selected_skill.name == skill.name
            and self._selected_skill.source == skill.source
        )

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

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _select_skill(self, skill) -> None:
        self._selected_skill = skill
        if self._editor_panel:
            self._editor_panel.set_skill(skill)
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
            self._editor_panel.clear()
        self.state.update()
        if e.page:
            self._show_snackbar(e.page, t("extensions.skills_refreshed"))

    # ------------------------------------------------------------------
    # Callbacks from SkillEditorPanel
    # ------------------------------------------------------------------

    def _handle_skill_saved(self, skill_name: str, skill_source: str) -> None:
        """Called by the editor panel after a successful save."""
        self._load_skills()
        for s in self._skills:
            if s.name == skill_name and s.source == skill_source:
                self._selected_skill = s
                break
        self._refresh_skill_list()
        if self._editor_panel:
            self._editor_panel.set_skill(self._selected_skill)
        self.state.update()

    def _handle_skill_deleted(self) -> None:
        """Called by the editor panel after a successful delete."""
        self._selected_skill = None
        self._load_skills()
        self._refresh_skill_list()
        if self._editor_panel:
            self._editor_panel.clear()
        self.state.update()

    # ------------------------------------------------------------------
    # ZIP install
    # ------------------------------------------------------------------

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
        except ImportError:
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
            self._editor_panel.clear()
        self.state.update()
        self._show_snackbar(
            page,
            t("extensions.install_zip_success", count=str(len(installed))),
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _show_snackbar(page: ft.Page, message: str) -> None:
        snackbar = ft.SnackBar(content=ft.Text(message))
        page.show_dialog(snackbar)

    def refresh(self) -> None:
        """Rebuild the extensions page."""
        self._build_ui()
