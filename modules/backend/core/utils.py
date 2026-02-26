"""
Core Utilities.

Shared utility functions used across the backend.
All modules should import utilities from this module.
"""

from datetime import datetime, timezone


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
        __import__('time').time(), tz=timezone.utc
    ).replace(tzinfo=None)
