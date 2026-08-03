from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a JSON configuration object from disk."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_timeout(config: dict[str, Any]) -> int:
    """Return the positive integer request timeout."""
    timeout = config.get("timeout", 30)
    if not isinstance(timeout, int) or timeout <= 0:
        raise ValueError("timeout must be a positive integer")
    return timeout
