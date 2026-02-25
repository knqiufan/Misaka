"""
Tests for the UpdateCheckService.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from misaka.services.update_check_service import (
    UpdateCheckResult,
    UpdateCheckService,
)


@pytest.fixture
def service() -> UpdateCheckService:
    return UpdateCheckService()


class TestCompareVersions:

    def test_newer_version(self) -> None:
        assert UpdateCheckService._compare_versions("1.0.25", "1.1.0") is True

    def test_same_version(self) -> None:
        assert UpdateCheckService._compare_versions("1.0.25", "1.0.25") is False

    def test_older_version(self) -> None:
        assert UpdateCheckService._compare_versions("1.1.0", "1.0.25") is False

    def test_major_version_bump(self) -> None:
        assert UpdateCheckService._compare_versions("1.9.9", "2.0.0") is True

    def test_minor_version_bump(self) -> None:
        assert UpdateCheckService._compare_versions("1.0.0", "1.1.0") is True

    def test_patch_version_bump(self) -> None:
        assert UpdateCheckService._compare_versions("1.0.0", "1.0.1") is True

    def test_invalid_current(self) -> None:
        assert UpdateCheckService._compare_versions("invalid", "1.0.0") is False

    def test_invalid_latest(self) -> None:
        assert UpdateCheckService._compare_versions("1.0.0", "invalid") is False

    def test_both_invalid(self) -> None:
        assert UpdateCheckService._compare_versions("bad", "also_bad") is False

    def test_large_version_numbers(self) -> None:
        assert UpdateCheckService._compare_versions("99.99.99", "100.0.0") is True


class TestUpdateCheckResult:

    def test_dataclass_fields(self) -> None:
        result = UpdateCheckResult(
            current_version="1.0.0",
            latest_version="1.1.0",
            update_available=True,
            checked_at="2026-01-01T00:00:00",
        )
        assert result.current_version == "1.0.0"
        assert result.latest_version == "1.1.0"
        assert result.update_available is True

    def test_no_update_available(self) -> None:
        result = UpdateCheckResult(
            current_version="1.1.0",
            latest_version="1.1.0",
            update_available=False,
            checked_at="2026-01-01T00:00:00",
        )
        assert result.update_available is False


class TestUpdateCheckService:

    async def test_check_for_update_available(self, service: UpdateCheckService) -> None:
        """check_for_update should detect when an update is available."""
        with patch.object(service, "_get_current_version", return_value="1.0.25"), \
             patch.object(service, "_get_latest_npm_version", return_value="1.1.0"):
            result = await service.check_for_update()
            assert result.update_available is True
            assert result.current_version == "1.0.25"
            assert result.latest_version == "1.1.0"

    async def test_check_for_update_not_available(self, service: UpdateCheckService) -> None:
        """check_for_update should detect when already up to date."""
        with patch.object(service, "_get_current_version", return_value="1.1.0"), \
             patch.object(service, "_get_latest_npm_version", return_value="1.1.0"):
            result = await service.check_for_update()
            assert result.update_available is False

    async def test_check_for_update_no_current(self, service: UpdateCheckService) -> None:
        """check_for_update should handle missing current version."""
        with patch.object(service, "_get_current_version", return_value=None), \
             patch.object(service, "_get_latest_npm_version", return_value="1.1.0"):
            result = await service.check_for_update()
            assert result.update_available is False
            assert result.current_version is None

    async def test_check_for_update_no_latest(self, service: UpdateCheckService) -> None:
        """check_for_update should handle missing latest version."""
        with patch.object(service, "_get_current_version", return_value="1.0.25"), \
             patch.object(service, "_get_latest_npm_version", return_value=None):
            result = await service.check_for_update()
            assert result.update_available is False
            assert result.latest_version is None

    async def test_check_for_update_has_timestamp(self, service: UpdateCheckService) -> None:
        """check_for_update result should have a valid checked_at timestamp."""
        with patch.object(service, "_get_current_version", return_value="1.0.0"), \
             patch.object(service, "_get_latest_npm_version", return_value="1.0.0"):
            result = await service.check_for_update()
            assert result.checked_at != ""
            assert "T" in result.checked_at  # ISO format

    async def test_http_get_version_success(self, service: UpdateCheckService) -> None:
        """_http_get_version should parse version from registry JSON."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"version": "1.2.3"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("misaka.services.update_check_service.urlopen", return_value=mock_response):
            version = service._http_get_version()
            assert version == "1.2.3"

    async def test_http_get_version_failure(self, service: UpdateCheckService) -> None:
        """_http_get_version should return None on network failure."""
        from urllib.error import URLError

        with patch("misaka.services.update_check_service.urlopen", side_effect=URLError("fail")):
            version = service._http_get_version()
            assert version is None

    async def test_http_get_version_invalid_json(self, service: UpdateCheckService) -> None:
        """_http_get_version should return None on invalid JSON."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"not json"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("misaka.services.update_check_service.urlopen", return_value=mock_response):
            version = service._http_get_version()
            assert version is None

    async def test_perform_update_success(self, service: UpdateCheckService) -> None:
        """perform_update should return True on successful update."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"updated\n", b"")
        mock_proc.returncode = 0

        progress_messages: list[str] = []

        with patch("shutil.which", return_value="/usr/bin/npm"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc), \
             patch("misaka.utils.platform.clear_claude_cache"):
            result = await service.perform_update(on_progress=progress_messages.append)
            assert result is True

    async def test_perform_update_no_npm(self, service: UpdateCheckService) -> None:
        """perform_update should return False when npm is not found."""
        progress_messages: list[str] = []

        with patch("shutil.which", return_value=None):
            result = await service.perform_update(on_progress=progress_messages.append)
            assert result is False
            assert any("npm not found" in m for m in progress_messages)

    async def test_perform_update_failure(self, service: UpdateCheckService) -> None:
        """perform_update should return False on update failure."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"error occurred\n")
        mock_proc.returncode = 1

        with patch("shutil.which", return_value="/usr/bin/npm"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await service.perform_update()
            assert result is False

    async def test_fetch_version_via_npm_cli_success(self, service: UpdateCheckService) -> None:
        """_fetch_version_via_npm_cli should parse version from npm output."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"1.2.3\n", b"")
        mock_proc.returncode = 0

        with patch("shutil.which", return_value="/usr/bin/npm"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            version = await service._fetch_version_via_npm_cli("@anthropic-ai/claude-code")
            assert version == "1.2.3"

    async def test_fetch_version_via_npm_cli_no_npm(self, service: UpdateCheckService) -> None:
        """_fetch_version_via_npm_cli should return None when npm is missing."""
        with patch("shutil.which", return_value=None):
            version = await service._fetch_version_via_npm_cli("@anthropic-ai/claude-code")
            assert version is None

    async def test_fetch_version_via_npm_cli_bad_output(self, service: UpdateCheckService) -> None:
        """_fetch_version_via_npm_cli should return None for non-version output."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"not a version string\n", b"")
        mock_proc.returncode = 0

        with patch("shutil.which", return_value="/usr/bin/npm"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            version = await service._fetch_version_via_npm_cli("@anthropic-ai/claude-code")
            assert version is None

    async def test_fetch_version_via_npm_cli_failure_exit(self, service: UpdateCheckService) -> None:
        """_fetch_version_via_npm_cli should return None on non-zero exit."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"error\n")
        mock_proc.returncode = 1

        with patch("shutil.which", return_value="/usr/bin/npm"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            version = await service._fetch_version_via_npm_cli("@anthropic-ai/claude-code")
            assert version is None

    async def test_perform_update_timeout(self, service: UpdateCheckService) -> None:
        """perform_update should return False on timeout."""
        mock_proc = AsyncMock()
        mock_proc.communicate.side_effect = asyncio.TimeoutError()

        progress_messages: list[str] = []

        with patch("shutil.which", return_value="/usr/bin/npm"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await service.perform_update(on_progress=progress_messages.append)
            assert result is False
            assert any("timed out" in m.lower() for m in progress_messages)

    async def test_perform_update_exception(self, service: UpdateCheckService) -> None:
        """perform_update should return False on unexpected exception."""
        progress_messages: list[str] = []

        with patch("shutil.which", return_value="/usr/bin/npm"), \
             patch("asyncio.create_subprocess_exec", side_effect=OSError("broken")):
            result = await service.perform_update(on_progress=progress_messages.append)
            assert result is False
            assert any("failed" in m.lower() for m in progress_messages)

    async def test_http_get_version_missing_version_key(self, service: UpdateCheckService) -> None:
        """_http_get_version should return None when JSON has no version key."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"name": "foo"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("misaka.services.update_check_service.urlopen", return_value=mock_response):
            version = service._http_get_version()
            assert version is None

    async def test_http_get_version_invalid_version_format(self, service: UpdateCheckService) -> None:
        """_http_get_version should return None when version doesn't match pattern."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"version": "not-a-version"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("misaka.services.update_check_service.urlopen", return_value=mock_response):
            version = service._http_get_version()
            assert version is None

    async def test_get_current_version_no_claude(self, service: UpdateCheckService) -> None:
        """_get_current_version should return None when claude CLI not found."""
        with patch("misaka.services.update_check_service.find_claude_binary", return_value=None, create=True), \
             patch.dict("sys.modules", {}):
            # Patch the import chain
            with patch.object(service, "_get_current_version", return_value=None):
                result = await service.check_for_update()
                assert result.current_version is None

    async def test_check_for_update_both_none(self, service: UpdateCheckService) -> None:
        """check_for_update should handle both versions being None."""
        with patch.object(service, "_get_current_version", return_value=None), \
             patch.object(service, "_get_latest_npm_version", return_value=None):
            result = await service.check_for_update()
            assert result.update_available is False
            assert result.current_version is None
            assert result.latest_version is None
