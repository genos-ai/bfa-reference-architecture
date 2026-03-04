"""Session management REST endpoints."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from modules.backend.core.dependencies import DbSession, RequestId
from modules.backend.core.pagination import (
    PaginationParams,
    create_paginated_response,
    get_pagination_params,
)
from modules.backend.schemas.base import ApiResponse
from modules.backend.schemas.session import (
    ChannelBindRequest,
    ChannelResponse,
    SessionCreate,
    SessionListResponse,
    SessionMessageCreate,
    SessionMessageResponse,
    SessionResponse,
    SessionUpdate,
)
from modules.backend.services.session import SessionService

router = APIRouter()


def _to_response(session) -> SessionResponse:
    """Convert Session model to SessionResponse with computed fields."""
    resp = SessionResponse.model_validate(session)
    if session.cost_budget_usd is not None:
        resp.budget_remaining_usd = max(
            0.0, session.cost_budget_usd - session.total_cost_usd
        )
    return resp


# --- Session CRUD ---


@router.post(
    "",
    response_model=ApiResponse[SessionResponse],
    status_code=201,
    summary="Create a session",
    description="Create a new interactive session with optional goal, agent, and cost budget.",
)
async def create_session(
    data: SessionCreate,
    db: DbSession,
    request_id: RequestId,
    user_id: str | None = Query(default=None, description="Owner user ID (temporary — will come from auth context)"),
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.create_session(data, user_id=user_id)
    return ApiResponse(data=_to_response(session))


@router.get(
    "/{session_id}",
    response_model=ApiResponse[SessionResponse],
    summary="Get a session",
    description="Get a session by ID with current cost and status.",
)
async def get_session(
    session_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.get_session(session_id)
    return ApiResponse(data=_to_response(session))


@router.patch(
    "/{session_id}",
    response_model=ApiResponse[SessionResponse],
    summary="Update a session",
    description="Update session fields (goal, agent, budget, metadata).",
)
async def update_session(
    session_id: str,
    data: SessionUpdate,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.update_session(session_id, data)
    return ApiResponse(data=_to_response(session))


@router.get(
    "",
    summary="List sessions",
    description="List sessions for the current user with optional status filter.",
)
async def list_sessions(
    db: DbSession,
    request_id: RequestId,
    pagination: PaginationParams = Depends(get_pagination_params),
    user_id: str | None = Query(default=None, description="Filter by user ID"),
    status: str | None = Query(default=None, description="Filter by status"),
) -> dict:
    service = SessionService(db)
    sessions, total = await service.list_sessions(
        user_id=user_id,
        status_filter=status,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return create_paginated_response(
        items=sessions,
        item_schema=SessionListResponse,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        request_id=request_id,
    )


# --- State Transitions ---


@router.post(
    "/{session_id}/suspend",
    response_model=ApiResponse[SessionResponse],
    summary="Suspend a session",
    description="Suspend a session — pauses for human/AI input or approval.",
)
async def suspend_session(
    session_id: str,
    db: DbSession,
    request_id: RequestId,
    reason: str = Query(..., description="Reason for suspension"),
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.suspend_session(session_id, reason)
    return ApiResponse(data=_to_response(session))


@router.post(
    "/{session_id}/resume",
    response_model=ApiResponse[SessionResponse],
    summary="Resume a session",
    description="Resume a suspended session.",
)
async def resume_session(
    session_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.resume_session(session_id)
    return ApiResponse(data=_to_response(session))


@router.post(
    "/{session_id}/complete",
    response_model=ApiResponse[SessionResponse],
    summary="Complete a session",
    description="Mark a session as completed — goal achieved or user ended.",
)
async def complete_session(
    session_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.complete_session(session_id)
    return ApiResponse(data=_to_response(session))


# --- Channel Binding ---


@router.post(
    "/{session_id}/channels",
    response_model=ApiResponse[ChannelResponse],
    status_code=201,
    summary="Bind a channel",
    description="Bind a communication channel to this session.",
)
async def bind_channel(
    session_id: str,
    data: ChannelBindRequest,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[ChannelResponse]:
    service = SessionService(db)
    binding = await service.bind_channel(session_id, data.channel_type, data.channel_id)
    return ApiResponse(data=ChannelResponse.model_validate(binding))


@router.delete(
    "/{session_id}/channels/{channel_type}/{channel_id}",
    status_code=204,
    summary="Unbind a channel",
    description="Unbind a communication channel from this session.",
)
async def unbind_channel(
    session_id: str,
    channel_type: str,
    channel_id: str,
    db: DbSession,
    request_id: RequestId,
) -> None:
    service = SessionService(db)
    await service.unbind_channel(session_id, channel_type, channel_id)


@router.get(
    "/by-channel/{channel_type}/{channel_id}",
    response_model=ApiResponse[SessionResponse],
    summary="Find session by channel",
    description="Find the active session bound to a specific channel.",
)
async def get_session_by_channel(
    channel_type: str,
    channel_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.get_session_by_channel(channel_type, channel_id)
    return ApiResponse(data=_to_response(session))


# --- Messages ---


@router.get(
    "/{session_id}/messages",
    summary="Get session messages",
    description="Get conversation history for a session.",
)
async def get_messages(
    session_id: str,
    db: DbSession,
    request_id: RequestId,
    pagination: PaginationParams = Depends(get_pagination_params),
) -> dict:
    service = SessionService(db)
    messages, total = await service.get_messages(
        session_id, limit=pagination.limit, offset=pagination.offset
    )
    return create_paginated_response(
        items=messages,
        item_schema=SessionMessageResponse,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        request_id=request_id,
    )


# --- Streaming ---


@router.post(
    "/{session_id}/messages",
    summary="Send message and stream events",
    description="Send a message to the session and stream agent progress events as SSE.",
)
async def send_message_stream(
    session_id: str,
    data: SessionMessageCreate,
    db: DbSession,
) -> StreamingResponse:
    """Send a message to a session and stream events as SSE."""
    from modules.backend.agents.mission_control.mission_control import handle

    service = SessionService(db)

    async def generate():
        async for event in handle(
            session_id,
            data.content,
            session_service=service,
            sender_id=data.sender_id,
        ):
            yield f"event: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
