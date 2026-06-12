"""Vector database backend settings panel."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
from typing import TYPE_CHECKING, Any

import flet as ft

from misaka import config
from misaka.config import SettingKeys
from misaka.i18n import t
from misaka.ui.common.theme import (
    make_button,
    make_outlined_button,
    make_text_button,
    make_text_field,
    show_snackbar,
)

if TYPE_CHECKING:
    from misaka.db.database import DatabaseBackend
    from misaka.state import AppState

_BACKENDS = ("sqlite", "seekdb_embedded", "seekdb_remote")


class VectorBackendPanel(ft.Container):
    """Configure sqlite-vec or SeekDB storage without restarting the app."""

    def __init__(
        self,
        state: AppState,
        db: DatabaseBackend | None = None,
    ) -> None:
        super().__init__(expand=True)
        self.state = state
        self.db = db
        self.padding = ft.Padding.symmetric(horizontal=24, vertical=16)
        self._pyseekdb_available = _is_pyseekdb_available()
        self._selected_backend = self._load_backend()
        self._load_remote_config()
        self._build_ui()

    def refresh(self) -> None:
        self._pyseekdb_available = _is_pyseekdb_available()
        self._selected_backend = self._load_backend()
        self._load_remote_config()
        self._build_ui()

    def _load_backend(self) -> str:
        settings_service = self.state.get_service("settings_service")
        value = (
            settings_service.get(SettingKeys.VECTOR_BACKEND)
            if settings_service
            else self.db.get_setting(SettingKeys.VECTOR_BACKEND) if self.db else None
        )
        return value if value in _BACKENDS else "sqlite"

    def _load_remote_config(self) -> None:
        saved = self.db.get_seekdb_config() if self.db else None
        saved = saved or {}
        self._host = str(saved.get("host", "127.0.0.1"))
        self._port = str(saved.get("port", 2881))
        self._user = str(saved.get("user", "root"))
        self._password = str(saved.get("password", ""))
        self._database_name = str(saved.get("database_name", "misaka_kb"))

    def _build_ui(self) -> None:
        self._radio_group = ft.RadioGroup(
            value=self._selected_backend,
            content=ft.Column(
                controls=[
                    self._build_backend_option(
                        "sqlite",
                        "settings.vector_backend_sqlite",
                        "settings.vector_backend_sqlite_desc",
                    ),
                    self._build_backend_option(
                        "seekdb_embedded",
                        "settings.vector_backend_seekdb_embedded",
                        "settings.vector_backend_seekdb_embedded_desc",
                    ),
                    self._build_backend_option(
                        "seekdb_remote",
                        "settings.vector_backend_seekdb_remote",
                        "settings.vector_backend_seekdb_remote_desc",
                    ),
                ],
                spacing=2,
            ),
            on_change=self._on_backend_change,
        )

        self._host_field = make_text_field(
            label=t("settings.vector_backend_host"),
            value=self._host,
            expand=True,
        )
        self._port_field = make_text_field(
            label=t("settings.vector_backend_port"),
            value=self._port,
            width=140,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._user_field = make_text_field(
            label=t("settings.vector_backend_user"),
            value=self._user,
            expand=True,
        )
        self._password_field = make_text_field(
            label=t("settings.vector_backend_password"),
            value=self._password,
            password=True,
            can_reveal_password=True,
            expand=True,
        )
        self._database_field = make_text_field(
            label=t("settings.vector_backend_database"),
            value=self._database_name,
            expand=True,
        )
        self._remote_form = ft.Column(
            controls=[
                ft.Text(
                    t("settings.vector_backend_remote_connection"),
                    size=13,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Row(controls=[self._host_field, self._port_field], spacing=10),
                ft.Row(
                    controls=[self._user_field, self._password_field],
                    spacing=10,
                ),
                self._database_field,
                make_outlined_button(
                    t("settings.vector_backend_test"),
                    icon=ft.Icons.CABLE,
                    on_click=self._on_test_connection,
                    disabled=not self._pyseekdb_available,
                ),
            ],
            spacing=10,
            visible=self._selected_backend == "seekdb_remote",
        )

        hints = self._build_availability_hints()
        self.content = ft.Column(
            controls=[
                ft.Text(
                    t("settings.vector_backend_title"),
                    size=16,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Text(t("settings.vector_backend_desc"), size=12, opacity=0.6),
                self._radio_group,
                *hints,
                ft.Divider(height=1, color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
                self._remote_form,
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.WARNING_AMBER_ROUNDED,
                            size=16,
                            color=ft.Colors.AMBER,
                        ),
                        ft.Text(
                            t("settings.vector_backend_rebuild_hint"),
                            size=11,
                            color=ft.Colors.AMBER,
                            expand=True,
                        ),
                    ],
                    spacing=8,
                ),
                ft.Row(
                    controls=[
                        make_button(
                            t("common.save"),
                            icon=ft.Icons.SAVE_OUTLINED,
                            on_click=self._on_save,
                        )
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _build_backend_option(
        self,
        backend: str,
        label_key: str,
        desc_key: str,
    ) -> ft.Control:
        disabled = not self._is_backend_selectable(backend)
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Radio(value=backend, label="", disabled=disabled),
                    ft.Column(
                        controls=[
                            ft.Text(
                                t(label_key),
                                size=13,
                                weight=ft.FontWeight.W_500,
                                opacity=0.4 if disabled else 1.0,
                            ),
                            ft.Text(
                                t(desc_key),
                                size=11,
                                opacity=0.35 if disabled else 0.6,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=0,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        )

    def _build_availability_hints(self) -> list[ft.Control]:
        hint = self._unavailable_hint()
        if hint:
            return [self._build_hint(hint)]
        return []

    def _unavailable_hint(self) -> str:
        if not self._pyseekdb_available:
            return t("settings.vector_backend_install_hint")
        if config.IS_WINDOWS:
            return t("settings.vector_backend_windows_hint")
        return ""

    @staticmethod
    def _build_hint(message: str) -> ft.Control:
        return ft.Row(
            controls=[
                ft.Icon(ft.Icons.INFO_OUTLINE, size=15, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(message, size=11, opacity=0.65, expand=True),
            ],
            spacing=8,
        )

    def _is_backend_selectable(self, backend: str) -> bool:
        if backend == "sqlite":
            return True
        if not self._pyseekdb_available:
            return False
        return backend != "seekdb_embedded" or not config.IS_WINDOWS

    def _on_backend_change(self, e: ft.ControlEvent) -> None:
        selected = e.data or e.control.value
        if selected not in _BACKENDS or not self._is_backend_selectable(selected):
            return
        self._selected_backend = selected
        self._remote_form.visible = selected == "seekdb_remote"
        with contextlib.suppress(RuntimeError):
            self._remote_form.update()

    def _on_test_connection(self, _: ft.ControlEvent) -> None:
        values = self._read_remote_values()
        if values is None:
            return

        async def _run() -> None:
            try:
                await asyncio.to_thread(_test_remote_connection, values)
            except Exception as exc:
                show_snackbar(
                    self.state.page,
                    t("settings.vector_backend_test_failed").replace("{error}", str(exc)),
                    bgcolor=ft.Colors.ERROR,
                )
                return
            show_snackbar(self.state.page, t("settings.vector_backend_test_success"))

        self.state.page.run_task(_run)

    def _on_save(self, _: ft.ControlEvent) -> None:
        if not self._is_backend_selectable(self._selected_backend):
            show_snackbar(
                self.state.page,
                self._unavailable_hint(),
                bgcolor=ft.Colors.ERROR,
            )
            return
        remote_config = None
        if self._selected_backend == "seekdb_remote":
            remote_config = self._read_remote_values()
            if remote_config is None:
                return

        current = self._load_backend()
        changed = current != self._selected_backend
        has_existing_documents = bool(
            self.db
            and any(
                self.db.get_kb_documents_by_kb(kb.id)
                for kb in self.db.get_all_knowledge_bases()
            )
        )
        if changed and has_existing_documents:
            self._show_switch_confirmation(remote_config)
        else:
            self._save(remote_config)

    def _show_switch_confirmation(self, remote_config: dict[str, Any] | None) -> None:
        page = self.state.page

        def _confirm(_: ft.ControlEvent) -> None:
            page.pop_dialog()
            self._save(remote_config)

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(
                    t("settings.vector_backend_switch_title"),
                    size=16,
                    weight=ft.FontWeight.W_600,
                ),
                content=ft.Text(t("settings.vector_backend_switch_confirm"), size=13),
                actions=[
                    make_text_button(
                        t("common.cancel"),
                        on_click=lambda _: page.pop_dialog(),
                    ),
                    make_button(t("common.confirm"), on_click=_confirm),
                ],
            )
        )

    def _save(self, remote_config: dict[str, Any] | None) -> None:
        services = getattr(self.state, "services", None)
        if services is None:
            show_snackbar(
                self.state.page,
                t("settings.vector_backend_save_failed").replace(
                    "{error}", "Service container unavailable"
                ),
                bgcolor=ft.Colors.ERROR,
            )
            return
        try:
            changed = services.configure_vector_backend(
                self._selected_backend,
                remote_config,
            )
        except Exception as exc:
            show_snackbar(
                self.state.page,
                t("settings.vector_backend_save_failed").replace("{error}", str(exc)),
                bgcolor=ft.Colors.ERROR,
            )
            return

        message_key = (
            "settings.vector_backend_saved_rebuild"
            if changed
            else "settings.vector_backend_saved"
        )
        show_snackbar(self.state.page, t(message_key))
        self._load_remote_config()

    def _read_remote_values(self) -> dict[str, Any] | None:
        host = (self._host_field.value or "").strip()
        user = (self._user_field.value or "").strip() or "root"
        password = self._password_field.value or ""
        database_name = (self._database_field.value or "").strip()
        try:
            port = int((self._port_field.value or "").strip())
        except ValueError:
            port = 0
        if not host or not database_name or not 1 <= port <= 65535:
            show_snackbar(
                self.state.page,
                t("settings.vector_backend_invalid_remote"),
                bgcolor=ft.Colors.ERROR,
            )
            return None
        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database_name": database_name,
        }


def _is_pyseekdb_available() -> bool:
    try:
        importlib.import_module("pyseekdb")
    except Exception:
        return False
    return True


def _test_remote_connection(values: dict[str, Any]) -> None:
    import pyseekdb

    client = pyseekdb.Client(
        host=values["host"],
        port=values["port"],
        user=values["user"],
        password=values["password"],
        database=values["database_name"],
    )
    try:
        client.list_collections()
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
