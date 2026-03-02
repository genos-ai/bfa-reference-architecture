"""
FastAPI Dependencies.

Shared dependencies for request handling.
"""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.database import get_db_session

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_request_id(x_request_id: str | None = Header(None)) -> str:
    """Extract or generate request ID from headers."""
    import uuid

    return x_request_id or str(uuid.uuid4())


RequestId = Annotated[str, Depends(get_request_id)]


async def get_event_bus():
    """FastAPI dependency for session event bus."""
    from redis.asyncio import Redis as AsyncRedis

    from modules.backend.core.config import get_redis_url
    from modules.backend.events.bus import SessionEventBus

    redis = AsyncRedis.from_url(get_redis_url())
    try:
        yield SessionEventBus(redis)
    finally:
        await redis.close()
