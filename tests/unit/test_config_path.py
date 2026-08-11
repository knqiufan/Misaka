"""Tests for runtime PATH refresh after package-manager installs."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from misaka import config


def test_expanded_path_merges_fresh_registry_entries() -> None:
    with patch.dict(os.environ, {"PATH": os.pathsep.join(("old-bin", "shared-bin"))}), patch(
        "misaka.config._get_windows_registry_path_dirs",
        return_value=["new-bin", "shared-bin"],
    ), patch("misaka.config.get_extra_path_dirs", return_value=["extra-bin"]):
        result = config.get_expanded_path().split(os.pathsep)

    assert result == ["old-bin", "shared-bin", "new-bin", "extra-bin"]


def test_windows_registry_path_reader_uses_user_and_machine_values() -> None:
    key = MagicMock()
    key.__enter__.return_value = key
    fake_winreg = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        HKEY_LOCAL_MACHINE=object(),
        OpenKey=MagicMock(return_value=key),
        QueryValueEx=MagicMock(
            side_effect=[
                (os.pathsep.join(("user-a", "user-b")), 1),
                ("machine-a", 1),
            ]
        ),
    )

    with patch.object(config, "IS_WINDOWS", True), patch.dict(
        sys.modules,
        {"winreg": fake_winreg},
    ):
        result = config._get_windows_registry_path_dirs()

    assert result == ["user-a", "user-b", "machine-a"]
    assert fake_winreg.OpenKey.call_count == 2


def test_windows_extra_paths_include_package_manager_locations() -> None:
    environment = {
        "APPDATA": r"C:\Users\tester\AppData\Roaming",
        "LOCALAPPDATA": r"C:\Users\tester\AppData\Local",
        "PROGRAMFILES": r"C:\Program Files",
    }
    with patch.object(config, "IS_WINDOWS", True), patch.dict(
        os.environ,
        environment,
        clear=False,
    ), patch("pathlib.Path.is_dir", return_value=False):
        paths = config.get_extra_path_dirs()

    normalized = [path.replace("\\", "/") for path in paths]
    assert "C:/Program Files/nodejs" in normalized
    assert "C:/Program Files/Git/cmd" in normalized
    assert any(path.endswith("Microsoft/WindowsApps") for path in normalized)
    assert any(path.endswith("Microsoft/WinGet/Links") for path in normalized)
