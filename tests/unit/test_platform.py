"""
Tests for platform subprocess and Claude binary helpers.
"""

from __future__ import annotations

import sys
import subprocess
from unittest.mock import patch

import pytest

from misaka.utils.platform import (
    build_background_subprocess_kwargs,
    clear_claude_cache,
    find_claude_sdk_binary,
    wrap_windows_script_command,
)


class TestBackgroundSubprocessHelpers:

    def test_wrap_windows_script_command_wraps_cmd_file(self) -> None:
        with patch("misaka.utils.platform.IS_WINDOWS", True):
            command = wrap_windows_script_command(
                "C:/Users/test/AppData/Roaming/npm/claude.cmd",
                ["--version"],
            )
        assert command == [
            "cmd.exe",
            "/d",
            "/s",
            "/c",
            '""C:/Users/test/AppData/Roaming/npm/claude.cmd" --version"',
        ]

    def test_wrap_windows_script_command_returns_direct_command_for_exe(self) -> None:
        with patch("misaka.utils.platform.IS_WINDOWS", True):
            command = wrap_windows_script_command(
                "C:/Users/test/AppData/Roaming/npm/claude.exe",
                ["--version"],
            )
        assert command == ["C:/Users/test/AppData/Roaming/npm/claude.exe", "--version"]

    @pytest.mark.skipif(sys.platform != "win32", reason="STARTUPINFO is Windows-only")
    def test_build_background_subprocess_kwargs_returns_windows_startupinfo(self) -> None:
        fake_startupinfo = subprocess.STARTUPINFO()
        with patch("misaka.utils.platform.IS_WINDOWS", True), \
             patch("misaka.utils.platform.subprocess.STARTUPINFO", return_value=fake_startupinfo):
            kwargs = build_background_subprocess_kwargs()

        assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW
        assert kwargs["startupinfo"] is fake_startupinfo
        assert fake_startupinfo.dwFlags & subprocess.STARTF_USESHOWWINDOW


class TestClaudeSdkBinary:

    def test_find_claude_sdk_binary_prefers_exe_over_cmd(self) -> None:
        clear_claude_cache()
        with patch("misaka.utils.platform.IS_WINDOWS", True), \
             patch(
                 "misaka.utils.platform._get_claude_candidate_paths",
                 return_value=["C:/npm/claude.cmd", "C:/npm/claude.exe"],
             ), \
             patch("misaka.utils.platform._validate_claude_binary", return_value=True):
            assert find_claude_sdk_binary() == "C:/npm/claude.exe"

    def test_find_claude_sdk_binary_falls_back_to_cmd(self) -> None:
        clear_claude_cache()
        with patch("misaka.utils.platform.IS_WINDOWS", True), \
             patch(
                 "misaka.utils.platform._get_claude_candidate_paths",
                 return_value=["C:/npm/claude.cmd"],
             ), \
             patch("misaka.utils.platform._validate_claude_binary", return_value=True):
            assert find_claude_sdk_binary() == "C:/npm/claude.cmd"
