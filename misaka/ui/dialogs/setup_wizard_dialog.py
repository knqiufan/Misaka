"""Setup Wizard dialog component.

Multi-step guided setup dialog shown on first launch.
Steps: 1) Environment check  2) Provider config  3) Working directory  4) Done

Reuses EnvCheckService for CLI detection and RouterConfigService for
provider configuration.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from misaka.config import SettingKeys
from misaka.i18n import t
from misaka.ui.common.theme import (
    ERROR_RED,
    RADIUS_MD,
    SUCCESS_GREEN,
    WARNING_AMBER,
    make_badge,
    make_button,
    make_divider,
    make_icon_button,
    make_outlined_button,
    make_text_field,
)

if TYPE_CHECKING:
    from misaka.state import AppState

logger = logging.getLogger(__name__)

_TOTAL_STEPS = 4


class SetupWizardDialog(ft.Column):
    """Multi-step setup wizard shown on first launch.

    Manages its own step index and renders different content per step.
    Wrapped inside an AlertDialog by the caller (AppShell).
    """

    def __init__(
        self,
        state: AppState,
        *,
        on_finish: Callable[[], None] | None = None,
        on_skip: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            spacing=12,
            tight=True,
        )
        self.state = state
        self._on_finish = on_finish
        self._on_skip = on_skip

        self._current_step = 0
        self._env_checking = False

        # Provider form values
        self._provider_name = ""
        self._provider_api_key = ""
        self._provider_base_url = ""

        # Working directory
        self._workdir = ""

        self._build_ui()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        step_content = self._build_step_content()
        stepper_indicators = self._build_stepper_indicators()
        nav_buttons = self._build_nav_buttons()

        self.controls = [
            self._build_header(),
            make_divider(),
            stepper_indicators,
            make_divider(),
            ft.Container(
                content=step_content,
                padding=ft.Padding.only(top=4, bottom=4),
            ),
            make_divider(),
            nav_buttons,
        ]

    def _build_header(self) -> ft.Control:
        return ft.Row(
            controls=[
                ft.Icon(ft.Icons.ROCKET_LAUNCH, size=28, color=ft.Colors.PRIMARY),
                ft.Column(
                    controls=[
                        ft.Text(
                            t("setup_wizard.title"),
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            t("setup_wizard.subtitle"),
                            size=12,
                            opacity=0.6,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                make_icon_button(
                    ft.Icons.CLOSE,
                    on_click=lambda e: self._handle_skip(),
                    icon_size=20,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _build_stepper_indicators(self) -> ft.Control:
        step_labels = [
            (ft.Icons.BUILD_CIRCLE, t("setup_wizard.step_env")),
            (ft.Icons.KEY, t("setup_wizard.step_provider")),
            (ft.Icons.FOLDER_OPEN, t("setup_wizard.step_workdir")),
            (ft.Icons.CHECK_CIRCLE, t("setup_wizard.step_done")),
        ]

        indicators: list[ft.Control] = []
        for i, (icon, label) in enumerate(step_labels):
            is_active = i == self._current_step
            is_done = i < self._current_step

            if is_done:
                color = SUCCESS_GREEN
                icon_name = ft.Icons.CHECK_CIRCLE
            elif is_active:
                color = ft.Colors.PRIMARY
                icon_name = icon
            else:
                color = ft.Colors.ON_SURFACE_VARIANT
                icon_name = icon

            step_indicator = ft.Column(
                controls=[
                    ft.Icon(icon_name, size=22, color=color),
                    ft.Text(
                        label,
                        size=10,
                        weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.NORMAL,
                        color=color,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
                expand=True,
            )
            indicators.append(step_indicator)

            if i < len(step_labels) - 1:
                line_color = SUCCESS_GREEN if is_done else ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE)
                indicators.append(
                    ft.Container(
                        height=2,
                        bgcolor=line_color,
                        expand=True,
                        margin=ft.Margin.only(top=4),
                        border_radius=1,
                    )
                )

        return ft.Container(
            content=ft.Row(
                controls=indicators,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            padding=ft.Padding.symmetric(vertical=8, horizontal=4),
        )

    # ------------------------------------------------------------------
    # Step content builders
    # ------------------------------------------------------------------

    def _build_step_content(self) -> ft.Control:
        builders = [
            self._build_env_step,
            self._build_provider_step,
            self._build_workdir_step,
            self._build_done_step,
        ]
        return builders[self._current_step]()

    def _build_env_step(self) -> ft.Control:
        check_result = self.state.env_check_result
        if not check_result and not self._env_checking:
            return ft.Column(
                controls=[
                    ft.Text(t("setup_wizard.step_env_desc"), size=13, opacity=0.7),
                    ft.Container(height=16),
                    ft.Row(
                        controls=[
                            ft.ProgressRing(width=20, height=20, stroke_width=2),
                            ft.Text(t("setup_wizard.env_checking"), size=13, opacity=0.7),
                        ],
                        spacing=10,
                    ),
                ],
                spacing=8,
            )

        if self._env_checking:
            return ft.Column(
                controls=[
                    ft.Text(t("setup_wizard.step_env_desc"), size=13, opacity=0.7),
                    ft.Container(height=16),
                    ft.Row(
                        controls=[
                            ft.ProgressRing(width=20, height=20, stroke_width=2),
                            ft.Text(t("setup_wizard.env_checking"), size=13, opacity=0.7),
                        ],
                        spacing=10,
                    ),
                ],
                spacing=8,
            )

        tool_cards: list[ft.Control] = []
        for tool in check_result.tools:
            tool_cards.append(self._build_tool_row(tool))

        all_ok = check_result.all_installed

        status_row = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE if all_ok else ft.Icons.WARNING_AMBER,
                        color=SUCCESS_GREEN if all_ok else WARNING_AMBER,
                        size=18,
                    ),
                    ft.Text(
                        t("env_check.all_ready") if all_ok else t("setup_wizard.step_env_desc"),
                        size=13,
                        color=SUCCESS_GREEN if all_ok else WARNING_AMBER,
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding.symmetric(vertical=4),
        )

        recheck_btn = make_outlined_button(
            t("setup_wizard.recheck"),
            icon=ft.Icons.REFRESH,
            on_click=lambda e: self._recheck_env(),
        )

        return ft.Column(
            controls=[
                ft.Text(t("setup_wizard.step_env_desc"), size=13, opacity=0.7),
                ft.Container(height=4),
                ft.Column(controls=tool_cards, spacing=6),
                status_row,
                ft.Row(controls=[ft.Container(expand=True), recheck_btn]),
            ],
            spacing=8,
        )

    def _build_tool_row(self, tool) -> ft.Control:
        is_installed = tool.is_installed
        if is_installed:
            icon = ft.Icon(ft.Icons.CHECK_CIRCLE, color=SUCCESS_GREEN, size=20)
            version = f"v{tool.version}" if tool.version else t("env_check.installed")
            badge = make_badge(t("env_check.installed"), bgcolor=SUCCESS_GREEN)
        else:
            icon = ft.Icon(ft.Icons.CANCEL, color=ERROR_RED, size=20)
            version = t("env_check.not_installed")
            badge = make_badge(t("env_check.not_installed"), bgcolor=ERROR_RED)

        return ft.Container(
            content=ft.Row(
                controls=[
                    icon,
                    ft.Column(
                        controls=[
                            ft.Text(tool.name, size=13, weight=ft.FontWeight.W_500),
                            ft.Text(version, size=11, opacity=0.5),
                        ],
                        spacing=1,
                        expand=True,
                    ),
                    badge,
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            border_radius=RADIUS_MD,
            border=ft.Border.all(
                1,
                SUCCESS_GREEN if is_installed
                else ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
            ),
        )

    def _build_provider_step(self) -> ft.Control:
        router_svc = self.state.get_service("router_config_service")
        has_existing = False
        if router_svc:
            active = router_svc.get_active()
            if active and active.api_key:
                has_existing = True

        if has_existing:
            return ft.Column(
                controls=[
                    ft.Text(t("setup_wizard.step_provider_desc"), size=13, opacity=0.7),
                    ft.Container(height=12),
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.CHECK_CIRCLE, color=SUCCESS_GREEN, size=24),
                            ft.Text(
                                t("setup_wizard.provider_exists"),
                                size=14,
                                color=SUCCESS_GREEN,
                                weight=ft.FontWeight.W_500,
                            ),
                        ],
                        spacing=10,
                    ),
                ],
                spacing=8,
            )

        name_field = make_text_field(
            label=t("setup_wizard.provider_name"),
            hint_text=t("setup_wizard.provider_name_hint"),
            value=self._provider_name,
            on_change=lambda e: self._update_provider_field("name", e.control.value),
        )
        key_field = make_text_field(
            label=t("setup_wizard.provider_api_key"),
            hint_text=t("setup_wizard.provider_api_key_hint"),
            value=self._provider_api_key,
            password=True,
            can_reveal_password=True,
            on_change=lambda e: self._update_provider_field("api_key", e.control.value),
        )
        url_field = make_text_field(
            label=t("setup_wizard.provider_base_url"),
            hint_text=t("setup_wizard.provider_base_url_hint"),
            value=self._provider_base_url,
            on_change=lambda e: self._update_provider_field("base_url", e.control.value),
        )

        return ft.Column(
            controls=[
                ft.Text(t("setup_wizard.step_provider_desc"), size=13, opacity=0.7),
                ft.Container(height=4),
                name_field,
                key_field,
                url_field,
            ],
            spacing=10,
        )

    def _build_workdir_step(self) -> ft.Control:
        workdir_field = make_text_field(
            label=t("setup_wizard.workdir_label"),
            hint_text=t("setup_wizard.workdir_hint"),
            value=self._workdir,
            on_change=lambda e: self._update_workdir(e.control.value),
            expand=True,
        )

        browse_btn = make_outlined_button(
            t("setup_wizard.workdir_browse"),
            icon=ft.Icons.FOLDER_OPEN,
            on_click=lambda e: self._browse_workdir(),
        )

        return ft.Column(
            controls=[
                ft.Text(t("setup_wizard.step_workdir_desc"), size=13, opacity=0.7),
                ft.Container(height=4),
                ft.Row(
                    controls=[workdir_field, browse_btn],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                ),
            ],
            spacing=8,
        )

    def _build_done_step(self) -> ft.Control:
        return ft.Column(
            controls=[
                ft.Container(height=8),
                ft.Column(
                    controls=[
                        ft.Icon(
                            ft.Icons.CELEBRATION,
                            size=48,
                            color=ft.Colors.PRIMARY,
                        ),
                        ft.Container(height=8),
                        ft.Text(
                            t("setup_wizard.done_title"),
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            t("setup_wizard.done_message"),
                            size=13,
                            opacity=0.6,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )

    # ------------------------------------------------------------------
    # Navigation buttons
    # ------------------------------------------------------------------

    def _build_nav_buttons(self) -> ft.Control:
        is_first = self._current_step == 0
        is_last = self._current_step == _TOTAL_STEPS - 1

        left_controls: list[ft.Control] = []
        if not is_last:
            left_controls.append(
                make_outlined_button(
                    t("setup_wizard.skip"),
                    on_click=lambda e: self._handle_skip(),
                )
            )

        right_controls: list[ft.Control] = []
        if not is_first:
            right_controls.append(
                make_outlined_button(
                    t("setup_wizard.back"),
                    icon=ft.Icons.ARROW_BACK,
                    on_click=lambda e: self._go_back(),
                )
            )

        if is_last:
            right_controls.append(
                make_button(
                    t("setup_wizard.finish"),
                    icon=ft.Icons.CHECK,
                    on_click=lambda e: self._handle_finish(),
                )
            )
        else:
            right_controls.append(
                make_button(
                    t("setup_wizard.next"),
                    icon=ft.Icons.ARROW_FORWARD,
                    on_click=lambda e: self._go_next(),
                )
            )

        return ft.Row(
            controls=[
                ft.Row(controls=left_controls, spacing=8),
                ft.Container(expand=True),
                ft.Row(controls=right_controls, spacing=8),
            ],
        )

    # ------------------------------------------------------------------
    # Navigation logic
    # ------------------------------------------------------------------

    def _go_next(self) -> None:
        if self._current_step == 1:
            self._save_provider()
        if self._current_step == 2:
            self._save_workdir()
        if self._current_step < _TOTAL_STEPS - 1:
            self._current_step += 1
            self._rebuild()

    def _go_back(self) -> None:
        if self._current_step > 0:
            self._current_step -= 1
            self._rebuild()

    def _handle_finish(self) -> None:
        self._mark_completed()
        if self._on_finish:
            self._on_finish()

    def _handle_skip(self) -> None:
        self._mark_completed()
        if self._on_skip:
            self._on_skip()

    def _mark_completed(self) -> None:
        settings_svc = self.state.get_service("settings_service")
        if settings_svc:
            settings_svc.set(SettingKeys.SETUP_WIZARD_COMPLETED, "true")

    # ------------------------------------------------------------------
    # Provider logic
    # ------------------------------------------------------------------

    def _update_provider_field(self, field: str, value: str) -> None:
        if field == "name":
            self._provider_name = value
        elif field == "api_key":
            self._provider_api_key = value
        elif field == "base_url":
            self._provider_base_url = value

    def _save_provider(self) -> None:
        if not self._provider_api_key:
            return

        router_svc = self.state.get_service("router_config_service")
        if not router_svc:
            return

        name = self._provider_name or "Default"

        config_json: dict = {"env": {}}
        config_json["env"]["ANTHROPIC_AUTH_TOKEN"] = self._provider_api_key
        if self._provider_base_url:
            config_json["env"]["ANTHROPIC_BASE_URL"] = self._provider_base_url

        config_json_str = json.dumps(config_json, indent=2, ensure_ascii=False)

        active = router_svc.get_active()
        if active and not active.api_key:
            router_svc.update(
                active.id,
                name=name,
                api_key=self._provider_api_key,
                base_url=self._provider_base_url,
                config_json=config_json_str,
            )
            router_svc.activate(active.id)
        else:
            new_config = router_svc.create(
                name=name,
                api_key=self._provider_api_key,
                base_url=self._provider_base_url,
                config_json=config_json_str,
            )
            router_svc.activate(new_config.id)

        logger.info("Setup wizard: saved provider config '%s'", name)

    # ------------------------------------------------------------------
    # Working directory logic
    # ------------------------------------------------------------------

    def _update_workdir(self, value: str) -> None:
        self._workdir = value

    def _save_workdir(self) -> None:
        if not self._workdir:
            return
        settings_svc = self.state.get_service("settings_service")
        if settings_svc:
            settings_svc.set("default_working_dir", self._workdir)
            logger.info("Setup wizard: saved working dir '%s'", self._workdir)

    def _browse_workdir(self) -> None:
        from misaka.ui.file.components.folder_picker import FolderPicker

        def on_select(path: str) -> None:
            self._workdir = path
            self._rebuild()

        picker = FolderPicker(
            page=self.state.page,
            on_select=on_select,
            initial_path=self._workdir or None,
        )
        picker.show()

    # ------------------------------------------------------------------
    # Environment check logic
    # ------------------------------------------------------------------

    def _recheck_env(self) -> None:
        env_svc = self.state.get_service("env_check_service")
        if not env_svc:
            return

        self._env_checking = True
        self._rebuild()

        async def _do_recheck():
            result = await env_svc.check_all()
            self.state.env_check_result = result
            self._env_checking = False
            self._rebuild()
            self.state.update()

        self.state.page.run_task(_do_recheck)

    # ------------------------------------------------------------------
    # Rebuild
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        self._build_ui()
        self.state.update()
