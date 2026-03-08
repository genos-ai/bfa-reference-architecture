"""
API Version 1 Router.

Aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

from modules.backend.api.v1.endpoints import agents, missions, notes, playbooks, sessions

router = APIRouter()

# Notes endpoints
router.include_router(notes.router, prefix="/notes", tags=["notes"])

# Agent endpoints
router.include_router(agents.router, prefix="/agents", tags=["agents"])

# Session endpoints
router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])

# Mission record endpoints (audit, history, cost)
router.include_router(missions.router, prefix="/missions", tags=["missions"])

# Playbook and mission endpoints
router.include_router(playbooks.router, prefix="/playbooks", tags=["playbooks"])
