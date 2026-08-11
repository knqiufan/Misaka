"""Search skills.sh and install skills with its official CLI."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from misaka.config import get_expanded_path
from misaka.utils.platform import (
    build_background_subprocess_kwargs,
    wrap_windows_script_command,
)

logger = logging.getLogger(__name__)

_SKILLS_API_BASE_URL = "https://skills.sh/api"
_HTTP_TIMEOUT = 15
_INSTALL_TIMEOUT = 300
_SAFE_SOURCE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$"
)
_SAFE_SKILL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass
class MarketSkill:
    """A skill entry returned by the online directory."""

    id: str
    name: str
    description: str
    source: str
    install_count: int = 0
    relevance_score: float = 0.0
    content: str = ""
    refs: dict[str, str] = field(default_factory=dict)


@dataclass
class MarketSearchResult:
    """Result of a skills.sh search query."""

    query: str
    skills: list[MarketSkill]
    total: int = 0
    error: str | None = None


@dataclass(frozen=True)
class SkillInstallResult:
    """Result of a non-interactive skills CLI installation."""

    skill_name: str
    success: bool
    message: str
    command: tuple[str, ...] = ()
    returncode: int | None = None


class SkillMarketService:
    """Search skills.sh and install complete skill packages for Claude Code."""

    def __init__(self, base_url: str = _SKILLS_API_BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")

    async def search(self, query: str, limit: int = 20) -> MarketSearchResult:
        """Search the skills.sh directory."""
        normalized_query = query.strip()
        if len(normalized_query) < 2:
            return MarketSearchResult(query=query, skills=[], total=0)

        limit = max(1, min(50, limit))
        url = f"{self._base_url}/search?{urlencode({'q': normalized_query})}"
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(self._http_get_json, url),
                timeout=_HTTP_TIMEOUT + 5,
            )
        except asyncio.TimeoutError:
            logger.warning("Skill market search timed out for %r", query)
            return MarketSearchResult(query=query, skills=[], error="timeout")
        except Exception as exc:
            logger.warning("Skill market search failed: %s", exc)
            return MarketSearchResult(query=query, skills=[], error=str(exc))

        raw_skills = data.get("skills") or []
        skills = [
            self._parse_skill(item)
            for item in raw_skills[:limit]
            if isinstance(item, dict)
        ]
        total = data.get("count", len(raw_skills))
        return MarketSearchResult(
            query=normalized_query,
            skills=skills,
            total=total if isinstance(total, int) else len(skills),
        )

    async def get_skill_content(self, source: str, skill_id: str) -> str | None:
        """Return content only when the directory supplies a direct raw URL.

        skills.sh intentionally delegates package resolution to its CLI. Most search
        responses do not expose raw content, so preview absence must not block install.
        """
        del source, skill_id
        return None

    async def install_skill(self, skill: MarketSkill) -> SkillInstallResult:
        """Install a complete skill package globally for Claude Code."""
        if not _SAFE_SOURCE_RE.fullmatch(skill.source) or not _SAFE_SKILL_ID_RE.fullmatch(
            skill.id
        ):
            return SkillInstallResult(
                skill.name,
                False,
                "The marketplace entry has an invalid repository or skill ID.",
            )

        expanded_path = get_expanded_path()
        npx_path = shutil.which("npx", path=expanded_path)
        if not npx_path:
            message = "npx was not found. Install Node.js or install this skill manually."
            return SkillInstallResult(skill.name, False, message)

        command = wrap_windows_script_command(
            npx_path,
            [
                "-y",
                "skills",
                "add",
                skill.source,
                "--skill",
                skill.id,
                "-g",
                "-a",
                "claude-code",
                "-y",
            ],
        )
        env = os.environ.copy()
        env["PATH"] = expanded_path
        env.setdefault("CI", "1")

        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                **build_background_subprocess_kwargs(),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=_INSTALL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
                raise
        except asyncio.TimeoutError:
            return SkillInstallResult(
                skill.name,
                False,
                "Skill installation timed out",
                tuple(command),
            )
        except Exception as exc:
            logger.warning("Skill installation failed: %s", exc)
            return SkillInstallResult(
                skill.name,
                False,
                f"Failed to start the skills installer: {exc}",
                tuple(command),
            )

        if proc.returncode != 0:
            detail = (stderr or stdout).decode(errors="replace").strip()
            detail = detail[-2000:] if detail else "Unknown installer error"
            logger.warning("Skill installation failed (rc=%s): %s", proc.returncode, detail)
            return SkillInstallResult(
                skill.name,
                False,
                detail,
                tuple(command),
                proc.returncode,
            )

        return SkillInstallResult(
            skill.name,
            True,
            f"{skill.name} installed successfully",
            tuple(command),
            proc.returncode,
        )

    @staticmethod
    def _http_get_json(url: str) -> dict:
        request = Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "Misaka/1.0"},
        )
        try:
            with urlopen(request, timeout=_HTTP_TIMEOUT) as response:
                data = json.loads(response.read())
        except (URLError, json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"HTTP request failed: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError("skills.sh returned an invalid response")
        return data

    @staticmethod
    def _parse_skill(data: dict) -> MarketSkill:
        source = str(data.get("source") or "")
        skill_id = str(data.get("skillId") or data.get("id") or "")
        full_id = str(data.get("id") or "")
        refs = dict(data["refs"]) if isinstance(data.get("refs"), dict) else {}
        if source and skill_id:
            refs.setdefault(
                "skills.sh",
                f"https://skills.sh/{quote(source, safe='/')}/{quote(skill_id, safe='')}",
            )
        if source.count("/") == 1:
            refs.setdefault("github", f"https://github.com/{source}")
        return MarketSkill(
            id=skill_id,
            name=str(data.get("name") or data.get("title") or skill_id or full_id),
            description=str(data.get("description") or ""),
            source=source,
            install_count=int(data.get("installs") or data.get("install_count") or 0),
            relevance_score=float(data.get("relevance_score") or 0.0),
            content=str(data.get("content") or data.get("raw_content") or ""),
            refs={str(key): str(value) for key, value in refs.items() if value},
        )


def _url_encode(value: str) -> str:
    """Compatibility helper retained for callers and unit tests."""
    return quote(value, safe="")


def _sanitize_dir_name(name: str) -> str:
    """Compatibility helper for existing local package naming tests."""
    sanitized = name.lower().replace(" ", "-")
    sanitized = re.sub(r"[^a-z0-9\-]", "", sanitized)
    sanitized = re.sub(r"-{2,}", "-", sanitized)
    return sanitized.strip("-")
