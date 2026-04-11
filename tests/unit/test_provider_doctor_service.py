"""
Tests for the ProviderDoctorService.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from misaka.db.database import DatabaseBackend
from misaka.services.doctor.provider_doctor_service import (
    DoctorReport,
    ProbeResult,
    ProviderDoctorService,
    Severity,
)


@pytest.fixture
def service(db: DatabaseBackend) -> ProviderDoctorService:
    return ProviderDoctorService(db)


class TestSeverityEnum:
    def test_values(self) -> None:
        assert Severity.OK.value == "ok"
        assert Severity.WARNING.value == "warning"
        assert Severity.ERROR.value == "error"


class TestProbeResult:
    def test_defaults(self) -> None:
        result = ProbeResult(
            probe_id="test",
            title="Test",
            severity=Severity.OK,
            message="ok",
        )
        assert result.suggestion == ""

    def test_with_suggestion(self) -> None:
        result = ProbeResult(
            probe_id="test",
            title="Test",
            severity=Severity.ERROR,
            message="fail",
            suggestion="fix it",
        )
        assert result.suggestion == "fix it"


class TestDoctorReport:
    def test_all_ok(self) -> None:
        report = DoctorReport(
            probes=[
                ProbeResult("a", "A", Severity.OK, "ok"),
                ProbeResult("b", "B", Severity.OK, "ok"),
            ],
            checked_at="2026-01-01T00:00:00",
        )
        assert report.all_ok is True
        assert report.has_errors is False
        assert report.has_warnings is False
        assert report.error_count == 0
        assert report.warning_count == 0

    def test_with_error(self) -> None:
        report = DoctorReport(
            probes=[
                ProbeResult("a", "A", Severity.OK, "ok"),
                ProbeResult("b", "B", Severity.ERROR, "fail"),
            ],
        )
        assert report.all_ok is False
        assert report.has_errors is True
        assert report.error_count == 1

    def test_with_warning(self) -> None:
        report = DoctorReport(
            probes=[
                ProbeResult("a", "A", Severity.WARNING, "warn"),
                ProbeResult("b", "B", Severity.OK, "ok"),
            ],
        )
        assert report.all_ok is False
        assert report.has_warnings is True
        assert report.warning_count == 1

    def test_mixed(self) -> None:
        report = DoctorReport(
            probes=[
                ProbeResult("a", "A", Severity.OK, "ok"),
                ProbeResult("b", "B", Severity.WARNING, "warn"),
                ProbeResult("c", "C", Severity.ERROR, "fail"),
            ],
        )
        assert report.error_count == 1
        assert report.warning_count == 1
        assert report.all_ok is False


class TestProbeCliExistence:
    def test_cli_found(self, service: ProviderDoctorService) -> None:
        with patch(
            "misaka.services.doctor.provider_doctor_service.find_claude_binary",
            return_value="/usr/bin/claude",
        ):
            result = service._probe_cli_existence()
            assert result.severity == Severity.OK
            assert result.probe_id == "cli_existence"
            assert "/usr/bin/claude" in result.message

    def test_cli_not_found(self, service: ProviderDoctorService) -> None:
        with patch(
            "misaka.services.doctor.provider_doctor_service.find_claude_binary",
            return_value=None,
        ):
            result = service._probe_cli_existence()
            assert result.severity == Severity.ERROR
            assert result.suggestion == "cli_install_suggestion"

    def test_cli_os_error(self, service: ProviderDoctorService) -> None:
        with patch(
            "misaka.services.doctor.provider_doctor_service.find_claude_binary",
            side_effect=OSError("boom"),
        ):
            result = service._probe_cli_existence()
            assert result.severity == Severity.ERROR


class TestProbeApiKey:
    def test_valid_anthropic_key(self, db: DatabaseBackend) -> None:
        config_json = json.dumps(
            {"env": {"ANTHROPIC_AUTH_TOKEN": "sk-ant-abcdefghij1234567890-extra"}}
        )
        db.create_router_config(
            name="Test",
            config_json=config_json,
            is_active=1,
        )
        svc = ProviderDoctorService(db)
        result = svc._probe_api_key()
        assert result.severity == Severity.OK
        assert "sk-ant-abc" in result.message
        assert result.message.endswith("...")  is False  # has trailing chars

    def test_no_active_config(self, service: ProviderDoctorService) -> None:
        result = service._probe_api_key()
        assert result.severity == Severity.WARNING
        assert result.message == "no_active_config"

    def test_no_key_configured(self, db: DatabaseBackend) -> None:
        db.create_router_config(
            name="Empty",
            config_json="{}",
            is_active=1,
        )
        svc = ProviderDoctorService(db)
        result = svc._probe_api_key()
        assert result.severity == Severity.ERROR
        assert result.message == "no_key_configured"

    def test_non_standard_key(self, db: DatabaseBackend) -> None:
        config_json = json.dumps(
            {"env": {"ANTHROPIC_AUTH_TOKEN": "some-custom-proxy-key"}}
        )
        db.create_router_config(
            name="Proxy",
            config_json=config_json,
            is_active=1,
        )
        svc = ProviderDoctorService(db)
        result = svc._probe_api_key()
        assert result.severity == Severity.WARNING
        assert result.message == "non_standard_format"

    def test_fallback_to_api_key_field(self, db: DatabaseBackend) -> None:
        db.create_router_config(
            name="Legacy",
            config_json="{}",
            api_key="sk-ant-abcdefghij1234567890-extra",
            is_active=1,
        )
        svc = ProviderDoctorService(db)
        result = svc._probe_api_key()
        assert result.severity == Severity.OK


class TestProbeEnvVars:
    def test_no_active_config(self, service: ProviderDoctorService) -> None:
        result = service._probe_env_vars()
        assert result.severity == Severity.WARNING
        assert result.message == "no_active_config"

    def test_invalid_config_json(self, db: DatabaseBackend) -> None:
        db.create_router_config(
            name="Bad",
            config_json="not-json",
            is_active=1,
        )
        svc = ProviderDoctorService(db)
        result = svc._probe_env_vars()
        assert result.severity == Severity.ERROR
        assert result.message == "invalid_config_json"

    def test_all_vars_set(self, db: DatabaseBackend) -> None:
        config_json = json.dumps(
            {"env": {"ANTHROPIC_AUTH_TOKEN": "sk-ant-test1234567890123456-x"}}
        )
        db.create_router_config(
            name="Good",
            config_json=config_json,
            is_active=1,
        )
        svc = ProviderDoctorService(db)
        result = svc._probe_env_vars()
        assert result.severity == Severity.OK
        assert result.message == "all_set"

    def test_invalid_base_url(self, db: DatabaseBackend) -> None:
        config_json = json.dumps(
            {
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "sk-test",
                    "ANTHROPIC_BASE_URL": "ftp://bad",
                }
            }
        )
        db.create_router_config(
            name="BadUrl",
            config_json=config_json,
            is_active=1,
        )
        svc = ProviderDoctorService(db)
        result = svc._probe_env_vars()
        assert result.severity == Severity.WARNING
        assert "invalid_base_url" in result.message

    def test_no_auth_token_warning(self, db: DatabaseBackend) -> None:
        config_json = json.dumps({"env": {"ANTHROPIC_BASE_URL": "https://api.example.com"}})
        db.create_router_config(
            name="NoToken",
            config_json=config_json,
            is_active=1,
        )
        svc = ProviderDoctorService(db)
        result = svc._probe_env_vars()
        assert result.severity == Severity.WARNING
        assert "no_auth_token" in result.message


class TestProbeCliSettings:
    def test_settings_file_exists(
        self, service: ProviderDoctorService, tmp_path: Path
    ) -> None:
        settings_file = tmp_path / "settings.json"
        settings_file.write_text('{"env": {}}', encoding="utf-8")

        with patch(
            "misaka.services.doctor.provider_doctor_service.Path.home",
            return_value=tmp_path,
        ):
            (tmp_path / ".claude").mkdir(exist_ok=True)
            (tmp_path / ".claude" / "settings.json").write_text(
                '{"env": {}}', encoding="utf-8"
            )
            result = service._probe_cli_settings()
            assert result.severity == Severity.OK

    def test_settings_file_not_found(
        self, service: ProviderDoctorService, tmp_path: Path
    ) -> None:
        with patch(
            "misaka.services.doctor.provider_doctor_service.Path.home",
            return_value=tmp_path,
        ):
            result = service._probe_cli_settings()
            assert result.severity == Severity.WARNING
            assert result.message == "file_not_found"

    def test_settings_invalid_json(
        self, service: ProviderDoctorService, tmp_path: Path
    ) -> None:
        with patch(
            "misaka.services.doctor.provider_doctor_service.Path.home",
            return_value=tmp_path,
        ):
            claude_dir = tmp_path / ".claude"
            claude_dir.mkdir(exist_ok=True)
            (claude_dir / "settings.json").write_text("not json", encoding="utf-8")
            result = service._probe_cli_settings()
            assert result.severity == Severity.ERROR
            assert result.message == "invalid_json"


class TestProbeNodejs:
    def test_node_found(self, service: ProviderDoctorService) -> None:
        with patch("shutil.which", return_value="/usr/bin/node"):
            result = service._probe_nodejs()
            assert result.severity == Severity.OK
            assert "/usr/bin/node" in result.message

    def test_node_not_found(self, service: ProviderDoctorService) -> None:
        with patch("shutil.which", return_value=None):
            result = service._probe_nodejs()
            assert result.severity == Severity.ERROR
            assert result.suggestion == "nodejs_install_suggestion"


class TestRunAll:
    async def test_returns_five_probes(self, service: ProviderDoctorService) -> None:
        with patch(
            "misaka.services.doctor.provider_doctor_service.find_claude_binary",
            return_value="/usr/bin/claude",
        ), patch("shutil.which", return_value="/usr/bin/node"), patch(
            "misaka.services.doctor.provider_doctor_service.Path.home",
            return_value=Path("/tmp/nonexistent"),
        ):
            report = await service.run_all()
            assert len(report.probes) == 5
            assert report.checked_at != ""
            assert any(p.probe_id == "cli_existence" for p in report.probes)
            assert any(p.probe_id == "api_key" for p in report.probes)
            assert any(p.probe_id == "env_vars" for p in report.probes)
            assert any(p.probe_id == "cli_settings" for p in report.probes)
            assert any(p.probe_id == "nodejs" for p in report.probes)

    async def test_all_ok_when_everything_configured(
        self, db: DatabaseBackend, tmp_path: Path
    ) -> None:
        config_json = json.dumps(
            {"env": {"ANTHROPIC_AUTH_TOKEN": "sk-ant-abcdefghij1234567890-extra"}}
        )
        db.create_router_config(
            name="Full",
            config_json=config_json,
            is_active=1,
        )

        with patch(
            "misaka.services.doctor.provider_doctor_service.find_claude_binary",
            return_value="/usr/bin/claude",
        ), patch("shutil.which", return_value="/usr/bin/node"), patch(
            "misaka.services.doctor.provider_doctor_service.Path.home",
            return_value=tmp_path,
        ):
            claude_dir = tmp_path / ".claude"
            claude_dir.mkdir(exist_ok=True)
            (claude_dir / "settings.json").write_text("{}", encoding="utf-8")

            svc = ProviderDoctorService(db)
            report = await svc.run_all()
            assert report.all_ok is True
            assert report.error_count == 0
            assert report.warning_count == 0


class TestExtractApiKey:
    def test_from_env_auth_token(self) -> None:
        config = json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": "key123"}})
        assert ProviderDoctorService._extract_api_key(config, "") == "key123"

    def test_from_env_api_key(self) -> None:
        config = json.dumps({"env": {"ANTHROPIC_API_KEY": "key456"}})
        assert ProviderDoctorService._extract_api_key(config, "") == "key456"

    def test_fallback_key(self) -> None:
        assert ProviderDoctorService._extract_api_key("{}", "fallback") == "fallback"

    def test_invalid_json_uses_fallback(self) -> None:
        assert ProviderDoctorService._extract_api_key("bad", "fb") == "fb"

    def test_empty_returns_empty(self) -> None:
        assert ProviderDoctorService._extract_api_key("{}", "") == ""
