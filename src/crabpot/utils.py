"""Shared utility functions for CrabPot."""

from datetime import datetime
from typing import Optional


def format_uptime(start_time_iso: Optional[str]) -> str:
    """Format a container start time (ISO 8601) as a human-readable uptime string."""
    if not start_time_iso:
        return "--"
    try:
        start_dt = datetime.fromisoformat(start_time_iso.replace("Z", "+00:00"))
        delta = datetime.now(start_dt.tzinfo) - start_dt
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return "--"

        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    except (ValueError, TypeError):
        return "--"
