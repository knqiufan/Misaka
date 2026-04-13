"""
Skill market service — search and install skills from online registries.

Uses the Skyll public API (https://api.skyll.app) which aggregates skills
from skills.sh, community registries, and GitHub repositories.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_SKYLL_BASE_URL = "https://api.skyll.app"
_HTTP_TIMEOUT = 15


@dataclass
class MarketSkill:
    """A skill entry returned from the online market."""

    id: str
    name: str
    description: str
    source: str  # e.g. "vercel-labs/agent-skills"
    install_count: int = 0
    relevance_score: float = 0.0
    content: str = ""
    refs: dict[str, str] = field(default_factory=dict)


@dataclass
class MarketSearchResult:
    """Result of a market search query."""

    query: str
    skills: list[MarketSkill]
    total: int = 0
    error: str | None = None


class SkillMarketService:
    """Service for searching and installing skills from online registries."""

    def __init__(self, base_url: str = _SKYLL_BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 20) -> MarketSearchResult:
        """Search the online skill registry.

        Args:
            query: Search text.
            limit: Maximum number of results (1-50).

        Returns:
            A :class:`MarketSearchResult` with matching skills.
        """
        if not query or not query.strip():
            return MarketSearchResult(query=query, skills=[], total=0)

        limit = max(1, min(50, limit))
        url = f"{self._base_url}/search?q={_url_encode(query)}&limit={limit}"

        try:
            loop = asyncio.get_running_loop()
            data = await asyncio.wait_for(
                loop.run_in_executor(None, self._http_get_json, url),
                timeout=_HTTP_TIMEOUT + 5,
            )
        except asyncio.TimeoutError:
            logger.warning("Market search timed out for query %r", query)
            return MarketSearchResult(
                query=query, skills=[], total=0, error="timeout",
            )
        except Exception as exc:
            logger.warning("Market search failed: %s", exc)
            return MarketSearchResult(
                query=query, skills=[], total=0, error=str(exc),
            )

        skills = [self._parse_skill(item) for item in data.get("skills", [])]
        return MarketSearchResult(
            query=query,
            skills=skills,
            total=data.get("count", len(skills)),
        )

    async def get_skill_content(
        self, source: str, skill_id: str,
    ) -> str | None:
        """Fetch the full SKILL.md content for a specific skill.

        Args:
            source: The source identifier (e.g. "vercel-labs/agent-skills").
            skill_id: The skill ID.

        Returns:
            The SKILL.md content as a string, or None on failure.
        """
        url = f"{self._base_url}/skills/{_url_encode(source)}/{_url_encode(skill_id)}"

        try:
            loop = asyncio.get_running_loop()
            data = await asyncio.wait_for(
                loop.run_in_executor(None, self._http_get_json, url),
                timeout=_HTTP_TIMEOUT + 5,
            )
        except Exception as exc:
            logger.warning("Failed to fetch skill content: %s", exc)
            return None

        return data.get("content") or data.get("skill", {}).get("content")

    async def install_skill(
        self, skill: MarketSkill, content: str | None = None,
    ) -> Path | None:
        """Install a market skill to the local skills directory.

        Downloads the SKILL.md content and writes it to
        ``~/.claude/skills/<skill_id>/SKILL.md``.

        Args:
            skill: The market skill to install.
            content: Pre-fetched content. If None, will be fetched.

        Returns:
            The path to the installed SKILL.md, or None on failure.
        """
        if not content:
            content = skill.content or None
        if not content:
            content = await self.get_skill_content(skill.source, skill.id)

        if not content:
            logger.warning("No content available for skill %r", skill.id)
            return None

        safe_id = _sanitize_dir_name(skill.id)
        if not safe_id:
            safe_id = _sanitize_dir_name(skill.name) or "skill"

        skills_root = Path.home() / ".claude" / "skills"
        skill_dir = skills_root / safe_id
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_file = skill_dir / "SKILL.md"
        try:
            full_content = self._build_skill_content(skill, content)
            skill_file.write_text(full_content, encoding="utf-8")
            logger.info("Installed market skill %r to %s", skill.id, skill_file)
            return skill_file
        except OSError as exc:
            logger.error("Failed to write skill file %s: %s", skill_file, exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_skill_content(skill: MarketSkill, content: str) -> str:
        """Prepend YAML front-matter if not already present."""
        stripped = content.lstrip("\n")
        if stripped.startswith("---"):
            return content

        lines = [
            "---",
            f"name: {skill.name}",
        ]
        if skill.description:
            lines.append(f"description: {skill.description}")
        lines.append(f"source: {skill.source}")
        lines.extend(["---", "", content])
        return "\n".join(lines)

    @staticmethod
    def _http_get_json(url: str) -> dict:
        """Synchronous HTTP GET returning parsed JSON (run in executor)."""
        req = Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "Misaka/1.0",
        })
        try:
            with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                return json.loads(resp.read())
        except (URLError, json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"HTTP request failed: {exc}") from exc

    @staticmethod
    def _parse_skill(data: dict) -> MarketSkill:
        """Parse a skill dict from the API response."""
        return MarketSkill(
            id=data.get("id", ""),
            name=data.get("name") or data.get("id", ""),
            description=data.get("description", ""),
            source=data.get("source", ""),
            install_count=data.get("install_count", 0),
            relevance_score=data.get("relevance_score", 0.0),
            content=data.get("content", ""),
            refs=data.get("refs") or {},
        )


def _url_encode(s: str) -> str:
    """Minimal URL encoding for query parameters."""
    from urllib.parse import quote
    return quote(s, safe="")


def _sanitize_dir_name(name: str) -> str:
    """Sanitize a string for use as a directory name."""
    import re
    sanitized = name.lower().replace(" ", "-")
    sanitized = re.sub(r"[^a-z0-9\-]", "", sanitized)
    sanitized = re.sub(r"-{2,}", "-", sanitized)
    return sanitized.strip("-")
