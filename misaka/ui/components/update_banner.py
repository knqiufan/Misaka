"""Update notification banner component.

Dismissable notification banner shown when a Claude Code CLI
update is available. Displays current vs latest version with
an update button.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import flet as ft

from misaka.i18n import t

if TYPE_CHECKING:
    from misaka.state import AppState


class UpdateBanner(ft.Container):
    """Notification banner shown when a Claude Code update is available.

    Appears at the top of the chat view (below the header bar).
    Dismissable with an X button.
    """

    def __init__(
        self,
        state: AppState,
        on_update: Callable[[], None] | None = None,
        on_dismiss: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self._on_update = on_update
        self._on_dismiss = on_dismiss
        self._build_ui()

    def _build_ui(self) -> None:
        result = self.state.update_check_result
        dismissed = getattr(self.state, "update_dismissed", False)
        updating = getattr(self.state, "update_in_progress", False)

        # Determine visibility
        if not result or not result.update_available or dismissed:
            self.visible = False
            self.content = ft.Container()
            return

        self.visible = True

        # Banner text
        if updating:
            banner_text = t("update.updating")
            banner_icon = ft.ProgressRing(width=16, height=16, stroke_width=2)
        else:
            banner_text = t(
                "update.available",
                version=result.latest_version or "?",
                current=result.current_version or "?",
            )
            banner_icon = ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ft.Colors.BLUE)

        # Update button
        update_btn = ft.Button(
            content=t("update.update_now"),
            on_click=self._handle_update,
            disabled=updating,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE,
                color=ft.Colors.WHITE,
            ),
        )

        # Dismiss button
        dismiss_btn = ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_size=16,
            on_click=self._handle_dismiss,
            style=ft.ButtonStyle(padding=4),
            tooltip=t("update.dismiss"),
        )

        self.content = ft.Container(
            content=ft.Row(
                controls=[
                    banner_icon,
                    ft.Text(
                        banner_text,
                        size=13,
                        expand=True,
                    ),
                    update_btn,
                    dismiss_btn,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.BLUE),
            border_radius=0,
        )

    def _handle_update(self, e: ft.ControlEvent) -> None:
        if self._on_update:
            self._on_update()

    def _handle_dismiss(self, e: ft.ControlEvent) -> None:
        if self._on_dismiss:
            self._on_dismiss()

    def refresh(self) -> None:
        """Update visibility and content based on state."""
        self._build_ui()
