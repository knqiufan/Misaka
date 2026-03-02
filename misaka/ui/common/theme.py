"""
Theme configuration for Misaka — Misaka Design System.

Defines Material Design 3 themes with a modern, refined aesthetic
inspired by fletmint's visual language: dual-border inputs, soft shadows,
pill-shaped buttons, and badge-style status indicators.

All component factories use semantic MD3 color tokens so they adapt
automatically to dark / light / system modes.
"""

from __future__ import annotations

import sys

import flet as ft

# ---------------------------------------------------------------------------
# Color palette — Neo Minimal Tech
# ---------------------------------------------------------------------------

ACCENT_BLUE = "#6366f1"
ACCENT_BLUE_LIGHT = "#818cf8"

DARK_BG = "#08080c"
DARK_SURFACE = "#101018"
DARK_SURFACE_VARIANT = "#1a1a24"
DARK_ON_SURFACE = "#e8e8ed"
DARK_ON_SURFACE_VARIANT = "#9494a0"
DARK_BORDER = "#2a2a36"

LIGHT_BG = "#f6f7fa"
LIGHT_SURFACE = "#ffffff"
LIGHT_SURFACE_VARIANT = "#f0f1f5"
LIGHT_ON_SURFACE = "#111118"
LIGHT_ON_SURFACE_VARIANT = "#64647a"
LIGHT_BORDER = "#dddde6"

SUCCESS_GREEN = "#10b981"
WARNING_AMBER = "#f59e0b"
ERROR_RED = "#ef4444"

RADIUS_SM = 8
RADIUS_MD = 10
RADIUS_LG = 14
RADIUS_XL = 18

# ---------------------------------------------------------------------------
# Font resolution
# ---------------------------------------------------------------------------

def _resolve_ui_font_family() -> str:
    if sys.platform.startswith("win"):
        return "Microsoft YaHei UI"
    if sys.platform == "darwin":
        return "PingFang SC"
    return "Noto Sans CJK SC"


def _resolve_mono_font_family() -> str:
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

def _make_expansion_tile_theme() -> ft.ExpansionTileTheme:
    return ft.ExpansionTileTheme(
        icon_color=ft.Colors.ON_SURFACE_VARIANT,
        text_color=ft.Colors.ON_SURFACE,
        collapsed_text_color=ft.Colors.ON_SURFACE,
        collapsed_icon_color=ft.Colors.ON_SURFACE_VARIANT,
    )


def get_dark_theme(accent: str = ACCENT_BLUE) -> ft.Theme:
    """Return the dark theme for Misaka."""
    return ft.Theme(
        font_family=FONT_FAMILY,
        color_scheme_seed=accent,
        color_scheme=ft.ColorScheme(
            primary=accent,
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


def get_light_theme(accent: str = ACCENT_BLUE) -> ft.Theme:
    """Return the light theme for Misaka."""
    return ft.Theme(
        font_family=FONT_FAMILY,
        color_scheme_seed=accent,
        color_scheme=ft.ColorScheme(
            primary=accent,
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
# Component factories — Misaka Design System
# ---------------------------------------------------------------------------

# ---- Text field -----------------------------------------------------------

def make_text_field(**kwargs) -> ft.TextField:
    """Create a modern styled TextField with refined focus glow."""
    defaults = dict(
        border=ft.InputBorder.OUTLINE,
        border_radius=RADIUS_MD,
        border_color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        focused_border_color=ft.Colors.PRIMARY,
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


# ---- Dropdown -------------------------------------------------------------

def make_dropdown(**kwargs) -> ft.Dropdown:
    """Create a modern styled Dropdown matching text-field aesthetics."""
    defaults = dict(
        border=ft.InputBorder.OUTLINE,
        border_radius=RADIUS_MD,
        border_color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
        focused_border_color=ft.Colors.PRIMARY,
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


# ---- Card container -------------------------------------------------------

def make_card(
    content: ft.Control,
    *,
    padding: int | ft.Padding = 0,
    margin: int | ft.Margin | None = None,
    on_click: object = None,
    **kwargs,
) -> ft.Container:
    """Wrap *content* in a card with soft shadow and refined border."""
    return ft.Container(
        content=content,
        padding=padding,
        margin=margin or ft.Margin.symmetric(horizontal=16, vertical=4),
        border_radius=RADIUS_LG,
        border=ft.Border.all(
            1, ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        ),
        shadow=ft.BoxShadow(
            blur_radius=8,
            spread_radius=-2,
            color=ft.Colors.with_opacity(0.04, ft.Colors.BLACK),
            offset=ft.Offset(0, 2),
        ),
        on_click=on_click,
        **kwargs,
    )


# ---- Section card (settings / config pages) -------------------------------

def make_section_card(content: ft.Control, **kwargs) -> ft.Container:
    """Card variant used for full-width settings sections."""
    return make_card(content, padding=0, **kwargs)


# ---- Buttons --------------------------------------------------------------

_BUTTON_SHAPE = ft.ContinuousRectangleBorder(radius=28)


def make_button(
    text: str,
    *,
    icon: str | None = None,
    on_click: object = None,
    color: str | None = None,
    bgcolor: str | None = None,
    **kwargs,
) -> ft.Button:
    """Primary filled button with pill shape."""
    return ft.Button(
        content=text,
        icon=icon,
        on_click=on_click,
        color=color,
        bgcolor=bgcolor,
        style=ft.ButtonStyle(
            shape=_BUTTON_SHAPE,
            padding=ft.Padding.symmetric(horizontal=20, vertical=10),
        ),
        **kwargs,
    )


def make_outlined_button(
    text: str,
    *,
    icon: str | None = None,
    on_click: object = None,
    **kwargs,
) -> ft.Button:
    """Unified button style (same as primary pill button)."""
    return ft.Button(
        content=text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            shape=_BUTTON_SHAPE,
            padding=ft.Padding.symmetric(horizontal=20, vertical=10),
        ),
        **kwargs,
    )


def make_text_button(
    text: str,
    *,
    on_click: object = None,
    **kwargs,
) -> ft.TextButton:
    """Subtle text button with pill shape."""
    return ft.TextButton(
        text,
        on_click=on_click,
        style=ft.ButtonStyle(
            shape=_BUTTON_SHAPE,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        ),
        **kwargs,
    )


def make_icon_button(
    icon: str,
    *,
    tooltip: str | None = None,
    on_click: object = None,
    icon_size: int = 18,
    icon_color: str | None = None,
    **kwargs,
) -> ft.IconButton:
    """Consistent icon button with compact padding."""
    return ft.IconButton(
        icon=icon,
        tooltip=tooltip,
        on_click=on_click,
        icon_size=icon_size,
        icon_color=icon_color,
        style=ft.ButtonStyle(padding=6, shape=ft.CircleBorder()),
        **kwargs,
    )


def make_danger_button(
    text: str,
    *,
    icon: str | None = None,
    on_click: object = None,
    **kwargs,
) -> ft.Button:
    """Destructive action button (red)."""
    return ft.Button(
        content=text,
        icon=icon,
        on_click=on_click,
        color=ft.Colors.WHITE,
        bgcolor=ERROR_RED,
        style=ft.ButtonStyle(
            shape=_BUTTON_SHAPE,
            padding=ft.Padding.symmetric(horizontal=20, vertical=10),
        ),
        **kwargs,
    )


# ---- Badge / status tag ---------------------------------------------------

def make_badge(
    text: str,
    *,
    color: str = "#ffffff",
    bgcolor: str = SUCCESS_GREEN,
    icon: str | None = None,
    size: int = 10,
) -> ft.Container:
    """Small pill-shaped status badge (success / warning / error / info)."""
    row_controls: list[ft.Control] = []
    if icon:
        row_controls.append(ft.Icon(icon, size=size + 2, color=color))
    row_controls.append(
        ft.Text(text, size=size, weight=ft.FontWeight.BOLD, color=color),
    )
    return ft.Container(
        content=ft.Row(controls=row_controls, spacing=4, tight=True),
        bgcolor=bgcolor,
        border_radius=6,
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
    )


def make_success_badge(text: str, **kw) -> ft.Container:
    return make_badge(text, bgcolor=SUCCESS_GREEN, **kw)


def make_warning_badge(text: str, **kw) -> ft.Container:
    return make_badge(text, bgcolor=WARNING_AMBER, **kw)


def make_error_badge(text: str, **kw) -> ft.Container:
    return make_badge(text, bgcolor=ERROR_RED, **kw)


def make_info_badge(text: str, **kw) -> ft.Container:
    return make_badge(text, bgcolor=ACCENT_BLUE, **kw)


# ---- Dialog ---------------------------------------------------------------

def make_dialog(
    *,
    title: str,
    content: ft.Control,
    actions: list[ft.Control] | None = None,
    **kwargs,
) -> ft.AlertDialog:
    """Consistently styled AlertDialog with rounded corners."""
    return ft.AlertDialog(
        title=ft.Text(title, weight=ft.FontWeight.W_600),
        content=content,
        actions=actions or [],
        shape=ft.ContinuousRectangleBorder(radius=32),
        **kwargs,
    )


def make_form_dialog(
    *,
    title: str,
    content: ft.Control,
    actions: list[ft.Control] | None = None,
    subtitle: str | None = None,
    icon: str | None = None,
    width: int = 640,
    **kwargs,
) -> ft.AlertDialog:
    """Modern form dialog with grouped layout and flexible styling."""
    header_controls: list[ft.Control] = []
    if icon:
        header_controls.append(
            ft.Container(
                content=ft.Icon(icon, size=16, color=ft.Colors.PRIMARY),
                width=28,
                height=28,
                border_radius=14,
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
                alignment=ft.Alignment.CENTER,
            ),
        )
    header_controls.append(
        ft.Column(
            controls=[
                ft.Text(title, size=17, weight=ft.FontWeight.W_600),
                ft.Text(subtitle, size=12, opacity=0.68, visible=bool(subtitle)),
            ],
            spacing=2,
            expand=True,
        ),
    )
    return ft.AlertDialog(
        modal=True,
        bgcolor=ft.Colors.SURFACE,
        shape=ft.RoundedRectangleBorder(radius=22),
        inset_padding=ft.Padding.symmetric(horizontal=24, vertical=20),
        content_padding=ft.Padding.only(left=20, right=20, top=16, bottom=12),
        actions_padding=ft.Padding.only(left=16, right=16, top=8, bottom=14),
        action_button_padding=0,
        actions_alignment=ft.MainAxisAlignment.END,
        scrollable=True,
        content=ft.Container(
            width=width,
            content=ft.Column(
                controls=[
                    ft.Row(controls=header_controls, spacing=10),
                    ft.Divider(height=1, color=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE)),
                    content,
                ],
                spacing=12,
                tight=True,
            ),
        ),
        actions=actions or [],
        **kwargs,
    )


# ---- Empty state placeholder ----------------------------------------------

def make_empty_state(
    icon: str,
    text: str,
    *,
    hint: str | None = None,
    icon_size: int = 40,
    icon_opacity: float = 0.2,
) -> ft.Container:
    """Centered placeholder shown when a list or panel has no content."""
    controls: list[ft.Control] = [
        ft.Icon(icon, size=icon_size, opacity=icon_opacity),
        ft.Text(text, size=13, opacity=0.5, text_align=ft.TextAlign.CENTER),
    ]
    if hint:
        controls.append(
            ft.Text(hint, size=11, opacity=0.35, text_align=ft.TextAlign.CENTER),
        )
    return ft.Container(
        content=ft.Column(
            controls=controls,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )


# ---- Confirm dialog -------------------------------------------------------

def make_confirm_dialog(
    *,
    title: str,
    content: str,
    confirm_label: str,
    cancel_label: str,
    on_confirm: object,
    on_cancel: object,
    danger: bool = False,
) -> ft.AlertDialog:
    """Pre-built confirmation dialog (e.g. delete actions).

    When *danger* is True the confirm button uses the destructive style.
    """
    confirm_btn = (
        make_danger_button(confirm_label, on_click=on_confirm)
        if danger
        else make_button(confirm_label, on_click=on_confirm)
    )
    return make_dialog(
        title=title,
        content=ft.Text(content),
        actions=[
            make_text_button(cancel_label, on_click=on_cancel),
            confirm_btn,
        ],
    )


# ---- Snack-bar helper ------------------------------------------------------

def show_snackbar(page: ft.Page, message: str, *, bgcolor: str | None = None) -> None:
    """Display a brief notification at the bottom of the page."""
    snack = ft.SnackBar(content=ft.Text(message), duration=3000)
    if bgcolor:
        snack.bgcolor = bgcolor
    page.overlay.append(snack)
    snack.open = True
    page.update()


# ---- Divider --------------------------------------------------------------

def make_divider() -> ft.Divider:
    """Subtle horizontal divider."""
    return ft.Divider(
        height=1,
        color=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
    )


# ---- Code block theme (GitHub Dark / One Dark Pro palettes) ---------------

CODE_THEME_GITHUB_DARK = {
    "bg": "#0d1117",
    "keyword": "#ff7b72",
    "function": "#d2a8ff",
    "string": "#a5d6ff",
    "comment": "#8b949e",
    "number": "#79c0ff",
}

CODE_THEME_ONE_DARK = {
    "bg": "#282c34",
    "keyword": "#c678dd",
    "function": "#61afef",
    "string": "#98c379",
    "comment": "#5c6370",
    "number": "#d19a66",
}


# ---------------------------------------------------------------------------
# Page-level theme application
# ---------------------------------------------------------------------------

def apply_theme(page: ft.Page, mode: str, accent: str = ACCENT_BLUE) -> None:
    """Apply a theme mode to the Flet page.

    Args:
        page: The Flet page to theme.
        mode: One of "system", "light", or "dark".
        accent: Hex color string for the accent color.
    """
    page.theme = get_light_theme(accent)
    page.dark_theme = get_dark_theme(accent)

    if mode == "dark":
        page.theme_mode = ft.ThemeMode.DARK
    elif mode == "light":
        page.theme_mode = ft.ThemeMode.LIGHT
    else:
        page.theme_mode = ft.ThemeMode.SYSTEM
