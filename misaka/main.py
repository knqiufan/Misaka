"""
Misaka application entry point.

Initializes the Flet application, sets up the database,
creates services, and builds the main UI with proper
dependency injection and graceful shutdown handling.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

# Allow running this file as a script (e.g. via `flet run misaka/main.py`)
# while still resolving absolute imports like `import misaka.*`.
if __package__ in {None, ""}:
    _project_root = Path(__file__).resolve().parent.parent
    _project_root_str = str(_project_root)
    if _project_root_str not in sys.path:
        sys.path.insert(0, _project_root_str)

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


def _is_truthy_env(name: str) -> bool:
    """Return True when an env var looks enabled."""
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _is_source_tree() -> bool:
    """Detect if running from repository source tree."""
    return (Path(__file__).resolve().parent.parent / "pyproject.toml").exists()


def _is_debug_mode() -> bool:
    """Enable debug defaults for source/dev runs or explicit env."""
    return _is_truthy_env("MISAKA_DEBUG") or _is_source_tree()


def _is_hot_reload_mode() -> bool:
    """Enable hot reload by default in debug mode."""
    if _is_truthy_env("MISAKA_DISABLE_HOT_RELOAD"):
        return False
    if _is_truthy_env("MISAKA_HOT_RELOAD"):
        return True
    return _is_debug_mode()


def _launch_flet_hot_reload(script_path: Path) -> int:
    """Run app via Flet CLI with hot reload."""
    env = os.environ.copy()
    env["MISAKA_FLET_CLI_CHILD"] = "1"
    env["MISAKA_DEBUG"] = env.get("MISAKA_DEBUG", "1")
    project_root = script_path.parent.parent
    relative_script = script_path.relative_to(project_root)
    commands = [
        [
            "flet",
            "run",
            "-d",
            "-r",
            "--assets",
            "assets",
            str(relative_script),
        ],
        ["flet", "run", "-m", "misaka.main", "-d", "-r"],
    ]
    last_exit_code = 1
    for cmd in commands:
        try:
            exit_code = subprocess.run(cmd, check=False, env=env, cwd=project_root).returncode
            last_exit_code = exit_code
            if exit_code == 0:
                return 0
        except OSError as exc:
            print(f"Warning: failed to start Flet hot reload runner: {exc}", file=sys.stderr)
            return 1
    return last_exit_code


def _maybe_delegate_hot_reload() -> bool:
    """Delegate startup to Flet CLI in dev mode."""
    if os.environ.get("MISAKA_FLET_CLI_CHILD") == "1":
        return False
    if not _is_hot_reload_mode():
        return False

    script_path = Path(__file__).resolve()
    exit_code = _launch_flet_hot_reload(script_path)
    if exit_code == 0:
        return True

    print("Warning: hot reload mode unavailable, falling back to standard run.", file=sys.stderr)
    return False


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
            except (OSError, RuntimeError) as exc:
                logger.warning("Error aborting Claude stream: %s", exc)

        # Stop all MCP server subprocesses
        try:
            await self.mcp_service.stop_all()
        except (OSError, RuntimeError) as exc:
            logger.warning("Error stopping MCP servers: %s", exc)

        # Close database connection
        try:
            self.db.close()
            logger.info("Database closed")
        except (OSError, RuntimeError) as exc:
            logger.warning("Error closing database: %s", exc)


def _setup_logging() -> None:
    """Configure application logging.

    Logs to both stderr and a file in the data directory.
    When MISAKA_DEBUG is set, logging level is DEBUG.
    """
    ensure_data_dir()

    # Keep default logs concise. Enable full DEBUG only when explicitly requested.
    verbose_log = _is_truthy_env("MISAKA_VERBOSE_LOG")
    level = logging.DEBUG if verbose_log else logging.INFO

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
    if verbose_log:
        logging.getLogger("flet").setLevel(logging.DEBUG)
        logging.getLogger("watchdog").setLevel(logging.DEBUG)
        logging.getLogger("claude_agent_sdk").setLevel(logging.DEBUG)
    else:
        logging.getLogger("flet").setLevel(logging.WARNING)
        logging.getLogger("watchdog").setLevel(logging.WARNING)
        logging.getLogger("claude_agent_sdk").setLevel(logging.INFO)


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
    saved_accent = services.settings_service.get(SettingKeys.ACCENT_COLOR) or "#6366f1"
    state.accent_color = saved_accent
    apply_theme(page, state.theme_mode, state.accent_color)

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
    if _maybe_delegate_hot_reload():
        return

    _setup_logging()
    logger.info("Starting Misaka...")
    assets = str(Path(__file__).resolve().parent.parent / "assets")
    ft.run(_main, assets_dir=assets)


if __name__ == "__main__":
    main()
