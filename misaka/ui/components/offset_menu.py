"""Custom dropdown menu with stable overlay behavior."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class OffsetMenuOption:
    """Single selectable option in offset menu."""

    key: str
    label: str


class OffsetMenu(ft.PopupMenuButton):
    """Pill-style menu using PopupMenuButton overlay."""

    def __init__(
        self,
        *,
        value: str,
        options: list[OffsetMenuOption],
        on_change: Callable[[str], None] | None = None,
        width: int = 96,
        menu_width: int = 120,
        offset_y: int = 10,
    ) -> None:
        self._value = value
        self._options = options
        self._on_change = on_change
        self._width = width
        self._offset_y = offset_y
        super().__init__(
            content=self._build_trigger(),
            items=self._build_items(),
            tooltip="",
            menu_padding=ft.Padding.only(top=max(offset_y, 0), bottom=6),
            shape=ft.RoundedRectangleBorder(radius=14),
            size_constraints=ft.BoxConstraints(min_width=menu_width, max_width=menu_width),
        )

    def _build_items(self) -> list[ft.PopupMenuItem]:
        items: list[ft.PopupMenuItem] = []
        for option in self._options:
            items.append(
                ft.PopupMenuItem(
                    content=ft.Row(
                        controls=[
                            ft.Text(option.label, size=12, expand=True),
                            ft.Icon(
                                ft.Icons.CHECK_ROUNDED,
                                size=14,
                                visible=option.key == self._value,
                            ),
                        ],
                        spacing=6,
                    ),
                    height=34,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=0),
                    on_click=lambda e, key=option.key: self._select_option(key),
                ),
            )
        return items

    def _build_trigger(self) -> ft.Control:
        label = self._selected_label()
        return ft.Container(
            width=self._width,
            height=34,
            border_radius=999,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.10, ft.Colors.ON_SURFACE)),
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
            content=ft.Row(
                controls=[
                    ft.Text(label, size=12, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN_ROUNDED, size=16),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _selected_label(self) -> str:
        for option in self._options:
            if option.key == self._value:
                return option.label
        return self._value

    def _select_option(self, key: str) -> None:
        if key == self._value:
            return
        self._value = key
        self.content = self._build_trigger()
        self.items = self._build_items()
        self.update()
        if self._on_change:
            self._on_change(key)
