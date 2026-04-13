"""
Main application shell for Misaka.

Implements the root layout: navigation rail + content area.
The content area switches between pages (Dashboard, Chat, Settings,
Plugins, Extensions) based on navigation selection.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import flet as ft

from misaka.ui.chat.pages.chat_page import ChatPage
from misaka.ui.common.theme import apply_theme
from misaka.ui.dashboard.pages.dashboard_page import DashboardPage
from misaka.ui.dialogs.env_check_dialog import EnvCheckDialog
from misaka.ui.dialogs.setup_wizard_dialog import SetupWizardDialog
from misaka.ui.navigation.nav_rail import build_nav_rail
from misaka.ui.pages.plugins_page import PluginsPage
from misaka.ui.settings.pages.settings_page import SettingsPage
from misaka.ui.skills.pages.extensions_page import ExtensionsPage

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState


class AppShell(ft.Row):
    """Root layout control for the Misaka application.

    Contains the navigation rail on the left and a content area
    that switches between pages based on navigation selection.
    """

    def __init__(self, state: AppState) -> None:
        super().__init__(spacing=0, expand=True)
        self.state = state
        # Extract db from services if available
        self._db: DatabaseBackend | None = None
        if hasattr(state, 'services') and state.services:
            self._db = state.services.db

        self._nav_rail: ft.Container | None = None
        self._content_area: ft.Container | None = None
        self._dashboard_page: DashboardPage | None = None
        self._chat_page: ChatPage | None = None
        self._settings_page: SettingsPage | None = None
        self._plugins_page: PluginsPage | None = None
        self._extensions_page: ExtensionsPage | None = None
        self._env_check_dialog: EnvCheckDialog | None = None
        self._setup_wizard_dialog: SetupWizardDialog | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        # Build navigation rail
        self._nav_rail = build_nav_rail(
            state=self.state,
            on_change=self._on_nav_change,
            on_theme_toggle=self._on_theme_toggle,
        )

        # Build all pages
        self._build_pages()

        # Select current page
        current_page = self._get_current_page()

        self._content_area = ft.Container(
            content=current_page,
            expand=True,
        )

        self.controls = [
            self._nav_rail,
            self._content_area,
        ]

    def _build_pages(self) -> None:
        """Create all page instances."""
        if not self._db:
            self._get_fallback_db()

        self._dashboard_page = DashboardPage(state=self.state)

        self._chat_page = ChatPage(state=self.state, db=self._db)
        self._wire_chat_callbacks()

        self._settings_page = SettingsPage(
            state=self.state,
            db=self._db,
            on_theme_change=self._apply_theme,
            on_locale_change=self._on_locale_change,
        )

        self._plugins_page = PluginsPage(
            state=self.state,
            db=self._db,
        )

        self._extensions_page = ExtensionsPage(state=self.state)

    def _wire_chat_callbacks(self) -> None:
        """Wire ChatPage send/abort callbacks to Claude integration."""
        if not self._chat_page:
            return
        handler = self._chat_page._stream_handler
        self._chat_page.set_claude_callbacks(
            send_callback=handler.send_to_claude,
            abort_callback=handler.abort_claude,
        )

    def _get_fallback_db(self):
        """Get a database backend if not available from services."""
        from misaka.db.database import create_database
        db = create_database()
        db.initialize()
        self._db = db
        return db

    def _get_current_page(self) -> ft.Control:
        """Return the page control for the current navigation state."""
        page_map = {
            "dashboard": self._dashboard_page,
            "chat": self._chat_page,
            "settings": self._settings_page,
            "plugins": self._plugins_page,
            "extensions": self._extensions_page,
        }
        return page_map.get(self.state.current_page, self._dashboard_page)

    def _on_nav_change(self, page_name: str) -> None:
        """Handle navigation rail selection changes."""
        if page_name == self.state.current_page:
            return

        self.state.current_page = page_name

        # Switch the content area
        current_page = self._get_current_page()

        # Refresh the target page
        should_refresh = page_name != "chat"
        if should_refresh and hasattr(current_page, 'refresh'):
            current_page.refresh()

        if self._content_area:
            self._content_area.content = current_page

        # Rebuild nav rail to update selected state
        self._nav_rail = build_nav_rail(
            state=self.state,
            on_change=self._on_nav_change,
            on_theme_toggle=self._on_theme_toggle,
        )
        self.controls[0] = self._nav_rail

        self.state.update()

    def _on_theme_toggle(self) -> None:
        """Cycle through theme modes: system -> light -> dark -> system."""
        cycle = {"system": "light", "light": "dark", "dark": "system"}
        new_mode = cycle.get(self.state.theme_mode, "system")
        self._apply_theme(new_mode)

    def _apply_theme(self, mode: str) -> None:
        """Apply the selected theme and persist it."""
        self.state.theme_mode = mode
        apply_theme(self.state.page, mode, self.state.accent_color)

        # Persist the theme choice
        settings_svc = self.state.get_service('settings_service')
        if settings_svc:
            try:
                settings_svc.set_theme(mode)
            except (OSError, ValueError) as exc:
                import logging
                logging.getLogger(__name__).warning("Failed to persist theme: %s", exc)

        # Rebuild nav rail to update theme icon
        self._nav_rail = build_nav_rail(
            state=self.state,
            on_change=self._on_nav_change,
            on_theme_toggle=self._on_theme_toggle,
        )
        self.controls[0] = self._nav_rail

        self.state.update()

    def _on_locale_change(self, locale: str) -> None:
        """Handle language change from settings page."""
        self.rebuild_for_locale_change()

    def rebuild_for_locale_change(self) -> None:
        """Rebuild all pages after a locale change."""
        self._build_pages()
        current_page = self._get_current_page()
        if self._content_area:
            self._content_area.content = current_page
        # Rebuild nav rail (labels change with locale)
        self._nav_rail = build_nav_rail(
            state=self.state,
            on_change=self._on_nav_change,
            on_theme_toggle=self._on_theme_toggle,
        )
        self.controls[0] = self._nav_rail
        self.state.update()

    def get_dashboard_page(self) -> DashboardPage | None:
        """Return the dashboard page instance for initial data loading."""
        return self._dashboard_page

    def get_chat_page(self) -> ChatPage | None:
        """Return the chat page instance for external wiring."""
        return self._chat_page

    def show_setup_wizard(self) -> None:
        """Show the setup wizard dialog on first launch."""
        if not self.state.page:
            return

        self._setup_wizard_dialog = SetupWizardDialog(
            state=self.state,
            on_finish=self._dismiss_setup_wizard,
            on_skip=self._dismiss_setup_wizard,
        )

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=ft.Colors.SURFACE,
            shape=ft.RoundedRectangleBorder(radius=18),
            content_padding=ft.Padding.symmetric(horizontal=28, vertical=24),
            actions_padding=0,
            scrollable=True,
            content=ft.Container(
                content=self._setup_wizard_dialog,
                width=480,
            ),
            actions=[],
        )
        self.state.page.show_dialog(dialog)

    def _dismiss_setup_wizard(self) -> None:
        """Dismiss the setup wizard dialog."""
        if self.state.page:
            with contextlib.suppress(AttributeError, RuntimeError):
                self.state.page.pop_dialog()
        self.state.update()

    def show_env_check_dialog(self) -> None:
        """Show the environment check dialog as an overlay on the page."""
        if not self.state.page:
            return

        self._env_check_dialog = EnvCheckDialog(
            state=self.state,
            on_install=self._handle_env_install,
            on_dismiss=self._dismiss_env_check,
            on_recheck=self._recheck_env,
        )

        # Use page overlay via AlertDialog
        dialog = ft.AlertDialog(
            modal=True,
            content=self._env_check_dialog,
            actions=[],
        )
        self.state.page.show_dialog(dialog)

    def _handle_env_install(self, tool_name: str) -> None:
        """Handle tool install request from env check dialog."""
        env_svc = self.state.get_service('env_check_service')
        if env_svc:
            async def _do_install():
                await env_svc.install_tool(tool_name)
                result = await env_svc.check_all()
                self.state.env_check_result = result
                if self._env_check_dialog:
                    self._env_check_dialog.refresh()
                self.state.update()

            self.state.page.run_task(_do_install)

    def _dismiss_env_check(self) -> None:
        """Dismiss the environment check dialog."""
        self.state.show_env_check_dialog = False
        if self.state.page:
            # Close any open dialogs
            with contextlib.suppress(AttributeError, RuntimeError):
                self.state.page.pop_dialog()
        self.state.update()

    def _recheck_env(self) -> None:
        """Re-run environment checks."""
        env_svc = self.state.get_service('env_check_service')
        if env_svc:
            async def _do_recheck():
                await asyncio.sleep(0)
                result = await env_svc.check_all()
                self.state.env_check_result = result
                if self._env_check_dialog:
                    self._env_check_dialog.refresh()
                self.state.update()

            self.state.page.run_task(_do_recheck)
