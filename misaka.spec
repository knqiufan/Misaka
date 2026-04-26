# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Misaka.

Builds a single-directory distribution containing the Misaka
desktop application (Python + Flet).

Usage:
    pyinstaller misaka.spec

Or via:
    pip install -e ".[build]"
    pyinstaller misaka.spec
"""

import sys
from pathlib import Path

import certifi
import flet
import flet_desktop

block_cipher = None

# Project root directory
project_root = Path(SPECPATH)

# i18n JSON files must be bundled so Path(__file__).parent finds them when frozen
_i18n_dir = project_root / "misaka" / "i18n"
_assets_dir = project_root / "assets"

# Flet icon data files (loaded at runtime; PyInstaller does not auto-collect them)
_flet_path = Path(flet.__file__).parent
_flet_datas = []
_material_icons = _flet_path / "controls" / "material" / "icons.json"
if _material_icons.exists():
    _flet_datas.append((str(_material_icons), "flet/controls/material"))
_cupertino_icons = _flet_path / "controls" / "cupertino" / "cupertino_icons.json"
if _cupertino_icons.exists():
    _flet_datas.append((str(_cupertino_icons), "flet/controls/cupertino"))

# flet_desktop contains the Flutter desktop client binary (flet.exe + DLLs + data).
# It MUST be bundled — otherwise the frozen app tries to download it at runtime,
# which fails with SSL errors in some environments.
_flet_desktop_path = Path(flet_desktop.__file__).parent
_flet_desktop_app = _flet_desktop_path / "app"
_flet_desktop_datas = []
if _flet_desktop_app.exists():
    _flet_desktop_datas.append((str(_flet_desktop_app), "flet_desktop/app"))
    _flet_exe = _flet_desktop_app / "flet" / "flet.exe"
    if _flet_exe.exists():
        print(f"[misaka.spec] Flet desktop client found: {_flet_exe}")
    else:
        print(f"[misaka.spec] WARNING: flet.exe not found at {_flet_exe}")
else:
    print(f"[misaka.spec] CRITICAL: flet_desktop/app directory not found at {_flet_desktop_app}")
    print("[misaka.spec] The packaged app will fail to start! Run: pip install flet-desktop")

# certifi CA bundle for SSL verification in frozen environments
_certifi_pem = Path(certifi.where())
_certifi_datas = [
    (str(_certifi_pem), "certifi"),
]

_datas = [
    (str(_i18n_dir / "en.json"), "misaka/i18n"),
    (str(_i18n_dir / "zh_CN.json"), "misaka/i18n"),
    (str(_i18n_dir / "zh_TW.json"), "misaka/i18n"),
    (str(_assets_dir), "assets"),
    *_flet_datas,
    *_flet_desktop_datas,
    *_certifi_datas,
]

a = Analysis(
    [str(project_root / "misaka" / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        "misaka",
        "misaka.config",
        "misaka.state",
        "misaka.commands",
        "misaka.db",
        "misaka.db.database",
        "misaka.db.sqlite_backend",
        "misaka.db.models",
        "misaka.db.migrations",
        "misaka.db.row_mappers",
        "misaka.services",
        "misaka.services.chat",
        "misaka.services.chat.claude_service",
        "misaka.services.chat.message_service",
        "misaka.services.chat.permission_service",
        "misaka.services.chat.session_service",
        "misaka.services.common",
        "misaka.services.common.claude_env_builder",
        "misaka.services.file",
        "misaka.services.file.file_service",
        "misaka.services.file.update_check_service",
        "misaka.services.mcp",
        "misaka.services.mcp.mcp_service",
        "misaka.services.session",
        "misaka.services.session.session_import_service",
        "misaka.services.settings",
        "misaka.services.settings.cli_settings_service",
        "misaka.services.settings.provider_service",
        "misaka.services.settings.router_config_service",
        "misaka.services.settings.settings_service",
        "misaka.services.skills",
        "misaka.services.skills.env_check_service",
        "misaka.services.skills.skill_service",
        "misaka.services.task",
        "misaka.services.task.task_service",
        "misaka.ui",
        "misaka.ui.common",
        "misaka.ui.common.app_shell",
        "misaka.ui.common.theme",
        "misaka.ui.components",
        "misaka.ui.pages",
        "misaka.ui.chat",
        "misaka.ui.chat.components",
        "misaka.ui.chat.pages",
        "misaka.ui.file",
        "misaka.ui.file.components",
        "misaka.ui.navigation",
        "misaka.ui.panels",
        "misaka.ui.settings",
        "misaka.ui.settings.pages",
        "misaka.ui.skills",
        "misaka.ui.skills.pages",
        "misaka.ui.status",
        "misaka.ui.task",
        "misaka.ui.task.components",
        "misaka.ui.dialogs",
        "misaka.utils",
        "misaka.utils.file_utils",
        "misaka.utils.path_safety",
        "misaka.utils.platform",
        "misaka.utils.time_utils",
        "misaka.i18n",
        # Third-party hidden imports
        "flet",
        "flet_core",
        "flet_runtime",
        "flet_desktop",
        "flet_desktop.version",
        "pygments",
        "pygments.lexers",
        "pygments.formatters",
        "aiofiles",
        "anyio",
        "watchdog",
        "watchdog.observers",
        "sqlite3",
        "certifi",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        "runtime_hooks/fix_ssl_certs.py",
        "runtime_hooks/suppress_console.py",
    ],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "IPython",
        "jupyter",
        "notebook",
        # Avoid multiple Qt bindings (PyInstaller allows only one)
        "PyQt5",
        "PyQt6",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Misaka",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI application, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Misaka",
)

# macOS app bundle (only on macOS)
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Misaka.app",
        icon="assets/icon.ico",
        bundle_identifier="com.misaka.app",
        info_plist={
            "CFBundleShortVersionString": "0.1.2",
            "CFBundleVersion": "0.1.2",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
