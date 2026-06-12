"""Tests for vector backend availability guards in settings."""

from __future__ import annotations

from types import SimpleNamespace

from misaka.ui.settings.components import vector_backend_panel
from misaka.ui.settings.components.vector_backend_panel import VectorBackendPanel


class FakeState:
    def __init__(self) -> None:
        self.page = SimpleNamespace()
        self.services = None

    def get_service(self, name: str):
        return None


def test_seekdb_options_disabled_when_dependency_missing(monkeypatch, db) -> None:
    monkeypatch.setattr(vector_backend_panel, "_is_pyseekdb_available", lambda: False)
    panel = VectorBackendPanel(FakeState(), db=db)

    assert panel._is_backend_selectable("sqlite") is True
    assert panel._is_backend_selectable("seekdb_embedded") is False
    assert panel._is_backend_selectable("seekdb_remote") is False


def test_windows_disables_only_embedded_seekdb(monkeypatch, db) -> None:
    monkeypatch.setattr(vector_backend_panel, "_is_pyseekdb_available", lambda: True)
    monkeypatch.setattr(vector_backend_panel.config, "IS_WINDOWS", True)
    panel = VectorBackendPanel(FakeState(), db=db)

    assert panel._is_backend_selectable("seekdb_embedded") is False
    assert panel._is_backend_selectable("seekdb_remote") is True
