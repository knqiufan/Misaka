"""
Misaka application entry point.

Initializes the Flet application, sets up the database,
creates services, and builds the main UI with proper
dependency injection and graceful shutdown handling.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import flet as ft

import misaka.i18n as i18n
from misaka.config import LOG_PATH, SettingKeys, ensure_data_dir
from misaka.db.database import DatabaseBackend, create_database
from misaka.services.claude_service import ClaudeService
from misaka.services.cli_settings_service import CliSettingsService
from misaka.services.env_check_service import EnvCheckService
from misaka.services.file_service import FileService
from misaka.services.mcp_service import MCPService
from misaka.services.message_service import MessageService
from misaka.services.permission_service import PermissionService
from misaka.services.provider_service import ProviderService
from misaka.services.router_config_service import RouterConfigService
from misaka.services.session_import_service import SessionImportService
from misaka.services.session_service import SessionService
from misaka.services.settings_service import SettingsService
from misaka.services.skill_service import SkillService
from misaka.services.task_service import TaskService
from misaka.services.update_check_service import UpdateCheckService
from misaka.state import AppState
from misaka.ui.app_shell import AppShell
from misaka.ui.theme import apply_theme

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Dependency injection container holding all service instances.

    Created once per application lifecycle. Services share a single
    database backend and can reference each other as needed.
    """

    def __init__(self, db: DatabaseBackend) -> None:
        self.db = db

        # Core services
        self.permission_service = PermissionService()
        self.settings_service = SettingsService(db)
        self.session_service = SessionService(db)
        self.message_service = MessageService(db)
        self.provider_service = ProviderService(db)
        self.task_service = TaskService(db)
        self.file_service = FileService()
        self.mcp_service = MCPService()
        self.claude_service = ClaudeService(db, self.permission_service)

        # New services
        self.env_check_service = EnvCheckService()
        self.update_check_service = UpdateCheckService()
        self.skill_service = SkillService()
        self.session_import_service = SessionImportService()
        self.cli_settings_service = CliSettingsService()
        self.router_config_service = RouterConfigService(
            db, self.cli_settings_service
        )

    async def close(self) -> None:
        """Release resources held by services."""
        # Abort any active Claude streaming
        if self.claude_service.is_streaming:
            logger.info("Aborting active Claude stream during shutdown")
            try:
                await self.claude_service.abort()
            except Exception as exc:
                logger.warning("Error aborting Claude stream: %s", exc)

        # Stop all MCP server subprocesses
        try:
            await self.mcp_service.stop_all()
        except Exception as exc:
            logger.warning("Error stopping MCP servers: %s", exc)

        # Close database connection
        try:
            self.db.close()
            logger.info("Database closed")
        except Exception as exc:
            logger.warning("Error closing database: %s", exc)


def _setup_logging() -> None:
    """Configure application logging.

    Logs to both stderr and a file in the data directory.
    When MISAKA_DEBUG is set, logging level is DEBUG.
    """
    ensure_data_dir()

    is_debug = bool(os.environ.get("MISAKA_DEBUG"))
    level = logging.DEBUG if is_debug else logging.INFO

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]

    try:
        file_handler = logging.FileHandler(str(LOG_PATH), encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        handlers.append(file_handler)
    except OSError as exc:
        print(f"Warning: could not open log file {LOG_PATH}: {exc}", file=sys.stderr)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def _main(page: ft.Page) -> None:
    """Flet application target function.

    Called by ``ft.app()`` with the Page object representing the window.
    Sets up infrastructure, creates services, wires UI, and registers
    cleanup handlers.
    """
    # --- Initialize infrastructure ---
    ensure_data_dir()
    db = create_database()
    db.initialize()

    # --- Create service container ---
    services = ServiceContainer(db)

    # --- Ensure default router config exists ---
    services.router_config_service.ensure_default_config()

    # --- Set up page properties ---
    page.title = "Misaka"
    _icon_path = str(Path(__file__).resolve().parent.parent / "assets" / "icon.ico")
    page.window.icon = _icon_path
    page.window.width = 1280
    page.window.height = 860
    page.window.min_width = 800
    page.window.min_height = 600

    # --- Create state ---
    state = AppState(page)

    # --- Apply saved theme ---
    saved_theme = services.settings_service.get_theme()
    state.theme_mode = saved_theme
    apply_theme(page, state.theme_mode)

    # --- Load initial data ---
    state.sessions = services.session_service.get_all()

    # --- Load MCP servers ---
    mcp_servers = services.mcp_service.load_mcp_servers()
    mcp_sdk_format = services.mcp_service.to_sdk_format(mcp_servers)
    logger.info("Loaded %d MCP servers", len(mcp_servers))

    # --- Store services on state for UI access ---
    state.services = services
    state.mcp_servers_sdk = mcp_sdk_format

    # --- Initialize i18n ---
    saved_lang = services.settings_service.get(SettingKeys.LANGUAGE)
    locale = saved_lang if saved_lang in i18n.SUPPORTED_LOCALES else i18n.DEFAULT_LOCALE
    i18n.init(locale)
    state.locale = locale

    # --- Build UI ---
    app_shell = AppShell(state)
    page.add(app_shell)
    page.update()

    # --- Run environment check on startup ---
    async def _run_env_check() -> None:
        result = await services.env_check_service.check_all()
        state.env_check_result = result
        if not result.all_installed:
            state.show_env_check_dialog = True
        state.update()

    page.run_task(_run_env_check)

    # --- Check for Claude Code updates ---
    async def _run_update_check() -> None:
        result = await services.update_check_service.check_for_update()
        state.update_check_result = result
        state.update()

    page.run_task(_run_update_check)

    # --- Register cleanup ---
    async def on_disconnect(e: ft.ControlEvent) -> None:
        logger.info("Application disconnecting, cleaning up resources")
        await services.close()

    page.on_disconnect = on_disconnect

    logger.info("Misaka started successfully")


def main() -> None:
    """Application entry point."""
    _setup_logging()
    logger.info("Starting Misaka...")
    assets = str(Path(__file__).resolve().parent.parent / "assets")
    ft.run(_main, assets_dir=assets)


if __name__ == "__main__":
    main()
