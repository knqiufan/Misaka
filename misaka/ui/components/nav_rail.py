"""Navigation rail component.

Custom vertical navigation bar on the left side of the application.
Slim icon-focused design with pill-shaped selection indicators.
Destinations: Chat, Settings, Plugins, Skills.
Includes a theme toggle at the bottom.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t

if TYPE_CHECKING:
    from misaka.state import AppState


_PAGE_TO_INDEX = {
    "chat": 0,
    "settings": 1,
    "plugins": 2,
    "extensions": 3,
}

_INDEX_TO_PAGE = {v: k for k, v in _PAGE_TO_INDEX.items()}

_NAV_ITEMS: list[dict] = [
    {
        "page": "chat",
        "icon": ft.Icons.CHAT_BUBBLE_OUTLINE,
        "selected_icon": ft.Icons.CHAT_BUBBLE,
        "label_key": "nav.chat",
    },
    {
        "page": "settings",
        "icon": ft.Icons.SETTINGS_OUTLINED,
        "selected_icon": ft.Icons.SETTINGS,
        "label_key": "nav.settings",
    },
    {
        "page": "plugins",
        "icon": ft.Icons.EXTENSION_OUTLINED,
        "selected_icon": ft.Icons.EXTENSION,
        "label_key": "nav.plugins",
    },
    {
        "page": "extensions",
        "icon": ft.Icons.CODE_OUTLINED,
        "selected_icon": ft.Icons.CODE,
        "label_key": "nav.extensions",
    },
]


def _build_nav_item(
    item: dict,
    is_selected: bool,
    on_click: Callable[[str], None],
) -> ft.Control:
    """Build a single navigation item — icon with pill selection indicator."""
    page_name = item["page"]
    icon_name = item["selected_icon"] if is_selected else item["icon"]
    label = t(item["label_key"])

    icon_color = ft.Colors.PRIMARY if is_selected else ft.Colors.ON_SURFACE_VARIANT

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(icon_name, size=20, color=icon_color),
                    width=42,
                    height=34,
                    border_radius=10,
                    bgcolor=(
                        ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY)
                        if is_selected
                        else ft.Colors.TRANSPARENT
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Text(
                    label,
                    size=9,
                    weight=ft.FontWeight.W_500 if is_selected else ft.FontWeight.NORMAL,
                    color=icon_color,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        ),
        width=54,
        padding=ft.Padding.symmetric(vertical=3),
        alignment=ft.Alignment.CENTER,
        on_click=lambda e, p=page_name: on_click(p),
        ink=True,
        border_radius=10,
    )


def build_nav_rail(
    state: AppState,
    on_change: Callable[[str], None] | None = None,
    on_theme_toggle: Callable[[], None] | None = None,
) -> ft.Container:
    """Build the main navigation rail as a custom Column layout."""
    current_page = state.current_page

    def handle_click(page_name: str) -> None:
        if on_change:
            on_change(page_name)

    def handle_theme(e: ft.ControlEvent) -> None:
        if on_theme_toggle:
            on_theme_toggle()

    theme_icons = {
        "dark": ft.Icons.DARK_MODE,
        "light": ft.Icons.LIGHT_MODE,
        "system": ft.Icons.BRIGHTNESS_AUTO,
    }
    theme_icon = theme_icons.get(state.theme_mode, ft.Icons.BRIGHTNESS_AUTO)
    theme_label = t("common.theme_label", mode=state.theme_mode.title())

    nav_items = [
        _build_nav_item(item, item["page"] == current_page, handle_click)
        for item in _NAV_ITEMS
    ]

    theme_btn = ft.Container(
        content=ft.IconButton(
            icon=theme_icon,
            tooltip=theme_label,
            on_click=handle_theme,
            icon_size=18,
            style=ft.ButtonStyle(padding=6),
        ),
        alignment=ft.Alignment.CENTER,
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(height=4),
                *nav_items,
                ft.Container(expand=True),
                theme_btn,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        ),
        width=60,
        padding=ft.Padding.only(top=8, bottom=8, left=3, right=3),
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border=ft.Border(
            right=ft.BorderSide(
                1,
                ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
        ),
    )
