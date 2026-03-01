"""Folder picker dialog component.

A dialog-based folder browser for selecting a project working directory.
"""

from __future__ import annotations

import os
import string
import sys
from pathlib import Path
from typing import Callable

import flet as ft

from misaka.i18n import t

IS_WINDOWS = sys.platform == "win32"


class FolderPicker:
    """Dialog-based folder browser for selecting a directory.

    Presents a modal ``ft.AlertDialog`` with:
    - A path text-field + Go button for direct navigation
    - A parent-directory (up-arrow) button
    - On Windows, a drive-letter dropdown (C:, D:, ...)
    - A scrollable list of sub-directories (hidden dirs excluded)
    - Select / Cancel action buttons
    """

    def __init__(
        self,
        page: ft.Page,
        on_select: Callable[[str], None],
        initial_path: str | None = None,
    ) -> None:
        self._page = page
        self._on_select = on_select
        self._current_path = Path(initial_path) if initial_path else Path.home()
        self._dir_list: ft.ListView | None = None
        self._path_field: ft.TextField | None = None
        self._drive_dropdown: ft.Dropdown | None = None
        self._dialog: ft.AlertDialog | None = None
        self._build_dialog()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_dialog(self) -> None:
        """Build the complete dialog widget tree."""

        # --- Path input row ---
        from misaka.ui.theme import make_text_field as _mtf
        self._path_field = _mtf(
            value=str(self._current_path),
            expand=True,
            dense=True,
            text_size=13,
            on_submit=lambda e: self._navigate_to(self._path_field.value),
        )

        from misaka.ui.theme import make_button, make_icon_button
        go_button = make_button(
            t("folder_picker.go"),
            on_click=lambda e: self._navigate_to(self._path_field.value),
        )

        parent_button = make_icon_button(
            ft.Icons.ARROW_UPWARD,
            tooltip=t("folder_picker.parent"),
            on_click=self._go_parent,
            icon_size=20,
        )

        path_row = ft.Row(
            controls=[parent_button, self._path_field, go_button],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # --- Drive selector (Windows only) ---
        drive_row: ft.Control | None = None
        if IS_WINDOWS:
            available_drives: list[ft.dropdown.Option] = []
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.isdir(drive):
                    available_drives.append(ft.dropdown.Option(drive))

            current_drive = str(self._current_path)[:3] if len(str(self._current_path)) >= 3 else "C:\\"
            from misaka.ui.theme import make_dropdown as _mdd
            self._drive_dropdown = _mdd(
                options=available_drives,
                value=current_drive,
                width=100,
                dense=True,
                text_size=13,
                on_select=self._handle_drive_change,
            )
            drive_row = ft.Row(
                controls=[
                    ft.Text("Drive:", size=13, weight=ft.FontWeight.W_500),
                    self._drive_dropdown,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        # --- Directory listing ---
        self._dir_list = ft.ListView(
            spacing=0,
            expand=True,
        )

        dir_container = ft.Container(
            content=self._dir_list,
            height=350,
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            ),
            border_radius=10,
            padding=4,
        )

        # --- Assemble content column ---
        content_controls: list[ft.Control] = [path_row]
        if drive_row is not None:
            content_controls.append(drive_row)
        content_controls.append(dir_container)

        content = ft.Container(
            content=ft.Column(
                controls=content_controls,
                spacing=12,
                tight=True,
            ),
            width=550,
            padding=ft.Padding.only(top=8),
        )

        from misaka.ui.theme import make_dialog, make_outlined_button
        select_button = make_button(
            t("folder_picker.select"),
            icon=ft.Icons.CHECK,
            on_click=self._handle_select,
        )

        cancel_button = make_outlined_button(
            t("folder_picker.cancel"),
            icon=ft.Icons.CLOSE,
            on_click=self._handle_cancel,
        )

        self._dialog = make_dialog(
            title=t("folder_picker.title"),
            content=content,
            actions=[cancel_button, select_button],
            modal=True,
            actions_alignment=ft.MainAxisAlignment.END,
        )

        # Populate the directory list for the initial path
        self._refresh_listing()

    # ------------------------------------------------------------------
    # Directory listing
    # ------------------------------------------------------------------

    def _refresh_listing(self) -> None:
        """Read the current directory and populate ``_dir_list``."""
        if self._dir_list is None:
            return

        self._dir_list.controls.clear()

        # Update the path text-field
        if self._path_field is not None:
            self._path_field.value = str(self._current_path)

        # Update drive dropdown on Windows
        if IS_WINDOWS and self._drive_dropdown is not None:
            current_drive = str(self._current_path)[:3]
            self._drive_dropdown.value = current_drive

        try:
            entries = sorted(os.listdir(self._current_path), key=str.lower)
        except (PermissionError, OSError):
            self._dir_list.controls.append(
                ft.Container(
                    content=ft.Text(
                        t("folder_picker.error"),
                        size=13,
                        italic=True,
                        color=ft.Colors.ERROR,
                    ),
                    padding=12,
                )
            )
            self._page.update()
            return

        dirs_found = False
        for name in entries:
            # Skip hidden directories (starting with '.')
            if name.startswith("."):
                continue

            full_path = os.path.join(str(self._current_path), name)
            try:
                if not os.path.isdir(full_path):
                    continue
            except (PermissionError, OSError):
                continue

            dirs_found = True
            self._dir_list.controls.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.FOLDER, color=ft.Colors.AMBER),
                    title=ft.Text(name, size=13),
                    dense=True,
                    on_click=lambda e, p=full_path: self._navigate_to(p),
                )
            )

        if not dirs_found:
            self._dir_list.controls.append(
                ft.Container(
                    content=ft.Text(
                        t("folder_picker.empty"),
                        size=13,
                        italic=True,
                        opacity=0.6,
                    ),
                    padding=12,
                )
            )

        self._page.update()

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    def _navigate_to(self, path: str) -> None:
        """Navigate to *path* if it is a valid directory, then refresh."""
        target = Path(path)
        try:
            if target.is_dir():
                self._current_path = target.resolve()
                self._refresh_listing()
        except (PermissionError, OSError):
            # Silently ignore inaccessible paths
            pass

    def _go_parent(self, e=None) -> None:
        """Navigate to the parent of the current directory."""
        parent = self._current_path.parent
        # Avoid navigating above root (e.g. C:\ on Windows, / on Unix)
        if parent != self._current_path:
            self._current_path = parent
            self._refresh_listing()

    def _handle_drive_change(self, e: ft.ControlEvent) -> None:
        """Handle a drive letter selection on Windows."""
        drive = e.control.value
        if drive:
            self._navigate_to(drive)

    # ------------------------------------------------------------------
    # Dialog actions
    # ------------------------------------------------------------------

    def _handle_select(self, e=None) -> None:
        """Invoke the *on_select* callback with the current path and close."""
        self._page.pop_dialog()
        self._on_select(str(self._current_path))

    def _handle_cancel(self, e=None) -> None:
        """Close the dialog without selecting a folder."""
        self._page.pop_dialog()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Show the folder-picker dialog."""
        # Re-populate in case the filesystem changed since last open
        self._refresh_listing()
        self._page.show_dialog(self._dialog)

    @property
    def dialog(self) -> ft.AlertDialog:
        """Return the underlying ``ft.AlertDialog`` instance."""
        assert self._dialog is not None
        return self._dialog

    @property
    def current_path(self) -> str:
        """Return the path currently displayed in the picker."""
        return str(self._current_path)
