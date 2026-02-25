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
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        expand=True,
                    ),
                    ft.Button(
                        content=t("extensions.new_skill"),
                        icon=ft.Icons.ADD,
                        on_click=self._show_create_dialog,
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

        # --- Search ---
        search_field = ft.TextField(
            hint_text=t("extensions.search_skills"),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=8,
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
            border=ft.Border(right=ft.BorderSide(1, ft.Colors.OUTLINE)),
        )

        # --- Right panel: editor ---
        self._editor_field = ft.TextField(
            multiline=True,
            min_lines=20,
            max_lines=40,
            expand=True,
            border_radius=8,
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
            "global": ft.Colors.BLUE,
            "project": ft.Colors.GREEN,
            "installed": ft.Colors.ORANGE,
            "plugin": ft.Colors.PURPLE,
        }

        badge = ft.Container(
            content=ft.Text(
                source_labels.get(skill.source, skill.source),
                size=10,
                color=ft.Colors.WHITE,
                weight=ft.FontWeight.BOLD,
            ),
            bgcolor=source_colors.get(skill.source, ft.Colors.GREY),
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        )

        # Header
        editor_header = ft.Row(
            controls=[
                ft.Text(
                    skill.name,
                    size=18,
                    weight=ft.FontWeight.W_500,
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
                ft.Button(
                    t("extensions.save_skill"),
                    icon=ft.Icons.SAVE,
                    on_click=self._save_skill,
                )
            )
            action_buttons.append(
                ft.OutlinedButton(
                    t("extensions.delete_skill"),
                    icon=ft.Icons.DELETE,
                    on_click=self._confirm_delete_skill,
                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
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
                ft.Divider(height=1),
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
            padding=ft.Padding.symmetric(horizontal=4, vertical=4),
            border_radius=6,
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

        dialog = ft.AlertDialog(
            title=ft.Text(t("extensions.delete_skill_title")),
            content=ft.Text(t("extensions.delete_skill_confirm")),
            actions=[
                ft.TextButton(
                    t("common.cancel"),
                    on_click=lambda ev: page.pop_dialog(),
                ),
                ft.Button(
                    t("common.delete"),
                    on_click=do_delete,
                    color=ft.Colors.WHITE,
                    bgcolor=ft.Colors.ERROR,
                ),
            ],
        )
        page.show_dialog(dialog)

    def _show_create_dialog(self, e: ft.ControlEvent) -> None:
        if not e.page:
            return
        page = e.page

        name_field = ft.TextField(
            label=t("extensions.skill_name"),
            hint_text=t("extensions.skill_name_hint"),
            autofocus=True,
            dense=True,
        )
        scope_dropdown = ft.Dropdown(
            label=t("extensions.skill_scope"),
            value="global",
            options=[
                ft.dropdown.Option(key="global", text=t("extensions.source_global")),
                ft.dropdown.Option(key="project", text=t("extensions.source_project")),
            ],
            dense=True,
        )
        content_field = ft.TextField(
            label=t("extensions.skill_content"),
            hint_text=t("extensions.skill_content_hint"),
            multiline=True,
            min_lines=6,
            max_lines=12,
        )

        def do_create(ev):
            name = (name_field.value or "").strip()
            content = content_field.value or ""
            scope = scope_dropdown.value or "global"
            if not name:
                return
            svc = self._get_skill_service()
            if svc:
                try:
                    svc.create_skill(name, content, scope=scope)
                    page.pop_dialog()
                    self._show_snackbar(page, t("extensions.skill_created"))
                    self._load_skills()
                    # Select newly created skill
                    for s in self._skills:
                        if s.name == name:
                            self._selected_skill = s
                            break
                    self._refresh_skill_list()
                    if self._editor_panel:
                        self._editor_panel.content = self._build_editor_content()
                    self.state.update()
                except Exception as exc:
                    logger.error("Failed to create skill: %s", exc)

        dialog = ft.AlertDialog(
            title=ft.Text(t("extensions.create_skill_title")),
            content=ft.Column(
                controls=[name_field, scope_dropdown, content_field],
                spacing=12,
                tight=True,
                width=400,
            ),
            actions=[
                ft.TextButton(
                    t("common.cancel"),
                    on_click=lambda ev: page.pop_dialog(),
                ),
                ft.Button(
                    t("common.save"),
                    on_click=do_create,
                ),
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
