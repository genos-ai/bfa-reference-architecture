"""
Mission Record API endpoints.

Read endpoints for querying mission execution history,
decisions, and cost breakdowns. Write operations happen via
the MissionPersistenceService called from the dispatch loop.

Temporal endpoints (execute, approve, status) are gated by
the temporal.enabled feature flag.
"""

from fastapi import APIRouter

from modules.backend.core.dependencies import DbSession, RequestId
from modules.backend.core.exceptions import NotFoundError
from modules.backend.schemas.base import ApiResponse
from modules.backend.schemas.mission_record import (
    MissionCostBreakdown,
    MissionDecisionResponse,
    MissionListResponse,
    MissionRecordDetailResponse,
    MissionRecordResponse,
)
from modules.backend.services.mission_persistence import MissionPersistenceService

router = APIRouter()


@router.get("", response_model=ApiResponse, summary="List mission records")
async def list_missions(
    db: DbSession,
    request_id: RequestId,
    status: str | None = None,
    roster_name: str | None = None,
    objective_category: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ApiResponse:
    """List mission execution records with optional filters."""
    service = MissionPersistenceService(db)
    missions, total = await service.list_missions(
        status=status,
        roster_name=roster_name,
        objective_category=objective_category,
        limit=limit,
        offset=offset,
    )

    return ApiResponse(
        success=True,
        data=MissionListResponse(
            missions=[MissionRecordResponse.model_validate(m) for m in missions],
            total=total,
            page_size=limit,
            offset=offset,
        ).model_dump(),
        metadata={"request_id": request_id},
    )


@router.get(
    "/{mission_id}",
    response_model=ApiResponse,
    summary="Get mission record detail",
)
async def get_mission(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Get a mission record with full execution details."""
    service = MissionPersistenceService(db)
    mission = await service.get_mission(mission_id)

    if not mission:
        raise NotFoundError(f"Mission '{mission_id}' not found")

    response = MissionRecordDetailResponse.model_validate(mission)
    return ApiResponse(
        success=True,
        data=response.model_dump(),
        metadata={"request_id": request_id},
    )


@router.get(
    "/{mission_id}/decisions",
    response_model=ApiResponse,
    summary="Get mission decision audit trail",
)
async def get_mission_decisions(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Get the decision audit trail for a mission."""
    service = MissionPersistenceService(db)

    mission = await service.get_mission(mission_id)
    if not mission:
        raise NotFoundError(f"Mission '{mission_id}' not found")

    decisions = await service.get_decisions(mission_id)
    items = [
        MissionDecisionResponse.model_validate(d).model_dump()
        for d in decisions
    ]

    return ApiResponse(
        success=True,
        data={"decisions": items, "count": len(items)},
        metadata={"request_id": request_id},
    )


@router.get(
    "/{mission_id}/cost",
    response_model=ApiResponse,
    summary="Get mission cost breakdown",
)
async def get_mission_cost(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Get detailed cost breakdown for a mission."""
    service = MissionPersistenceService(db)
    breakdown = await service.get_cost_breakdown(mission_id)

    return ApiResponse(
        success=True,
        data=breakdown.model_dump(),
        metadata={"request_id": request_id},
    )


# =============================================================================
# Mission execution
# =============================================================================


@router.post(
    "/{mission_id}/execute",
    response_model=ApiResponse,
    summary="Execute a mission",
)
async def execute_mission(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Execute a mission. Uses Temporal when enabled, direct dispatch otherwise."""
    from modules.backend.core.config import get_app_config

    config = get_app_config()

    if config.temporal.enabled:
        return await _execute_via_temporal(mission_id, db, request_id, config)

    return await _execute_direct(mission_id, db, request_id)


async def _execute_direct(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Direct mission execution via handle_mission()."""
    from modules.backend.agents.mission_control.dispatch_adapter import (
        MissionControlDispatchAdapter,
    )
    from modules.backend.services.mission import MissionService
    from modules.backend.services.session import SessionService

    session_service = SessionService(db)
    adapter = MissionControlDispatchAdapter(
        session_service=session_service,
        db_session=db,
    )
    service = MissionService(
        session=db,
        mission_control_dispatch=adapter,
        session_service=session_service,
    )

    mission = await service.execute_mission(mission_id)

    from modules.backend.schemas.mission import MissionResponse
    response = MissionResponse.model_validate(mission)
    return ApiResponse(
        success=True,
        data=response.model_dump(),
        metadata={"request_id": request_id},
    )


async def _execute_via_temporal(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
    config,
) -> ApiResponse:
    """Temporal-based mission execution."""
    from modules.backend.temporal.client import get_temporal_client
    from modules.backend.temporal.models import MissionWorkflowInput
    from modules.backend.temporal.workflow import AgentMissionWorkflow

    # Need the mission record for brief and roster
    service = MissionPersistenceService(db)
    mission_record = await service.get_mission(mission_id)
    brief = ""
    roster = "default"
    budget = 10.0
    if mission_record:
        brief = mission_record.objective_statement or ""
        roster = mission_record.roster_name or "default"
        budget = mission_record.total_cost_usd or 10.0

    client = await get_temporal_client()
    handle = await client.start_workflow(
        AgentMissionWorkflow.run,
        MissionWorkflowInput(
            mission_id=mission_id,
            session_id=mission_id,
            mission_brief=brief,
            roster_name=roster,
            mission_budget_usd=budget,
        ),
        id=f"mission-{mission_id}",
        task_queue=config.temporal.task_queue,
    )

    return ApiResponse(
        success=True,
        data={
            "workflow_id": handle.id,
            "mission_id": mission_id,
            "status": "started",
        },
        metadata={"request_id": request_id},
    )


@router.post(
    "/{mission_id}/approve",
    response_model=ApiResponse,
    summary="Submit approval for a mission",
)
async def submit_approval(
    mission_id: str,
    decision: str,
    responder_id: str,
    request_id: RequestId,
    reason: str | None = None,
) -> ApiResponse:
    """Send an approval decision to a waiting Temporal workflow."""
    from modules.backend.core.config import get_app_config

    config = get_app_config()
    if not config.temporal.enabled:
        return ApiResponse(
            success=False,
            data={
                "error": "temporal_not_enabled",
                "message": "Approval signals require Temporal.",
            },
            metadata={"request_id": request_id},
        )

    from modules.backend.temporal.client import get_temporal_client
    from modules.backend.temporal.models import ApprovalDecision
    from modules.backend.temporal.workflow import AgentMissionWorkflow

    client = await get_temporal_client()
    handle = client.get_workflow_handle(f"mission-{mission_id}")

    await handle.signal(
        AgentMissionWorkflow.submit_approval,
        ApprovalDecision(
            decision=decision,
            responder_type="human",
            responder_id=responder_id,
            reason=reason,
        ),
    )

    return ApiResponse(
        success=True,
        data={
            "mission_id": mission_id,
            "decision": decision,
            "status": "signal_sent",
        },
        metadata={"request_id": request_id},
    )


@router.get(
    "/{mission_id}/status",
    response_model=ApiResponse,
    summary="Get mission execution status",
)
async def get_mission_status(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Get mission status — Temporal Query or DB fallback."""
    from modules.backend.core.config import get_app_config

    config = get_app_config()

    if config.temporal.enabled:
        try:
            from modules.backend.temporal.client import get_temporal_client
            from modules.backend.temporal.workflow import AgentMissionWorkflow

            client = await get_temporal_client()
            handle = client.get_workflow_handle(f"mission-{mission_id}")
            status = await handle.query(AgentMissionWorkflow.get_status)
            return ApiResponse(
                success=True,
                data={
                    "source": "temporal",
                    "mission_id": status.mission_id,
                    "workflow_status": status.workflow_status,
                    "mission_status": status.mission_status,
                    "total_cost_usd": status.total_cost_usd,
                    "waiting_for_approval": status.waiting_for_approval,
                    "error": status.error,
                },
                metadata={"request_id": request_id},
            )
        except Exception:
            pass  # Fall through to DB query

    # Fallback: direct DB query
    service = MissionPersistenceService(db)
    try:
        status_dict = await service.get_mission_status(mission_id)
        return ApiResponse(
            success=True,
            data={"source": "database", **status_dict},
            metadata={"request_id": request_id},
        )
    except Exception:
        raise NotFoundError(f"Mission '{mission_id}' not found")
