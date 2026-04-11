"""Provider Doctor diagnostic dialog.

Displays structured diagnostic probe results in a modal overlay
with severity-graded cards (OK/Warning/Error) and fix suggestions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from misaka.i18n import t
from misaka.services.doctor.provider_doctor_service import DoctorReport, Severity
from misaka.ui.common.theme import (
    ERROR_RED,
    RADIUS_LG,
    RADIUS_MD,
    SUCCESS_GREEN,
    WARNING_AMBER,
    make_button,
    make_divider,
    make_icon_button,
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


class DoctorDialog(ft.Column):
    """Modal overlay dialog showing provider diagnostic results."""

    def __init__(
        self,
        report: DoctorReport | None = None,
        on_dismiss: Callable[[], None] | None = None,
        on_recheck: Callable[[], None] | None = None,
        is_loading: bool = False,
    ) -> None:
        super().__init__(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )
        self._report = report
        self._on_dismiss = on_dismiss
        self._on_recheck = on_recheck
        self._is_loading = is_loading
        self._build_ui()

    def _build_ui(self) -> None:
        if self._is_loading:
            self.controls = [self._build_loading()]
            self.expand = True
            return

        if not self._report:
            self.visible = False
            self.controls = []
            return

        self.visible = True
        report = self._report

        probe_cards = [self._build_probe_card(p) for p in report.probes]

        if report.all_ok:
            summary = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color=SUCCESS_GREEN, size=20),
                        ft.Text(
                            t("doctor.all_ok"),
                            size=14,
                            color=SUCCESS_GREEN,
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=8,
                ),
                padding=ft.Padding.symmetric(vertical=8),
            )
        else:
            parts: list[ft.Control] = []
            if report.has_errors:
                parts.append(
                    ft.Text(
                        t("doctor.has_errors").replace("{count}", str(report.error_count)),
                        size=13,
                        color=ERROR_RED,
                    )
                )
            if report.has_warnings:
                parts.append(
                    ft.Text(
                        t("doctor.has_warnings").replace("{count}", str(report.warning_count)),
                        size=13,
                        color=WARNING_AMBER,
                    )
                )
            summary = ft.Container(
                content=ft.Column(controls=parts, spacing=4),
                padding=ft.Padding.symmetric(vertical=8),
            )

        actions = ft.Row(
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
            spacing=12,
        )

        dialog_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.HEALTH_AND_SAFETY,
                                size=28,
                                color=ft.Colors.PRIMARY,
                            ),
                            ft.Text(
                                t("doctor.title"),
                                size=20,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Container(expand=True),
                            make_icon_button(
                                ft.Icons.CLOSE,
                                on_click=self._handle_dismiss,
                                icon_size=20,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        t("doctor.description"),
                        size=13,
                        opacity=0.7,
                    ),
                    make_divider(),
                    ft.Column(controls=probe_cards, spacing=8),
                    summary,
                    make_divider(),
                    actions,
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
            ),
            width=560,
            max_height=600,
            padding=24,
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.SURFACE,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=24,
                color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK),
            ),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
        )

        self.controls = [
            ft.Container(
                content=dialog_content,
                alignment=ft.Alignment.CENTER,
                expand=True,
                bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK),
            )
        ]
        self.expand = True

    def _build_loading(self) -> ft.Control:
        dialog_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.HEALTH_AND_SAFETY,
                                size=28,
                                color=ft.Colors.PRIMARY,
                            ),
                            ft.Text(
                                t("doctor.title"),
                                size=20,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=20),
                    ft.Row(
                        controls=[
                            ft.ProgressRing(width=20, height=20, stroke_width=2),
                            ft.Text(t("doctor.running"), size=14, opacity=0.7),
                        ],
                        spacing=12,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Container(height=20),
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=560,
            padding=24,
            border_radius=RADIUS_LG,
            bgcolor=ft.Colors.SURFACE,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=24,
                color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK),
            ),
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            ),
        )

        return ft.Container(
            content=dialog_content,
            alignment=ft.Alignment.CENTER,
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLACK),
        )

    def _build_probe_card(self, probe) -> ft.Control:
        color = _SEVERITY_COLORS[probe.severity]
        icon = _SEVERITY_ICONS[probe.severity]

        title_key = _PROBE_TITLE_KEYS.get(probe.probe_id)
        title_text = t(title_key) if title_key else probe.title

        msg_key = _MESSAGE_KEYS.get(probe.message)
        message_text = t(msg_key) if msg_key else probe.message

        suggestion_controls: list[ft.Control] = []
        if probe.suggestion:
            sug_key = _SUGGESTION_KEYS.get(probe.suggestion)
            sug_text = t(sug_key) if sug_key else probe.suggestion
            suggestion_controls.append(
                ft.Text(
                    f"💡 {sug_text}",
                    size=11,
                    opacity=0.7,
                    italic=True,
                )
            )

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, color=color, size=24),
                    ft.Column(
                        controls=[
                            ft.Text(
                                title_text,
                                size=14,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Text(
                                message_text,
                                size=12,
                                opacity=0.6,
                            ),
                            *suggestion_controls,
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=12,
            border_radius=RADIUS_MD,
            border=ft.Border.all(1, color),
        )

    def _handle_dismiss(self, e: ft.ControlEvent | None = None) -> None:
        if self._on_dismiss:
            self._on_dismiss()

    def _handle_recheck(self, e: ft.ControlEvent | None = None) -> None:
        if self._on_recheck:
            self._on_recheck()

    def refresh(self, report: DoctorReport | None = None, is_loading: bool = False) -> None:
        """Update the dialog with a new report."""
        self._report = report
        self._is_loading = is_loading
        self._build_ui()
