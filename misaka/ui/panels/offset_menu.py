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
        icon_map: dict[str, str] | None = None,
        color_map: dict[str, str] | None = None,
        width: int = 96,
        menu_width: int = 120,
        offset_y: int = 10,
    ) -> None:
        self._value = value
        self._options = options
        self._on_change = on_change
        self._icon_map = icon_map or {}
        self._color_map = color_map or {}
        self._width = width
        self._offset_y = offset_y
        super().__init__(
            content=self._build_trigger(),
            items=self._build_items(),
            tooltip="",
            menu_padding=ft.Padding.only(top=max(offset_y, 0), bottom=6),
            shape=ft.RoundedRectangleBorder(radius=14),
            size_constraints=ft.BoxConstraints(min_width=menu_width, max_width=menu_width),
            elevation=8,
            shadow_color=ft.Colors.with_opacity(0.12, ft.Colors.BLACK),
            popup_animation_style=ft.AnimationStyle(
                duration=250,
                curve=ft.AnimationCurve.EASE_OUT_CUBIC,
            ),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
        )

    def _build_items(self) -> list[ft.PopupMenuItem]:
        items: list[ft.PopupMenuItem] = []
        for option in self._options:
            icon_name = self._icon_map.get(option.key)
            color = self._color_map.get(option.key)
            row_controls: list[ft.Control] = []
            if icon_name:
                row_controls.append(
                    ft.Icon(
                        icon_name,
                        size=14,
                        color=color if color else None,
                        opacity=0.9,
                    ),
                )
            text_kw = {"size": 12, "expand": True}
            if color:
                text_kw["color"] = color
            row_controls.append(ft.Text(option.label, **text_kw))
            row_controls.append(
                ft.Icon(
                    ft.Icons.CHECK_ROUNDED,
                    size=14,
                    visible=option.key == self._value,
                ),
            )
            items.append(
                ft.PopupMenuItem(
                    content=ft.Row(
                        controls=row_controls,
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
        icon_name = self._icon_map.get(self._value)
        color = self._color_map.get(self._value)
        trigger_controls: list[ft.Control] = []
        if icon_name:
            trigger_controls.append(
                ft.Icon(
                    icon_name,
                    size=14,
                    color=color if color else None,
                    opacity=0.9,
                ),
            )
        text_kw: dict = {
            "size": 12,
            "expand": True,
            "max_lines": 1,
            "overflow": ft.TextOverflow.ELLIPSIS,
        }
        if color:
            text_kw["color"] = color
        trigger_controls.append(ft.Text(label, **text_kw))
        trigger_controls.append(ft.Icon(ft.Icons.ARROW_DROP_DOWN_ROUNDED, size=16))
        return ft.Container(
            width=self._width,
            height=34,
            border_radius=999,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE)),
            bgcolor=ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE),
            shadow=ft.BoxShadow(
                blur_radius=6,
                spread_radius=-1,
                color=ft.Colors.with_opacity(0.06, ft.Colors.BLACK),
                offset=ft.Offset(0, 2),
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=0),
            content=ft.Row(
                controls=trigger_controls,
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
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
