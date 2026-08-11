"""Tests for the skills.sh marketplace service."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from misaka.services.skills.skill_market_service import (
    MarketSearchResult,
    MarketSkill,
    SkillInstallResult,
    SkillMarketService,
    _sanitize_dir_name,
    _url_encode,
)


@pytest.fixture
def service() -> SkillMarketService:
    return SkillMarketService()


@pytest.fixture
def sample_skill() -> MarketSkill:
    return MarketSkill(
        id="react-best-practices",
        name="React Best Practices",
        description="Performance optimization guidelines for React",
        source="vercel-labs/agent-skills",
        install_count=1250,
        refs={"github": "https://github.com/vercel-labs/agent-skills"},
    )


@pytest.fixture
def sample_api_response() -> dict:
    return {
        "query": "react",
        "count": 2,
        "skills": [
            {
                "id": "vercel-labs/agent-skills/react-best-practices",
                "skillId": "react-best-practices",
                "name": "React Best Practices",
                "description": "React optimization",
                "source": "vercel-labs/agent-skills",
                "installs": 1250,
            },
            {
                "id": "community/react-skills/react-testing",
                "skillId": "react-testing",
                "name": "React Testing",
                "description": "Testing React components",
                "source": "community/react-skills",
                "installs": 500,
            },
        ],
    }


class TestHelpers:
    def test_url_encode(self) -> None:
        assert _url_encode("react + next.js") == "react%20%2B%20next.js"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("My Skill", "my-skill"),
            ("react@best/practices!", "reactbestpractices"),
            ("my--skill---name", "my-skill-name"),
            ("!!!", ""),
        ],
    )
    def test_sanitize_dir_name(self, value: str, expected: str) -> None:
        assert _sanitize_dir_name(value) == expected


class TestDataclasses:
    def test_market_skill_defaults(self) -> None:
        skill = MarketSkill(id="test", name="Test", description="", source="src")
        assert skill.install_count == 0
        assert skill.content == ""
        assert skill.refs == {}

    def test_search_error(self) -> None:
        result = MarketSearchResult("react", [], error="timeout")
        assert result.error == "timeout"

    def test_install_result_is_structured(self) -> None:
        result = SkillInstallResult("Test", True, "done", ("npx",), 0)
        assert result.success is True
        assert result.command == ("npx",)


class TestParsing:
    def test_parse_skills_sh_response(self) -> None:
        raw = {
            "id": "vercel-labs/agent-skills/react-best-practices",
            "skillId": "react-best-practices",
            "name": "React Best Practices",
            "description": "A test",
            "source": "vercel-labs/agent-skills",
            "installs": 1234,
        }
        skill = SkillMarketService._parse_skill(raw)
        assert skill.id == "react-best-practices"
        assert skill.install_count == 1234
        assert skill.refs["github"] == "https://github.com/vercel-labs/agent-skills"
        assert skill.refs["skills.sh"].endswith("/react-best-practices")

    def test_parse_legacy_fields_and_does_not_mutate_refs(self) -> None:
        refs = {"docs": "https://example.test"}
        raw = {
            "id": "my-skill",
            "source": "owner/repo",
            "install_count": 9,
            "refs": refs,
        }
        skill = SkillMarketService._parse_skill(raw)
        assert skill.name == "my-skill"
        assert skill.install_count == 9
        assert refs == {"docs": "https://example.test"}

    def test_parse_minimal_response(self) -> None:
        skill = SkillMarketService._parse_skill({})
        assert skill.id == ""
        assert skill.name == ""


class TestHttpGetJson:
    def test_success(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps({"key": "value"}).encode()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch(
            "misaka.services.skills.skill_market_service.urlopen",
            return_value=response,
        ):
            assert SkillMarketService._http_get_json("https://example.test") == {
                "key": "value"
            }

    @pytest.mark.parametrize("payload", [b"not json", b"[]"])
    def test_invalid_response(self, payload: bytes) -> None:
        response = MagicMock()
        response.read.return_value = payload
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch(
            "misaka.services.skills.skill_market_service.urlopen",
            return_value=response,
        ), pytest.raises(RuntimeError):
            SkillMarketService._http_get_json("https://example.test")


class TestSearch:
    async def test_search_success(
        self,
        service: SkillMarketService,
        sample_api_response: dict,
    ) -> None:
        with patch.object(
            service,
            "_http_get_json",
            return_value=sample_api_response,
        ) as http_get:
            result = await service.search(" react ", limit=1)
        assert result.error is None
        assert result.query == "react"
        assert result.total == 2
        assert [skill.id for skill in result.skills] == ["react-best-practices"]
        assert http_get.call_args.args[0].endswith("/search?q=react")

    @pytest.mark.parametrize("query", ["", " ", "a"])
    async def test_short_query_skips_network(
        self,
        service: SkillMarketService,
        query: str,
    ) -> None:
        with patch.object(service, "_http_get_json") as http_get:
            result = await service.search(query)
        assert result.skills == []
        http_get.assert_not_called()

    async def test_limit_is_clamped(
        self,
        service: SkillMarketService,
        sample_api_response: dict,
    ) -> None:
        with patch.object(service, "_http_get_json", return_value=sample_api_response):
            result = await service.search("react", limit=-5)
        assert len(result.skills) == 1

    async def test_timeout(self, service: SkillMarketService) -> None:
        with patch.object(service, "_http_get_json", side_effect=asyncio.TimeoutError):
            result = await service.search("react")
        assert result.error == "timeout"

    async def test_network_error(self, service: SkillMarketService) -> None:
        with patch.object(
            service,
            "_http_get_json",
            side_effect=RuntimeError("connection refused"),
        ):
            result = await service.search("react")
        assert result.error == "connection refused"


def _process(returncode: int = 0, stdout: bytes = b"ok", stderr: bytes = b""):
    process = MagicMock()
    process.returncode = returncode
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.wait = AsyncMock(return_value=returncode)
    return process


class TestInstallSkill:
    @pytest.mark.parametrize(
        "skill",
        [
            MarketSkill("", "Broken", "", ""),
            MarketSkill("--all", "Broken", "", "owner/repo"),
            MarketSkill("safe", "Broken", "", "--help"),
        ],
    )
    async def test_rejects_invalid_market_entry(
        self,
        service: SkillMarketService,
        skill: MarketSkill,
    ) -> None:
        result = await service.install_skill(skill)
        assert result.success is False
        assert "invalid" in result.message

    async def test_missing_npx(
        self,
        service: SkillMarketService,
        sample_skill: MarketSkill,
    ) -> None:
        with patch(
            "misaka.services.skills.skill_market_service.get_expanded_path",
            return_value="PATH",
        ), patch(
            "misaka.services.skills.skill_market_service.shutil.which",
            return_value=None,
        ):
            result = await service.install_skill(sample_skill)
        assert result.success is False
        assert "Node.js" in result.message

    async def test_runs_official_cli_non_interactively(
        self,
        service: SkillMarketService,
        sample_skill: MarketSkill,
    ) -> None:
        process = _process()
        with patch(
            "misaka.services.skills.skill_market_service.get_expanded_path",
            return_value="EXPANDED_PATH",
        ), patch(
            "misaka.services.skills.skill_market_service.shutil.which",
            return_value="/bin/npx",
        ), patch(
            "misaka.services.skills.skill_market_service.wrap_windows_script_command",
            side_effect=lambda path, args: [path, *args],
        ), patch(
            "misaka.services.skills.skill_market_service.build_background_subprocess_kwargs",
            return_value={"creationflags": 1},
        ), patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=process,
        ) as create_process:
            result = await service.install_skill(sample_skill)

        assert result.success is True
        assert result.returncode == 0
        command = create_process.call_args.args
        assert command == (
            "/bin/npx",
            "-y",
            "skills",
            "add",
            "vercel-labs/agent-skills",
            "--skill",
            "react-best-practices",
            "-g",
            "-a",
            "claude-code",
            "-y",
        )
        kwargs = create_process.call_args.kwargs
        assert kwargs["stdin"] is asyncio.subprocess.DEVNULL
        assert kwargs["env"]["PATH"] == "EXPANDED_PATH"
        assert kwargs["env"]["CI"]
        assert kwargs["creationflags"] == 1

    async def test_reports_cli_error(
        self,
        service: SkillMarketService,
        sample_skill: MarketSkill,
    ) -> None:
        process = _process(returncode=2, stderr=b"package not found")
        with patch(
            "misaka.services.skills.skill_market_service.get_expanded_path",
            return_value="PATH",
        ), patch(
            "misaka.services.skills.skill_market_service.shutil.which",
            return_value="npx",
        ), patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=process,
        ):
            result = await service.install_skill(sample_skill)
        assert result.success is False
        assert result.returncode == 2
        assert result.message == "package not found"

    async def test_kills_timed_out_installer(
        self,
        service: SkillMarketService,
        sample_skill: MarketSkill,
    ) -> None:
        process = _process()
        process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        with patch(
            "misaka.services.skills.skill_market_service.get_expanded_path",
            return_value="PATH",
        ), patch(
            "misaka.services.skills.skill_market_service.shutil.which",
            return_value="npx",
        ), patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=process,
        ):
            result = await service.install_skill(sample_skill)
        assert result.success is False
        assert "timed out" in result.message
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()

    async def test_reports_start_failure(
        self,
        service: SkillMarketService,
        sample_skill: MarketSkill,
    ) -> None:
        with patch(
            "misaka.services.skills.skill_market_service.get_expanded_path",
            return_value="PATH",
        ), patch(
            "misaka.services.skills.skill_market_service.shutil.which",
            return_value="npx",
        ), patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=OSError("blocked"),
        ):
            result = await service.install_skill(sample_skill)
        assert result.success is False
        assert "blocked" in result.message


class TestServiceInit:
    def test_default_base_url(self) -> None:
        assert SkillMarketService()._base_url == "https://skills.sh/api"

    def test_custom_base_url_strips_slashes(self) -> None:
        assert SkillMarketService("https://example.test///")._base_url == (
            "https://example.test"
        )
