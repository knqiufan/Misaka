"""Skill market panel — online skill browser and installer.

Provides search, browsing, preview, and one-click install of skills
from the skills.sh ecosystem via the Skyll public API.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import (
    RADIUS_LG,
    make_button,
    make_empty_state,
    make_outlined_button,
    make_text_field,
)

if TYPE_CHECKING:
    from misaka.services.skills.skill_market_service import MarketSkill
    from misaka.state import AppState

logger = logging.getLogger(__name__)


class SkillMarketPanel(ft.Column):
    """Online skill market browser panel."""

    def __init__(self, state: AppState) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self._results: list[MarketSkill] = []
        self._selected_skill: MarketSkill | None = None
        self._is_searching = False
        self._is_installing = False
        self._search_query = ""
        self._result_list = ft.ListView(
            expand=True,
            spacing=6,
            padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            scroll=ft.ScrollMode.AUTO,
        )
        self._preview_container = ft.Container(expand=True)
        self._search_field: ft.TextField | None = None
        self._build_ui()

    def _get_market_service(self):
        return self.state.get_service("skill_market_service")

    def _get_skill_service(self):
        return self.state.get_service("skill_service")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._search_field = make_text_field(
            hint_text=t("extensions.market_search"),
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=RADIUS_LG,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            on_submit=self._on_search_submit,
        )

        search_row = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(content=self._search_field, expand=True),
                    make_button(
                        t("extensions.market_search_btn"),
                        icon=ft.Icons.SEARCH,
                        on_click=self._on_search_click,
                    ),
                    make_outlined_button(
                        t("extensions.market_load_popular"),
                        icon=ft.Icons.TRENDING_UP,
                        on_click=self._on_load_popular,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        )

        self._result_list.controls = [self._build_empty_hint()]

        left_panel = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=self._result_list,
                        expand=True,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            width=320,
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
            margin=ft.Margin.only(right=20),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        self._preview_container = ft.Container(
            content=self._build_empty_preview(),
            expand=True,
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
            padding=ft.Padding.all(16),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        content_row = ft.Row(
            controls=[left_panel, self._preview_container],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        self.controls = [search_row, content_row]

    def _build_empty_hint(self) -> ft.Container:
        empty = make_empty_state(
            ft.Icons.STORE_OUTLINED,
            t("extensions.market_hint"),
            icon_size=44,
            icon_opacity=0.25,
        )
        return ft.Container(
            content=empty,
            padding=ft.Padding.symmetric(vertical=32, horizontal=16),
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
        )

    @staticmethod
    def _build_empty_preview() -> ft.Control:
        return ft.Column(
            controls=[
                ft.Icon(ft.Icons.STORE_OUTLINED, size=48, opacity=0.2),
                ft.Text(
                    t("extensions.market_hint"),
                    size=14,
                    opacity=0.4,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )

    # ------------------------------------------------------------------
    # Result list
    # ------------------------------------------------------------------

    def _rebuild_result_list(self) -> None:
        if not self._results:
            msg = (
                t("extensions.market_no_results")
                if self._search_query
                else t("extensions.market_hint")
            )
            hint = (
                t("extensions.market_no_results_desc")
                if self._search_query
                else None
            )
            empty = make_empty_state(
                ft.Icons.SEARCH_OFF if self._search_query else ft.Icons.STORE_OUTLINED,
                msg,
                hint=hint,
                icon_size=44,
                icon_opacity=0.25,
            )
            self._result_list.controls = [
                ft.Container(
                    content=empty,
                    padding=ft.Padding.symmetric(vertical=32, horizontal=16),
                    border_radius=RADIUS_LG,
                    bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
                    border=ft.Border.all(
                        1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
                    ),
                )
            ]
            return

        controls: list[ft.Control] = []
        for skill in self._results:
            is_selected = (
                self._selected_skill is not None
                and self._selected_skill.id == skill.id
                and self._selected_skill.source == skill.source
            )
            controls.append(self._build_skill_card(skill, is_selected))
        self._result_list.controls = controls

    def _build_skill_card(
        self, skill: MarketSkill, is_selected: bool,
    ) -> ft.Control:
        install_text = t("extensions.market_installs", count=str(skill.install_count))

        item_content = ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(
                        ft.Icons.EXTENSION_OUTLINED,
                        size=18,
                        color=(
                            ft.Colors.PRIMARY
                            if is_selected
                            else ft.Colors.ON_SURFACE_VARIANT
                        ),
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
                            weight=(
                                ft.FontWeight.W_600
                                if is_selected
                                else ft.FontWeight.W_500
                            ),
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            skill.description or skill.source,
                            size=10,
                            opacity=0.6,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Row(
                            controls=[
                                ft.Text(install_text, size=9, opacity=0.4),
                                ft.Text(
                                    f"⭐ {skill.relevance_score:.0f}",
                                    size=9,
                                    opacity=0.4,
                                ),
                            ],
                            spacing=8,
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
            "on_click": lambda e, s=skill: self._on_select_skill(s),
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
    # Preview panel
    # ------------------------------------------------------------------

    def _build_skill_preview(self, skill: MarketSkill) -> ft.Control:
        from misaka.ui.common.theme import make_badge

        source_badge = make_badge(skill.source, bgcolor="#7c3aed")
        install_text = t("extensions.market_installs", count=str(skill.install_count))

        header = ft.Row(
            controls=[
                ft.Icon(ft.Icons.EXTENSION, size=24, color=ft.Colors.PRIMARY),
                ft.Text(skill.name, size=18, weight=ft.FontWeight.W_600),
                source_badge,
                ft.Container(expand=True),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        score_text = f"{skill.relevance_score:.1f}"

        meta_row = ft.Row(
            controls=[
                ft.Icon(ft.Icons.DOWNLOAD, size=14, opacity=0.5),
                ft.Text(install_text, size=12, opacity=0.5),
                ft.Container(width=12),
                ft.Icon(ft.Icons.STAR_ROUNDED, size=14, color="#f59e0b"),
                ft.Text(score_text, size=12, opacity=0.5),
            ],
            spacing=6,
        )

        desc = ft.Text(
            skill.description or "",
            size=13,
            opacity=0.7,
        )

        content_preview = ft.TextField(
            value=skill.content or t("extensions.market_preview"),
            multiline=True,
            min_lines=10,
            max_lines=25,
            read_only=True,
            expand=True,
            border_radius=12,
        )

        install_btn = make_button(
            t("extensions.market_install"),
            icon=ft.Icons.DOWNLOAD,
            on_click=lambda e, s=skill: self._on_install_skill(e, s),
        )

        refs_controls: list[ft.Control] = []
        if skill.refs:
            for ref_label, ref_url in skill.refs.items():
                if ref_url:
                    refs_controls.append(
                        ft.TextButton(
                            content=ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.OPEN_IN_NEW, size=14),
                                    ft.Text(ref_label, size=12),
                                ],
                                spacing=4,
                                tight=True,
                            ),
                            url=ref_url,
                        )
                    )

        action_row = ft.Row(
            controls=[install_btn, *refs_controls],
            spacing=8,
        )

        return ft.Column(
            controls=[
                header,
                meta_row,
                desc,
                ft.Divider(height=1, thickness=1, opacity=0.1),
                content_preview,
                action_row,
            ],
            spacing=10,
            expand=True,
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_search_submit(self, e: ft.ControlEvent) -> None:
        if not self._search_field:
            return
        query = (self._search_field.value or "").strip()
        if query:
            self._search_query = query
            self._do_search(query)

    def _on_search_click(self, e: ft.ControlEvent) -> None:
        if self._search_field:
            query = (self._search_field.value or "").strip()
            if query:
                self._search_query = query
                self._do_search(query)

    def _on_load_popular(self, e: ft.ControlEvent) -> None:
        self._search_query = "popular"
        if self._search_field:
            self._search_field.value = "popular"
        self._do_search("popular")

    def _do_search(self, query: str) -> None:
        if self._is_searching:
            return
        page = self.page
        if not page:
            return

        svc = self._get_market_service()
        if not svc:
            logger.warning("SkillMarketService not available")
            return

        self._is_searching = True
        self._result_list.controls = [
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.ProgressRing(width=20, height=20, stroke_width=2),
                        ft.Text(t("extensions.market_searching"), size=13, opacity=0.6),
                    ],
                    spacing=10,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(vertical=40),
            )
        ]
        self.state.update()

        async def _run_search() -> None:
            try:
                result = await svc.search(query, limit=30)
                self._results = result.skills
                self._is_searching = False

                if result.error:
                    self._show_snackbar(
                        page, t("extensions.market_search_error", error=result.error),
                    )
                self._rebuild_result_list()
                self.state.update()
            except Exception as exc:
                self._is_searching = False
                logger.error("Market search failed: %s", exc)
                self._show_snackbar(
                    page, t("extensions.market_search_error", error=str(exc)),
                )
                self._rebuild_result_list()
                self.state.update()

        page.run_task(_run_search)

    def _on_select_skill(self, skill: MarketSkill) -> None:
        self._selected_skill = skill
        self._rebuild_result_list()

        if skill.content:
            self._preview_container.content = self._build_skill_preview(skill)
            self.state.update()
        else:
            self._preview_container.content = ft.Column(
                controls=[
                    ft.ProgressRing(width=24, height=24, stroke_width=2),
                    ft.Text(t("common.loading"), size=13, opacity=0.5),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            )
            self.state.update()
            self._fetch_and_show_content(skill)

    def _fetch_and_show_content(self, skill: MarketSkill) -> None:
        page = self.page
        if not page:
            return
        svc = self._get_market_service()
        if not svc:
            return

        async def _fetch() -> None:
            content = await svc.get_skill_content(skill.source, skill.id)
            if content:
                skill.content = content
            if (
                self._selected_skill
                and self._selected_skill.id == skill.id
                and self._selected_skill.source == skill.source
            ):
                self._preview_container.content = self._build_skill_preview(skill)
                self.state.update()

        page.run_task(_fetch)

    def _on_install_skill(self, e: ft.ControlEvent, skill: MarketSkill) -> None:
        page = e.page
        if not page or self._is_installing:
            return

        svc = self._get_market_service()
        if not svc:
            return

        self._is_installing = True

        async def _install() -> None:
            try:
                result = await svc.install_skill(skill, content=skill.content or None)
                self._is_installing = False
                if result:
                    self._show_snackbar(
                        page,
                        t("extensions.market_installed", name=skill.name),
                    )
                else:
                    self._show_snackbar(
                        page,
                        t("extensions.market_install_failed", error="No content"),
                    )
            except Exception as exc:
                self._is_installing = False
                logger.error("Market install failed: %s", exc)
                self._show_snackbar(
                    page,
                    t("extensions.market_install_failed", error=str(exc)),
                )

        page.run_task(_install)

    @staticmethod
    def _show_snackbar(page: ft.Page, message: str) -> None:
        snackbar = ft.SnackBar(content=ft.Text(message))
        page.show_dialog(snackbar)
