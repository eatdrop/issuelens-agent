from __future__ import annotations

import re


def slugify(value: str) -> str:
    """Create an ASCII-oriented URL slug."""
    normalized = value.strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def truncate(value: str, limit: int) -> str:
    """Truncate text to a non-negative character limit."""
    return value[:limit]
