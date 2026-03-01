"""
Theme configuration for Misaka.

Defines Material Design 3 themes with Misaka's color palette
for dark, light, and system modes. Modern minimalist tech aesthetic.
"""

from __future__ import annotations

import sys

import flet as ft

# ---------------------------------------------------------------------------
# Color palette — Neo Minimal Tech
# ---------------------------------------------------------------------------

# Primary accent — indigo-500, vibrant yet restrained
ACCENT_BLUE = "#6366f1"
ACCENT_BLUE_LIGHT = "#818cf8"

# Dark theme — deep, immersive, near-black
DARK_BG = "#08080c"
DARK_SURFACE = "#101018"
DARK_SURFACE_VARIANT = "#1a1a24"
DARK_ON_SURFACE = "#e8e8ed"
DARK_ON_SURFACE_VARIANT = "#9494a0"
DARK_BORDER = "#2a2a36"

# Light theme — crisp whites with cool undertones
LIGHT_BG = "#f6f7fa"
LIGHT_SURFACE = "#ffffff"
LIGHT_SURFACE_VARIANT = "#f0f1f5"
LIGHT_ON_SURFACE = "#111118"
LIGHT_ON_SURFACE_VARIANT = "#64647a"
LIGHT_BORDER = "#dddde6"

# Semantic colors — softer, more refined
SUCCESS_GREEN = "#10b981"
WARNING_AMBER = "#f59e0b"
ERROR_RED = "#ef4444"

# Consistent border radius — larger for modern feel
RADIUS_SM = 8
RADIUS_MD = 10
RADIUS_LG = 14
RADIUS_XL = 18

# Preferred UI font family.
# NOTE:
# Flet/Flutter expects a single font-family name here rather than a CSS-style
# comma-separated fallback list. Using a CSS font stack causes lookup failure,
# then engine fallback may mix glyph providers per character (especially CJK),
# which can render words like "关于" with inconsistent glyph shapes.
def _resolve_ui_font_family() -> str:
    """Return a stable platform-native UI font family."""
    if sys.platform.startswith("win"):
        # Full CJK coverage and stable weight rendering on Windows.
        return "Microsoft YaHei UI"
    if sys.platform == "darwin":
        return "PingFang SC"
    return "Noto Sans CJK SC"


def _resolve_mono_font_family() -> str:
    """Return a stable platform-native monospace font family."""
    if sys.platform.startswith("win"):
        return "Consolas"
    if sys.platform == "darwin":
        return "Menlo"
    return "DejaVu Sans Mono"


FONT_FAMILY = _resolve_ui_font_family()
MONO_FONT_FAMILY = _resolve_mono_font_family()


# ---------------------------------------------------------------------------
# Theme factory
# ---------------------------------------------------------------------------

def _input_border(color: str) -> ft.InputBorder:
    return ft.InputBorder.OUTLINE


def _make_expansion_tile_theme() -> ft.ExpansionTileTheme:
    return ft.ExpansionTileTheme(
        icon_color=ft.Colors.ON_SURFACE_VARIANT,
        text_color=ft.Colors.ON_SURFACE,
        collapsed_text_color=ft.Colors.ON_SURFACE,
        collapsed_icon_color=ft.Colors.ON_SURFACE_VARIANT,
    )


def get_dark_theme() -> ft.Theme:
    """Return the dark theme for Misaka."""
    return ft.Theme(
        font_family=FONT_FAMILY,
        color_scheme_seed=ACCENT_BLUE,
        color_scheme=ft.ColorScheme(
            primary=ACCENT_BLUE,
            on_primary="#ffffff",
            surface=DARK_BG,
            on_surface=DARK_ON_SURFACE,
            surface_container=DARK_SURFACE,
            surface_container_high=DARK_SURFACE_VARIANT,
            on_surface_variant=DARK_ON_SURFACE_VARIANT,
            outline=DARK_BORDER,
        ),
        expansion_tile_theme=_make_expansion_tile_theme(),
    )


def get_light_theme() -> ft.Theme:
    """Return the light theme for Misaka."""
    return ft.Theme(
        font_family=FONT_FAMILY,
        color_scheme_seed=ACCENT_BLUE,
        color_scheme=ft.ColorScheme(
            primary=ACCENT_BLUE,
            on_primary="#ffffff",
            surface=LIGHT_BG,
            on_surface=LIGHT_ON_SURFACE,
            surface_container=LIGHT_SURFACE,
            surface_container_high=LIGHT_SURFACE_VARIANT,
            on_surface_variant=LIGHT_ON_SURFACE_VARIANT,
            outline=LIGHT_BORDER,
        ),
        expansion_tile_theme=_make_expansion_tile_theme(),
    )


# ---------------------------------------------------------------------------
# Modern input component factories
# ---------------------------------------------------------------------------

def make_text_field(**kwargs) -> ft.TextField:
    """Create a modern styled TextField with consistent look across the app."""
    defaults = dict(
        border=ft.InputBorder.OUTLINE,
        border_radius=RADIUS_MD,
        border_color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        focused_border_color=ACCENT_BLUE,
        focused_border_width=1.5,
        border_width=1,
        fill_color=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
        filled=True,
        text_size=13,
        label_style=ft.TextStyle(size=12),
        content_padding=ft.Padding.symmetric(horizontal=14, vertical=10),
    )
    defaults.update(kwargs)
    return ft.TextField(**defaults)


def make_dropdown(**kwargs) -> ft.Dropdown:
    """Create a modern styled Dropdown with consistent look across the app."""
    defaults = dict(
        border=ft.InputBorder.OUTLINE,
        border_radius=RADIUS_MD,
        border_color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        focused_border_color=ACCENT_BLUE,
        focused_border_width=1.5,
        border_width=1,
        fill_color=ft.Colors.with_opacity(0.03, ft.Colors.ON_SURFACE),
        filled=True,
        text_size=13,
        label_style=ft.TextStyle(size=12),
        content_padding=ft.Padding.symmetric(horizontal=14, vertical=10),
    )
    defaults.update(kwargs)
    return ft.Dropdown(**defaults)


def apply_theme(page: ft.Page, mode: str) -> None:
    """Apply a theme mode to the Flet page.

    Args:
        page: The Flet page to theme.
        mode: One of "system", "light", or "dark".
    """
    page.theme = get_light_theme()
    page.dark_theme = get_dark_theme()

    if mode == "dark":
        page.theme_mode = ft.ThemeMode.DARK
    elif mode == "light":
        page.theme_mode = ft.ThemeMode.LIGHT
    else:
        page.theme_mode = ft.ThemeMode.SYSTEM
