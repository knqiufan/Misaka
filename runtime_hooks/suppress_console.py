"""
PyInstaller runtime hook - suppress console windows on Windows.

When the app is packaged as a GUI exe (console=False), every subprocess
spawned without CREATE_NO_WINDOW will briefly flash a console window.
This hook patches subprocess.Popen and asyncio.create_subprocess_exec
so that all child processes (including those created by third-party
libraries like claude_agent_sdk / anyio) inherit the hidden-window flags.
"""

import sys

if sys.platform == "win32":
    import asyncio
    import subprocess

    _CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW  # 0x08000000

    def _make_hidden_startupinfo():
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        return si

    # --- Patch subprocess.Popen ---
    _orig_popen_init = subprocess.Popen.__init__

    def _patched_popen_init(self, args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
        if kwargs.get("startupinfo") is None:
            kwargs["startupinfo"] = _make_hidden_startupinfo()
        _orig_popen_init(self, args, **kwargs)

    subprocess.Popen.__init__ = _patched_popen_init

    # --- Patch asyncio.create_subprocess_exec ---
    _orig_create_subprocess_exec = asyncio.create_subprocess_exec

    async def _patched_create_subprocess_exec(program, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
        if kwargs.get("startupinfo") is None:
            kwargs["startupinfo"] = _make_hidden_startupinfo()
        return await _orig_create_subprocess_exec(program, *args, **kwargs)

    asyncio.create_subprocess_exec = _patched_create_subprocess_exec
