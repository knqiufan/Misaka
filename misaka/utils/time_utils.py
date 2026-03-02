"""
Time formatting utilities for Misaka.

Provides reusable time/date formatting functions used across
UI components (chat list, message items, import dialog, etc.).
"""

from __future__ import annotations

from datetime import date, datetime, timezone


def format_relative_time(iso_str: str) -> str:
    """Format an ISO datetime string to a human-readable relative time.

    Examples: "5s ago", "3m ago", "2h ago", "4d ago", "1mo ago", "2y ago".
    Falls back to the date portion on parse failure.
    """
    if not iso_str:
        return ""
    try:
        cleaned = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        total_seconds = int((now - dt).total_seconds())
        if total_seconds < 0:
            return iso_str[:10]
        if total_seconds < 60:
            return f"{total_seconds}s ago"
        minutes = total_seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        months = days // 30
        if months < 12:
            return f"{months}mo ago"
        return f"{days // 365}y ago"
    except (ValueError, TypeError, AttributeError):
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


def format_short_time(iso_str: str) -> str:
    """Extract HH:MM from an ISO datetime string.

    Returns the time portion only (e.g. "14:30").
    """
    if not iso_str:
        return ""
    try:
        if "T" in iso_str:
            return iso_str.split("T")[1][:5]
        return iso_str[:16]
    except (IndexError, ValueError):
        return ""


def format_date_or_time(iso_str: str) -> str:
    """Format to HH:MM if today, otherwise MM-DD.

    Used in chat list sidebar to show recent timestamps compactly.
    """
    if not iso_str:
        return ""
    try:
        if "T" in iso_str:
            parts = iso_str.split("T")
            date_part = parts[0]
            time_part = parts[1][:5]
            today = date.today().isoformat()
            if date_part == today:
                return time_part
            return date_part[5:]  # MM-DD
        return iso_str[:10]
    except (IndexError, ValueError):
        return ""
