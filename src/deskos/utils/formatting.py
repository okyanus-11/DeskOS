"""Human readable formatting helpers shared by widgets and apps."""

from __future__ import annotations

import time
from datetime import datetime


def format_bytes(value: float | int | None, precision: int = 1) -> str:
    if value is None:
        return "—"
    size = float(value)
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024.0
        index += 1
    if index == 0:
        return f"{int(size)} {units[index]}"
    return f"{size:.{precision}f} {units[index]}"


def format_rate(bytes_per_second: float | None) -> str:
    if bytes_per_second is None:
        return "—"
    return f"{format_bytes(bytes_per_second)}/s"


def format_percent(value: float | None, precision: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:.{precision}f}%"


def format_duration(seconds: float | int | None) -> str:
    """Format a duration as ``1d 04h 12m`` style text."""
    if seconds is None:
        return "—"
    total = max(0, int(seconds))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m"
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def format_stopwatch(milliseconds: int) -> str:
    total_ms = max(0, int(milliseconds))
    minutes, remainder = divmod(total_ms, 60_000)
    seconds, centis = divmod(remainder, 1000)
    return f"{minutes:02d}:{seconds:02d}.{centis // 10:02d}"


def format_timer(seconds_remaining: int) -> str:
    total = max(0, int(seconds_remaining))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def truncate(text: str, length: int = 80, suffix: str = "…") -> str:
    if len(text) <= length:
        return text
    return text[: max(0, length - len(suffix))].rstrip() + suffix


def relative_time(iso_timestamp: str | None) -> str:
    """Format an ISO-8601 timestamp relative to now."""
    if not iso_timestamp:
        return "—"
    try:
        moment = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return iso_timestamp
    delta = time.time() - moment.timestamp()
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)} min ago"
    if delta < 86400:
        return f"{int(delta // 3600)} h ago"
    if delta < 604800:
        return f"{int(delta // 86400)} d ago"
    return moment.strftime("%Y-%m-%d")
