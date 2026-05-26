"""Settings page.

Application settings with a left navigation menu and right content panel.
Each settings module is loaded as an independent panel component on demand.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.ui.common.theme import RADIUS_LG, RADIUS_MD

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState

# Menu item definitions: (panel_id, i18n_key, icon)
_MENU_ITEMS: list[tuple[str, str, object]] = [
    ("appearance", "settings.settings_menu_appearance", ft.Icons.PALETTE_OUTLINED),
    ("permission", "settings.settings_menu_permission", ft.Icons.SECURITY_OUTLINED),
    ("router", "settings.settings_menu_router", ft.Icons.ROUTER_OUTLINED),
    ("system_prompt", "settings.settings_menu_system_prompt", ft.Icons.PSYCHOLOGY_OUTLINED),
    ("update", "settings.settings_menu_update", ft.Icons.SYSTEM_UPDATE_OUTLINED),
    ("env_status", "settings.settings_menu_env", ft.Icons.SETTINGS_APPLICATIONS_OUTLINED),
    ("log_viewer", "settings.settings_menu_log", ft.Icons.ARTICLE_OUTLINED),
    ("language", "settings.settings_menu_language", ft.Icons.TRANSLATE_OUTLINED),
    ("about", "settings.settings_menu_about", ft.Icons.INFO_OUTLINED),
]


class SettingsPage(ft.Column):
    """Application settings page with left menu + right content panel layout."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend | None = None,
        on_theme_change: Callable[[str], None] | None = None,
        on_locale_change: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        self.db = db
        self._on_theme_change = on_theme_change
        self._on_locale_change = on_locale_change
        self._active_panel_id: str = "appearance"
        self._content_area: ft.Container | None = None
        self._menu_column: ft.Column | None = None
        self._panel_cache: dict[str, ft.Control] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        menu = self._build_menu()
        self._content_area = ft.Container(
            content=self._load_panel(self._active_panel_id),
            expand=True,
            padding=ft.Padding.all(10),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        menu_border_color = ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)
        menu_container = ft.Container(
            content=menu,
            width=200,
            padding=ft.Padding.symmetric(vertical=12, horizontal=6),
            border=ft.Border(right=ft.BorderSide(1, menu_border_color)),
        )

        inner = ft.Row(
            controls=[menu_container, self._content_area],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        main_card = ft.Container(
            content=inner,
            margin=ft.Margin.symmetric(horizontal=10, vertical=10),
            expand=True,
            border_radius=RADIUS_MD,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
            shadow=[
                ft.BoxShadow(
                    blur_radius=24, spread_radius=-4,
                    color=ft.Colors.with_opacity(0.08, ft.Colors.BLACK),
                    offset=ft.Offset(0, 4),
                ),
                ft.BoxShadow(
                    blur_radius=12, spread_radius=-2,
                    color=ft.Colors.with_opacity(0.04, ft.Colors.BLACK),
                    offset=ft.Offset(0, 2),
                ),
            ],
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        self.controls = [main_card]

    def _build_menu(self) -> ft.Column:
        """Build the left navigation menu."""
        items: list[ft.Control] = []
        for panel_id, i18n_key, icon in _MENU_ITEMS:
            is_active = panel_id == self._active_panel_id
            item = self._build_menu_item(panel_id, i18n_key, icon, is_active)
            items.append(item)

        self._menu_column = ft.Column(
            controls=items,
            spacing=2,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        return self._menu_column

    def _build_menu_item(
        self, panel_id: str, i18n_key: str, icon: str, is_active: bool,
    ) -> ft.Control:
        """Build a single menu item."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        icon,
                        size=18,
                        color=ft.Colors.PRIMARY if is_active else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        t(i18n_key),
                        size=13,
                        weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_400,
                        color=ft.Colors.PRIMARY if is_active else ft.Colors.ON_SURFACE,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            border_radius=RADIUS_LG,
            bgcolor=(
                ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY)
                if is_active else ft.Colors.TRANSPARENT
            ),
            on_click=lambda e, pid=panel_id: self._on_menu_click(pid),
            ink=True,
        )

    def _on_menu_click(self, panel_id: str) -> None:
        """Handle menu item click — switch active panel."""
        if panel_id == self._active_panel_id:
            return
        self._active_panel_id = panel_id
        self._panel_cache.pop(panel_id, None)
        self._build_ui()
        with contextlib.suppress(Exception):
            self.update()

    def _load_panel(self, panel_id: str) -> ft.Control:
        """Load and return the panel component for the given ID."""
        if panel_id in self._panel_cache:
            return self._panel_cache[panel_id]

        panel = self._create_panel(panel_id)
        self._panel_cache[panel_id] = panel
        return panel

    def _create_panel(self, panel_id: str) -> ft.Control:
        """Create a new panel instance by ID."""
        if panel_id == "appearance":
            return self._create_appearance_panel()
        elif panel_id == "permission":
            return self._create_permission_panel()
        elif panel_id == "router":
            return self._create_router_panel()
        elif panel_id == "system_prompt":
            return self._create_system_prompt_panel()
        elif panel_id == "update":
            return self._create_update_panel()
        elif panel_id == "env_status":
            return self._create_env_status_panel()
        elif panel_id == "log_viewer":
            return self._create_log_viewer_panel()
        elif panel_id == "language":
            return self._create_language_panel()
        elif panel_id == "about":
            return self._create_about_panel()
        return ft.Container(content=ft.Text("Unknown panel"), expand=True)

    def _create_appearance_panel(self) -> ft.Control:
        from misaka.ui.settings.components.appearance_panel import AppearancePanel
        return AppearancePanel(
            self.state,
            db=self.db,
            on_theme_change=self._on_theme_change,
            on_locale_change=self._on_locale_change,
            rebuild_settings_ui=self._rebuild_settings_ui,
        )

    def _create_permission_panel(self) -> ft.Control:
        from misaka.ui.settings.components.permission_panel import PermissionPanel
        return PermissionPanel(self.state, db=self.db)

    def _create_router_panel(self) -> ft.Control:
        from misaka.ui.settings.components.router_panel import RouterPanel
        return RouterPanel(self.state, db=self.db)

    def _create_system_prompt_panel(self) -> ft.Control:
        from misaka.ui.settings.components.system_prompt_panel import SystemPromptPanel
        return SystemPromptPanel(self.state, db=self.db)

    def _create_update_panel(self) -> ft.Control:
        from misaka.ui.settings.components.update_panel import UpdatePanel
        return UpdatePanel(self.state, db=self.db)

    def _create_env_status_panel(self) -> ft.Control:
        from misaka.ui.settings.components.env_status_panel import EnvStatusPanel
        return EnvStatusPanel(self.state, db=self.db)

    def _create_log_viewer_panel(self) -> ft.Control:
        from misaka.ui.settings.components.log_viewer_panel import LogViewerPanel
        return LogViewerPanel(self.state, db=self.db)

    def _create_language_panel(self) -> ft.Control:
        from misaka.ui.settings.components.appearance_panel import AppearancePanel
        return AppearancePanel(
            self.state,
            db=self.db,
            on_theme_change=self._on_theme_change,
            on_locale_change=self._on_locale_change,
            rebuild_settings_ui=self._rebuild_settings_ui,
            show_language_only=True,
        )

    def _create_about_panel(self) -> ft.Control:
        from misaka.ui.settings.components.about_panel import AboutPanel
        return AboutPanel(self.state, db=self.db)

    def _rebuild_settings_ui(self) -> None:
        """Callback for child panels to trigger a full settings page rebuild."""
        self._panel_cache.clear()
        self._build_ui()
        with contextlib.suppress(Exception):
            self.update()

    def refresh(self) -> None:
        """Rebuild the settings page."""
        self._panel_cache.clear()
        self._build_ui()
