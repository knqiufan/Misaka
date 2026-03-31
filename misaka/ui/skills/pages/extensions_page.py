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
from misaka.ui.common.context_menu import ContextMenuItem, shared_context_menu
from misaka.ui.common.theme import (
    RADIUS_LG,
    RADIUS_MD,
    make_button,
    make_danger_button,
    make_dialog,
    make_empty_state,
    make_outlined_button,
    make_text_button,
    make_text_field,
)
from misaka.ui.skills.pages.skill_editor_panel import SkillEditorPanel
from misaka.utils.platform import open_in_file_manager

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
        self._file_picker: ft.FilePicker | None = None
        self._initialized = False
        # Build the UI skeleton without loading data yet.
        # Data is loaded on first refresh() or when the page becomes visible.
        self._build_ui_skeleton()

    def _get_skill_service(self):
        return self.state.get_service("skill_service")

    # ------------------------------------------------------------------
    # Skill loading & filtering
    # ------------------------------------------------------------------

    def _load_skills(self) -> None:
        """Scan all skill sources and populate ``_skills``."""
        svc = self._get_skill_service()
        if not svc:
            logger.warning("SkillService not available, cannot load skills")
            self._skills = []
            self._apply_filter()
            return
        try:
            self._skills = svc.list_skills()
        except Exception as exc:
            logger.warning("Failed to load skills: %s", exc)
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
    # UI construction (one-time skeleton)
    # ------------------------------------------------------------------

    def _build_ui_skeleton(self) -> None:
        """Build the static UI structure once. Data is populated later."""
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
        # Show empty state initially
        self._skill_list.controls = [self._build_empty_list_indicator()]

        left_panel = self._build_left_panel(search_field)

        self._editor_panel = SkillEditorPanel(
            self.state,
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
                        t("extensions.new_skill"),
                        icon=ft.Icons.ADD,
                        on_click=self._show_create_skill_dialog,
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
        card = ft.Container(**card_style)
        return ft.GestureDetector(
            content=card,
            on_secondary_tap_down=lambda e, s=skill: self._on_skill_context_menu(e, s),
        )

    # ------------------------------------------------------------------
    # Context menu (right-click on skill item)
    # ------------------------------------------------------------------

    def _on_skill_context_menu(self, e: ft.TapEvent, skill) -> None:
        """Show context menu for a skill list item."""
        page = self.page
        if not page:
            return
        pos = e.global_position
        items: list[ContextMenuItem] = [
            ContextMenuItem(
                icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                label=t("right_panel.open_in_file_manager"),
                on_click=lambda s=skill: self._open_skill_in_file_manager(s),
                icon_color="#64748b",
            ),
        ]
        if skill.source in ("global", "project", "installed"):
            items.append(ContextMenuItem(
                icon=ft.Icons.DELETE,
                label=t("extensions.delete_skill"),
                on_click=lambda s=skill: self._confirm_delete_skill(s),
                icon_color=ft.Colors.ERROR,
            ))
        shared_context_menu.show(page, global_x=pos.x, global_y=pos.y, items=items)

    def _open_skill_in_file_manager(self, skill) -> None:
        shared_context_menu.dismiss()
        open_in_file_manager(skill.file_path)

    def _confirm_delete_skill(self, skill) -> None:
        """Show delete confirmation dialog for a skill from the list."""
        shared_context_menu.dismiss()
        page = self.page
        if not page:
            return
        name, source = skill.name, skill.source

        def do_delete(_ev: ft.ControlEvent) -> None:
            page.pop_dialog()
            svc = self._get_skill_service()
            if not svc:
                return
            try:
                svc.delete_skill(name, source=source)
                self._show_snackbar(page, t("extensions.skill_deleted"))
                self._reload_after_delete(name, source)
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
    # New skill creation
    # ------------------------------------------------------------------

    def _show_create_skill_dialog(self, e: ft.ControlEvent) -> None:
        """Show dialog to create a new skill."""
        page = e.page
        if not page:
            return

        name_field = make_text_field(
            label=t("extensions.skill_name"),
            hint_text=t("extensions.skill_name_hint"),
            dense=True,
            autofocus=True,
        )
        content_field = make_text_field(
            label=t("extensions.skill_content"),
            hint_text=t("extensions.skill_content_hint"),
            multiline=True,
            min_lines=6,
            max_lines=12,
        )

        scope_state = {"scope": "global"}

        def _build_scope_buttons() -> ft.Row:
            """Build scope selector buttons (Global / Project)."""
            def make_scope_btn(label: str, value: str) -> ft.Container:
                is_active = scope_state["scope"] == value
                return ft.Container(
                    content=ft.Text(
                        label,
                        size=12,
                        weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_400,
                        color=ft.Colors.ON_PRIMARY if is_active else ft.Colors.ON_SURFACE,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=6),
                    border_radius=RADIUS_LG,
                    bgcolor=(
                        ft.Colors.PRIMARY
                        if is_active
                        else ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)
                    ),
                    on_click=lambda _, v=value: _on_scope_change(v),
                    ink=True,
                )

            return ft.Row(
                controls=[
                    ft.Text(t("extensions.skill_scope"), size=12, opacity=0.7),
                    make_scope_btn(t("extensions.source_global"), "global"),
                    make_scope_btn(t("extensions.source_project"), "project"),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        scope_row_container = ft.Container(content=_build_scope_buttons())

        def _on_scope_change(value: str) -> None:
            scope_state["scope"] = value
            scope_row_container.content = _build_scope_buttons()
            scope_row_container.update()

        def do_create(_ev: ft.ControlEvent) -> None:
            name = (name_field.value or "").strip()
            if not name:
                self._show_snackbar(page, t("extensions.skill_name_required"))
                return
            svc = self._get_skill_service()
            if not svc:
                return
            try:
                new_skill = svc.create_skill(
                    name, content_field.value or "", scope=scope_state["scope"],
                )
            except FileExistsError:
                self._show_snackbar(page, t("extensions.skill_exists"))
                return
            except Exception as exc:
                logger.error("Failed to create skill: %s", exc)
                return

            page.pop_dialog()
            self._load_skills()
            # Select the newly created skill
            for s in self._skills:
                if s.name == new_skill.name and s.source == new_skill.source:
                    self._selected_skill = s
                    break
            self._refresh_skill_list()
            if self._editor_panel and self._selected_skill:
                self._editor_panel.set_skill(self._selected_skill)
            self.state.update()
            self._show_snackbar(page, t("extensions.skill_created"))

        dialog_content = ft.Column(
            controls=[
                name_field,
                scope_row_container,
                content_field,
            ],
            spacing=12,
            tight=True,
            width=480,
        )

        dialog = make_dialog(
            title=t("extensions.create_skill_title"),
            content=dialog_content,
            actions=[
                make_text_button(
                    t("common.cancel"),
                    on_click=lambda ev: page.pop_dialog(),
                ),
                make_button(t("extensions.new_skill"), on_click=do_create),
            ],
        )
        page.show_dialog(dialog)

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

    def _handle_skill_deleted(self, name: str, source: str) -> None:
        """Called by the editor panel after a successful delete."""
        self._reload_after_delete(name, source)

    def _reload_after_delete(self, deleted_name: str, deleted_source: str) -> None:
        """Reload skills and update UI after a skill is deleted.

        Clears the editor only when the deleted skill was the one being viewed,
        preserving the selection otherwise.
        """
        is_selected_deleted = (
            self._selected_skill is not None
            and self._selected_skill.name == deleted_name
            and self._selected_skill.source == deleted_source
        )
        self._load_skills()
        if is_selected_deleted:
            self._selected_skill = None
            if self._editor_panel:
                self._editor_panel.clear()
        self._refresh_skill_list()
        self.state.update()

    def _ensure_file_picker(self) -> ft.FilePicker | None:
        """Lazily create and register a FilePicker on the page.

        Flet's FilePicker is a Service control — it must be appended to
        ``page.services`` (not overlay) and the page must be updated
        before the picker can be used.  We create it once and reuse it.
        """
        if self._file_picker is not None:
            return self._file_picker

        page = self.state.page
        if not page:
            return None

        picker = ft.FilePicker()
        page.services.append(picker)
        page.update()
        self._file_picker = picker
        return picker

    # ------------------------------------------------------------------
    # ZIP install
    # ------------------------------------------------------------------

    def _pick_zip_and_install(self, e: ft.ControlEvent) -> None:
        if not e.page:
            return
        page = e.page

        picker = self._ensure_file_picker()
        if not picker:
            return

        async def _do_pick() -> None:
            try:
                files = await picker.pick_files(
                    dialog_title=t("extensions.install_from_zip"),
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["zip"],
                    allow_multiple=False,
                )
            except Exception as exc:
                logger.warning("FilePicker failed: %s", exc)
                files = None

            if files:
                zip_path = files[0].path
                if zip_path:
                    self._install_skill_from_zip_path(page, zip_path)

        page.run_task(_do_pick)

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
        """Reload skill data and update the existing UI controls.

        Called by AppShell when the user navigates to this page.
        Does NOT rebuild the control tree — only reloads data and
        updates the list contents in-place.
        """
        self._load_skills()
        self._refresh_skill_list()
        # Clear editor selection on page re-entry to avoid stale state
        if not self._initialized:
            self._initialized = True
