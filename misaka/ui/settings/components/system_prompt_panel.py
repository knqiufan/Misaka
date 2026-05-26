"""System prompt settings panel.

Allows users to configure a global default system prompt that is
injected into all conversations. Supports editing, saving, restoring
defaults, and selecting from preset prompts.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import flet as ft

from misaka.config import SettingKeys
from misaka.i18n import t
from misaka.ui.common.theme import (
    RADIUS_LG,
    make_button,
    make_outlined_button,
    show_snackbar,
)

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState

_DEFAULT_SYSTEM_PROMPT = (
    "永远用中文与我对话\n"
    "如果敢胡编乱造或偷懒或写BUG，我将狠狠抽打我手里的这只小猫咪"
)

_PRESET_PROMPTS: list[tuple[str, str]] = [
    ("中文对话", "永远用中文与我对话"),
    ("严格质量", "如果敢胡编乱造或偷懒或写BUG，我将狠狠抽打我手里的这只小猫咪"),
    ("简洁回复", "回复尽量简洁，避免冗余解释"),
    ("代码优先", "优先给出代码实现，减少文字描述"),
]


class SystemPromptPanel(ft.Container):
    """Panel for configuring the global default system prompt."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend | None = None,
    ) -> None:
        super().__init__(expand=True)
        self._state = state
        self._db = db
        self._text_field: ft.TextField | None = None
        self._build_ui()

    def _get_current_prompt(self) -> str:
        """Read current system prompt from settings service or DB."""
        settings_svc = self._state.get_service("settings_service")
        if settings_svc and hasattr(settings_svc, "get_default_system_prompt"):
            val = settings_svc.get_default_system_prompt()
            return val or ""
        if self._db:
            val = self._db.get_setting(SettingKeys.DEFAULT_SYSTEM_PROMPT)
            return val or ""
        return ""

    def _save_prompt(self, value: str) -> None:
        """Persist system prompt value."""
        settings_svc = self._state.get_service("settings_service")
        if settings_svc and hasattr(settings_svc, "set"):
            settings_svc.set(SettingKeys.DEFAULT_SYSTEM_PROMPT, value)
        elif self._db:
            self._db.set_setting(SettingKeys.DEFAULT_SYSTEM_PROMPT, value)

    def _build_ui(self) -> None:
        current = self._get_current_prompt()

        self._text_field = ft.TextField(
            value=current,
            multiline=True,
            min_lines=4,
            max_lines=12,
            label=t("settings.system_prompt_label"),
            hint_text=t("settings.system_prompt_hint"),
            border_radius=RADIUS_LG,
            text_size=13,
        )

        save_btn = make_button(
            t("settings.system_prompt_save"),
            icon=ft.Icons.SAVE_OUTLINED,
            on_click=self._handle_save,
        )
        restore_btn = make_outlined_button(
            t("settings.system_prompt_restore"),
            icon=ft.Icons.RESTORE,
            on_click=self._handle_restore,
        )
        clear_btn = make_outlined_button(
            t("settings.system_prompt_clear"),
            icon=ft.Icons.CLEAR_ALL,
            on_click=self._handle_clear,
        )

        preset_chips = self._build_preset_chips()

        self.content = ft.Column(
            controls=[
                ft.Text(
                    t("settings.system_prompt"),
                    size=16,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Text(
                    t("settings.system_prompt_desc"),
                    size=12,
                    opacity=0.6,
                ),
                self._text_field,
                ft.Row(
                    controls=[save_btn, restore_btn, clear_btn],
                    spacing=8,
                ),
                ft.Divider(height=1, thickness=0.5),
                ft.Text(
                    t("settings.system_prompt_presets"),
                    size=13,
                    weight=ft.FontWeight.W_500,
                    opacity=0.7,
                ),
                ft.Column(controls=preset_chips, spacing=6),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self.padding = ft.Padding.symmetric(horizontal=24, vertical=16)

    def _build_preset_chips(self) -> list[ft.Control]:
        """Build clickable preset prompt items."""
        items: list[ft.Control] = []
        for label, prompt_text in _PRESET_PROMPTS:
            items.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.ADD_CIRCLE_OUTLINE,
                                size=14,
                                color=ft.Colors.PRIMARY,
                                opacity=0.6,
                            ),
                            ft.Text(label, size=12, weight=ft.FontWeight.W_500),
                            ft.Text(
                                prompt_text[:40] + ("..." if len(prompt_text) > 40 else ""),
                                size=11,
                                opacity=0.5,
                                expand=True,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.PRIMARY),
                    border=ft.Border.all(
                        1, ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
                    ),
                    on_click=lambda e, txt=prompt_text: self._append_preset(txt),
                    ink=True,
                )
            )
        return items

    def _append_preset(self, text: str) -> None:
        """Append a preset prompt to the text field."""
        if not self._text_field:
            return
        current = self._text_field.value or ""
        if current.strip():
            self._text_field.value = current.rstrip("\n") + "\n" + text
        else:
            self._text_field.value = text
        with contextlib.suppress(Exception):
            self._text_field.update()

    def _handle_save(self, e: ft.ControlEvent) -> None:
        """Save the current text field value."""
        if not self._text_field:
            return
        value = (self._text_field.value or "").strip()
        self._save_prompt(value)
        self._text_field.value = value
        with contextlib.suppress(Exception):
            self._text_field.update()
        if e.page:
            show_snackbar(e.page, t("settings.system_prompt_saved"))

    def _handle_restore(self, e: ft.ControlEvent) -> None:
        """Restore default system prompt."""
        if not self._text_field:
            return
        self._text_field.value = _DEFAULT_SYSTEM_PROMPT
        with contextlib.suppress(Exception):
            self._text_field.update()

    def _handle_clear(self, e: ft.ControlEvent) -> None:
        """Clear the text field."""
        if not self._text_field:
            return
        self._text_field.value = ""
        with contextlib.suppress(Exception):
            self._text_field.update()

    def refresh(self) -> None:
        """Rebuild the panel UI."""
        self._build_ui()
