"""Appearance and language section builders for the Settings page."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

import misaka.i18n as i18n
from misaka.i18n import t
from misaka.ui.common.theme import apply_theme

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState

_THEME_MODES = [
    ("system", "settings.theme_system", ft.Icons.BRIGHTNESS_AUTO),
    ("light", "settings.theme_light", ft.Icons.LIGHT_MODE),
    ("dark", "settings.theme_dark", ft.Icons.DARK_MODE),
]

_ACCENT_COLORS = [
    ("#6366f1", "Indigo"),
    ("#3b82f6", "Blue"),
    ("#10b981", "Emerald"),
    ("#f43f5e", "Rose"),
    ("#f59e0b", "Amber"),
    ("#8b5cf6", "Purple"),
    ("#14b8a6", "Teal"),
]

_LANGUAGES = [
    ("zh-CN", "\u7b80\u4f53\u4e2d\u6587"),
    ("zh-TW", "\u7e41\u9ad4\u4e2d\u6587"),
    ("en", "English"),
]


def build_appearance_section(
    state: AppState,
    on_theme_click: Callable[[str], None],
    on_accent_click: Callable[[str], None],
) -> ft.Control:
    """Build the theme mode and accent color selection section."""
    theme_buttons = _build_theme_buttons(state, on_theme_click)
    color_circles = _build_accent_circles(state, on_accent_click)

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(t("settings.appearance"), size=16, weight=ft.FontWeight.W_600),
                ft.Text(t("settings.appearance_desc"), size=12, opacity=0.6),
                ft.Row(controls=theme_buttons, spacing=8),
                ft.Text(t("settings.accent_color"), size=14, weight=ft.FontWeight.W_500),
                ft.Text(t("settings.accent_color_desc"), size=12, opacity=0.6),
                ft.Row(controls=color_circles, spacing=8),
            ],
            spacing=12,
        ),
        padding=ft.Padding.symmetric(horizontal=24, vertical=16),
    )


def _build_theme_buttons(
    state: AppState,
    on_click: Callable[[str], None],
) -> list[ft.Control]:
    use_white_active_text = state.theme_mode == "light"
    buttons: list[ft.Control] = []
    for mode, label_key, icon in _THEME_MODES:
        is_active = state.theme_mode == mode
        active_text_color = ft.Colors.WHITE if is_active and use_white_active_text else None
        btn = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, size=18, color=active_text_color),
                    ft.Text(t(label_key), size=13, color=active_text_color),
                ],
                spacing=6,
            ),
            bgcolor=ft.Colors.PRIMARY if is_active else ft.Colors.TRANSPARENT,
            border=ft.Border.all(
                1,
                ft.Colors.PRIMARY if is_active else ft.Colors.OUTLINE,
            ),
            border_radius=10,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            on_click=lambda e, m=mode: on_click(m),
            ink=True,
        )
        buttons.append(btn)
    return buttons


def _build_accent_circles(
    state: AppState,
    on_click: Callable[[str], None],
) -> list[ft.Control]:
    current_accent = getattr(state, "accent_color", "#6366f1")
    circles: list[ft.Control] = []
    for hex_color, color_name in _ACCENT_COLORS:
        is_selected = current_accent == hex_color
        circle = ft.Container(
            width=28,
            height=28,
            bgcolor=hex_color,
            border_radius=14,
            border=ft.Border.all(
                3 if is_selected else 1,
                ft.Colors.ON_SURFACE if is_selected
                else ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
            ),
            tooltip=color_name,
            on_click=lambda e, c=hex_color: on_click(c),
            ink=True,
        )
        circles.append(circle)
    return circles


def change_theme(
    state: AppState,
    mode: str,
    on_theme_change: Callable[[str], None] | None,
    rebuild_ui: Callable[[], None],
) -> None:
    """Apply a new theme mode and trigger UI rebuild."""
    state.theme_mode = mode
    apply_theme(state.page, mode, state.accent_color)
    if on_theme_change:
        on_theme_change(mode)
    rebuild_ui()
    state.update()


def change_accent_color(
    state: AppState,
    color: str,
    db: DatabaseBackend | None,
    rebuild_ui: Callable[[], None],
) -> None:
    """Apply a new accent color and persist to database."""
    state.accent_color = color
    if db:
        db.set_setting("accent_color", color)
    apply_theme(state.page, state.theme_mode, color)
    rebuild_ui()
    state.update()


def build_language_section(
    state: AppState,
    on_language_click: Callable[[str], None],
) -> ft.Control:
    """Build the language selection section."""
    current_locale = getattr(state, "locale", "zh-CN")
    use_white_active_text = state.theme_mode == "light"

    lang_buttons: list[ft.Control] = []
    for locale_code, locale_label in _LANGUAGES:
        is_active = current_locale == locale_code
        active_text_color = ft.Colors.WHITE if is_active and use_white_active_text else None
        btn = ft.Container(
            content=ft.Text(locale_label, size=13, color=active_text_color),
            bgcolor=ft.Colors.PRIMARY if is_active else ft.Colors.TRANSPARENT,
            border=ft.Border.all(
                1,
                ft.Colors.PRIMARY if is_active else ft.Colors.OUTLINE,
            ),
            border_radius=10,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            on_click=lambda e, loc=locale_code: on_language_click(loc),
            ink=True,
        )
        lang_buttons.append(btn)

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(t("settings.language"), size=16, weight=ft.FontWeight.W_600),
                ft.Text(t("settings.language_desc"), size=12, opacity=0.6),
                ft.Row(controls=lang_buttons, spacing=8),
            ],
            spacing=12,
        ),
        padding=ft.Padding.symmetric(horizontal=24, vertical=16),
    )


def change_language(
    state: AppState,
    locale: str,
    db: DatabaseBackend | None,
    on_locale_change: Callable[[str], None] | None,
    rebuild_ui: Callable[[], None],
) -> None:
    """Persist locale preference, update i18n, and trigger rebuild."""
    if db:
        db.set_setting("language", locale)
    i18n.set_locale(locale)
    state.locale = locale
    if on_locale_change:
        on_locale_change(locale)
    else:
        rebuild_ui()
        state.update()
