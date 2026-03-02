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
from typing import TYPE_CHECKING

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
    preview: str  # first 200 chars of first user message
    user_message_count: int
    assistant_message_count: int
    created_at: str  # ISO format
    updated_at: str  # ISO format
    file_size: int  # bytes


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


def _extract_text_from_content(content) -> str:  # noqa: ANN001
    """Extract plain text from a Claude message ``content`` field.

    ``content`` can be:
    * A plain string.
    * A list of content blocks, each with ``type`` and ``text`` keys.
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


def _parse_jsonl_metadata(file_path: Path) -> ClaudeSessionInfo | None:
    """Single-pass parse of a JSONL session file for metadata extraction.

    Returns ``None`` if the file cannot be read or is above the size limit.
    """
    try:
        file_size = file_path.stat().st_size
    except OSError as exc:
        logger.warning("Cannot stat %s: %s", file_path, exc)
        return None

    if file_size > _MAX_FILE_SIZE:
        logger.info("Skipping %s: file size %d exceeds limit", file_path, file_size)
        return None

    session_id = file_path.stem  # UUID filename without .jsonl

    cwd = ""
    version = ""
    git_branch = ""
    preview = ""
    user_count = 0
    assistant_count = 0
    first_timestamp = ""
    last_timestamp = ""
    first_user_text = ""

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

                # Extract metadata from non-typed lines (cwd, version, etc.)
                if "cwd" in entry and not cwd:
                    cwd = entry["cwd"]
                if "version" in entry and not version:
                    version = str(entry["version"])
                if "gitBranch" in entry:
                    git_branch = entry["gitBranch"]

                entry_type = entry.get("type")
                timestamp = entry.get("timestamp", "")

                if timestamp:
                    if not first_timestamp:
                        first_timestamp = timestamp
                    last_timestamp = timestamp

                if entry_type == "user":
                    user_count += 1
                    msg = entry.get("message", {})
                    if isinstance(msg, dict) and user_count == 1:
                        first_user_text = _extract_text_from_content(
                            msg.get("content", "")
                        )
                elif entry_type == "assistant":
                    assistant_count += 1

    except OSError as exc:
        logger.warning("Error reading %s: %s", file_path, exc)
        return None

    preview = first_user_text[:200] if first_user_text else ""

    # Derive project info from parent directory name.
    encoded_project = file_path.parent.name
    project_path = _decode_project_path(encoded_project)
    project_name = Path(project_path).name if project_path else encoded_project

    # Fall back to file modification times when timestamps are absent.
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
        cwd=cwd,
        git_branch=git_branch,
        version=version,
        preview=preview,
        user_message_count=user_count,
        assistant_message_count=assistant_count,
        created_at=first_timestamp,
        updated_at=last_timestamp,
        file_size=file_size,
    )


def _parse_jsonl_messages(file_path: Path) -> list[dict]:
    """Parse all user/assistant messages from a JSONL session file.

    Returns a list of dicts with keys: ``role``, ``content`` (JSON string),
    ``timestamp``, and optionally ``token_usage`` (JSON string).
    """
    messages: list[tuple[int, dict]] = []

    try:
        file_size = file_path.stat().st_size
    except OSError as exc:
        logger.warning("Cannot stat %s: %s", file_path, exc)
        return messages

    if file_size > _MAX_FILE_SIZE:
        logger.info("Skipping %s: file size %d exceeds limit", file_path, file_size)
        return messages

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

                entry_type = entry.get("type")
                if entry_type not in ("user", "assistant"):
                    continue

                msg = entry.get("message", {})
                if not isinstance(msg, dict):
                    continue

                role = msg.get("role", entry_type)
                content = msg.get("content", "")
                timestamp = entry.get("timestamp", "")

                content_str = _normalise_content(content)

                result: dict = {
                    "role": role,
                    "content": content_str,
                    "timestamp": timestamp,
                }

                token_usage = _extract_token_usage(entry, msg)
                if token_usage is not None:
                    result["token_usage"] = token_usage

                messages.append((line_no, result))

    except OSError as exc:
        logger.warning("Error reading %s: %s", file_path, exc)

    messages.sort(key=lambda m: (m[1].get("timestamp", ""), m[0]))
    return [m[1] for m in messages]


def _normalise_content(content) -> str:  # noqa: ANN001
    """Normalize message content to a JSON string of blocks."""
    if isinstance(content, str):
        return json.dumps([{"type": "text", "text": content}])
    if isinstance(content, list):
        return json.dumps(content)
    return json.dumps([{"type": "text", "text": str(content)}])


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


def _make_title(project_name: str, preview: str) -> str:
    """Build a human-readable session title from the project name and preview.

    Takes the project name and the first few words of the first user message.
    """
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

class SessionImportService:
    """Discovers and imports Claude Code CLI sessions from disk."""

    def __init__(self, projects_dir: Path | None = None) -> None:
        self._projects_dir = projects_dir or _CLAUDE_PROJECTS_DIR

    # ----- Public API -----

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
        return _make_title(info.project_name, info.preview)

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

        # Duplicate check: O(1) lookup via indexed column.
        existing = db.get_session_by_sdk_id(session_id)
        if existing is not None:
            raise ValueError(
                f"Session {session_id} has already been imported "
                f"(Misaka session {existing.id})"
            )

        # Parse metadata and messages.
        info = _parse_jsonl_metadata(file_path)
        if info is None:
            raise ValueError(
                f"Failed to parse session metadata from {file_path}"
            )

        messages = _parse_jsonl_messages(file_path)

        # Build session title.
        title = _make_title(info.project_name, info.preview)

        # Create the session in the database.
        session = db.create_session(
            title=title,
            working_directory=info.cwd or info.project_path,
            mode="code",
        )

        # Store the CLI session UUID so we can detect duplicates later.
        db.update_sdk_session_id(session.id, session_id)

        # Insert all parsed messages in a single batch.
        db.add_messages_batch(
            session_id=session.id,
            messages=[
                {"role": m["role"], "content": m["content"], "token_usage": m.get("token_usage")}
                for m in messages
            ],
        )

        logger.info(
            "Imported session %s (%d messages) as Misaka session %s",
            session_id,
            len(messages),
            session.id,
        )
        return session

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
