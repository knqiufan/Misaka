"""UI state tests for environment install progress and errors."""

from __future__ import annotations

from unittest.mock import MagicMock

import misaka.i18n as i18n
from misaka.services.skills.env_check_service import (
    EnvironmentCheckResult,
    InstallResult,
    ToolStatus,
)
from misaka.ui.dialogs.env_check_dialog import EnvCheckDialog
from misaka.ui.settings.components.env_status_panel import EnvStatusPanel


def _state() -> MagicMock:
    state = MagicMock()
    state.env_check_result = EnvironmentCheckResult(
        tools=[
            ToolStatus(
                "Git",
                "git",
                None,
                False,
                "https://git-scm.com/downloads",
                "winget install Git.Git",
            )
        ],
        all_installed=False,
        checked_at="2026-08-11T00:00:00Z",
    )
    return state


def setup_module() -> None:
    i18n.init("en")


def test_dialog_retains_install_error() -> None:
    dialog = EnvCheckDialog(_state())
    result = InstallResult("Git", False, "permission denied", returncode=1)

    dialog.finish_install(result)

    assert dialog._installing_tool is None
    assert dialog._status_is_error is True
    assert dialog._status_message is not None
    assert "permission denied" in dialog._status_message


def test_dialog_retains_install_success() -> None:
    dialog = EnvCheckDialog(_state())
    result = InstallResult("Git", True, "installed")

    dialog.finish_install(result)

    assert dialog._status_is_error is False
    assert dialog._status_message == "Git installed successfully."


def test_settings_panel_retains_install_error() -> None:
    panel = EnvStatusPanel(_state())
    result = InstallResult("Git", False, "permission denied", returncode=1)

    panel._finish_install(result)

    assert panel._install_error is True
    assert panel._install_message is not None
    assert "permission denied" in panel._install_message
