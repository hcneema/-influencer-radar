"""Parse human-readable date range strings into a since datetime."""
from __future__ import annotations
import re
from datetime import datetime, timedelta, timezone


def parse_since(value: str) -> datetime:
    """
    Parse a --since argument into a UTC datetime.

    Accepted formats:
      3d   → 3 days ago
      2w   → 2 weeks ago
      6m   → 6 months ago (approx: 30 days each)
      1y   → 1 year ago (approx: 365 days)
      2022-01-15 → exact date (midnight UTC)

    Returns a timezone-aware UTC datetime.
    """
    value = value.strip().lower()

    m = re.fullmatch(r"(\d+)([dwmy])", value)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = {"d": n, "w": n * 7, "m": n * 30, "y": n * 365}[unit]
        return datetime.now(timezone.utc) - timedelta(days=days)

    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    raise ValueError(
        f"Cannot parse --since value: '{value}'. "
        "Use formats like: 3d, 2w, 6m, 1y, or 2022-01-15"
    )


def reddit_time_filter(since: datetime | None) -> str:
    """
    Map a since datetime to Reddit's nearest time_filter preset.
    Reddit only supports: hour, day, week, month, year, all.
    We pick the smallest bucket that fully covers the requested range.
    """
    if since is None:
        return "all"
    delta = datetime.now(timezone.utc) - since
    days = delta.total_seconds() / 86400
    if days <= 1:
        return "day"
    elif days <= 7:
        return "week"
    elif days <= 31:
        return "month"
    elif days <= 365:
        return "year"
    return "all"


def to_rfc3339(dt: datetime) -> str:
    """Format a datetime as RFC 3339 for YouTube API publishedAfter."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
