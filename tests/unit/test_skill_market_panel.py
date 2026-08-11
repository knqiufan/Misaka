"""Tests for skill marketplace UI integration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from misaka.i18n import init
from misaka.services.skills.skill_market_service import (
    MarketSkill,
    SkillInstallResult,
)
from misaka.ui.skills.pages.skill_market_panel import SkillMarketPanel


class DummyPage:
    def __init__(self) -> None:
        self.pending = None
        self.dialog = None

    def run_task(self, callback) -> None:
        self.pending = callback()

    def show_dialog(self, dialog) -> None:
        self.dialog = dialog


def _skill() -> MarketSkill:
    return MarketSkill(
        id="react-best-practices",
        name="React Best Practices",
        description="React guidance",
        source="vercel-labs/agent-skills",
        install_count=42,
    )


def _panel(service, callback=None) -> SkillMarketPanel:
    state = SimpleNamespace(
        update=MagicMock(),
        get_service=lambda name: service if name == "skill_market_service" else None,
    )
    return SkillMarketPanel(state, on_installed=callback)


def test_selecting_search_result_does_not_require_raw_content() -> None:
    init("en")
    service = MagicMock()
    panel = _panel(service)
    skill = _skill()
    panel._results = [skill]

    panel._on_select_skill(skill)

    assert panel._selected_skill is skill
    assert panel._preview_container.content is not None
    service.get_skill_content.assert_not_called()


async def test_successful_install_refreshes_existing_discovery() -> None:
    init("en")
    service = MagicMock()
    service.install_skill = AsyncMock(
        return_value=SkillInstallResult("React Best Practices", True, "done", returncode=0)
    )
    callback = MagicMock()
    panel = _panel(service, callback)
    page = DummyPage()
    skill = _skill()

    panel._on_install_skill(SimpleNamespace(page=page), skill)
    await page.pending

    service.install_skill.assert_awaited_once_with(skill)
    callback.assert_called_once_with()
    assert panel._is_installing is False
    assert "installed" in page.dialog.content.value.lower()


async def test_install_failure_surfaces_cli_message() -> None:
    init("en")
    service = MagicMock()
    service.install_skill = AsyncMock(
        return_value=SkillInstallResult(
            "React Best Practices",
            False,
            "package not found",
            returncode=2,
        )
    )
    panel = _panel(service)
    page = DummyPage()

    panel._on_install_skill(SimpleNamespace(page=page), _skill())
    await page.pending

    assert "package not found" in page.dialog.content.value
