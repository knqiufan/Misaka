"""
Tests for the SkillMarketService.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from misaka.services.skills.skill_market_service import (
    MarketSearchResult,
    MarketSkill,
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
        relevance_score=85.5,
        content="# React Best Practices\n\nOptimize your React apps.",
        refs={"github": "https://github.com/vercel-labs/agent-skills"},
    )


@pytest.fixture
def sample_api_response() -> dict:
    return {
        "query": "react",
        "count": 2,
        "skills": [
            {
                "id": "react-best-practices",
                "name": "React Best Practices",
                "description": "React optimization",
                "source": "vercel-labs/agent-skills",
                "install_count": 1250,
                "relevance_score": 85.5,
                "content": "# React Best Practices",
                "refs": {"github": "https://github.com/vercel-labs/agent-skills"},
            },
            {
                "id": "react-testing",
                "name": "React Testing",
                "description": "Testing React components",
                "source": "community/react-skills",
                "install_count": 500,
                "relevance_score": 72.0,
                "content": "",
                "refs": {},
            },
        ],
    }


class TestUrlEncode:

    def test_basic_encoding(self) -> None:
        assert _url_encode("hello world") == "hello%20world"

    def test_special_characters(self) -> None:
        assert _url_encode("react+next.js") == "react%2Bnext.js"

    def test_empty_string(self) -> None:
        assert _url_encode("") == ""

    def test_already_safe(self) -> None:
        assert _url_encode("hello") == "hello"


class TestSanitizeDirName:

    def test_basic_name(self) -> None:
        assert _sanitize_dir_name("My Skill") == "my-skill"

    def test_special_characters(self) -> None:
        assert _sanitize_dir_name("react@best/practices!") == "reactbestpractices"

    def test_consecutive_hyphens(self) -> None:
        assert _sanitize_dir_name("my--skill---name") == "my-skill-name"

    def test_leading_trailing_hyphens(self) -> None:
        assert _sanitize_dir_name("-my-skill-") == "my-skill"

    def test_empty_after_sanitize(self) -> None:
        assert _sanitize_dir_name("!!!") == ""


class TestMarketSkill:

    def test_dataclass_fields(self, sample_skill: MarketSkill) -> None:
        assert sample_skill.id == "react-best-practices"
        assert sample_skill.name == "React Best Practices"
        assert sample_skill.install_count == 1250
        assert sample_skill.source == "vercel-labs/agent-skills"
        assert "github" in sample_skill.refs

    def test_defaults(self) -> None:
        skill = MarketSkill(id="test", name="Test", description="", source="src")
        assert skill.install_count == 0
        assert skill.relevance_score == 0.0
        assert skill.content == ""
        assert skill.refs == {}


class TestMarketSearchResult:

    def test_success_result(self) -> None:
        result = MarketSearchResult(
            query="react",
            skills=[],
            total=0,
        )
        assert result.error is None
        assert result.total == 0

    def test_error_result(self) -> None:
        result = MarketSearchResult(
            query="react",
            skills=[],
            total=0,
            error="timeout",
        )
        assert result.error == "timeout"


class TestParseSkill:

    def test_parse_full_response(self) -> None:
        data = {
            "id": "test-skill",
            "name": "Test Skill",
            "description": "A test",
            "source": "user/repo",
            "install_count": 100,
            "relevance_score": 50.0,
            "content": "# Content",
            "refs": {"github": "https://github.com/user/repo"},
        }
        skill = SkillMarketService._parse_skill(data)
        assert skill.id == "test-skill"
        assert skill.name == "Test Skill"
        assert skill.install_count == 100

    def test_parse_minimal_response(self) -> None:
        skill = SkillMarketService._parse_skill({})
        assert skill.id == ""
        assert skill.name == ""
        assert skill.install_count == 0

    def test_parse_name_fallback_to_id(self) -> None:
        skill = SkillMarketService._parse_skill({"id": "my-skill"})
        assert skill.name == "my-skill"


class TestBuildSkillContent:

    def test_adds_front_matter(self, sample_skill: MarketSkill) -> None:
        content = "# My Skill\nDoes things."
        result = SkillMarketService._build_skill_content(sample_skill, content)
        assert result.startswith("---\n")
        assert "name: React Best Practices" in result
        assert "description: Performance optimization" in result
        assert "source: vercel-labs/agent-skills" in result
        assert content in result

    def test_preserves_existing_front_matter(self, sample_skill: MarketSkill) -> None:
        content = "---\nname: Existing\n---\n# Content"
        result = SkillMarketService._build_skill_content(sample_skill, content)
        assert result == content

    def test_no_description(self) -> None:
        skill = MarketSkill(id="s", name="S", description="", source="src")
        content = "# Content"
        result = SkillMarketService._build_skill_content(skill, content)
        assert "description:" not in result


class TestHttpGetJson:

    def test_success(self) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"key": "value"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "misaka.services.skills.skill_market_service.urlopen",
            return_value=mock_response,
        ):
            result = SkillMarketService._http_get_json("https://example.com/api")
            assert result == {"key": "value"}

    def test_network_failure(self) -> None:
        from urllib.error import URLError

        with patch(
            "misaka.services.skills.skill_market_service.urlopen",
            side_effect=URLError("fail"),
        ):
            with pytest.raises(RuntimeError, match="HTTP request failed"):
                SkillMarketService._http_get_json("https://example.com/api")

    def test_invalid_json(self) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b"not json"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "misaka.services.skills.skill_market_service.urlopen",
            return_value=mock_response,
        ):
            with pytest.raises(RuntimeError, match="HTTP request failed"):
                SkillMarketService._http_get_json("https://example.com/api")


class TestSearch:

    async def test_search_success(
        self, service: SkillMarketService, sample_api_response: dict,
    ) -> None:
        with patch.object(
            service, "_http_get_json", return_value=sample_api_response,
        ):
            result = await service.search("react", limit=10)
            assert result.error is None
            assert len(result.skills) == 2
            assert result.skills[0].id == "react-best-practices"
            assert result.total == 2

    async def test_search_empty_query(self, service: SkillMarketService) -> None:
        result = await service.search("", limit=10)
        assert result.skills == []
        assert result.total == 0

    async def test_search_whitespace_query(self, service: SkillMarketService) -> None:
        result = await service.search("   ", limit=10)
        assert result.skills == []

    async def test_search_timeout(self, service: SkillMarketService) -> None:
        import asyncio
        with patch.object(
            service, "_http_get_json", side_effect=asyncio.TimeoutError,
        ):
            result = await service.search("react")
            assert result.error == "timeout"
            assert result.skills == []

    async def test_search_network_error(self, service: SkillMarketService) -> None:
        with patch.object(
            service, "_http_get_json", side_effect=RuntimeError("connection refused"),
        ):
            result = await service.search("react")
            assert result.error is not None
            assert result.skills == []

    async def test_search_limit_clamped(
        self, service: SkillMarketService, sample_api_response: dict,
    ) -> None:
        with patch.object(
            service, "_http_get_json", return_value=sample_api_response,
        ) as mock_http:
            await service.search("react", limit=100)
            call_url = mock_http.call_args[0][0]
            assert "limit=50" in call_url

    async def test_search_limit_minimum(
        self, service: SkillMarketService, sample_api_response: dict,
    ) -> None:
        with patch.object(
            service, "_http_get_json", return_value=sample_api_response,
        ) as mock_http:
            await service.search("react", limit=-5)
            call_url = mock_http.call_args[0][0]
            assert "limit=1" in call_url


class TestGetSkillContent:

    async def test_success(self, service: SkillMarketService) -> None:
        api_response = {"content": "# Skill Content\nDoes things."}
        with patch.object(service, "_http_get_json", return_value=api_response):
            content = await service.get_skill_content("user/repo", "my-skill")
            assert content == "# Skill Content\nDoes things."

    async def test_nested_response(self, service: SkillMarketService) -> None:
        api_response = {"skill": {"content": "# Nested Content"}}
        with patch.object(service, "_http_get_json", return_value=api_response):
            content = await service.get_skill_content("user/repo", "my-skill")
            assert content == "# Nested Content"

    async def test_failure(self, service: SkillMarketService) -> None:
        with patch.object(
            service, "_http_get_json", side_effect=RuntimeError("fail"),
        ):
            content = await service.get_skill_content("user/repo", "my-skill")
            assert content is None


class TestInstallSkill:

    async def test_install_success(
        self, service: SkillMarketService, sample_skill: MarketSkill, tmp_path: Path,
    ) -> None:
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = await service.install_skill(sample_skill)
            assert result is not None
            assert result.exists()
            assert result.name == "SKILL.md"
            content = result.read_text(encoding="utf-8")
            assert "React Best Practices" in content
            assert "# React Best Practices" in content

    async def test_install_with_preexisting_content(
        self, service: SkillMarketService, sample_skill: MarketSkill, tmp_path: Path,
    ) -> None:
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = await service.install_skill(
                sample_skill, content="# Custom Content",
            )
            assert result is not None
            content = result.read_text(encoding="utf-8")
            assert "# Custom Content" in content

    async def test_install_no_content(
        self, service: SkillMarketService, tmp_path: Path,
    ) -> None:
        skill = MarketSkill(
            id="empty-skill",
            name="Empty",
            description="No content",
            source="test/repo",
        )
        with patch.object(service, "get_skill_content", return_value=None):
            result = await service.install_skill(skill)
            assert result is None

    async def test_install_fetches_content_when_missing(
        self, service: SkillMarketService, tmp_path: Path,
    ) -> None:
        skill = MarketSkill(
            id="fetch-skill",
            name="Fetch Skill",
            description="Needs fetch",
            source="test/repo",
        )
        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch.object(
                 service, "get_skill_content",
                 return_value="# Fetched Content",
             ):
            result = await service.install_skill(skill)
            assert result is not None
            content = result.read_text(encoding="utf-8")
            assert "# Fetched Content" in content

    async def test_install_sanitizes_directory_name(
        self, service: SkillMarketService, tmp_path: Path,
    ) -> None:
        skill = MarketSkill(
            id="My Skill!!!",
            name="My Skill",
            description="Test",
            source="test/repo",
            content="# Content",
        )
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = await service.install_skill(skill)
            assert result is not None
            assert "my-skill" in str(result.parent.name)

    async def test_install_overwrites_existing(
        self, service: SkillMarketService, sample_skill: MarketSkill, tmp_path: Path,
    ) -> None:
        skills_dir = tmp_path / ".claude" / "skills" / "react-best-practices"
        skills_dir.mkdir(parents=True)
        old_file = skills_dir / "SKILL.md"
        old_file.write_text("old content", encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = await service.install_skill(sample_skill)
            assert result is not None
            content = result.read_text(encoding="utf-8")
            assert "old content" not in content
            assert "React Best Practices" in content


class TestServiceInit:

    def test_default_base_url(self) -> None:
        svc = SkillMarketService()
        assert svc._base_url == "https://api.skyll.app"

    def test_custom_base_url(self) -> None:
        svc = SkillMarketService(base_url="https://custom.api.dev/")
        assert svc._base_url == "https://custom.api.dev"

    def test_trailing_slash_stripped(self) -> None:
        svc = SkillMarketService(base_url="https://api.example.com///")
        assert svc._base_url == "https://api.example.com"
