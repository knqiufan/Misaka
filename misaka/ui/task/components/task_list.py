"""Task list component.

Displays tasks associated with the current session with status
indicators, click-to-toggle functionality, and inline creation.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from misaka.db.models import TaskItem
from misaka.i18n import t

_STATUS_CONFIG = {
    "pending": {
        "icon": ft.Icons.RADIO_BUTTON_UNCHECKED,
        "color": ft.Colors.GREY,
        "next": "in_progress",
    },
    "in_progress": {
        "icon": ft.Icons.PENDING,
        "color": ft.Colors.ORANGE,
        "next": "completed",
    },
    "completed": {
        "icon": ft.Icons.CHECK_CIRCLE,
        "color": ft.Colors.GREEN,
        "next": "pending",
    },
    "failed": {
        "icon": ft.Icons.ERROR,
        "color": ft.Colors.RED,
        "next": "pending",
    },
}


class TaskList(ft.Column):
    """List of tasks for the current session with status management."""

    def __init__(
        self,
        tasks: list[TaskItem] | None = None,
        on_status_change: Callable[[str, str], None] | None = None,
        on_create: Callable[[str], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(spacing=0, expand=True)
        self._tasks = tasks or []
        self._on_status_change = on_status_change
        self._on_create = on_create
        self._on_delete = on_delete
        self._build_ui()

    def _build_ui(self) -> None:
        from misaka.ui.common.theme import make_text_field

        controls: list[ft.Control] = []

        new_task_field = make_text_field(
            hint_text=t("right_panel.add_task"),
            dense=True,
            border_radius=8,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            on_submit=self._handle_create,
        )
        controls.append(
            ft.Container(
                content=new_task_field,
                padding=ft.Padding.only(left=8, right=8, bottom=8),
            )
        )

        if not self._tasks:
            controls.append(
                ft.Container(
                    content=ft.Text(
                        t("right_panel.no_tasks"),
                        italic=True,
                        size=12,
                        opacity=0.5,
                    ),
                    padding=16,
                    alignment=ft.Alignment.CENTER,
                )
            )
        else:
            task_items = ft.ListView(
                controls=[self._build_task(t_item) for t_item in self._tasks],
                expand=True,
                spacing=2,
            )
            controls.append(task_items)

        self.controls = controls

    def _build_task(self, task: TaskItem) -> ft.Control:
        """Build a single task item."""
        config = _STATUS_CONFIG.get(task.status, _STATUS_CONFIG["pending"])

        status_btn = ft.IconButton(
            icon=config["icon"],
            icon_color=config["color"],
            icon_size=18,
            tooltip=f"Click to set {config['next']}",
            on_click=lambda e, tid=task.id, ns=config["next"]: self._handle_status(tid, ns),
            style=ft.ButtonStyle(padding=4),
        )

        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_size=14,
            tooltip=t("right_panel.delete_task"),
            on_click=lambda e, tid=task.id: self._handle_delete(tid),
            style=ft.ButtonStyle(padding=4),
            opacity=0.5,
        )

        title_style = ft.TextDecoration.LINE_THROUGH if task.status == "completed" else None

        return ft.Container(
            content=ft.Row(
                controls=[
                    status_btn,
                    ft.Column(
                        controls=[
                            ft.Text(
                                task.title,
                                size=13,
                                expand=True,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                decoration=title_style,
                            ),
                            ft.Text(
                                task.description or "",
                                size=11,
                                opacity=0.5,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ) if task.description else ft.Container(height=0),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    delete_btn,
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
            border_radius=6,
            ink=True,
        )

    def _handle_status(self, task_id: str, next_status: str) -> None:
        if self._on_status_change:
            self._on_status_change(task_id, next_status)

    def _handle_delete(self, task_id: str) -> None:
        if self._on_delete:
            self._on_delete(task_id)

    def _handle_create(self, e: ft.ControlEvent) -> None:
        title = (e.control.value or "").strip()
        if not title:
            return
        e.control.value = ""
        e.control.update()
        if self._on_create:
            self._on_create(title)

    def set_tasks(self, tasks: list[TaskItem]) -> None:
        """Update the task list."""
        self._tasks = tasks
        self._build_ui()
