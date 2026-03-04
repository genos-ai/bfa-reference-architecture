"""
API Version 1 Router.

Aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

from modules.backend.api.v1.endpoints import agents, notes, sessions

router = APIRouter()

# Notes endpoints
router.include_router(notes.router, prefix="/notes", tags=["notes"])

# Agent endpoints
router.include_router(agents.router, prefix="/agents", tags=["agents"])

# Session endpoints
router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
