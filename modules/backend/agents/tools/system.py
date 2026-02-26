"""
Shared system tool implementations.

Pure functions for system health checking and application metadata.
No PydanticAI dependency.
"""

import asyncio
from typing import Any


async def check_system_health() -> dict:
    """Check the health of all backend services (database, Redis).

    Returns:
        Dict with component names as keys and status dicts as values.
    """
    from modules.backend.api.health import check_database, check_redis

    db_check, redis_check = await asyncio.gather(
        check_database(),
        check_redis(),
        return_exceptions=True,
    )

    if isinstance(db_check, Exception):
        db_check = {"status": "error", "error": str(db_check)}
    if isinstance(redis_check, Exception):
        redis_check = {"status": "error", "error": str(redis_check)}

    return {
        "database": db_check,
        "redis": redis_check,
    }


async def get_app_info(app_config: Any) -> dict:
    """Get application metadata from configuration.

    Args:
        app_config: The application config object (from get_app_config()).

    Returns:
        Dict with name, version, environment, and debug status.
    """
    app = app_config.application
    return {
        "name": app.name,
        "version": app.version,
        "environment": app.environment,
        "debug": app.debug,
    }
