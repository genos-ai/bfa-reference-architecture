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
