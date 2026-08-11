"""Knowledge base selector popup for chat RAG integration.

Displays a checkbox list of active knowledge bases with embedded chunks,
allowing the user to select one or more KBs for the current chat session.
Selection state is stored per session in ``state.kb.selected_kb_ids``.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

import flet as ft

from misaka.i18n import t

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)


class KBSelector(ft.Container):
    """Popup panel listing available knowledge bases with multi-select."""

    def __init__(
        self,
        state: AppState,
        *,
        on_change: object | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self._on_change = on_change
        self._kb_list: list[dict[str, Any]] = []
        self._items_column: ft.Column | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._items_column = ft.Column(spacing=0, tight=True)
        header = self._build_header()
        self.content = ft.Column(
            controls=[header, self._items_column],
            spacing=0,
            tight=True,
        )
        self.border_radius = 14
        self.border = ft.Border.all(
            1, ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE),
        )
        self.bgcolor = ft.Colors.SURFACE_CONTAINER
        self.padding = ft.Padding.symmetric(vertical=6)
        self.width = 320
        self.shadow = ft.BoxShadow(
            blur_radius=16,
            spread_radius=-2,
            offset=ft.Offset(0, 6),
            color=ft.Colors.with_opacity(0.16, ft.Colors.BLACK),
        )
        self.clip_behavior = ft.ClipBehavior.ANTI_ALIAS

    def _build_header(self) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.MENU_BOOK_ROUNDED,
                        size=14,
                        color=ft.Colors.PRIMARY,
                    ),
                    ft.Text(
                        t("chat.kb_select_title"),
                        size=12,
                        weight=ft.FontWeight.W_600,
                        expand=True,
                    ),
                    ft.Container(
                        content=ft.Text(
                            t("chat.kb_select_all"),
                            size=10,
                            color=ft.Colors.PRIMARY,
                        ),
                        on_click=self._handle_toggle_all,
                        ink=True,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                        border_radius=4,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=14, right=10, top=6, bottom=6),
            border=ft.Border(
                bottom=ft.BorderSide(
                    1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                ),
            ),
        )

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload available KBs and rebuild the item list."""
        self._kb_list = self._load_available_kbs()
        self._render_items()

    def _load_available_kbs(self) -> list[dict[str, Any]]:
        kb_svc = self.state.get_service("kb_service")
        if not kb_svc:
            return []
        try:
            return kb_svc.get_kb_for_chat_selection()
        except Exception:
            logger.exception("Failed to load KBs for chat selection")
            return []

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_items(self) -> None:
        if not self._items_column:
            return

        if not self._kb_list:
            self._items_column.controls = [self._build_empty_hint()]
            self._safe_update(self._items_column)
            return

        selected = set(self._get_selected_ids())
        items = [self._build_kb_item(kb, kb["id"] in selected) for kb in self._kb_list]
        self._items_column.controls = items
        self._safe_update(self._items_column)

    def _build_empty_hint(self) -> ft.Control:
        return ft.Container(
            content=ft.Text(
                t("chat.kb_no_available"),
                size=11,
                opacity=0.5,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        )

    def _build_kb_item(self, kb: dict[str, Any], selected: bool) -> ft.Control:
        kb_id = kb["id"]
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Checkbox(
                        value=selected,
                        on_change=lambda e, kid=kb_id: self._handle_toggle(kid, e),
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                kb.get("name", ""),
                                size=12,
                                weight=ft.FontWeight.W_500,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                f"{kb.get('document_count', 0)} {t('kb.documents').lower()}"
                                f" · {kb.get('chunk_count', 0)} {t('kb.chunks').lower()}",
                                size=10,
                                opacity=0.5,
                            ),
                        ],
                        spacing=1,
                        expand=True,
                        tight=True,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(left=6, right=14, top=2, bottom=2),
            ink=True,
        )

    # ------------------------------------------------------------------
    # Selection logic
    # ------------------------------------------------------------------

    def _get_session_id(self) -> str:
        return self.state.current_session_id or "__global__"

    def _get_selected_ids(self) -> list[str]:
        sid = self._get_session_id()
        if self.state.kb:
            # Preserve selection order: it determines stable RAG merge order.
            return list(dict.fromkeys(self.state.kb.selected_kb_ids.get(sid, [])))
        return []

    def _set_selected_ids(self, ids: list[str]) -> None:
        sid = self._get_session_id()
        kb = self.state.ensure_kb_state()
        kb.selected_kb_ids[sid] = ids

    def _handle_toggle(self, kb_id: str, e: ft.ControlEvent) -> None:
        selected = self._get_selected_ids()
        if e.data == "true":
            if kb_id not in selected:
                selected.append(kb_id)
        else:
            selected = [selected_id for selected_id in selected if selected_id != kb_id]
        self._set_selected_ids(selected)
        self._notify_change()

    def _handle_toggle_all(self, e: ft.ControlEvent) -> None:
        selected = self._get_selected_ids()
        all_ids = [kb["id"] for kb in self._kb_list]
        if set(selected) >= set(all_ids):
            self._set_selected_ids([])
        else:
            self._set_selected_ids(all_ids)
        self._render_items()
        self._notify_change()

    def _notify_change(self) -> None:
        if callable(self._on_change):
            self._on_change()

    def get_selected_count(self) -> int:
        return len(self._get_selected_ids())

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_update(control: ft.Control) -> None:
        with contextlib.suppress(Exception):
            control.update()
