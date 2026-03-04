"""
Agent Endpoints.

REST API for agent interaction: chat, streaming, and registry listing.
All chat goes through sessions. Auto-creates ephemeral session when none provided.
"""

from pydantic import BaseModel, Field

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from modules.backend.core.dependencies import DbSession, RequestId
from modules.backend.core.logging import get_logger
from modules.backend.schemas.base import ApiResponse

logger = get_logger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Request body for agent chat."""

    message: str = Field(
        ...,
        min_length=1,
        description="User message to send to the agent",
    )
    agent: str | None = Field(
        default=None,
        description="Target a specific agent by name, bypassing routing.",
    )
    session_id: str | None = Field(
        default=None,
        description="Session ID. Auto-created if omitted.",
    )


class ChatResponse(BaseModel):
    """Response from an agent."""

    agent_name: str
    output: str
    session_id: str | None = None


class AgentInfo(BaseModel):
    """Agent registry entry."""

    agent_name: str
    description: str
    keywords: list[str]
    tools: list[str]


@router.post(
    "/chat",
    response_model=ApiResponse[ChatResponse],
    summary="Chat with an agent",
    description="Send a message to mission control. Auto-creates a session if none provided.",
)
async def agent_chat(
    data: ChatRequest,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[ChatResponse]:
    """Send a message to an agent. Auto-creates ephemeral session when no session_id provided."""
    from modules.backend.agents.mission_control.mission_control import collect
    from modules.backend.services.session import SessionService
    from modules.backend.schemas.session import SessionCreate

    service = SessionService(db)

    session_id = data.session_id
    if not session_id:
        session = await service.create_session(
            SessionCreate(agent_id=data.agent, goal=data.message[:200]),
        )
        session_id = session.id

    result = await collect(
        session_id,
        data.message,
        session_service=service,
    )

    return ApiResponse(
        data=ChatResponse(
            agent_name=result.get("agent_name", ""),
            output=result.get("output", ""),
            session_id=session_id,
        ),
    )


@router.post(
    "/chat/stream",
    summary="Chat with an agent (streaming SSE)",
    description="Send a message to an agent and receive progress events via Server-Sent Events.",
)
async def agent_chat_stream(
    data: ChatRequest,
    db: DbSession,
) -> StreamingResponse:
    """Stream agent progress events as SSE."""
    from modules.backend.agents.mission_control.mission_control import handle
    from modules.backend.services.session import SessionService
    from modules.backend.schemas.session import SessionCreate

    service = SessionService(db)

    session_id = data.session_id
    if not session_id:
        session = await service.create_session(
            SessionCreate(agent_id=data.agent, goal=data.message[:200]),
        )
        session_id = session.id

    async def generate():
        async for event in handle(session_id, data.message, session_service=service):
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


@router.get(
    "/registry",
    response_model=ApiResponse[list[AgentInfo]],
    summary="List available agents",
    description="Returns all enabled agents with their capabilities and keywords.",
)
async def agent_registry(
    request_id: RequestId,
) -> ApiResponse[list[AgentInfo]]:
    """List all available agents."""
    from modules.backend.agents.mission_control.mission_control import list_agents

    agents = list_agents()
    return ApiResponse(
        data=[AgentInfo(**a) for a in agents],
    )
