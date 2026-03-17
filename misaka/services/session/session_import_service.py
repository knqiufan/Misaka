"""
Session import service for Claude Code CLI sessions.

Scans ``~/.claude/projects/`` for JSONL session files produced by the
Claude Code CLI and imports them into the Misaka database.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.db.models import ChatSession

logger = logging.getLogger(__name__)

# Maximum JSONL file size we are willing to parse (50 MB).
_MAX_FILE_SIZE = 50 * 1024 * 1024

# Where the Claude Code CLI stores project sessions.
_CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Regex for UUID-style filenames (with or without .jsonl extension).
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


# ---------------------------------------------------------------------------
# Data class for session metadata
# ---------------------------------------------------------------------------

@dataclass
class ClaudeSessionInfo:
    """Metadata extracted from a single Claude Code CLI session file."""

    session_id: str
    project_path: str
    project_name: str
    cwd: str
    git_branch: str
    version: str
    preview: str  # first 200 chars of first non-meta user message
    user_message_count: int  # merged (displayed) count
    assistant_message_count: int  # merged (displayed) count
    created_at: str  # ISO format
    updated_at: str  # ISO format
    file_size: int  # bytes
    slug: str = ""  # session slug from JSONL, e.g. "drifting-frolicking-mccarthy"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_project_path(encoded: str) -> str:
    """Decode a Claude CLI encoded project directory name back to a path.

    The CLI encodes project paths by replacing ``/`` (or ``\\``) with ``-``.
    For example:

    * Unix:  ``Users-foo-projects-bar``  ->  ``/Users/foo/projects/bar``
    * Windows: ``D:-code-project``       ->  ``D:/code/project``

    On Windows a leading single letter followed by ``-`` is recognised as a
    drive letter (e.g. ``D:-...`` -> ``D:/...``).
    """
    # Windows drive-letter detection: e.g. "D:-code-project"
    if len(encoded) >= 2 and encoded[0].isalpha() and encoded[1] == "-":
        # Replace the first "-" with ":/" and subsequent ones with "/"
        drive = encoded[0]
        rest = encoded[2:]  # everything after "D-"
        path = drive + ":/" + rest.replace("-", "/")
        return path

    # Unix-style: prepend "/" and replace all "-" with "/"
    return "/" + encoded.replace("-", "/")


def _extract_text_from_content(content: Any) -> str:
    """Extract plain text from a Claude message ``content`` field.

    Per spec §5: only ``type: "text"`` blocks contribute to preview.
    ``content`` can be a plain string or a list of content blocks.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def _content_to_blocks(content: Any) -> list[dict]:
    """Convert content to a list of content blocks for merging.

    Per spec §5.5: ``thinking`` blocks are converted to ``text`` for display.
    """
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    if isinstance(content, list):
        result: list[dict] = []
        for b in content:
            if not isinstance(b, dict) or not b.get("type"):
                continue
            block = dict(b)
            # Convert thinking to text for display (spec §5.5)
            if block.get("type") == "thinking":
                thinking_text = block.get("thinking", "")
                result.append({"type": "text", "text": str(thinking_text)})
            else:
                result.append(block)
        return result
    return [{"type": "text", "text": str(content)}] if content else []


def _merge_content_blocks(blocks_list: list[list[dict]]) -> list[dict]:
    """Concatenate content block lists in order."""
    result: list[dict] = []
    for blocks in blocks_list:
        result.extend(blocks)
    return result


@dataclass
class _RawMessageEntry:
    """Internal: a single user/assistant JSONL entry before merging."""

    line_no: int
    role: str
    content: Any
    timestamp: str
    entry: dict
    message: dict
    is_meta: bool = False


def _collect_user_assistant_entries(
    file_path: Path,
) -> tuple[list[_RawMessageEntry], dict[str, Any]]:
    """Read JSONL and collect user/assistant entries plus metadata.

    Returns:
        (entries, meta) where meta has: cwd, version, git_branch, slug,
        first_timestamp, last_timestamp, file_size.
    """
    entries: list[_RawMessageEntry] = []
    meta: dict[str, Any] = {
        "cwd": "",
        "version": "",
        "git_branch": "",
        "slug": "",
        "first_timestamp": "",
        "last_timestamp": "",
        "file_size": 0,
    }

    try:
        file_size = file_path.stat().st_size
    except OSError as exc:
        logger.warning("Cannot stat %s: %s", file_path, exc)
        return (entries, meta)

    meta["file_size"] = file_size
    if file_size > _MAX_FILE_SIZE:
        return (entries, meta)

    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as fh:
            for line_no, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(entry, dict):
                    continue

                # Extract metadata from any line
                if "cwd" in entry and not meta["cwd"]:
                    meta["cwd"] = entry["cwd"]
                if "version" in entry and not meta["version"]:
                    meta["version"] = str(entry["version"])
                if "gitBranch" in entry:
                    meta["git_branch"] = entry["gitBranch"]
                if "slug" in entry and not meta["slug"]:
                    meta["slug"] = str(entry["slug"]).strip()

                entry_type = entry.get("type")
                timestamp = entry.get("timestamp", "")
                if timestamp:
                    if not meta["first_timestamp"]:
                        meta["first_timestamp"] = timestamp
                    meta["last_timestamp"] = timestamp

                if entry_type not in ("user", "assistant"):
                    continue

                msg = entry.get("message", {})
                if not isinstance(msg, dict):
                    continue

                role = msg.get("role", entry_type)
                content = msg.get("content", "")
                is_meta = entry.get("isMeta", False) is True

                entries.append(
                    _RawMessageEntry(
                        line_no=line_no,
                        role=role,
                        content=content,
                        timestamp=timestamp,
                        entry=entry,
                        message=msg,
                        is_meta=is_meta,
                    )
                )
    except OSError as exc:
        logger.warning("Error reading %s: %s", file_path, exc)

    # Sort by timestamp then line_no
    entries.sort(key=lambda e: (e.timestamp, e.line_no))
    return (entries, meta)


def _merge_consecutive_same_role(
    entries: list[_RawMessageEntry],
) -> list[dict]:
    """Merge adjacent entries of the same role into single messages.

    Returns list of dicts with: role, content (JSON str), timestamp,
    token_usage (optional).
    """
    if not entries:
        return []

    merged: list[dict] = []
    current_role: str | None = None
    current_blocks: list[list[dict]] = []
    msg_first_ts = ""
    last_token_usage: str | None = None

    def flush() -> None:
        nonlocal current_blocks, last_token_usage, msg_first_ts
        if not current_blocks or current_role is None:
            return
        all_blocks = _merge_content_blocks(current_blocks)
        content_str = json.dumps(all_blocks) if all_blocks else "[]"
        m: dict = {
            "role": current_role,
            "content": content_str,
            "timestamp": msg_first_ts,
        }
        if last_token_usage is not None:
            m["token_usage"] = last_token_usage
        merged.append(m)
        current_blocks = []
        last_token_usage = None
        msg_first_ts = ""

    for e in entries:
        if current_role is not None and e.role != current_role:
            flush()
            current_role = None

        current_role = e.role
        current_blocks.append(_content_to_blocks(e.content))
        if not msg_first_ts and e.timestamp:
            msg_first_ts = e.timestamp

        if e.role == "assistant":
            usage = _extract_token_usage(e.entry, e.message)
            if usage is not None:
                last_token_usage = usage

    flush()
    return merged


def _parse_jsonl_metadata(file_path: Path) -> ClaudeSessionInfo | None:
    """Single-pass parse of a JSONL session file for metadata extraction.

    Uses merged message counts (consecutive same-role entries count as one).
    Preview excludes isMeta user messages per spec §4.4.

    Returns ``None`` if the file cannot be read or is above the size limit.
    """
    entries, meta = _collect_user_assistant_entries(file_path)
    if meta["file_size"] > _MAX_FILE_SIZE:
        logger.info(
            "Skipping %s: file size %d exceeds limit",
            file_path,
            meta["file_size"],
        )
        return None

    merged = _merge_consecutive_same_role(entries)
    user_count = sum(1 for m in merged if m["role"] == "user")
    assistant_count = sum(1 for m in merged if m["role"] == "assistant")

    # Preview: first non-isMeta user message text (spec §4.4)
    first_user_text = ""
    for e in entries:
        if e.role == "user" and not e.is_meta:
            first_user_text = _extract_text_from_content(e.content)
            break
    preview = first_user_text[:200] if first_user_text else ""

    # Derive project info from parent directory name
    session_id = file_path.stem
    encoded_project = file_path.parent.name
    project_path = _decode_project_path(encoded_project)
    project_name = Path(project_path).name if project_path else encoded_project

    first_timestamp = meta["first_timestamp"]
    last_timestamp = meta["last_timestamp"]
    if not first_timestamp:
        try:
            stat = file_path.stat()
            first_timestamp = _timestamp_from_epoch(stat.st_ctime)
            last_timestamp = _timestamp_from_epoch(stat.st_mtime)
        except OSError:
            first_timestamp = ""
            last_timestamp = first_timestamp
    if not last_timestamp:
        last_timestamp = first_timestamp

    return ClaudeSessionInfo(
        session_id=session_id,
        project_path=project_path,
        project_name=project_name,
        cwd=meta["cwd"],
        git_branch=meta["git_branch"],
        version=meta["version"],
        preview=preview,
        user_message_count=user_count,
        assistant_message_count=assistant_count,
        created_at=first_timestamp,
        updated_at=last_timestamp,
        file_size=meta["file_size"],
        slug=meta["slug"],
    )


def _parse_jsonl_messages(file_path: Path) -> list[dict]:
    """Parse all user/assistant messages from a JSONL session file.

    Consecutive same-role entries are merged into a single message.
    Returns a list of dicts with keys: ``role``, ``content`` (JSON string),
    ``timestamp``, and optionally ``token_usage`` (JSON string).
    """
    entries, meta = _collect_user_assistant_entries(file_path)
    if meta["file_size"] > _MAX_FILE_SIZE:
        logger.info(
            "Skipping %s: file size %d exceeds limit",
            file_path,
            meta["file_size"],
        )
        return []

    return _merge_consecutive_same_role(entries)


def _extract_token_usage(entry: dict, message: dict) -> str | None:
    """Extract token/cost usage from JSONL entry/message payload."""
    usage: dict[str, object] = {}
    msg_usage = message.get("usage")
    if isinstance(msg_usage, dict):
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            if key in msg_usage:
                usage[key] = msg_usage[key]
    cost_usd = entry.get("costUSD")
    if cost_usd is not None:
        usage["cost_usd"] = cost_usd
    if not usage:
        return None
    return json.dumps(usage)


def _timestamp_from_epoch(epoch: float) -> str:
    """Convert an epoch timestamp to an ISO-format string."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _make_title(
    project_name: str,
    preview: str,
    slug: str = "",
) -> str:
    """Build a human-readable session title.

    Per spec: prefers slug when available; otherwise project_name + preview.
    """
    if slug and slug.strip():
        return slug.strip()
    if not preview:
        return project_name or "Imported Session"
    words = preview.split()[:8]
    snippet = " ".join(words)
    if len(words) < len(preview.split()):
        snippet += "..."
    if project_name:
        return f"{project_name}: {snippet}"
    return snippet


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

def _matches_query(info: ClaudeSessionInfo, query: str) -> bool:
    """Check if session info matches the search query."""
    q = query.lower()
    fields = [
        info.project_name or "",
        info.preview or "",
        info.cwd or "",
        info.git_branch or "",
        info.project_path or "",
    ]
    return any(q in (f or "").lower() for f in fields)


class SessionImportService:
    """Discovers and imports Claude Code CLI sessions from disk."""

    def __init__(self, projects_dir: Path | None = None) -> None:
        self._projects_dir = projects_dir or _CLAUDE_PROJECTS_DIR

    # ----- Public API -----

    def list_cli_session_paths(self) -> list[tuple[Path, float]]:
        """List all CLI session JSONL paths with mtime, sorted by mtime desc.

        Returns:
            List of (path, mtime) tuples. Does not parse file contents.
        """
        result: list[tuple[Path, float]] = []

        if not self._projects_dir.is_dir():
            return result

        try:
            project_dirs = [
                p for p in self._projects_dir.iterdir() if p.is_dir()
            ]
        except OSError as exc:
            logger.warning("Cannot list %s: %s", self._projects_dir, exc)
            return result

        for project_dir in project_dirs:
            try:
                for jsonl_file in project_dir.glob("*.jsonl"):
                    if not _UUID_RE.match(jsonl_file.stem):
                        continue
                    try:
                        mtime = jsonl_file.stat().st_mtime
                        result.append((jsonl_file, mtime))
                    except OSError:
                        continue
            except OSError as exc:
                logger.warning("Cannot list %s: %s", project_dir, exc)

        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def parse_session_metadata(self, path: Path) -> ClaudeSessionInfo | None:
        """Parse metadata from a single session JSONL file."""
        return _parse_jsonl_metadata(path)

    def list_cli_sessions_paginated(
        self,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> tuple[list[ClaudeSessionInfo], int]:
        """Return a page of CLI sessions with optional search filter.

        Args:
            limit: Max number of sessions to return.
            offset: Number of sessions to skip.
            query: Optional search string to filter by project_name, preview,
                cwd, git_branch, project_path.

        Returns:
            (sessions, total_count). When query is set, total_count is the
            count of matching sessions (requires parsing all files).
        """
        paths_with_mtime = self.list_cli_session_paths()

        if query and query.strip():
            q = query.strip()
            all_infos: list[ClaudeSessionInfo] = []
            for path, _ in paths_with_mtime:
                info = self.parse_session_metadata(path)
                if info is not None and _matches_query(info, q):
                    all_infos.append(info)
            total = len(all_infos)
            page = all_infos[offset : offset + limit]
            return (page, total)
        else:
            total = len(paths_with_mtime)
            page_paths = paths_with_mtime[offset : offset + limit]
            infos: list[ClaudeSessionInfo] = []
            for path, _ in page_paths:
                info = self.parse_session_metadata(path)
                if info is not None:
                    infos.append(info)
            return (infos, total)

    def list_cli_sessions(self) -> list[ClaudeSessionInfo]:
        """Scan ``~/.claude/projects/`` for JSONL session files.

        Returns a list of :class:`ClaudeSessionInfo` sorted by
        ``updated_at`` descending (newest first).
        """
        sessions: list[ClaudeSessionInfo] = []

        if not self._projects_dir.is_dir():
            logger.info(
                "Claude projects directory does not exist: %s", self._projects_dir
            )
            return sessions

        try:
            project_dirs = [
                p for p in self._projects_dir.iterdir() if p.is_dir()
            ]
        except OSError as exc:
            logger.warning("Cannot list %s: %s", self._projects_dir, exc)
            return sessions

        for project_dir in project_dirs:
            try:
                jsonl_files = list(project_dir.glob("*.jsonl"))
            except OSError as exc:
                logger.warning("Cannot list %s: %s", project_dir, exc)
                continue

            for jsonl_file in jsonl_files:
                # Only consider UUID-named files.
                if not _UUID_RE.match(jsonl_file.stem):
                    continue

                info = _parse_jsonl_metadata(jsonl_file)
                if info is not None:
                    sessions.append(info)

        # Sort by updated_at descending (newest first).
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        logger.info("Found %d CLI sessions in %s", len(sessions), self._projects_dir)
        return sessions

    def get_session_title(self, session_id: str) -> str | None:
        """Read a live CLI session title from JSONL metadata/summary."""
        file_path = self._find_session_file(session_id)
        if file_path is None:
            return None

        summary_title = self._read_summary_title(file_path)
        if summary_title:
            return summary_title

        info = _parse_jsonl_metadata(file_path)
        if info is None:
            return None
        return _make_title(info.project_name, info.preview, info.slug)

    def _ensure_session_can_be_imported(
        self,
        session_id: str,
        db: DatabaseBackend,
        expected_message_count: int,
    ) -> None:
        """Reject duplicates unless the existing import is a stale partial record."""
        existing = db.get_session_by_sdk_id(session_id)
        if existing is None:
            return
        if self._is_stale_partial_import(db, existing.id, expected_message_count):
            logger.warning(
                "Removing stale imported session %s for CLI session %s",
                existing.id,
                session_id,
            )
            if not db.delete_session(existing.id):
                raise ValueError(
                    f"Session {session_id} has already been imported "
                    f"(Misaka session {existing.id})"
                )
            return
        raise ValueError(
            f"Session {session_id} has already been imported "
            f"(Misaka session {existing.id})"
        )

    @staticmethod
    def _is_stale_partial_import(
        db: DatabaseBackend,
        misaka_session_id: str,
        expected_message_count: int,
    ) -> bool:
        """Detect a previously interrupted import that left no messages behind."""
        if expected_message_count <= 0:
            return False
        messages, _ = db.get_messages(misaka_session_id, limit=1)
        return len(messages) == 0

    @staticmethod
    def _load_import_payload(file_path: Path) -> tuple[ClaudeSessionInfo, list[dict]]:
        """Parse the metadata and message payload required for import."""
        info = _parse_jsonl_metadata(file_path)
        if info is None:
            raise ValueError(
                f"Failed to parse session metadata from {file_path}"
            )
        messages = _parse_jsonl_messages(file_path)
        return (info, messages)

    @staticmethod
    def _rollback_failed_import(
        db: DatabaseBackend,
        session_id: str,
        cli_session_id: str,
    ) -> None:
        """Remove a partially created session after an import failure."""
        try:
            deleted = db.delete_session(session_id)
        except Exception:
            logger.exception(
                "Failed to roll back partial import for CLI session %s "
                "(Misaka session %s)",
                cli_session_id,
                session_id,
            )
            return
        if deleted:
            logger.warning(
                "Rolled back partial import for CLI session %s "
                "(Misaka session %s)",
                cli_session_id,
                session_id,
            )

    @staticmethod
    def _create_imported_session(
        db: DatabaseBackend,
        session_id: str,
        info: ClaudeSessionInfo,
        title: str,
        messages: list[dict],
    ) -> ChatSession:
        """Persist the imported session and roll back if any step fails."""
        session = db.create_session(
            title=title,
            working_directory=info.cwd or info.project_path,
            mode="agent",
        )
        try:
            db.update_sdk_session_id(session.id, session_id)
            db.add_messages_batch(
                session_id=session.id,
                messages=[
                    {
                        "role": message["role"],
                        "content": message["content"],
                        "token_usage": message.get("token_usage"),
                    }
                    for message in messages
                ],
            )
        except Exception:
            SessionImportService._rollback_failed_import(db, session.id, session_id)
            raise
        session.sdk_session_id = session_id
        return session

    def import_session(self, session_id: str, db: DatabaseBackend) -> ChatSession:
        """Import a Claude Code CLI session into the Misaka database.

        Args:
            session_id: The UUID of the CLI session (filename stem).
            db: A :class:`~misaka.db.database.DatabaseBackend` instance.

        Returns:
            The newly created :class:`~misaka.db.models.ChatSession`.

        Raises:
            FileNotFoundError: If the session JSONL file cannot be located.
            ValueError: If a session with the same ``sdk_session_id`` already
                exists in the database.
        """
        # Locate the JSONL file.
        file_path = self._find_session_file(session_id)
        if file_path is None:
            raise FileNotFoundError(
                f"Cannot find JSONL file for session {session_id}"
            )

        info, messages = self._load_import_payload(file_path)
        self._ensure_session_can_be_imported(
            session_id=session_id,
            db=db,
            expected_message_count=len(messages),
        )
        title = _make_title(info.project_name, info.preview, info.slug)
        session = self._create_imported_session(
            db=db,
            session_id=session_id,
            info=info,
            title=title,
            messages=messages,
        )

        logger.info(
            "Imported session %s (%d messages) as Misaka session %s",
            session_id,
            len(messages),
            session.id,
        )
        return session

    def delete_cli_session(self, session_id: str) -> None:
        """Delete a Claude CLI session JSONL file from disk."""
        file_path = self._find_session_file(session_id)
        if file_path is None:
            raise FileNotFoundError(
                f"Cannot find JSONL file for session {session_id}"
            )
        try:
            file_path.unlink()
        except OSError as exc:
            raise ValueError(
                f"Failed to delete CLI session {session_id}: {exc}"
            ) from exc
        logger.info("Deleted CLI session file for %s", session_id)

    # ----- Internals -----

    def _find_session_file(self, session_id: str) -> Path | None:
        """Locate the JSONL file for *session_id* within the projects dir."""
        if not self._projects_dir.is_dir():
            return None

        try:
            for project_dir in self._projects_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                candidate = project_dir / f"{session_id}.jsonl"
                if candidate.is_file():
                    return candidate
        except OSError as exc:
            logger.warning("Error searching for session %s: %s", session_id, exc)

        return None

    @staticmethod
    def _read_summary_title(file_path: Path) -> str | None:
        """Read the latest title-like summary entry from a JSONL transcript."""
        latest_summary: str | None = None
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("type") != "summary":
                        continue
                    summary = str(entry.get("summary", "")).strip()
                    if summary:
                        latest_summary = summary
        except OSError:
            return None
        return latest_summary
