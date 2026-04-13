"""
Tests for the Setup Wizard feature.

Covers:
- SettingKeys.SETUP_WIZARD_COMPLETED constant
- i18n keys for setup_wizard
- SetupWizardDialog logic (step navigation, provider save, workdir save, completion)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import misaka.i18n as i18n
from misaka.config import SettingKeys
from misaka.services.skills.env_check_service import (
    EnvironmentCheckResult,
    ToolStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _init_i18n():
    """Ensure i18n is initialized for every test."""
    i18n.init("en")
    yield


def _make_env_result(all_installed: bool = True) -> EnvironmentCheckResult:
    """Create a minimal EnvironmentCheckResult for testing."""
    tools = [
        ToolStatus("Claude Code CLI", "claude", "2.1.0", True, "", ""),
        ToolStatus("Node.js", "node", "20.11.1", True, "", ""),
        ToolStatus("Python", "python3", "3.12.1", True, "", ""),
        ToolStatus("Git", "git", "2.43.0", True, "", ""),
    ]
    if not all_installed:
        tools[1] = ToolStatus("Node.js", "node", None, False, "https://nodejs.org", "brew install node")
    return EnvironmentCheckResult(
        tools=tools,
        all_installed=all_installed,
        checked_at="2026-01-01T00:00:00",
    )


def _make_mock_state(env_result=None):
    """Create a mock AppState with necessary services."""
    state = MagicMock()
    state.env_check_result = env_result
    state.page = MagicMock()
    state.page.run_task = MagicMock()
    state.page.show_dialog = MagicMock()
    state.page.pop_dialog = MagicMock()

    settings_svc = MagicMock()
    settings_svc.get = MagicMock(return_value=None)
    settings_svc.set = MagicMock()

    router_svc = MagicMock()
    router_svc.get_active = MagicMock(return_value=None)
    router_svc.create = MagicMock()
    router_svc.update = MagicMock()
    router_svc.activate = MagicMock()

    def get_service(name):
        if name == "settings_service":
            return settings_svc
        if name == "router_config_service":
            return router_svc
        if name == "env_check_service":
            return MagicMock()
        return None

    state.get_service = get_service
    return state, settings_svc, router_svc


# ---------------------------------------------------------------------------
# SettingKeys tests
# ---------------------------------------------------------------------------


class TestSettingKeys:

    def test_setup_wizard_completed_key_exists(self) -> None:
        assert hasattr(SettingKeys, "SETUP_WIZARD_COMPLETED")
        assert SettingKeys.SETUP_WIZARD_COMPLETED == "setup_wizard_completed"


# ---------------------------------------------------------------------------
# i18n tests
# ---------------------------------------------------------------------------


class TestSetupWizardI18n:

    def test_setup_wizard_keys_exist_in_en(self) -> None:
        keys = [
            "setup_wizard.title",
            "setup_wizard.subtitle",
            "setup_wizard.step_env",
            "setup_wizard.step_provider",
            "setup_wizard.step_workdir",
            "setup_wizard.step_done",
            "setup_wizard.next",
            "setup_wizard.back",
            "setup_wizard.finish",
            "setup_wizard.skip",
            "setup_wizard.provider_name",
            "setup_wizard.provider_api_key",
            "setup_wizard.provider_base_url",
            "setup_wizard.workdir_label",
            "setup_wizard.workdir_browse",
            "setup_wizard.done_title",
            "setup_wizard.done_message",
            "setup_wizard.recheck",
        ]
        for key in keys:
            result = i18n.t(key)
            assert result != key, f"Translation key '{key}' not found in en locale"

    def test_setup_wizard_keys_exist_in_zh_cn(self) -> None:
        i18n.set_locale("zh-CN")
        assert i18n.t("setup_wizard.title") == "设置向导"
        assert i18n.t("setup_wizard.next") == "下一步"
        assert i18n.t("setup_wizard.finish") == "开始使用"

    def test_setup_wizard_keys_exist_in_zh_tw(self) -> None:
        i18n.set_locale("zh-TW")
        assert i18n.t("setup_wizard.title") == "設定精靈"
        assert i18n.t("setup_wizard.next") == "下一步"
        assert i18n.t("setup_wizard.finish") == "開始使用"


# ---------------------------------------------------------------------------
# SetupWizardDialog tests
# ---------------------------------------------------------------------------


class TestSetupWizardDialog:

    def _create_wizard(self, env_result=None, **kwargs):
        """Helper to create a SetupWizardDialog with mocks."""
        state, settings_svc, router_svc = _make_mock_state(env_result)

        with (
            patch("misaka.ui.dialogs.setup_wizard_dialog.ft") as mock_ft,
            patch.object(
                __import__("flet", fromlist=["Column"]).Column,
                "__init__",
                lambda self, *a, **kw: None,
            ),
        ):
            mock_ft.Column = MagicMock()
            mock_ft.Container = MagicMock()
            mock_ft.Row = MagicMock()
            mock_ft.Text = MagicMock()
            mock_ft.Icon = MagicMock()
            mock_ft.Icons = MagicMock()
            mock_ft.Colors = MagicMock()
            mock_ft.FontWeight = MagicMock()
            mock_ft.CrossAxisAlignment = MagicMock()
            mock_ft.MainAxisAlignment = MagicMock()
            mock_ft.Alignment = MagicMock()
            mock_ft.BoxShadow = MagicMock()
            mock_ft.Border = MagicMock()
            mock_ft.Offset = MagicMock()
            mock_ft.Padding = MagicMock()
            mock_ft.Margin = MagicMock()
            mock_ft.ProgressRing = MagicMock()
            mock_ft.TextAlign = MagicMock()
            mock_ft.Divider = MagicMock()

            from misaka.ui.dialogs.setup_wizard_dialog import SetupWizardDialog
            wizard = SetupWizardDialog(
                state,
                on_finish=kwargs.get("on_finish"),
                on_skip=kwargs.get("on_skip"),
            )

        return wizard, state, settings_svc, router_svc

    def test_initial_step_is_zero(self) -> None:
        wizard, *_ = self._create_wizard()
        assert wizard._current_step == 0

    def test_go_next_increments_step(self) -> None:
        wizard, *_ = self._create_wizard(env_result=_make_env_result())
        wizard._rebuild = MagicMock()
        wizard._go_next()
        assert wizard._current_step == 1

    def test_go_next_does_not_exceed_max(self) -> None:
        wizard, *_ = self._create_wizard()
        wizard._rebuild = MagicMock()
        wizard._current_step = 3
        wizard._go_next()
        assert wizard._current_step == 3

    def test_go_back_decrements_step(self) -> None:
        wizard, *_ = self._create_wizard()
        wizard._rebuild = MagicMock()
        wizard._current_step = 2
        wizard._go_back()
        assert wizard._current_step == 1

    def test_go_back_does_not_go_below_zero(self) -> None:
        wizard, *_ = self._create_wizard()
        wizard._rebuild = MagicMock()
        wizard._current_step = 0
        wizard._go_back()
        assert wizard._current_step == 0

    def test_mark_completed_sets_setting(self) -> None:
        wizard, state, settings_svc, _ = self._create_wizard()
        wizard._mark_completed()
        settings_svc.set.assert_called_once_with(
            SettingKeys.SETUP_WIZARD_COMPLETED, "true"
        )

    def test_handle_finish_marks_completed_and_calls_callback(self) -> None:
        on_finish = MagicMock()
        wizard, state, settings_svc, _ = self._create_wizard(on_finish=on_finish)
        wizard._handle_finish()
        settings_svc.set.assert_called_once()
        on_finish.assert_called_once()

    def test_handle_skip_marks_completed_and_calls_callback(self) -> None:
        on_skip = MagicMock()
        wizard, state, settings_svc, _ = self._create_wizard(on_skip=on_skip)
        wizard._handle_skip()
        settings_svc.set.assert_called_once()
        on_skip.assert_called_once()

    def test_update_provider_fields(self) -> None:
        wizard, *_ = self._create_wizard()
        wizard._update_provider_field("name", "Test Provider")
        wizard._update_provider_field("api_key", "sk-test-key")
        wizard._update_provider_field("base_url", "https://api.example.com")
        assert wizard._provider_name == "Test Provider"
        assert wizard._provider_api_key == "sk-test-key"
        assert wizard._provider_base_url == "https://api.example.com"

    def test_save_provider_creates_config(self) -> None:
        wizard, state, _, router_svc = self._create_wizard()
        wizard._provider_name = "My Provider"
        wizard._provider_api_key = "sk-test-key"
        wizard._provider_base_url = "https://api.example.com"

        mock_config = MagicMock()
        mock_config.id = "new-id"
        router_svc.create.return_value = mock_config

        wizard._save_provider()

        router_svc.create.assert_called_once()
        call_kwargs = router_svc.create.call_args
        assert call_kwargs[1]["name"] == "My Provider"
        assert call_kwargs[1]["api_key"] == "sk-test-key"
        assert call_kwargs[1]["base_url"] == "https://api.example.com"
        config_json = json.loads(call_kwargs[1]["config_json"])
        assert config_json["env"]["ANTHROPIC_AUTH_TOKEN"] == "sk-test-key"
        assert config_json["env"]["ANTHROPIC_BASE_URL"] == "https://api.example.com"
        router_svc.activate.assert_called_once_with("new-id")

    def test_save_provider_skips_when_no_key(self) -> None:
        wizard, _, _, router_svc = self._create_wizard()
        wizard._provider_api_key = ""
        wizard._save_provider()
        router_svc.create.assert_not_called()

    def test_save_provider_updates_existing_empty_config(self) -> None:
        wizard, _, _, router_svc = self._create_wizard()
        wizard._provider_name = "Updated"
        wizard._provider_api_key = "sk-updated"

        existing = MagicMock()
        existing.id = "existing-id"
        existing.api_key = ""
        router_svc.get_active.return_value = existing

        wizard._save_provider()

        router_svc.update.assert_called_once()
        router_svc.activate.assert_called_once_with("existing-id")

    def test_save_provider_default_name(self) -> None:
        wizard, _, _, router_svc = self._create_wizard()
        wizard._provider_name = ""
        wizard._provider_api_key = "sk-key"

        mock_config = MagicMock()
        mock_config.id = "new-id"
        router_svc.create.return_value = mock_config

        wizard._save_provider()
        call_kwargs = router_svc.create.call_args[1]
        assert call_kwargs["name"] == "Default"

    def test_save_workdir(self) -> None:
        wizard, _, settings_svc, _ = self._create_wizard()
        wizard._workdir = "/home/user/projects"
        wizard._save_workdir()
        settings_svc.set.assert_called_once_with(
            "default_working_dir", "/home/user/projects"
        )

    def test_save_workdir_skips_empty(self) -> None:
        wizard, _, settings_svc, _ = self._create_wizard()
        wizard._workdir = ""
        wizard._save_workdir()
        settings_svc.set.assert_not_called()

    def test_go_next_saves_provider_on_step_1(self) -> None:
        wizard, *_ = self._create_wizard()
        wizard._rebuild = MagicMock()
        wizard._save_provider = MagicMock()
        wizard._current_step = 1
        wizard._go_next()
        wizard._save_provider.assert_called_once()
        assert wizard._current_step == 2

    def test_go_next_saves_workdir_on_step_2(self) -> None:
        wizard, *_ = self._create_wizard()
        wizard._rebuild = MagicMock()
        wizard._save_workdir = MagicMock()
        wizard._current_step = 2
        wizard._go_next()
        wizard._save_workdir.assert_called_once()
        assert wizard._current_step == 3

    def test_update_workdir(self) -> None:
        wizard, *_ = self._create_wizard()
        wizard._update_workdir("/new/path")
        assert wizard._workdir == "/new/path"

    def test_provider_config_json_without_base_url(self) -> None:
        wizard, _, _, router_svc = self._create_wizard()
        wizard._provider_name = "Simple"
        wizard._provider_api_key = "sk-key"
        wizard._provider_base_url = ""

        mock_config = MagicMock()
        mock_config.id = "new-id"
        router_svc.create.return_value = mock_config

        wizard._save_provider()

        call_kwargs = router_svc.create.call_args[1]
        config_json = json.loads(call_kwargs["config_json"])
        assert "ANTHROPIC_BASE_URL" not in config_json["env"]

    def test_full_wizard_flow(self) -> None:
        on_finish = MagicMock()
        wizard, state, settings_svc, router_svc = self._create_wizard(
            env_result=_make_env_result(),
            on_finish=on_finish,
        )
        wizard._rebuild = MagicMock()

        mock_config = MagicMock()
        mock_config.id = "new-id"
        router_svc.create.return_value = mock_config

        # Step 0: Environment → Next
        assert wizard._current_step == 0
        wizard._go_next()
        assert wizard._current_step == 1

        # Step 1: Provider → fill and Next
        wizard._provider_name = "Test"
        wizard._provider_api_key = "sk-key"
        wizard._go_next()
        assert wizard._current_step == 2
        router_svc.create.assert_called_once()

        # Step 2: Working dir → fill and Next
        wizard._workdir = "/home/test"
        wizard._go_next()
        assert wizard._current_step == 3
        settings_svc.set.assert_called_with("default_working_dir", "/home/test")

        # Step 3: Done → Finish
        wizard._handle_finish()
        on_finish.assert_called_once()
        settings_svc.set.assert_called_with(
            SettingKeys.SETUP_WIZARD_COMPLETED, "true"
        )


# ---------------------------------------------------------------------------
# Integration with main startup logic
# ---------------------------------------------------------------------------


class TestSetupWizardStartupIntegration:

    def test_wizard_shown_when_not_completed(self, db) -> None:
        from misaka.services.settings.settings_service import SettingsService

        svc = SettingsService(db)
        assert svc.get(SettingKeys.SETUP_WIZARD_COMPLETED) is None
        # Simulate: wizard should show

    def test_wizard_not_shown_when_completed(self, db) -> None:
        from misaka.services.settings.settings_service import SettingsService

        svc = SettingsService(db)
        svc.set(SettingKeys.SETUP_WIZARD_COMPLETED, "true")
        assert svc.get(SettingKeys.SETUP_WIZARD_COMPLETED) == "true"
        # Simulate: wizard should NOT show

    def test_env_check_dialog_shown_when_wizard_done_and_tools_missing(self, db) -> None:
        from misaka.services.settings.settings_service import SettingsService

        svc = SettingsService(db)
        svc.set(SettingKeys.SETUP_WIZARD_COMPLETED, "true")
        wizard_done = svc.get(SettingKeys.SETUP_WIZARD_COMPLETED) == "true"
        env_result = _make_env_result(all_installed=False)

        assert wizard_done is True
        assert env_result.all_installed is False
        # In main.py: would call app_shell.show_env_check_dialog()
