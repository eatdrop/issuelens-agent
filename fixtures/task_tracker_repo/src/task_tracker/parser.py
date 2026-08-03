from __future__ import annotations

from datetime import datetime


def parse_due_date(raw_value: str | None) -> datetime | None:
    """Parse an optional ISO date used by the task tracker."""
    if raw_value is None:
        return None
    return datetime.fromisoformat(raw_value)
