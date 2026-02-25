"""
Shared test fixtures for Misaka tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from misaka.db.database import DatabaseBackend
from misaka.db.sqlite_backend import SQLiteBackend


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for test files."""
    return tmp_path


@pytest.fixture
def db(tmp_path: Path) -> DatabaseBackend:
    """Provide an initialized SQLite database backend for testing."""
    db_path = str(tmp_path / "test.db")
    backend = SQLiteBackend(db_path)
    backend.initialize()
    yield backend
    backend.close()
