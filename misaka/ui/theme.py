"""
Theme configuration for Misaka.

Defines Material Design 3 themes with Misaka's color palette
for dark, light, and system modes.
"""

from __future__ import annotations

import flet as ft


# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

# Primary accent — indigo-500, modern and vibrant
ACCENT_BLUE = "#6366f1"
ACCENT_BLUE_LIGHT = "#818cf8"

# Dark theme — deeper, richer backgrounds
DARK_BG = "#0f0f14"
DARK_SURFACE = "#18181b"
DARK_SURFACE_VARIANT = "#27272a"
DARK_ON_SURFACE = "#e4e4e7"
DARK_ON_SURFACE_VARIANT = "#a1a1aa"
DARK_BORDER = "#3f3f46"

# Light theme — cleaner whites
LIGHT_BG = "#fafafa"
LIGHT_SURFACE = "#ffffff"
LIGHT_SURFACE_VARIANT = "#f4f4f5"
LIGHT_ON_SURFACE = "#18181b"
LIGHT_ON_SURFACE_VARIANT = "#71717a"
LIGHT_BORDER = "#e4e4e7"

# Semantic colors
SUCCESS_GREEN = "#22c55e"
WARNING_AMBER = "#f59e0b"
ERROR_RED = "#ef4444"

# Consistent border radius
RADIUS_SM = 6
RADIUS_MD = 8
RADIUS_LG = 12
RADIUS_XL = 16

# Preferred font stack
FONT_FAMILY = "Segoe UI, SF Pro Display, -apple-system, Roboto, sans-serif"
MONO_FONT_FAMILY = "Cascadia Code, JetBrains Mono, Menlo, Consolas, monospace"


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
        border_color=ft.Colors.with_opacity(0.18, ft.Colors.ON_SURFACE),
        focused_border_color=ACCENT_BLUE,
        focused_border_width=2,
        border_width=1,
        fill_color=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
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
        border_color=ft.Colors.with_opacity(0.18, ft.Colors.ON_SURFACE),
        focused_border_color=ACCENT_BLUE,
        focused_border_width=2,
        border_width=1,
        fill_color=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
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
