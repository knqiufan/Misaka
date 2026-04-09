"""Token usage indicator bar.

Compact bar displayed between the message list and message input,
showing the latest token usage (input/output/cost) and an approximate
context-window progress bar.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t

if TYPE_CHECKING:
    from misaka.state import AppState, TokenUsageInfo

# Model ID substring -> context window size (tokens).
# Covers common Claude models; unknown models fall back to a default.
_CONTEXT_WINDOWS: dict[str, int] = {
    "opus-4": 200_000,
    "sonnet-4": 200_000,
    "claude-4": 200_000,
    "opus": 200_000,
    "sonnet": 200_000,
    "haiku": 200_000,
}
_DEFAULT_CONTEXT_WINDOW = 200_000

_BAR_HEIGHT = 3


def _format_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _guess_context_window(model: str | None) -> int:
    if not model:
        return _DEFAULT_CONTEXT_WINDOW
    lower = model.lower()
    for key, size in _CONTEXT_WINDOWS.items():
        if key in lower:
            return size
    return _DEFAULT_CONTEXT_WINDOW


class TokenUsageBar(ft.Container):
    """Compact token usage indicator shown above the input area."""

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self._info_row: ft.Row | None = None
        self._progress_bar: ft.Container | None = None
        self._progress_fill: ft.Container | None = None
        self.visible = False
        self._build_ui()

    def _build_ui(self) -> None:
        self._info_row = ft.Row(
            controls=[],
            spacing=12,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._progress_fill = ft.Container(
            height=_BAR_HEIGHT,
            border_radius=2,
            bgcolor=ft.Colors.PRIMARY,
            width=0,
            animate=ft.Animation(300, ft.AnimationCurve.EASE_OUT),
        )

        self._progress_bar = ft.Container(
            content=ft.Stack(
                controls=[
                    ft.Container(
                        height=_BAR_HEIGHT,
                        border_radius=2,
                        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
                        expand=True,
                    ),
                    self._progress_fill,
                ],
                height=_BAR_HEIGHT,
            ),
            padding=ft.Padding.symmetric(horizontal=16),
        )

        self.content = ft.Column(
            controls=[self._info_row, self._progress_bar],
            spacing=4,
            tight=True,
        )
        self.padding = ft.Padding.only(left=12, right=12, top=6, bottom=2)

    def _make_chip(
        self,
        label: str,
        value: str,
        *,
        icon: str | None = None,
        color: str | None = None,
    ) -> ft.Container:
        controls: list[ft.Control] = []
        if icon:
            controls.append(ft.Icon(icon, size=11, opacity=0.5))
        controls.append(
            ft.Text(label, size=10, opacity=0.5, weight=ft.FontWeight.W_400),
        )
        controls.append(
            ft.Text(
                value,
                size=10,
                weight=ft.FontWeight.W_600,
                color=color or ft.Colors.ON_SURFACE,
            ),
        )
        return ft.Container(
            content=ft.Row(controls=controls, spacing=3, tight=True),
        )

    def refresh(self) -> None:
        """Update the bar from current state."""
        usage: TokenUsageInfo | None = self.state.last_token_usage
        if not usage:
            if self.visible:
                self.visible = False
                with contextlib.suppress(Exception):
                    self.update()
            return

        total = usage.input_tokens + usage.output_tokens
        chips: list[ft.Control] = [
            self._make_chip(
                t("token_usage.input"), _format_tokens(usage.input_tokens),
                icon=ft.Icons.LOGIN_ROUNDED,
            ),
            self._make_chip(
                t("token_usage.output"), _format_tokens(usage.output_tokens),
                icon=ft.Icons.LOGOUT_ROUNDED,
            ),
        ]

        if usage.cache_read_input_tokens:
            chips.append(
                self._make_chip(
                    t("token_usage.cache_read"),
                    _format_tokens(usage.cache_read_input_tokens),
                    icon=ft.Icons.CACHED_ROUNDED,
                ),
            )

        if usage.cost_usd is not None and usage.cost_usd > 0:
            chips.append(
                self._make_chip(
                    t("token_usage.cost"),
                    f"${usage.cost_usd:.4f}",
                    icon=ft.Icons.ATTACH_MONEY_ROUNDED,
                    color=ft.Colors.PRIMARY,
                ),
            )

        chips.append(
            self._make_chip(
                t("token_usage.total"), _format_tokens(total),
                icon=ft.Icons.DATA_USAGE_ROUNDED,
            ),
        )

        if self._info_row:
            self._info_row.controls = chips

        # Context window progress
        session = self.state.current_session
        model = session.model if session else None
        ctx_window = _guess_context_window(model)
        ratio = min(total / ctx_window, 1.0) if ctx_window else 0.0

        if self._progress_fill:
            # Use fractional expand via percentage-based width
            # Since we can't easily get parent width, use a Stack approach
            # with a relative container
            self._progress_fill.width = None
            self._progress_fill.expand = True
            self._progress_fill.scale = ft.Scale(scale_x=ratio, alignment=ft.Alignment.CENTER_LEFT)

            # Color based on usage level
            if ratio > 0.9:
                fill_color = ft.Colors.ERROR
            elif ratio > 0.7:
                fill_color = ft.Colors.with_opacity(0.8, "#f59e0b")
            else:
                fill_color = ft.Colors.PRIMARY

            self._progress_fill.bgcolor = fill_color

        if self._progress_bar:
            pct_text = f"{ratio * 100:.0f}%"
            self._progress_bar.tooltip = t("token_usage.context_tooltip").format(
                used=_format_tokens(total),
                total=_format_tokens(ctx_window),
                percent=pct_text,
            )

        self.visible = True
        with contextlib.suppress(Exception):
            self.update()
