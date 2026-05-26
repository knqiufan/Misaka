"""Lightweight placeholder for assistant messages with many tool calls."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

import flet as ft

from misaka.config import get_assets_path
from misaka.db.models import Message
from misaka.i18n import t

BuildItemFn = Callable[[], ft.Control]


class MessageItemShell(ft.Container):
    """Deferred MessageItem: shows summary until loaded."""

    def __init__(
        self,
        message: Message,
        *,
        assistant_label: str,
        tool_count: int,
        build_full_item: BuildItemFn,
        on_replaced: Callable[[ft.Control], None] | None = None,
    ) -> None:
        super().__init__()
        self._message = message
        self._assistant_label = assistant_label
        self._tool_count = tool_count
        self._build_full_item = build_full_item
        self._on_replaced = on_replaced
        self._loading = False
        self._loaded = False
        self.key = message.id
        self._status_text = ft.Text(
            t("chat.message_heavy_load").format(count=tool_count),
            size=12,
            opacity=0.6,
        )
        self._build_ui()

    def _build_ui(self) -> None:
        claude_icon = str(get_assets_path() / "claude.png")
        header = ft.Row(
            controls=[
                ft.Image(
                    src=claude_icon, width=14, height=14, fit=ft.BoxFit.CONTAIN,
                ),
                ft.Text(
                    self._assistant_label,
                    size=12,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.PRIMARY,
                ),
            ],
            spacing=6,
        )
        load_btn = ft.TextButton(
            t("chat.message_heavy_load_btn"),
            on_click=self._on_load_click,
        )
        self.content = ft.Column(
            controls=[
                header,
                ft.Container(
                    content=ft.Row(
                        controls=[self._status_text, load_btn],
                        spacing=8,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=12),
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
                    on_click=self._on_load_click,
                    ink=True,
                ),
            ],
            spacing=8,
        )
        self.padding = ft.Padding.symmetric(horizontal=20, vertical=12)
        self.margin = ft.Margin.only(bottom=2)

    async def _load_async(self) -> None:
        if self._loaded or self._loading:
            return
        self._loading = True
        self._status_text.value = t("chat.message_heavy_loading")
        with contextlib.suppress(Exception):
            self._status_text.update()
        await asyncio.sleep(0)
        await self._materialize()

    def _on_load_click(self, e: ft.ControlEvent) -> None:
        page = e.page
        if page is not None:
            page.run_task(self._load_async)
        else:
            self._materialize_sync()

    def _materialize_sync(self) -> None:
        if self._loaded:
            return
        full = self._build_full_item()
        self._loaded = True
        if self._on_replaced:
            self._on_replaced(full)

    async def _materialize(self) -> None:
        if self._loaded:
            return
        full = self._build_full_item()
        self._loaded = True
        self._loading = False
        if self._on_replaced:
            self._on_replaced(full)
