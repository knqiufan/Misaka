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
    RADIUS_LG,
    RADIUS_MD,
    make_button,
    make_dialog,
    make_divider,
    make_empty_state,
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

        search_field = make_text_field(
            hint_text=t("extensions.search_skills"),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=RADIUS_LG,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            on_change=self._on_search,
        )

        self._skill_list = ft.ListView(
            expand=True,
            spacing=6,
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            scroll=ft.ScrollMode.AUTO,
        )
        self._refresh_skill_list()

        left_panel = self._build_left_panel(search_field)

        self._editor_panel = SkillEditorPanel(
            self.state,
            self._get_skill_service(),
            on_skill_saved=self._handle_skill_saved,
            on_skill_deleted=self._handle_skill_deleted,
        )

        editor_wrapper = ft.Container(
            content=self._editor_panel,
            expand=True,
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
            padding=0,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        main_content = ft.Row(
            controls=[left_panel, editor_wrapper],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        inner = ft.Column(
            controls=[header, main_content],
            spacing=0,
            expand=True,
        )

        main_card = ft.Container(
            content=inner,
            margin=ft.Margin.symmetric(horizontal=10, vertical=10),
            padding=ft.Padding.all(10),
            expand=True,
            border_radius=RADIUS_MD,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            ),
            shadow=[
                ft.BoxShadow(
                    blur_radius=24,
                    spread_radius=-4,
                    color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK),
                    offset=ft.Offset(0, 4),
                ),
                ft.BoxShadow(
                    blur_radius=12,
                    spread_radius=-2,
                    color=ft.Colors.with_opacity(0.04, ft.Colors.BLACK),
                    offset=ft.Offset(0, 2),
                ),
            ],
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        self.controls = [main_card]

    def _build_header(self) -> ft.Container:
        """Build page header with icon, title, description and action buttons."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(
                            ft.Icons.CODE,
                            size=24,
                            color=ft.Colors.PRIMARY,
                        ),
                        width=44,
                        height=44,
                        border_radius=RADIUS_LG,
                        bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                t("extensions.title"),
                                size=20,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(
                                t("extensions.description"),
                                size=12,
                                opacity=0.65,
                            ),
                        ],
                        spacing=2,
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
                spacing=16,
            ),
            padding=ft.Padding.only(bottom=20),
        )

    def _build_left_panel(self, search_field: ft.TextField) -> ft.Container:
        """Build left panel with search and skill list, styled as card."""
        panel_content = ft.Column(
            controls=[
                ft.Container(
                    content=search_field,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=12),
                ),
                ft.Container(
                    content=self._skill_list,
                    expand=True,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
            ],
            spacing=0,
            expand=True,
        )
        return ft.Container(
            content=panel_content,
            width=280,
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
            padding=ft.Padding.only(right=0),
            margin=ft.Margin.only(right=20),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
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
        hint = t("extensions.no_skills_desc") if not self._search_query else None
        empty = make_empty_state(
            ft.Icons.CODE_OFF,
            msg,
            hint=hint,
            icon_size=44,
            icon_opacity=0.25,
        )
        return ft.Container(
            content=empty,
            padding=ft.Padding.symmetric(vertical=32, horizontal=16),
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1,
                ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
        )

    @staticmethod
    def _build_group_header(label: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(
                label,
                size=11,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE),
            ),
            padding=ft.Padding.only(left=4, top=12, bottom=6),
        )

    def _is_skill_selected(self, skill) -> bool:
        return (
            self._selected_skill is not None
            and self._selected_skill.name == skill.name
            and self._selected_skill.source == skill.source
        )

    def _build_skill_item(self, skill, is_selected: bool) -> ft.Control:
        """Build a single skill list item with card style."""
        item_content = ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(
                        ft.Icons.DESCRIPTION_OUTLINED,
                        size=18,
                        color=ft.Colors.PRIMARY if is_selected else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    width=36,
                    height=36,
                    border_radius=RADIUS_LG,
                    bgcolor=(
                        ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)
                        if is_selected
                        else ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Text(
                            skill.name,
                            size=13,
                            weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.W_500,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            skill.description or skill.file_path,
                            size=10,
                            opacity=0.6,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        card_style: dict = {
            "content": item_content,
            "padding": ft.Padding.symmetric(horizontal=12, vertical=10),
            "border_radius": RADIUS_LG,
            "bgcolor": (
                ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY)
                if is_selected
                else ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE)
            ),
            "border": ft.Border.all(
                1,
                ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)
                if is_selected
                else ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
            "on_click": lambda e, s=skill: self._select_skill(s),
            "ink": True,
        }
        if is_selected:
            card_style["shadow"] = [
                ft.BoxShadow(
                    blur_radius=8,
                    spread_radius=-1,
                    color=ft.Colors.with_opacity(0.04, ft.Colors.BLACK),
                    offset=ft.Offset(0, 1),
                ),
            ]
        return ft.Container(**card_style)

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
