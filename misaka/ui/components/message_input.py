"""Message input component.

Multi-line text input area with send button, file attachment support,
slash-command menu, and keyboard shortcut handling.
Supports Shift+Enter for newline and Enter to send.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.commands import SlashCommand, filter_commands
from misaka.i18n import t
from misaka.ui.theme import MONO_FONT_FAMILY

if TYPE_CHECKING:
    from misaka.state import AppState


class MessageInput(ft.Container):
    """Message input area with send/stop button, file attachment, and slash commands."""

    def __init__(
        self,
        state: AppState,
        on_send: Callable[[str], None] | None = None,
        on_abort: Callable[[], None] | None = None,
        on_command: Callable[[str], None] | None = None,
        on_model_change: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self._on_send = on_send
        self._on_abort = on_abort
        self._on_command = on_command
        self._on_model_change = on_model_change
        self._text_field: ft.TextField | None = None
        self._send_btn: ft.IconButton | None = None
        self._command_menu: ft.Column | None = None
        self._command_menu_container: ft.Container | None = None
        self._input_shell: ft.Container | None = None
        self._badge_container: ft.Container | None = None
        self._model_indicator: ft.Container | None = None
        self._active_badge: SlashCommand | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        from misaka.ui.theme import make_text_field as _mtf
        self._text_field = _mtf(
            hint_text=t("chat.type_message"),
            expand=True,
            multiline=True,
            min_lines=1,
            max_lines=6,
            shift_enter=True,
            on_submit=self._handle_send,
            on_change=self._handle_text_change,
            border=ft.InputBorder.NONE,
            border_radius=0,
            border_width=0,
            filled=False,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=10),
            text_size=13,
        )

        is_streaming = self.state.is_streaming

        self._send_btn = ft.IconButton(
            icon=(
                ft.Icons.STOP_CIRCLE_ROUNDED
                if is_streaming
                else ft.Icons.SEND_ROUNDED
            ),
            tooltip=t("chat.stop") if is_streaming else t("chat.send"),
            on_click=self._handle_action,
            icon_color=ft.Colors.WHITE,
            bgcolor=ft.Colors.ERROR if is_streaming else ft.Colors.PRIMARY,
            icon_size=20,
            style=ft.ButtonStyle(shape=ft.CircleBorder(), padding=8),
        )

        attach_btn = self._build_utility_button(
            icon=ft.Icons.ATTACH_FILE_ROUNDED,
            tooltip=t("chat.attach_file"),
            on_click=self._handle_attach,
        )

        command_btn = self._build_utility_button(
            icon=ft.Icons.TERMINAL_ROUNDED,
            tooltip=t("chat.command_menu"),
            on_click=self._toggle_command_menu,
        )

        self._command_menu = ft.Column(spacing=0, tight=True)
        self._command_menu_container = ft.Container(
            content=self._command_menu,
            visible=False,
            border_radius=14,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE)),
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            padding=ft.Padding.symmetric(vertical=6),
            width=360,
            margin=ft.Margin.only(left=52, bottom=8),
            shadow=ft.BoxShadow(
                blur_radius=16,
                spread_radius=-2,
                offset=ft.Offset(0, 6),
                color=ft.Colors.with_opacity(0.16, ft.Colors.BLACK),
            ),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        self._badge_container = ft.Container(visible=False)

        self._model_indicator = self._build_model_indicator()

        input_row = ft.Row(
            controls=[attach_btn, command_btn, self._model_indicator,
                      self._badge_container, self._text_field, self._send_btn],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._input_shell = ft.Container(
            content=input_row,
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=18,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.10, ft.Colors.ON_SURFACE)),
            # bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE),
            # shadow=ft.BoxShadow(
            #     blur_radius=10,
            #     spread_radius=-3,
            #     offset=ft.Offset(0, 2),
            #     color=ft.Colors.with_opacity(0.10, ft.Colors.BLACK),
            # ),
        )

        self.content = ft.Column(
            controls=[self._command_menu_container, self._input_shell],
            spacing=0,
            tight=True,
        )
        self.padding = ft.Padding.symmetric(horizontal=12, vertical=8)

    @staticmethod
    def _build_utility_button(
        *,
        icon: str,
        tooltip: str,
        on_click: object,
    ) -> ft.Container:
        """Build modern utility icon button for input tools."""
        return ft.Container(
            content=ft.IconButton(
                icon=icon,
                tooltip=tooltip,
                on_click=on_click,
                icon_size=16,
                style=ft.ButtonStyle(
                    shape=ft.CircleBorder(),
                    padding=6,
                    overlay_color=ft.Colors.with_opacity(0.10, ft.Colors.PRIMARY),
                ),
            ),
            width=36,
            height=36,
            alignment=ft.Alignment.CENTER,
            border_radius=20,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
        )

    # ------------------------------------------------------------------
    # Slash-command menu
    # ------------------------------------------------------------------

    def _handle_text_change(self, e: ft.ControlEvent) -> None:
        """Detect '/' prefix and show/update the command menu."""
        value = e.data or ""
        if value.startswith("/"):
            query = value[1:]
            matches = filter_commands(query)
            self._show_command_menu(matches)
        else:
            self._hide_command_menu()

    def _show_command_menu(self, commands: list[SlashCommand]) -> None:
        if not self._command_menu or not self._command_menu_container:
            return
        if not commands:
            self._hide_command_menu()
            return

        items: list[ft.Control] = []
        for cmd in commands:
            items.append(self._build_command_item(cmd))

        self._command_menu.controls = items
        self._command_menu_container.visible = True
        self._command_menu_container.update()

    def _toggle_command_menu(self, e: ft.ControlEvent) -> None:
        """Toggle command menu when clicking the command button."""
        if self._command_menu_container and self._command_menu_container.visible:
            self._hide_command_menu()
            return
        self._show_command_menu(filter_commands(""))
        if self._text_field:
            self._text_field.focus()

    def _hide_command_menu(self) -> None:
        if self._command_menu_container and self._command_menu_container.visible:
            self._command_menu_container.visible = False
            self._command_menu_container.update()

    def _build_command_item(self, cmd: SlashCommand) -> ft.Control:
        """Build a single command row for the popup menu."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(cmd.icon, size=15, opacity=0.5),
                    ft.Text(
                        f"/{cmd.name}",
                        size=12,
                        weight=ft.FontWeight.W_500,
                        font_family=MONO_FONT_FAMILY,
                    ),
                    ft.Text(
                        cmd.description,
                        size=11,
                        opacity=0.4,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            on_click=lambda e, c=cmd: self._select_command(c),
            ink=True,
        )

    def _select_command(self, cmd: SlashCommand) -> None:
        """Handle selection of a slash command from the menu."""
        self._hide_command_menu()

        if cmd.name == "model":
            if self._text_field:
                self._text_field.value = ""
                self._text_field.update()
            self._show_model_menu()
            return

        if cmd.immediate:
            if self._text_field:
                self._text_field.value = ""
                self._text_field.update()
            if self._on_command:
                self._on_command(f"/{cmd.name}")
        else:
            self._set_badge(cmd)
            if self._text_field:
                self._text_field.value = ""
                self._text_field.update()
                self._text_field.focus()

    # ------------------------------------------------------------------
    # Model sub-menu
    # ------------------------------------------------------------------

    def _get_model_options(self) -> list[tuple[str, str]]:
        """Read model names from settings and build option list."""
        options: list[tuple[str, str]] = [("default", "Default")]
        cli_svc = self.state.get_service("cli_settings_service")
        if cli_svc:
            settings = cli_svc.read_settings()
            env = settings.get("env", {})
            sonnet = env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "Sonnet")
            opus = env.get("ANTHROPIC_DEFAULT_OPUS_MODEL", "Opus")
            haiku = env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "Haiku")
            main = env.get("ANTHROPIC_MODEL", "")
            if main and main != options[0][1]:
                options[0] = ("default", f"Default ({main})")
            options.append(("sonnet", sonnet if sonnet != "Sonnet" else "Sonnet"))
            options.append(("opus", opus if opus != "Opus" else "Opus"))
            options.append(("haiku", haiku if haiku != "Haiku" else "Haiku"))
            return options
        options.extend([("sonnet", "Sonnet"), ("opus", "Opus"), ("haiku", "Haiku")])
        return options

    def _show_model_menu(self) -> None:
        """Show a second-level menu for model selection."""
        if not self._command_menu or not self._command_menu_container:
            return

        options = self._get_model_options()
        current = self.state.selected_model

        items: list[ft.Control] = []
        for value, label in options:
            is_selected = value == current
            items.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.CHECK_ROUNDED if is_selected else ft.Icons.CIRCLE,
                                size=13,
                                opacity=1.0 if is_selected else 0.2,
                                color=ft.Colors.PRIMARY if is_selected else None,
                            ),
                            ft.Text(
                                label,
                                size=12,
                                weight=(
                                    ft.FontWeight.W_500
                                    if is_selected
                                    else ft.FontWeight.NORMAL
                                ),
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                    on_click=lambda e, v=value: self._select_model(v),
                    ink=True,
                )
            )

        self._command_menu.controls = items
        self._command_menu_container.visible = True
        self._command_menu_container.update()

    def _select_model(self, model: str) -> None:
        """Handle model selection from the sub-menu."""
        self._hide_command_menu()
        self.state.selected_model = model
        self._refresh_model_indicator()
        if self._on_model_change:
            self._on_model_change(model)

    def _build_model_indicator(self) -> ft.Container:
        """Build a small badge showing the currently selected model."""
        model = self.state.selected_model
        if model == "default":
            return ft.Container(visible=False)

        label = model.capitalize()
        return ft.Container(
            content=ft.Text(
                label,
                size=10,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.PRIMARY,
            ),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.2, ft.Colors.PRIMARY)),
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        )

    def _refresh_model_indicator(self) -> None:
        """Update the model indicator badge."""
        if not self._model_indicator:
            return
        model = self.state.selected_model
        if model == "default":
            self._model_indicator.visible = False
            self._model_indicator.content = None
        else:
            self._model_indicator.visible = True
            self._model_indicator.content = ft.Text(
                model.capitalize(),
                size=10,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.PRIMARY,
            )
            self._model_indicator.border = ft.Border.all(
                1, ft.Colors.with_opacity(0.2, ft.Colors.PRIMARY),
            )
            self._model_indicator.border_radius = 6
            self._model_indicator.padding = ft.Padding.symmetric(
                horizontal=6, vertical=2
            )
        with contextlib.suppress(Exception):
            self._model_indicator.update()

    # ------------------------------------------------------------------
    # Badge (non-immediate commands)
    # ------------------------------------------------------------------

    def _set_badge(self, cmd: SlashCommand) -> None:
        """Show a command badge before the input field."""
        self._active_badge = cmd
        if not self._badge_container:
            return
        self._badge_container.content = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(cmd.icon, size=13, color=ft.Colors.WHITE),
                    ft.Text(
                        f"/{cmd.name}",
                        size=11,
                        weight=ft.FontWeight.W_500,
                        color=ft.Colors.WHITE,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE_ROUNDED,
                        icon_size=12,
                        icon_color=ft.Colors.WHITE,
                        on_click=lambda e: self._remove_badge(),
                        style=ft.ButtonStyle(padding=0),
                    ),
                ],
                spacing=4,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=ft.Colors.PRIMARY,
            border_radius=8,
            padding=ft.Padding.only(left=8, right=2, top=4, bottom=4),
        )
        self._badge_container.visible = True
        self._badge_container.update()

    def _remove_badge(self) -> None:
        """Remove the active command badge."""
        self._active_badge = None
        if self._badge_container:
            self._badge_container.visible = False
            self._badge_container.content = ft.Container()
            self._badge_container.update()

    # ------------------------------------------------------------------
    # Send / action handling
    # ------------------------------------------------------------------

    def _handle_action(self, e: ft.ControlEvent) -> None:
        if self.state.is_streaming:
            if self._on_abort:
                self._on_abort()
        else:
            self._handle_send(e)

    def _handle_send(self, e: ft.ControlEvent) -> None:
        if not self._text_field:
            return

        user_text = (self._text_field.value or "").strip()

        if self._active_badge:
            badge = self._active_badge
            self._remove_badge()
            prompt = badge.prompt
            if user_text:
                prompt = f"{prompt}\n\nUser context: {user_text}"
            self._text_field.value = ""
            self._text_field.update()
            if self._on_send and prompt:
                self._on_send(prompt)
            return

        if not user_text:
            return

        self._text_field.value = ""
        self._text_field.update()
        self._hide_command_menu()
        if self._on_send:
            self._on_send(user_text)

    def _handle_attach(self, e: ft.ControlEvent) -> None:
        """Open a manual file-path dialog (stable fallback UX)."""
        page = getattr(self.state, "page", None)
        if not page:
            return

        from misaka.ui.theme import make_button, make_dialog, make_text_button

        path_field = ft.TextField(
            label=t("chat.attach_file"),
            hint_text="C:/path/to/file.txt\nD:/path/to/image.png",
            multiline=True,
            min_lines=3,
            max_lines=6,
            autofocus=True,
        )

        def do_confirm(ev: ft.ControlEvent) -> None:
            raw = (path_field.value or "").strip()
            if not raw:
                return
            parts = raw.replace(";", "\n").splitlines()
            paths = [p.strip().strip('"') for p in parts if p.strip()]
            self._append_file_paths(paths)
            page.pop_dialog()
            if self._text_field:
                self._text_field.focus()

        dialog = make_dialog(
            title=t("chat.attach_file"),
            content=ft.Column(
                controls=[
                    ft.Text("输入文件绝对路径，可多行粘贴或使用分号分隔。", size=12, opacity=0.7),
                    path_field,
                ],
                spacing=12,
                tight=True,
                width=460,
            ),
            actions=[
                make_text_button(t("common.cancel"), on_click=lambda ev: page.pop_dialog()),
                make_button(t("common.confirm"), on_click=do_confirm),
            ],
            modal=True,
        )
        page.show_dialog(dialog)

    def _append_file_paths(self, paths: list[str]) -> None:
        """Append selected file markers into input box."""
        if not paths or not self._text_field:
            return
        for path in paths:
            current = self._text_field.value or ""
            separator = "\n" if current else ""
            self._text_field.value = f"{current}{separator}[File: {path}]"
        self._text_field.update()

    # ------------------------------------------------------------------
    # Refresh / focus
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        if self._send_btn:
            is_streaming = self.state.is_streaming
            self._send_btn.icon = (
                ft.Icons.STOP_CIRCLE_ROUNDED if is_streaming else ft.Icons.SEND_ROUNDED
            )
            self._send_btn.tooltip = t("chat.stop") if is_streaming else t("chat.send")
            self._send_btn.bgcolor = ft.Colors.ERROR if is_streaming else ft.Colors.PRIMARY

    def focus(self) -> None:
        if self._text_field:
            self._text_field.focus()
