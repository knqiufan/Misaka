"""Floating notification panel component.

Displays a drop-down list of recent notifications with read/unread
state, relative timestamps, and action buttons. Rendered as an
overlay anchored to the bottom-left of the navigation rail.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import flet as ft

from misaka.db.models import Notification
from misaka.i18n import t
from misaka.ui.common.theme import make_icon_button

if TYPE_CHECKING:
    from misaka.state import AppState

# Icon / colour mapping per notification type
_TYPE_CONFIG: dict[str, tuple[str, str]] = {
    "info": (ft.Icons.INFO_OUTLINE, ft.Colors.BLUE),
    "success": (ft.Icons.CHECK_CIRCLE_OUTLINE, ft.Colors.GREEN),
    "warning": (ft.Icons.WARNING_AMBER_OUTLINED, ft.Colors.ORANGE),
    "error": (ft.Icons.ERROR_OUTLINE, ft.Colors.ERROR),
}

_PANEL_WIDTH = 360
_PANEL_MAX_HEIGHT = 480


def _relative_time(iso_ts: str) -> str:
    """Convert an ISO-format UTC timestamp to a human-readable relative string."""
    try:
        ts = datetime.fromisoformat(iso_ts).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return ""
    delta = datetime.now(timezone.utc) - ts
    seconds = max(0, math.floor(delta.total_seconds()))
    if seconds < 60:
        return t("notifications.just_now")
    minutes = seconds // 60
    if minutes < 60:
        return t("notifications.minutes_ago", n=minutes)
    hours = minutes // 60
    if hours < 24:
        return t("notifications.hours_ago", n=hours)
    days = hours // 24
    return t("notifications.days_ago", n=days)


class NotificationPanel(ft.Container):
    """Floating overlay panel listing recent notifications."""

    def __init__(
        self,
        state: AppState,
        on_close: Callable[[], None] | None = None,
        on_navigate_session: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self._state = state
        self._on_close = on_close
        self._on_navigate_session = on_navigate_session
        self._build_ui()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        notif_svc = self._state.get_service("notification_service")
        notifications: list[Notification] = notif_svc.get_all() if notif_svc else []

        header = self._build_header()

        if notifications:
            items = [self._build_item(n) for n in notifications]
            body: ft.Control = ft.ListView(
                controls=items,
                spacing=0,
                padding=0,
                expand=True,
            )
        else:
            body = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(
                            ft.Icons.NOTIFICATIONS_NONE,
                            size=40,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            t("notifications.empty"),
                            size=13,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=ft.Alignment.CENTER,
                expand=True,
                padding=ft.Padding.symmetric(vertical=32),
            )

        self.content = ft.Container(
            content=ft.Column(
                controls=[header, ft.Divider(height=1), body],
                spacing=0,
                expand=True,
            ),
            width=_PANEL_WIDTH,
            height=_PANEL_MAX_HEIGHT,
            bgcolor=ft.Colors.SURFACE,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=12,
            shadow=ft.BoxShadow(
                blur_radius=16,
                spread_radius=2,
                color=ft.Colors.with_opacity(0.12, ft.Colors.BLACK),
                offset=ft.Offset(0, 4),
            ),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        t("notifications.title"),
                        size=14,
                        weight=ft.FontWeight.W_600,
                        expand=True,
                    ),
                    ft.TextButton(
                        t("notifications.mark_all_read"),
                        on_click=self._handle_mark_all_read,
                        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8)),
                    ),
                    make_icon_button(
                        ft.Icons.DELETE_OUTLINE,
                        tooltip=t("notifications.clear_all"),
                        on_click=self._handle_clear_all,
                        icon_size=16,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            padding=ft.Padding.only(left=16, right=8, top=10, bottom=6),
        )

    # ------------------------------------------------------------------
    # Individual notification item
    # ------------------------------------------------------------------

    def _build_item(self, notif: Notification) -> ft.Control:
        icon_name, icon_color = _TYPE_CONFIG.get(
            notif.type, (ft.Icons.INFO_OUTLINE, ft.Colors.BLUE)
        )

        unread_indicator = ft.Container(
            width=6,
            height=6,
            border_radius=3,
            bgcolor=ft.Colors.PRIMARY if not notif.read else ft.Colors.TRANSPARENT,
        )

        title_weight = ft.FontWeight.W_600 if not notif.read else ft.FontWeight.NORMAL
        bg_color = (
            ft.Colors.with_opacity(0.04, ft.Colors.PRIMARY)
            if not notif.read
            else ft.Colors.TRANSPARENT
        )

        time_str = _relative_time(notif.timestamp)

        row = ft.Row(
            controls=[
                ft.Icon(icon_name, size=18, color=icon_color),
                ft.Column(
                    controls=[
                        ft.Text(notif.title, size=12, weight=title_weight, max_lines=1),
                        ft.Text(
                            notif.message,
                            size=11,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Column(
                    controls=[
                        unread_indicator,
                        ft.Text(
                            time_str,
                            size=10,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                    spacing=4,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        return ft.Container(
            content=row,
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            bgcolor=bg_color,
            on_click=lambda e, n=notif: self._handle_item_click(n),
            ink=True,
        )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_item_click(self, notif: Notification) -> None:
        notif_svc = self._state.get_service("notification_service")
        if notif_svc:
            notif_svc.mark_read(notif.id)

        if notif.session_id and self._on_navigate_session:
            self._on_navigate_session(notif.session_id)
            if self._on_close:
                self._on_close()
            return

        self.refresh()
        self._state.update()

    def _handle_mark_all_read(self, e: ft.ControlEvent) -> None:
        notif_svc = self._state.get_service("notification_service")
        if notif_svc:
            notif_svc.mark_all_read()
        self.refresh()
        self._state.update()

    def _handle_clear_all(self, e: ft.ControlEvent) -> None:
        notif_svc = self._state.get_service("notification_service")
        if notif_svc:
            notif_svc.clear_all()
        self.refresh()
        self._state.update()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild the panel contents from the current notification queue."""
        self._build_ui()
