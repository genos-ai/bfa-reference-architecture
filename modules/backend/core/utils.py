"""
Core Utilities.

Shared utility functions used across the backend.
All modules should import utilities from this module.
"""

import json as _json
import time
from datetime import datetime, timezone
from typing import Any


def estimate_tokens(data: Any) -> int:
    """Estimate token count for a data structure.

    Uses ~4 chars per token heuristic for JSON-serialized data.
    Accepts dicts, lists, strings, or any JSON-serializable value.
    """
    serialized = _json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
    return len(serialized) // 4


def utc_now() -> datetime:
    """
    Return current UTC time as timezone-naive datetime.

    All datetime values in the application should be timezone-naive
    and assumed to be UTC. This ensures consistent behavior across
    the codebase and simplifies database storage.

    Returns:
        Current UTC time with tzinfo stripped
    """
    return datetime.fromtimestamp(
        time.time(), tz=timezone.utc
    ).replace(tzinfo=None)
