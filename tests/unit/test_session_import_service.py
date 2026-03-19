"""
Tests for the CLI session import service.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from misaka.services.session import session_import_service as import_module
from misaka.services.session.session_import_service import (
    ClaudeSessionInfo,
    SessionImportService,
)


def _make_cli_session_file(projects_dir: Path, session_id: str) -> Path:
    # Use a Unix-style encoded project name to avoid Windows interpreting
    # "D:" as a drive letter in pathlib (which would escape tmp_path).
    project_dir = projects_dir / "Users-foo-projects-Misaka"
    project_dir.mkdir(parents=True, exist_ok=True)
    file_path = project_dir / f"{session_id}.jsonl"
    file_path.write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n')
    return file_path


def _make_session_info(session_id: str) -> ClaudeSessionInfo:
    return ClaudeSessionInfo(
        session_id=session_id,
        project_path="D:/code/Misaka",
        project_name="Misaka",
        cwd="D:/code/Misaka",
        git_branch="main",
        version="1.0.0",
        preview="hello",
        user_message_count=1,
        assistant_message_count=1,
        created_at="2026-03-18T00:00:00Z",
        updated_at="2026-03-18T00:01:00Z",
        file_size=128,
        slug="",
    )


class TestSessionImportService:
    def test_delete_cli_session_removes_jsonl_file(
        self,
        tmp_path: Path,
    ) -> None:
        session_id = "9df6e481-1fef-4cc9-a0d7-c1230e204c60"
        projects_dir = tmp_path / "projects"
        file_path = _make_cli_session_file(projects_dir, session_id)
        service = SessionImportService(projects_dir=projects_dir)

        service.delete_cli_session(session_id)

        assert file_path.exists() is False

    def test_delete_cli_session_raises_when_missing(
        self,
        tmp_path: Path,
    ) -> None:
        service = SessionImportService(projects_dir=tmp_path / "projects")

        with pytest.raises(FileNotFoundError, match="missing-session-id"):
            service.delete_cli_session("missing-session-id")

    def test_rolls_back_partial_import_when_message_insert_fails(
        self,
        db,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        session_id = "fa584e3d-4a59-4516-8bdf-f8efad7b376a"
        projects_dir = tmp_path / "projects"
        _make_cli_session_file(projects_dir, session_id)
        service = SessionImportService(projects_dir=projects_dir)

        monkeypatch.setattr(
            import_module,
            "_parse_jsonl_metadata",
            lambda _: _make_session_info(session_id),
        )
        monkeypatch.setattr(
            import_module,
            "_parse_jsonl_messages",
            lambda _: [{"role": "user", "content": '["hello"]', "token_usage": None}],
        )

        def _fail_add_messages(*args, **kwargs) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(db, "add_messages_batch", _fail_add_messages)

        with pytest.raises(RuntimeError, match="boom"):
            service.import_session(session_id, db)

        assert db.get_session_by_sdk_id(session_id) is None
        assert db.get_all_sessions() == []

    def test_reimports_stale_session_without_messages(
        self,
        db,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        session_id = "19709609-3f5b-40fc-b176-6630645629e4"
        projects_dir = tmp_path / "projects"
        _make_cli_session_file(projects_dir, session_id)
        service = SessionImportService(projects_dir=projects_dir)

        stale = db.create_session(
            title="Broken Import",
            working_directory="D:/code/Misaka",
            mode="agent",
        )
        db.update_sdk_session_id(stale.id, session_id)

        monkeypatch.setattr(
            import_module,
            "_parse_jsonl_metadata",
            lambda _: _make_session_info(session_id),
        )
        monkeypatch.setattr(
            import_module,
            "_parse_jsonl_messages",
            lambda _: [
                {"role": "user", "content": '[{"type":"text","text":"hello"}]'},
                {"role": "assistant", "content": '[{"type":"text","text":"world"}]'},
            ],
        )

        imported = service.import_session(session_id, db)
        messages, has_more = db.get_messages(imported.id, limit=10)

        assert imported.id != stale.id
        assert imported.sdk_session_id == session_id
        assert db.get_session(stale.id) is None
        assert [message.role for message in messages] == ["user", "assistant"]
        assert has_more is False
