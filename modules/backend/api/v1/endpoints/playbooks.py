"""
Playbook and Mission API endpoints.

Provides endpoints for listing playbooks, creating missions,
and monitoring mission status.
"""

from fastapi import APIRouter

from modules.backend.core.dependencies import DbSession, RequestId
from modules.backend.core.exceptions import NotFoundError
from modules.backend.schemas.base import ApiResponse
from modules.backend.schemas.mission import (
    MissionCreate,
    MissionDetailResponse,
    MissionResponse,
)
from modules.backend.schemas.playbook import (
    PlaybookDetailResponse,
    PlaybookListResponse,
)
from modules.backend.services.mission import MissionService
from modules.backend.services.playbook import PlaybookService

router = APIRouter()


def _get_playbook_service() -> PlaybookService:
    return PlaybookService()


def _get_mission_service(db: DbSession) -> MissionService:
    return MissionService(session=db)


# ---- Playbook endpoints ----


@router.get("", response_model=ApiResponse, summary="List playbooks")
async def list_playbooks(
    request_id: RequestId,
    enabled_only: bool = True,
) -> ApiResponse:
    """List available playbooks."""
    service = _get_playbook_service()
    playbooks = service.list_playbooks(enabled_only=enabled_only)

    items = [
        PlaybookListResponse(
            playbook_name=p.playbook_name,
            description=p.description,
            version=p.version,
            enabled=p.enabled,
            trigger_type=p.trigger.type,
            step_count=len(p.steps),
            budget_usd=p.budget.max_cost_usd,
            objective_category=p.objective.category,
            objective_priority=p.objective.priority,
            objective_owner=p.objective.owner,
        )
        for p in playbooks
    ]

    return ApiResponse(
        success=True,
        data={"playbooks": [item.model_dump() for item in items]},
        metadata={"request_id": request_id, "count": len(items)},
    )


@router.get(
    "/{playbook_name}",
    response_model=ApiResponse,
    summary="Get playbook detail",
)
async def get_playbook(
    playbook_name: str,
    request_id: RequestId,
) -> ApiResponse:
    """Get a specific playbook with full details."""
    service = _get_playbook_service()
    playbook = service.get_playbook(playbook_name)

    if not playbook:
        raise NotFoundError(
            message=f"Playbook '{playbook_name}' not found",
        )

    detail = PlaybookDetailResponse(
        playbook_name=playbook.playbook_name,
        description=playbook.description,
        objective=playbook.objective,
        version=playbook.version,
        enabled=playbook.enabled,
        trigger=playbook.trigger,
        budget=playbook.budget,
        context_keys=list(playbook.context.keys()),
        steps=playbook.steps,
    )

    return ApiResponse(
        success=True,
        data=detail.model_dump(),
        metadata={"request_id": request_id},
    )


# ---- Mission endpoints ----


@router.post(
    "/missions",
    response_model=ApiResponse,
    summary="Create ad-hoc mission",
)
async def create_mission(
    data: MissionCreate,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Create and start an ad-hoc mission."""
    from uuid import uuid4

    service = _get_mission_service(db)
    session_id = str(uuid4())

    mission = await service.create_adhoc_mission(
        objective=data.objective,
        triggered_by=data.triggered_by,
        session_id=session_id,
        roster_ref=data.roster_ref,
        complexity_tier=data.complexity_tier,
        cost_ceiling_usd=data.cost_ceiling_usd,
        upstream_context=data.upstream_context,
    )

    response = MissionResponse.model_validate(mission)
    return ApiResponse(
        success=True,
        data=response.model_dump(),
        metadata={"request_id": request_id},
    )


@router.get(
    "/missions",
    response_model=ApiResponse,
    summary="List missions",
)
async def list_missions(
    db: DbSession,
    request_id: RequestId,
    status: str | None = None,
    playbook_run_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ApiResponse:
    """List missions with optional filters."""
    service = _get_mission_service(db)
    missions, total = await service.list_missions(
        status=status,
        playbook_run_id=playbook_run_id,
        limit=limit,
        offset=offset,
    )

    items = [MissionResponse.model_validate(m).model_dump() for m in missions]
    return ApiResponse(
        success=True,
        data={"missions": items, "total": total},
        metadata={"request_id": request_id},
    )


@router.get(
    "/missions/{mission_id}",
    response_model=ApiResponse,
    summary="Get mission detail",
)
async def get_mission(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Get detailed mission info including context and results."""
    service = _get_mission_service(db)
    mission = await service.get_mission(mission_id)

    response = MissionDetailResponse.model_validate(mission)
    return ApiResponse(
        success=True,
        data=response.model_dump(),
        metadata={"request_id": request_id},
    )


@router.post(
    "/missions/{mission_id}/cancel",
    response_model=ApiResponse,
    summary="Cancel mission",
)
async def cancel_mission(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
    reason: str = "User cancelled",
) -> ApiResponse:
    """Cancel a running or pending mission."""
    service = _get_mission_service(db)
    mission = await service.cancel_mission(mission_id, reason=reason)

    response = MissionResponse.model_validate(mission)
    return ApiResponse(
        success=True,
        data=response.model_dump(),
        metadata={"request_id": request_id},
    )
