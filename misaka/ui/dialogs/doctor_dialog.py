"""Provider Doctor diagnostic dialog.

Renders structured diagnostic probe results as the content of
a Flet AlertDialog, with severity-graded rows and fix suggestions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.services.doctor.provider_doctor_service import DoctorReport, Severity
from misaka.ui.common.theme import (
    ERROR_RED,
    RADIUS_MD,
    SUCCESS_GREEN,
    WARNING_AMBER,
    make_button,
    make_outlined_button,
)

if TYPE_CHECKING:
    from collections.abc import Callable


_SEVERITY_COLORS: dict[Severity, str] = {
    Severity.OK: SUCCESS_GREEN,
    Severity.WARNING: WARNING_AMBER,
    Severity.ERROR: ERROR_RED,
}

_SEVERITY_ICONS: dict[Severity, str] = {
    Severity.OK: ft.Icons.CHECK_CIRCLE,
    Severity.WARNING: ft.Icons.WARNING_AMBER_ROUNDED,
    Severity.ERROR: ft.Icons.ERROR,
}

_PROBE_TITLE_KEYS: dict[str, str] = {
    "cli_existence": "doctor.probe_cli_existence",
    "api_key": "doctor.probe_api_key",
    "env_vars": "doctor.probe_env_vars",
    "cli_settings": "doctor.probe_cli_settings",
    "nodejs": "doctor.probe_nodejs",
}

_MESSAGE_KEYS: dict[str, str] = {
    "not_found": "doctor.msg_not_found",
    "no_active_config": "doctor.msg_no_active_config",
    "no_key_configured": "doctor.msg_no_key_configured",
    "non_standard_format": "doctor.msg_non_standard_format",
    "all_set": "doctor.msg_all_set",
    "no_auth_token": "doctor.msg_no_auth_token",
    "invalid_base_url": "doctor.msg_invalid_base_url",
    "invalid_config_json": "doctor.msg_invalid_config_json",
    "file_not_found": "doctor.msg_file_not_found",
    "invalid_json": "doctor.msg_invalid_json",
}

_SUGGESTION_KEYS: dict[str, str] = {
    "cli_install_suggestion": "doctor.suggestion_cli_install",
    "api_key_no_config_suggestion": "doctor.suggestion_api_key_no_config",
    "api_key_missing_suggestion": "doctor.suggestion_api_key_missing",
    "api_key_format_suggestion": "doctor.suggestion_api_key_format",
    "env_no_config_suggestion": "doctor.suggestion_env_no_config",
    "env_invalid_json_suggestion": "doctor.suggestion_env_invalid_json",
    "env_fix_suggestion": "doctor.suggestion_env_fix",
    "cli_settings_create_suggestion": "doctor.suggestion_cli_settings_create",
    "cli_settings_fix_suggestion": "doctor.suggestion_cli_settings_fix",
    "cli_settings_permission_suggestion": "doctor.suggestion_cli_settings_permission",
    "nodejs_install_suggestion": "doctor.suggestion_nodejs_install",
}

_SEVERITY_LABEL_KEYS: dict[Severity, str] = {
    Severity.OK: "doctor.severity_ok",
    Severity.WARNING: "doctor.severity_warning",
    Severity.ERROR: "doctor.severity_error",
}


def build_doctor_dialog(
    *,
    report: DoctorReport | None = None,
    is_loading: bool = False,
    on_dismiss: Callable[[], None] | None = None,
    on_recheck: Callable[[], None] | None = None,
) -> ft.AlertDialog:
    """Build a complete AlertDialog for provider diagnostics.

    Returns a ready-to-show ``ft.AlertDialog``.
    """
    content = _DoctorContent(
        report=report,
        is_loading=is_loading,
        on_dismiss=on_dismiss,
        on_recheck=on_recheck,
    )
    return ft.AlertDialog(
        modal=True,
        title=ft.Row(
            controls=[
                ft.Icon(ft.Icons.HEALTH_AND_SAFETY, size=24, color=ft.Colors.PRIMARY),
                ft.Text(t("doctor.title"), size=18, weight=ft.FontWeight.BOLD),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=content,
        actions_alignment=ft.MainAxisAlignment.END,
        content_padding=ft.Padding(left=24, right=24, top=8, bottom=0),
    )


class _DoctorContent(ft.Column):
    """Inner content column for the doctor dialog."""

    def __init__(
        self,
        report: DoctorReport | None = None,
        is_loading: bool = False,
        on_dismiss: Callable[[], None] | None = None,
        on_recheck: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(spacing=0)
        self._report = report
        self._is_loading = is_loading
        self._on_dismiss = on_dismiss
        self._on_recheck = on_recheck
        self.width = 480
        self._build_ui()

    def _build_ui(self) -> None:
        self.controls.clear()

        if self._is_loading:
            self.controls = [self._build_loading()]
            return

        if not self._report:
            self.controls = [ft.Text(t("doctor.running"), opacity=0.6)]
            return

        report = self._report

        self.controls.append(
            ft.Text(t("doctor.description"), size=13, opacity=0.6),
        )
        self.controls.append(ft.Container(height=12))

        for probe in report.probes:
            self.controls.append(self._build_probe_row(probe))
            self.controls.append(ft.Container(height=8))

        self.controls.append(ft.Container(height=4))
        self.controls.append(self._build_summary(report))
        self.controls.append(ft.Container(height=12))
        self.controls.append(self._build_actions())

    def _build_loading(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(height=12),
                    ft.Row(
                        controls=[
                            ft.ProgressRing(width=20, height=20, stroke_width=2),
                            ft.Text(t("doctor.running"), size=14, opacity=0.7),
                        ],
                        spacing=12,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Container(height=12),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=480,
        )

    def _build_probe_row(self, probe) -> ft.Control:
        color = _SEVERITY_COLORS[probe.severity]
        icon = _SEVERITY_ICONS[probe.severity]

        title_key = _PROBE_TITLE_KEYS.get(probe.probe_id)
        title_text = t(title_key) if title_key else probe.title

        msg_key = _MESSAGE_KEYS.get(probe.message)
        message_text = t(msg_key) if msg_key else probe.message

        severity_label = t(_SEVERITY_LABEL_KEYS[probe.severity])

        badge = ft.Container(
            content=ft.Text(severity_label, size=11, color=ft.Colors.WHITE),
            bgcolor=color,
            border_radius=4,
            padding=ft.Padding(left=8, right=8, top=2, bottom=2),
        )

        info_col_controls: list[ft.Control] = [
            ft.Row(
                controls=[
                    ft.Text(title_text, size=14, weight=ft.FontWeight.W_500),
                    ft.Container(expand=True),
                    badge,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Text(message_text, size=12, opacity=0.6),
        ]

        if probe.suggestion:
            sug_key = _SUGGESTION_KEYS.get(probe.suggestion)
            sug_text = t(sug_key) if sug_key else probe.suggestion
            info_col_controls.append(
                ft.Text(sug_text, size=11, opacity=0.5, italic=True),
            )

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, color=color, size=22),
                    ft.Column(
                        controls=info_col_controls,
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding(left=12, right=12, top=10, bottom=10),
            border_radius=RADIUS_MD,
            border=ft.Border.all(
                1,
                color if probe.severity != Severity.OK
                else ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
            ),
        )

    def _build_summary(self, report: DoctorReport) -> ft.Control:
        if report.all_ok:
            return ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=SUCCESS_GREEN, size=18),
                    ft.Text(
                        t("doctor.all_ok"),
                        size=13,
                        color=SUCCESS_GREEN,
                        weight=ft.FontWeight.W_500,
                    ),
                ],
                spacing=8,
            )

        parts: list[ft.Control] = []
        if report.has_errors:
            parts.append(ft.Row(
                controls=[
                    ft.Icon(ft.Icons.ERROR, color=ERROR_RED, size=16),
                    ft.Text(
                        t("doctor.has_errors").replace("{count}", str(report.error_count)),
                        size=13, color=ERROR_RED,
                    ),
                ],
                spacing=6,
            ))
        if report.has_warnings:
            parts.append(ft.Row(
                controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=WARNING_AMBER, size=16),
                    ft.Text(
                        t("doctor.has_warnings").replace("{count}", str(report.warning_count)),
                        size=13, color=WARNING_AMBER,
                    ),
                ],
                spacing=6,
            ))
        return ft.Column(controls=parts, spacing=4)

    def _build_actions(self) -> ft.Control:
        return ft.Row(
            controls=[
                ft.Container(expand=True),
                make_outlined_button(
                    t("doctor.close"),
                    on_click=self._handle_dismiss,
                ),
                make_button(
                    t("doctor.recheck"),
                    icon=ft.Icons.REFRESH,
                    on_click=self._handle_recheck,
                ),
            ],
            spacing=10,
        )

    def _handle_dismiss(self, e: ft.ControlEvent | None = None) -> None:
        if self._on_dismiss:
            self._on_dismiss()

    def _handle_recheck(self, e: ft.ControlEvent | None = None) -> None:
        if self._on_recheck:
            self._on_recheck()

    def refresh(
        self,
        report: DoctorReport | None = None,
        is_loading: bool = False,
    ) -> None:
        """Rebuild content with updated data."""
        if report is not None:
            self._report = report
        self._is_loading = is_loading
        self._build_ui()
