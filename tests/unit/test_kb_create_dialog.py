"""Tests for the knowledge base create/edit dialog."""

from __future__ import annotations

from types import SimpleNamespace

import flet as ft

from misaka.ui.knowledge.components.kb_create_dialog import show_kb_create_dialog


class _Page:
    def __init__(self) -> None:
        self.dialogs: list[ft.Control] = []

    def show_dialog(self, dialog: ft.Control) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        pass


class _State:
    def __init__(self, page: _Page) -> None:
        self.page = page
        self._services = {
            "kb_service": SimpleNamespace(get=lambda kb_id: None),
            "router_config_service": SimpleNamespace(
                get_available_embedding_models=lambda: [],
                get_available_reranker_models=lambda: [],
            ),
        }

    def get_service(self, name: str):
        return self._services.get(name)


def test_advanced_settings_fields_expand_inside_paired_rows() -> None:
    page = _Page()
    show_kb_create_dialog(_State(page))

    paired_rows = _find_advanced_paired_rows(page.dialogs[0])

    assert len(paired_rows) == 2
    for row in paired_rows:
        assert all(control.expand for control in row.controls)


def _find_advanced_paired_rows(control: ft.Control) -> list[ft.Row]:
    rows: list[ft.Row] = []
    _collect_advanced_paired_rows(control, rows)
    return rows


def _collect_advanced_paired_rows(control: ft.Control, rows: list[ft.Row]) -> None:
    if isinstance(control, ft.Row) and _is_advanced_pair_row(control):
        rows.append(control)

    children = getattr(control, "controls", None)
    if children:
        for child in children:
            _collect_advanced_paired_rows(child, rows)

    content = getattr(control, "content", None)
    if content:
        _collect_advanced_paired_rows(content, rows)


def _is_advanced_pair_row(row: ft.Row) -> bool:
    """Check if a Row contains two advanced number fields.

    Labels are compared against their translated values, so this works
    regardless of the current i18n locale.
    """
    advanced_translation_keys = {
        "kb.chunk_size",
        "kb.chunk_overlap",
        "kb.top_k",
        "kb.similarity_threshold",
    }
    from misaka.i18n import t
    advanced_translated = {t(key) for key in advanced_translation_keys}

    labels = {
        getattr(control, "label", "")
        for control in row.controls
        if isinstance(control, ft.TextField)
    }
    return len(labels) == 2 and labels.issubset(advanced_translated)
