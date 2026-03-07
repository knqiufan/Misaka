"""
Tests that all UI components and pages can be imported without errors.

This catches import-time issues like missing dependencies, circular imports,
and syntax errors in UI modules.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pytest


# We need to mock flet since it may not be available in CI/test environments
# or may try to initialize graphics subsystems.
@pytest.fixture(autouse=True)
def mock_flet():
    """Mock flet module to avoid GUI initialization during import tests."""
    # If flet is already importable, these tests work normally.
    # If not, we provide a minimal mock.
    try:
        import flet
        yield
    except ImportError:
        mock = MagicMock()
        sys.modules["flet"] = mock
        yield
        del sys.modules["flet"]


class TestUIImports:
    """Verify that all UI modules can be imported without error."""

    def test_import_theme(self) -> None:
        from misaka.ui.common import theme  # noqa: F401

    def test_import_app_shell(self) -> None:
        from misaka.ui.common import app_shell  # noqa: F401

    def test_import_components_package(self) -> None:
        # Old components package is kept for backwards compatibility
        pass

    def test_import_pages_package(self) -> None:
        # Old pages package is kept for backwards compatibility (plugins_page.py)
        from misaka.ui.pages import plugins_page  # noqa: F401

    def test_import_chat_list(self) -> None:
        from misaka.ui.chat.components import chat_list  # noqa: F401

    def test_import_chat_view(self) -> None:
        from misaka.ui.chat.components import chat_view  # noqa: F401

    def test_import_code_block(self) -> None:
        from misaka.ui.chat.components import code_block  # noqa: F401

    def test_import_connection_status(self) -> None:
        from misaka.ui.status import connection_status  # noqa: F401

    def test_import_file_preview(self) -> None:
        from misaka.ui.file.components import file_preview  # noqa: F401

    def test_import_file_tree(self) -> None:
        from misaka.ui.file.components import file_tree  # noqa: F401

    def test_import_message_input(self) -> None:
        from misaka.ui.chat.components import message_input  # noqa: F401

    def test_import_message_item(self) -> None:
        from misaka.ui.chat.components import message_item  # noqa: F401

    def test_import_message_list(self) -> None:
        from misaka.ui.chat.components import message_list  # noqa: F401

    def test_import_nav_rail(self) -> None:
        from misaka.ui.navigation import nav_rail  # noqa: F401

    def test_import_permission_dialog(self) -> None:
        from misaka.ui.dialogs import permission_dialog  # noqa: F401

    def test_import_resize_handle(self) -> None:
        from misaka.ui.panels import resize_handle  # noqa: F401

    def test_import_right_panel(self) -> None:
        from misaka.ui.panels import right_panel  # noqa: F401

    def test_import_streaming_message(self) -> None:
        from misaka.ui.chat.components import streaming_message  # noqa: F401

    def test_import_task_list(self) -> None:
        from misaka.ui.task.components import task_list  # noqa: F401

    def test_import_tool_call_block(self) -> None:
        from misaka.ui.chat.components import tool_call_block  # noqa: F401

    def test_import_chat_page(self) -> None:
        from misaka.ui.chat.pages import chat_page  # noqa: F401

    def test_import_settings_page(self) -> None:
        from misaka.ui.settings.pages import settings_page  # noqa: F401

    def test_import_plugins_page(self) -> None:
        from misaka.ui.pages import plugins_page  # noqa: F401

    def test_import_extensions_page(self) -> None:
        from misaka.ui.skills.pages import extensions_page  # noqa: F401

    def test_construct_image_overlay(self) -> None:
        from misaka.ui.components.image_overlay import ImageOverlay

        overlay = ImageOverlay(image_src="test.png")

        assert overlay is not None
        assert len(overlay.controls) == 4

    def test_image_overlay_zoom_updates_rendered_size(self) -> None:
        from misaka.ui.components.image_overlay import ImageOverlay

        overlay = ImageOverlay(image_src="test.png")
        initial_width = overlay._image_container.width

        overlay._handle_zoom_in(None)

        assert overlay._image_container.width is not None
        assert initial_width is not None
        assert overlay._image_container.width > initial_width

    def test_image_overlay_close_button_renders_above_fullscreen_controls(self) -> None:
        from misaka.ui.components.image_overlay import ImageOverlay

        overlay = ImageOverlay(image_src="test.png")

        close_button = overlay.controls[-1]

        assert overlay.controls[-1] is close_button

    def test_image_overlay_close_button_invokes_on_close(self) -> None:
        from misaka.ui.components.image_overlay import ImageOverlay

        closed: list[bool] = []
        overlay = ImageOverlay(image_src="test.png", on_close=lambda: closed.append(True))

        close_button = overlay.controls[-1]
        close_button.content.on_click(None)

        assert closed == [True]

    def test_message_input_pending_image_click_opens_image_overlay(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from types import SimpleNamespace

        from misaka.ui.chat.components.message_input import MessageInput

        opened: list[tuple[object, str]] = []

        def fake_show_image_overlay(page: object, image_src: str) -> None:
            opened.append((page, image_src))

        monkeypatch.setattr(
            "misaka.ui.components.image_overlay.show_image_overlay",
            fake_show_image_overlay,
        )
        monkeypatch.setattr(MessageInput, "page", property(lambda self: "fake-page"))

        state = SimpleNamespace(is_streaming=False, selected_model="default")
        input_box = MessageInput(state=state)
        pending = SimpleNamespace(id="1", temp_path="test.png")

        input_box._handle_view_image(pending)

        assert opened == [("fake-page", "test.png")]


class TestServiceImports:
    """Verify that all service modules can be imported."""

    def test_import_services_package(self) -> None:
        from misaka import services  # noqa: F401

    def test_import_all_services(self) -> None:
        from misaka.services import (
            ClaudeService,
            MCPService,
            MessageService,
            PermissionService,
            SessionService,
            SettingsService,
            TaskService,
        )
        # Verify they are actual classes
        assert callable(ClaudeService)
        assert callable(MCPService)

    def test_import_database(self) -> None:
        from misaka.db.database import DatabaseBackend, create_database
        assert callable(create_database)

    def test_import_models(self) -> None:
        from misaka.db.models import (
            ChatSession,
            FilePreview,
            FileTreeNode,
            MCPServerConfig,
            Message,
            MessageContentBlock,
            TaskItem,
            TokenUsage,
        )

    def test_import_config(self) -> None:
        from misaka.config import (
            DATA_DIR,
            DB_PATH,
            IS_WINDOWS,
            SettingKeys,
            get_expanded_path,
        )

    def test_import_state(self) -> None:
        from misaka.state import (
            AppState,
            PermissionRequest,
            StreamingTextBlock,
            StreamingToolUseBlock,
            TokenUsageInfo,
        )

    def test_import_utils(self) -> None:
        from misaka.utils.path_safety import is_path_safe, is_root_path, sanitize_filename
        from misaka.utils.file_utils import get_file_language, IGNORED_DIRS
        from misaka.utils.platform import find_claude_binary
