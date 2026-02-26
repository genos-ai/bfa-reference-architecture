# 31 — Event-Driven Session Architecture (Optional Module)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-02-26*

## Changelog

- 1.0.0 (2026-02-26): Initial event-driven session architecture — session model, event bus, streaming coordinator, plan management, memory architecture, approval gates, cost tracking, observability

---

## Module Status: Optional

This module is **optional**. Adopt when your project:
- Has interactive conversations (chat, messaging, agent sessions)
- Requires real-time streaming of agent thinking, tool calls, or progress
- Runs multi-step agent plans with approval gates or human-in-the-loop
- Operates long-running autonomous tasks spanning hours, days, or weeks
- Serves multiple channels (Telegram, TUI, WebSocket, CLI) from the same backend

**Dependencies**: This module requires **03-backend-architecture.md** (service layer), **06-event-architecture.md** (event primitives), **25-agentic-architecture.md** (agent concepts), and **26-agentic-pydanticai.md** (PydanticAI implementation).

**Relationship to existing docs**: This module does not replace docs 03, 25, 26, 27, 29, or 30. It layers a session and event model on top of them. Stateless CRUD endpoints (doc 03) continue to work unchanged. Channel adapters (doc 29) become event subscribers. Agent tools (doc 26) become event producers. The service layer remains the single source of business logic. Discovery endpoints (doc 30) remain stateless GET requests.

---

## Context

The existing architecture in doc 03 treats every interaction as a single HTTP request that receives a single JSON response. This is correct for CRUD operations (`GET /api/v1/notes`) and will remain unchanged by this module. However, five consumer types in the platform already violate the request/response assumption: Telegram (asynchronous message processing with edits and follow-ups), TUI (persistent interactive terminal with real-time updates), WebSocket push (real-time event delivery), background tasks (async job processing), and agent approval gates (pause-and-wait). Maintaining a request/response model for these while layering event-driven behavior on top creates two parallel interaction models that share the same service layer but use different conventions — a duplication that compounds with every new feature.

The event-driven session model unifies all interaction patterns under one architecture. The primitive is the **session** — a persistent, bidirectional context that carries conversation history, active agents, cost tracking, and channel bindings across an arbitrarily long interaction. Every action within a session produces **events** (`user.message.sent`, `agent.thinking.started`, `agent.tool.called`, `agent.response.chunk`). Channels subscribe to the event stream and render events in their native format. The coordinator returns `AsyncIterator[Event]`, not a response object. Streaming is the default path; synchronous responses are a degraded projection of the stream for clients that cannot handle events.

This model treats AI agents and humans as peers on the same event bus. There is no architectural difference between a human typing in Telegram and an AI agent generating a response — both produce messages into a session, both consume events from the session. The architecture does not care about the source.

---

## Core Axioms

**A1: The primitive is the session, not the request.** A session is a persistent bidirectional context with state (conversation history, active agents, plan progress), memory (rolling summary, retrieved memories), cost (accumulated token usage, budget remaining), and channel bindings (which transports are subscribed). Sessions outlive any individual request, channel connection, or server restart.

**A2: The event bus is the backbone.** Every action — human message, agent thought, tool call, approval request, cost update, plan step completion — is an event on the bus. Channels are projections of the event stream into transport-specific formats. REST materializes events into JSON responses. WebSocket pushes events directly. Telegram buffers and renders events as message edits. The TUI renders events in real-time panels.

**A3: Streaming is the default path.** The coordinator's `handle()` function returns `AsyncIterator[Event]`. There is no separate `complete()` path. Callers that need synchronous semantics collect the iterator to completion and extract the final result. This ensures every channel gets real-time progress without requiring a separate streaming implementation.

**A4: The coordinator is infrastructure, not intelligence.** The coordinator routes messages to agents, enforces cost budgets, manages approval gates, and yields events. It does not have a personality, make domain decisions, or call LLMs. It is a state machine with well-defined transitions.

**A5: Agents are configured functions, not class hierarchies.** Each agent is a `pydantic_ai.Agent()` instance with tools registered as `@agent.tool` decorators. Agents call service-layer methods through those tools. No agent contains business logic — the same rule as API endpoint handlers (doc 03) and MCP tool functions (doc 27).

---

## Graduated Complexity

Not every endpoint needs a session. The architecture supports four interaction tiers within the same codebase, same service layer, same module boundaries:

| Tier | Pattern | Session needed | Temporal needed | Example |
|------|---------|---------------|-----------------|---------|
| 1: Stateless CRUD | Request/response (doc 03) | No | No | `GET /api/v1/notes`, `POST /api/v1/notes` |
| 2: Stateless agent call | Request/response + optional SSE | No | No | One-shot summarization, single tool call |
| 3: Interactive session | Session + event stream | Yes | No | Chat conversation, multi-step agent task, approval flow |
| 4: Long-running autonomous | Session + Temporal + event stream | Yes | Yes | Week-long QA plan, research project, migration |

Tiers 1-2 use the existing patterns from docs 03 and 30. Tiers 3-4 use the patterns defined in this document. A `GET /api/v1/notes` does not create a session — it hits the endpoint, calls `NoteService.list_notes()`, returns JSON. Unchanged.

---

## Section 1: Session Model

### Session Entity

The session is a first-class domain entity stored in PostgreSQL.

```python
# modules/backend/models/session.py
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, JSON, Enum as SAEnum, Index
from sqlalchemy.dialects.postgresql import UUID
from modules.backend.models.base import Base
from modules.backend.core.utils import utc_now
import enum


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"       # Waiting for human/AI input
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(SAEnum(SessionStatus), nullable=False, default=SessionStatus.ACTIVE)

    # Identity
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    agent_id = Column(String(100), nullable=True)          # Primary agent assigned

    # Context
    goal = Column(String(2000), nullable=True)             # What this session is trying to achieve
    plan_id = Column(UUID(as_uuid=True), nullable=True)    # Active plan (Section 4)
    metadata = Column(JSON, nullable=True, default=dict)   # Extensible key-value pairs

    # Cost tracking
    total_input_tokens = Column(Float, nullable=False, default=0)
    total_output_tokens = Column(Float, nullable=False, default=0)
    total_cost_usd = Column(Float, nullable=False, default=0)
    cost_budget_usd = Column(Float, nullable=True)         # None = unlimited

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    last_activity_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=True)           # Auto-expire after inactivity

    __table_args__ = (
        Index("ix_sessions_user_status", "user_id", "status"),
        Index("ix_sessions_last_activity", "last_activity_at"),
    )
```

### Session Schemas

```python
# modules/backend/schemas/session.py
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """Create a new session. Goal is optional — sessions can start open-ended."""
    goal: str | None = Field(None, max_length=2000)
    agent_id: str | None = Field(None, description="Primary agent to assign")
    cost_budget_usd: float | None = Field(None, ge=0, description="Cost limit. None = unlimited.")
    metadata: dict | None = None


class SessionResponse(BaseModel):
    id: UUID
    status: str
    goal: str | None
    agent_id: str | None
    total_cost_usd: float
    cost_budget_usd: float | None
    created_at: datetime
    last_activity_at: datetime

    model_config = {"from_attributes": True}


class SessionMessage(BaseModel):
    """A message sent into a session from any source."""
    content: str = Field(..., min_length=1, max_length=50000)
    sender_type: str = Field(..., pattern="^(human|agent|system)$")
    sender_id: str | None = None
    channel: str | None = Field(None, description="Originating channel: telegram, tui, web, cli, mcp, a2a")
    attachments: list[dict] | None = None
```

### Session Service

```python
# modules/backend/services/session.py
from uuid import UUID
from modules.backend.services.base import BaseService
from modules.backend.schemas.session import SessionCreate, SessionResponse, SessionMessage
from modules.backend.models.session import Session, SessionStatus
from modules.backend.core.exceptions import NotFoundError, ValidationError


class SessionService(BaseService):
    """Manages session lifecycle. Does not contain agent logic — that lives in the coordinator."""

    async def create_session(self, data: SessionCreate, user_id: UUID | None = None) -> SessionResponse:
        session = Session(
            user_id=user_id,
            goal=data.goal,
            agent_id=data.agent_id,
            cost_budget_usd=data.cost_budget_usd,
            metadata=data.metadata or {},
        )
        self.db.add(session)
        await self.db.flush()
        return SessionResponse.model_validate(session)

    async def get_session(self, session_id: UUID) -> SessionResponse:
        session = await self._get_or_404(Session, session_id)
        return SessionResponse.model_validate(session)

    async def update_cost(self, session_id: UUID, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        session = await self._get_or_404(Session, session_id)
        session.total_input_tokens += input_tokens
        session.total_output_tokens += output_tokens
        session.total_cost_usd += cost_usd
        if session.cost_budget_usd and session.total_cost_usd >= session.cost_budget_usd:
            raise ValidationError(
                code="COST_BUDGET_EXCEEDED",
                message=f"Session cost {session.total_cost_usd:.4f} exceeds budget {session.cost_budget_usd:.4f}",
            )

    async def suspend_session(self, session_id: UUID, reason: str) -> None:
        session = await self._get_or_404(Session, session_id)
        session.status = SessionStatus.SUSPENDED
        session.metadata["suspend_reason"] = reason

    async def resume_session(self, session_id: UUID) -> None:
        session = await self._get_or_404(Session, session_id)
        if session.status != SessionStatus.SUSPENDED:
            raise ValidationError(code="INVALID_STATE", message=f"Cannot resume session in state {session.status}")
        session.status = SessionStatus.ACTIVE

    async def _get_or_404(self, model, id_: UUID):
        obj = await self.db.get(model, id_)
        if not obj:
            raise NotFoundError(code="SESSION_NOT_FOUND", message=f"Session {id_} not found")
        return obj
```

### Session-Channel Binding

A session can be active across multiple channels simultaneously. A human starts a session via TUI, then checks progress via Telegram. The session doesn't care — channels subscribe to the same event stream.

```python
# modules/backend/models/session.py (continued)
class SessionChannel(Base):
    __tablename__ = "session_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    channel_type = Column(String(50), nullable=False)      # telegram, tui, web, cli, mcp, a2a
    channel_id = Column(String(200), nullable=False)        # chat_id, connection_id, etc.
    bound_at = Column(DateTime, nullable=False, default=utc_now)
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_session_channels_session", "session_id", "is_active"),
        Index("ix_session_channels_channel", "channel_type", "channel_id"),
    )
```

### Anti-Patterns

- Do not store conversation history in the session row. Conversation history is stored in `session_messages` (a separate table) and managed by the memory architecture (Section 5). The session row tracks metadata, cost, and status.
- Do not use the session model for stateless CRUD. A `POST /api/v1/notes` does not create a session. Only interactive, multi-turn, or long-running interactions need sessions.
- Do not make the session table the place for domain data. Domain state (notes, projects, users) lives in domain tables. The session tracks the *interaction context* around domain operations.

### Files Involved

```
modules/backend/models/session.py           # NEW — Session, SessionChannel models
modules/backend/schemas/session.py          # NEW — SessionCreate, SessionResponse, SessionMessage
modules/backend/services/session.py         # NEW — SessionService
modules/backend/repositories/session.py     # NEW — SessionRepository
modules/backend/api/v1/endpoints/sessions.py # NEW — REST endpoints for session management
```

---

## Section 2: Event Bus

### Event Types

Every action within a session produces a typed event. Events follow the naming convention from doc 06 (`{domain}.{entity}.{action}`) extended with agent lifecycle events.

```python
# modules/backend/events/types.py
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from modules.backend.core.utils import utc_now


class SessionEvent(BaseModel):
    """Base event for all session activity. Every event on the bus extends this."""
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str                                    # e.g., "agent.response.chunk"
    session_id: UUID
    timestamp: datetime = Field(default_factory=utc_now)
    source: str                                        # "human", "agent:<agent_id>", "system"
    metadata: dict = Field(default_factory=dict)


# --- User events ---

class UserMessageEvent(SessionEvent):
    event_type: str = "user.message.sent"
    content: str
    channel: str                                       # telegram, tui, web, cli
    attachments: list[dict] = Field(default_factory=list)


class UserApprovalEvent(SessionEvent):
    event_type: str = "user.approval.granted"
    decision: str                                      # "approved", "rejected", "modified"
    approval_request_id: UUID
    reason: str | None = None
    modified_params: dict | None = None


# --- Agent events ---

class AgentThinkingEvent(SessionEvent):
    event_type: str = "agent.thinking.started"
    agent_id: str


class AgentToolCallEvent(SessionEvent):
    event_type: str = "agent.tool.called"
    agent_id: str
    tool_name: str
    tool_args: dict
    tool_call_id: str


class AgentToolResultEvent(SessionEvent):
    event_type: str = "agent.tool.returned"
    agent_id: str
    tool_name: str
    tool_call_id: str
    result: str | dict
    status: str = "success"                            # "success", "error"
    error_detail: dict | None = None


class AgentResponseChunkEvent(SessionEvent):
    event_type: str = "agent.response.chunk"
    agent_id: str
    content: str
    is_final: bool = False


class AgentResponseCompleteEvent(SessionEvent):
    event_type: str = "agent.response.complete"
    agent_id: str
    full_content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str


# --- Approval events ---

class ApprovalRequestedEvent(SessionEvent):
    event_type: str = "agent.approval.requested"
    approval_request_id: UUID = Field(default_factory=uuid4)
    agent_id: str
    action: str                                        # What the agent wants to do
    context: dict                                      # Why it's asking
    allowed_decisions: list[str] = Field(default=["approve", "reject", "modify"])
    responder_options: list[str] = Field(default=["human", "ai_agent", "automated_rule"])
    timeout_seconds: int | None = None                 # Auto-escalate after timeout


class ApprovalResponseEvent(SessionEvent):
    event_type: str = "approval.response.received"
    approval_request_id: UUID
    decision: str
    responder_type: str                                # "human", "ai_agent", "automated_rule"
    responder_id: str
    reason: str | None = None
    modified_params: dict | None = None


# --- Plan events ---

class PlanCreatedEvent(SessionEvent):
    event_type: str = "plan.created"
    plan_id: UUID
    goal: str
    step_count: int


class PlanStepStartedEvent(SessionEvent):
    event_type: str = "plan.step.started"
    plan_id: UUID
    step_id: UUID
    step_name: str
    assigned_agent: str


class PlanStepCompletedEvent(SessionEvent):
    event_type: str = "plan.step.completed"
    plan_id: UUID
    step_id: UUID
    result_summary: str
    status: str                                        # "completed", "failed", "skipped"


class PlanRevisedEvent(SessionEvent):
    event_type: str = "plan.revised"
    plan_id: UUID
    revision_reason: str
    steps_added: int = 0
    steps_removed: int = 0
    steps_modified: int = 0


# --- Cost events ---

class CostUpdateEvent(SessionEvent):
    event_type: str = "session.cost.updated"
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cumulative_cost_usd: float
    budget_remaining_usd: float | None
    model: str
    source_event_type: str                             # Which event triggered this cost
```

### Event Bus Transport

Use Redis Pub/Sub for real-time event delivery within the application. Rationale: Redis is already in the stack (doc 19 uses it for Taskiq), Pub/Sub is fire-and-forget with no persistence overhead, and latency is sub-millisecond.

```python
# modules/backend/events/bus.py
import json
from uuid import UUID
from typing import AsyncIterator
from redis.asyncio import Redis
from modules.backend.events.types import SessionEvent
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class EventBus:
    """Redis Pub/Sub event bus for session events."""

    def __init__(self, redis: Redis):
        self._redis = redis

    async def publish(self, event: SessionEvent) -> None:
        """Publish an event to the session's channel."""
        channel = f"session:{event.session_id}"
        payload = event.model_dump_json()
        await self._redis.publish(channel, payload)
        logger.debug("Event published", extra={
            "event_type": event.event_type,
            "session_id": str(event.session_id),
        })

    async def subscribe(self, session_id: UUID) -> AsyncIterator[SessionEvent]:
        """Subscribe to all events for a session. Yields events as they arrive."""
        channel = f"session:{session_id}"
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    event = _deserialize_event(data)
                    if event:
                        yield event
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()


def _deserialize_event(data: dict) -> SessionEvent | None:
    """Deserialize event JSON into typed event object."""
    event_type = data.get("event_type", "")
    event_class = EVENT_TYPE_MAP.get(event_type, SessionEvent)
    try:
        return event_class.model_validate(data)
    except Exception as e:
        logger.warning("Failed to deserialize event", extra={"event_type": event_type, "error": str(e)})
        return None


# Registry: event_type string → event class
EVENT_TYPE_MAP: dict[str, type[SessionEvent]] = {
    "user.message.sent": UserMessageEvent,
    "agent.thinking.started": AgentThinkingEvent,
    "agent.tool.called": AgentToolCallEvent,
    "agent.tool.returned": AgentToolResultEvent,
    "agent.response.chunk": AgentResponseChunkEvent,
    "agent.response.complete": AgentResponseCompleteEvent,
    "agent.approval.requested": ApprovalRequestedEvent,
    "approval.response.received": ApprovalResponseEvent,
    "plan.created": PlanCreatedEvent,
    "plan.step.started": PlanStepStartedEvent,
    "plan.step.completed": PlanStepCompletedEvent,
    "plan.revised": PlanRevisedEvent,
    "session.cost.updated": CostUpdateEvent,
}
```

### Temporal as Durable Event Log

For Tier 4 (long-running autonomous tasks), Temporal workflow history IS the durable event stream. Redis Pub/Sub handles real-time delivery to connected channels; Temporal handles crash recovery and multi-day persistence.

| Tier | Real-time transport | Durability layer |
|------|-------------------|-----------------|
| Tier 3: Interactive session | Redis Pub/Sub | PostgreSQL session state |
| Tier 4: Long-running autonomous | Redis Pub/Sub + Temporal event history | Temporal workflow history (primary) + PostgreSQL (domain state) |

Temporal stores orchestration state (workflow position, retry counts, signal queues). PostgreSQL stores domain state (conversation history, memories, plan/task records, decision logs). Never store large data in Temporal's event history — it bloats replay. Store references in Temporal; fetch from PostgreSQL in Activities.

### Event Bus Initialization

```python
# modules/backend/events/__init__.py
from modules.backend.events.bus import EventBus
from modules.backend.events.types import (
    SessionEvent, UserMessageEvent, AgentThinkingEvent,
    AgentToolCallEvent, AgentToolResultEvent,
    AgentResponseChunkEvent, AgentResponseCompleteEvent,
    ApprovalRequestedEvent, ApprovalResponseEvent,
    CostUpdateEvent, PlanCreatedEvent, PlanStepStartedEvent,
    PlanStepCompletedEvent, PlanRevisedEvent,
)

__all__ = [
    "EventBus",
    "SessionEvent", "UserMessageEvent", "AgentThinkingEvent",
    "AgentToolCallEvent", "AgentToolResultEvent",
    "AgentResponseChunkEvent", "AgentResponseCompleteEvent",
    "ApprovalRequestedEvent", "ApprovalResponseEvent",
    "CostUpdateEvent", "PlanCreatedEvent", "PlanStepStartedEvent",
    "PlanStepCompletedEvent", "PlanRevisedEvent",
]
```

### Anti-Patterns

- Do not use the event bus for inter-module communication that doesn't involve sessions. Module-to-module events (doc 06) continue to use Taskiq/Redis directly.
- Do not persist every event to PostgreSQL. The event bus is ephemeral (Redis Pub/Sub). Only events that matter for history or audit are persisted (see Section 5 memory architecture). If you need durable events, use Temporal.
- Do not put business logic in event handlers. Event subscribers render or forward events — they do not make domain decisions.

### Files Involved

```
modules/backend/events/__init__.py          # NEW — public exports
modules/backend/events/types.py             # NEW — all event type definitions
modules/backend/events/bus.py               # NEW — Redis Pub/Sub EventBus
```

---

## Section 3: Streaming Coordinator

### The `handle()` Function

The coordinator is the universal entry point for all interactive operations. It receives a session message, routes to the appropriate agent, and yields events as the agent works.

```python
# modules/backend/agents/coordinator/handler.py
from uuid import UUID
from typing import AsyncIterator
from modules.backend.events.types import (
    SessionEvent, UserMessageEvent, AgentThinkingEvent,
    AgentResponseChunkEvent, AgentResponseCompleteEvent,
    CostUpdateEvent,
)
from modules.backend.events.bus import EventBus
from modules.backend.services.session import SessionService
from modules.backend.agents.coordinator.router import route_to_agent
from modules.backend.agents.coordinator.cost import enforce_budget, calculate_cost
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


async def handle(
    session_id: UUID,
    message: UserMessageEvent,
    event_bus: EventBus,
    session_service: SessionService,
) -> AsyncIterator[SessionEvent]:
    """Universal coordinator entry point. Yields events as the agent works.

    All channels call this function. REST endpoints collect the iterator.
    WebSocket and SSE stream events directly. TUI renders events in panels.
    Telegram buffers and sends as message edits.
    """
    # 1. Enforce cost budget before any LLM call
    session = await session_service.get_session(session_id)
    enforce_budget(session)

    # 2. Publish the incoming message as an event
    await event_bus.publish(message)
    yield message

    # 3. Route to the appropriate agent based on session context
    agent, agent_id = await route_to_agent(session)

    # 4. Yield thinking event
    thinking = AgentThinkingEvent(session_id=session_id, source=f"agent:{agent_id}", agent_id=agent_id)
    await event_bus.publish(thinking)
    yield thinking

    # 5. Run the agent with streaming, yielding events as they arrive
    async with agent.run_stream(
        message.content,
        message_history=await _load_history(session_id),
        deps=await _build_deps(session_id, event_bus),
    ) as stream:
        full_content = ""
        async for chunk in stream.stream_text(delta=True):
            full_content += chunk
            chunk_event = AgentResponseChunkEvent(
                session_id=session_id,
                source=f"agent:{agent_id}",
                agent_id=agent_id,
                content=chunk,
                is_final=False,
            )
            await event_bus.publish(chunk_event)
            yield chunk_event

        # 6. Emit completion event with cost data
        usage = stream.usage()
        cost_usd = calculate_cost(usage, stream.model_name)

        complete = AgentResponseCompleteEvent(
            session_id=session_id,
            source=f"agent:{agent_id}",
            agent_id=agent_id,
            full_content=full_content,
            input_tokens=usage.request_tokens or 0,
            output_tokens=usage.response_tokens or 0,
            cost_usd=cost_usd,
            model=stream.model_name or "unknown",
        )
        await event_bus.publish(complete)
        yield complete

        # 7. Update session cost
        await session_service.update_cost(
            session_id,
            input_tokens=complete.input_tokens,
            output_tokens=complete.output_tokens,
            cost_usd=cost_usd,
        )
        cost_event = CostUpdateEvent(
            session_id=session_id,
            source="system",
            input_tokens=complete.input_tokens,
            output_tokens=complete.output_tokens,
            cost_usd=cost_usd,
            cumulative_cost_usd=session.total_cost_usd + cost_usd,
            budget_remaining_usd=(
                session.cost_budget_usd - session.total_cost_usd - cost_usd
                if session.cost_budget_usd else None
            ),
            model=complete.model,
            source_event_type="agent.response.complete",
        )
        await event_bus.publish(cost_event)
        yield cost_event
```

### Agent Router

```python
# modules/backend/agents/coordinator/router.py
from pydantic_ai import Agent
from modules.backend.schemas.session import SessionResponse
from modules.backend.agents.vertical import notes_agent, research_agent, code_review_agent
from modules.backend.core.exceptions import ValidationError

AGENT_REGISTRY: dict[str, Agent] = {
    "notes": notes_agent,
    "research": research_agent,
    "code_review": code_review_agent,
}


async def route_to_agent(session: SessionResponse) -> tuple[Agent, str]:
    """Route to the correct agent based on session configuration.

    Returns (agent_instance, agent_id).
    """
    agent_id = session.agent_id
    if not agent_id:
        raise ValidationError(code="NO_AGENT", message="Session has no assigned agent")
    agent = AGENT_REGISTRY.get(agent_id)
    if not agent:
        raise ValidationError(code="UNKNOWN_AGENT", message=f"Agent '{agent_id}' not found in registry")
    return agent, agent_id
```

### Channel Adapters as Event Consumers

Each channel adapter consumes the event stream from `handle()` and renders events in its native format. Adapters are thin — they translate events, nothing more.

**REST API (synchronous degraded mode):**

```python
# modules/backend/api/v1/endpoints/sessions.py
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from uuid import UUID
from modules.backend.core.dependencies import DbSession, get_event_bus
from modules.backend.services.session import SessionService
from modules.backend.agents.coordinator.handler import handle
from modules.backend.events.types import UserMessageEvent, AgentResponseCompleteEvent
import json

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/{session_id}/messages")
async def send_message(
    session_id: UUID,
    message: SessionMessage,
    db: DbSession,
    event_bus: EventBus = Depends(get_event_bus),
):
    """Send a message to a session. Returns SSE stream of events."""
    service = SessionService(db)
    user_event = UserMessageEvent(
        session_id=session_id,
        source=f"human:{message.sender_id or 'anonymous'}",
        content=message.content,
        channel="web",
    )

    async def event_stream():
        async for event in handle(session_id, user_event, event_bus, service):
            yield f"data: {event.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**Telegram adapter (buffered rendering):**

```python
# modules/telegram/session_handler.py
from modules.backend.agents.coordinator.handler import handle
from modules.backend.events.types import AgentResponseChunkEvent, AgentResponseCompleteEvent


async def handle_telegram_message(chat_id: int, text: str, session_id: UUID, ...):
    """Handle a Telegram message within a session."""
    # ... create UserMessageEvent ...

    response_text = ""
    message_id = None

    async for event in handle(session_id, user_event, event_bus, session_service):
        if isinstance(event, AgentResponseChunkEvent):
            response_text += event.content
            if message_id is None:
                # Send initial message
                msg = await bot.send_message(chat_id, response_text)
                message_id = msg.message_id
            elif len(response_text) % 100 < len(event.content):
                # Edit message every ~100 chars to avoid rate limits
                await bot.edit_message_text(response_text, chat_id, message_id)

        elif isinstance(event, AgentResponseCompleteEvent):
            # Final edit with complete text
            if message_id:
                await bot.edit_message_text(event.full_content, chat_id, message_id)
```

### Anti-Patterns

- Do not put business logic in the coordinator. The coordinator routes and yields events. Domain decisions live in agents and services.
- Do not call `agent.run()` (non-streaming). Always use `agent.run_stream()`. Synchronous callers collect the stream.
- Do not let channels call agents directly, bypassing the coordinator. All interactive operations go through `handle()` — this ensures cost tracking, event publishing, and session state management are consistent.

### Files Involved

```
modules/backend/agents/coordinator/handler.py   # NEW — handle() function
modules/backend/agents/coordinator/router.py    # NEW — agent routing
modules/backend/agents/coordinator/cost.py      # NEW — budget enforcement, cost calculation
modules/backend/api/v1/endpoints/sessions.py    # NEW — REST session endpoints
modules/telegram/session_handler.py             # MODIFY — consume event stream
modules/tui/session_panel.py                    # MODIFY — render events in TUI panels
```

---

## Section 4: Plan Management

### Plan as a Mutable DAG

Plans decompose goals into tasks with dependencies. Plans are mutable — when a task fails or new information emerges, the coordinator modifies remaining tasks rather than regenerating the entire plan.

### Database Schema

```sql
-- Plans: top-level goals with versioning
CREATE TABLE plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    goal TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',     -- active, completed, failed, cancelled
    version INTEGER NOT NULL DEFAULT 1,               -- Incremented on every revision
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

-- Tasks: DAG nodes
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES plans(id),
    name VARCHAR(200) NOT NULL,
    description TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    -- pending → ready → in_progress → completed | failed | waiting_for_input | waiting_for_approval
    assigned_agent VARCHAR(100),                       -- Which vertical agent handles this
    assigned_model VARCHAR(100),                       -- Model override (e.g., opus for hard tasks)
    input_data JSONB,                                  -- Parameters for the task
    output_data JSONB,                                 -- Result when completed
    error_data JSONB,                                  -- Error details when failed
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Task dependencies: DAG edges
CREATE TABLE task_dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id),        -- This task...
    depends_on_task_id UUID NOT NULL REFERENCES tasks(id), -- ...depends on this task
    dependency_type VARCHAR(20) NOT NULL DEFAULT 'completion',
    -- completion: must complete successfully
    -- data: needs output data (but can handle failure)
    UNIQUE (task_id, depends_on_task_id)
);

-- Task attempts: audit trail of every execution
CREATE TABLE task_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id),
    attempt_number INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,                       -- started, completed, failed
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd FLOAT NOT NULL DEFAULT 0,
    model VARCHAR(100),
    started_at TIMESTAMP NOT NULL DEFAULT now(),
    completed_at TIMESTAMP,
    error_message TEXT,
    UNIQUE (task_id, attempt_number)
);

-- Plan decisions: audit log of every coordinator decision
CREATE TABLE plan_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES plans(id),
    decision_type VARCHAR(50) NOT NULL,
    -- plan_created, task_added, task_removed, task_reordered,
    -- plan_revised, task_escalated, human_override, auto_approved
    description TEXT NOT NULL,
    decided_by VARCHAR(100) NOT NULL,                  -- "coordinator", "human:user_123", "rule:auto_approve"
    reasoning TEXT,
    plan_version_before INTEGER NOT NULL,
    plan_version_after INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

-- Index for finding ready tasks efficiently
CREATE INDEX ix_tasks_plan_status ON tasks(plan_id, status);
CREATE INDEX ix_task_deps_task ON task_dependencies(task_id);
CREATE INDEX ix_plan_decisions_plan ON plan_decisions(plan_id);
```

### Ready Task Query

```sql
-- Find tasks ready to execute: all dependencies satisfied
SELECT t.* FROM tasks t
WHERE t.plan_id = :plan_id
  AND t.status = 'pending'
  AND NOT EXISTS (
    SELECT 1 FROM task_dependencies td
    JOIN tasks dep ON dep.id = td.depends_on_task_id
    WHERE td.task_id = t.id
      AND dep.status NOT IN ('completed')
  )
ORDER BY t.sort_order;
```

### Plan Revision over Replanning

When a task fails, modify the remaining plan rather than regenerating from scratch. Rationale: downstream dependencies may remain valid, other systems may have been notified, and completed work should not be re-executed.

```python
# modules/backend/services/plan.py (excerpt)

async def handle_task_failure(self, plan_id: UUID, task_id: UUID, error: str) -> None:
    """Handle a failed task: retry, revise plan, or escalate."""
    task = await self.task_repo.get(task_id)

    if task.retry_count < task.max_retries:
        # Retry with same parameters
        task.retry_count += 1
        task.status = "ready"
        await self._log_decision(plan_id, "task_retried",
            f"Retrying task '{task.name}' (attempt {task.retry_count}/{task.max_retries})",
            decided_by="coordinator")
        return

    # Ask coordinator agent to revise the plan
    remaining_tasks = await self.task_repo.get_incomplete_tasks(plan_id)
    revision = await self._request_plan_revision(plan_id, task, error, remaining_tasks)

    if revision.should_skip:
        task.status = "skipped"
    elif revision.replacement_tasks:
        # Replace failed task with alternative approach
        for new_task in revision.replacement_tasks:
            await self.task_repo.create(new_task)
        task.status = "replaced"
    elif revision.should_escalate:
        task.status = "waiting_for_input"
        # Emit approval request event for human intervention
```

### Anti-Patterns

- Do not store plan data in Temporal's event history. Temporal owns orchestration state (workflow position). PostgreSQL owns domain state (plan records, task status). Temporal Activities read/write PostgreSQL.
- Do not replan from scratch on every failure. Modify remaining tasks. Full replanning loses completed work context.
- Do not allow agents to spin without progress. Track tool invocations and state hashes — if the same call repeats three times without meaningful state change, escalate to a smarter model or human.

### Files Involved

```
modules/backend/models/plan.py              # NEW — Plan, Task, TaskDependency, TaskAttempt, PlanDecision
modules/backend/schemas/plan.py             # NEW — PlanCreate, TaskStatus, PlanRevision
modules/backend/services/plan.py            # NEW — PlanService with DAG management
modules/backend/repositories/plan.py        # NEW — PlanRepository with ready-task query
modules/backend/api/v1/endpoints/plans.py   # MODIFY — extend with session-based plan endpoints
```

---

## Section 5: Memory Architecture

### Three Memory Layers

Long-running sessions require memory beyond the LLM context window. Three complementary memory types, all stored in PostgreSQL with pgvector:

| Memory type | What it stores | Scope | Storage | Retrieval |
|-------------|---------------|-------|---------|-----------|
| **Episodic** | What happened: events, conversations, outcomes | Per-session | Vector embeddings + metadata | Semantic search by similarity |
| **Semantic** | What was learned: facts, relationships, preferences | Cross-session | Structured records + vectors | Exact match + semantic search |
| **Procedural** | How to do things: successful strategies, tool patterns | Cross-agent | Relational records with success rates | Lookup by task type |

### Context Window Assembly

Assemble the context window for each agent call using PydanticAI's `history_processors`:

```
┌─────────────────────────────────────────────┐
│ System prompt (agent identity, current task) │  ~2K tokens
├─────────────────────────────────────────────┤
│ Core memory (task status, key decisions)     │  ~4K tokens
├─────────────────────────────────────────────┤
│ Rolling summary (anchored, compressed)       │  ~8K tokens
├─────────────────────────────────────────────┤
│ Retrieved memories (semantic search results) │  ~4K tokens
├─────────────────────────────────────────────┤
│ Last 10-20 verbatim messages                 │  remaining budget
└─────────────────────────────────────────────┘
```

### Anchored Rolling Summary

Use the Factory.ai pattern (July 2025): maintain a persistent summary anchored to a specific message index. When compression triggers, only the newly dropped message span is summarized and merged into the existing summary — never re-summarize already-summarized content.

The summary preserves four categories:
- **Session intent**: original goals, current objectives
- **Play-by-play**: sequence of major actions and outcomes
- **Artifact trail**: files created/modified with paths, resources produced
- **Breadcrumbs**: identifiers (IDs, URLs, keys) needed to re-fetch context

```python
# modules/backend/services/memory.py (excerpt)

class MemoryService:
    """Manages session memory: rolling summary, episodic/semantic storage, context assembly."""

    async def compress_history(
        self,
        session_id: UUID,
        messages: list[dict],
        anchor_index: int,
        existing_summary: str | None,
    ) -> str:
        """Compress messages[anchor_index:] into an updated rolling summary.

        Only summarizes the new span. Merges with existing summary.
        Uses a cheaper model (e.g., claude-haiku) for compression.
        """
        new_span = messages[anchor_index:]
        if not new_span:
            return existing_summary or ""

        prompt = f"""Summarize the following conversation span. Preserve:
1. SESSION INTENT: goals and current objectives
2. PLAY-BY-PLAY: sequence of actions and outcomes
3. ARTIFACT TRAIL: files, paths, resources created/modified
4. BREADCRUMBS: IDs, URLs, keys needed for continuity

Previous summary (DO NOT re-summarize this, only merge):
{existing_summary or '(none)'}

New messages to summarize:
{_format_messages(new_span)}"""

        result = await self._summarization_agent.run(prompt)
        return result.output

    async def assemble_context(
        self,
        session_id: UUID,
        current_messages: list[dict],
        max_tokens: int = 128000,
    ) -> list[dict]:
        """Assemble full context window for an agent call."""
        summary = await self._get_rolling_summary(session_id)
        memories = await self._search_memories(session_id, current_messages[-1])

        # Budget allocation
        summary_budget = min(8000, max_tokens // 4)
        memory_budget = min(4000, max_tokens // 8)
        remaining = max_tokens - summary_budget - memory_budget - 2000  # system prompt

        context = []
        if summary:
            context.append({"role": "system", "content": f"[Session Summary]\n{summary}"})
        if memories:
            context.append({"role": "system", "content": f"[Retrieved Memories]\n{_format_memories(memories)}"})

        # Add as many recent verbatim messages as fit
        recent = _trim_to_budget(current_messages, remaining)
        context.extend(recent)

        return context
```

### Memory Extraction Pipeline

After each `agent.response.complete` event, extract semantic memories as a background task:

```python
# modules/backend/tasks/memory_extraction.py

async def extract_memories(session_id: UUID, message_content: str, response_content: str):
    """Background task: extract facts from the latest exchange and deduplicate against existing memories."""
    # 1. Extract salient facts using a cheap model
    facts = await extraction_agent.run(
        f"Extract factual statements from this exchange:\nUser: {message_content}\nAssistant: {response_content}"
    )

    # 2. For each fact, check for contradictions or duplicates
    for fact in facts.output:
        existing = await memory_repo.search_similar(session_id, fact.text, threshold=0.85)
        if existing:
            # Update existing memory with new information
            await memory_repo.merge(existing[0].id, fact)
        else:
            # Store as new semantic memory
            await memory_repo.create_semantic_memory(session_id, fact)
```

### Anti-Patterns

- Do not keep the entire conversation history in the context window for sessions longer than ~20 messages. Context windows are finite and expensive. Compress aggressively.
- Do not use generic summarization. Structured summarization (with explicit categories) preserves file paths, IDs, and technical details that generic summaries discard.
- Do not store embeddings in Temporal. Memory is domain state — it belongs in PostgreSQL with pgvector.

### Files Involved

```
modules/backend/services/memory.py          # NEW — MemoryService with compression, assembly, extraction
modules/backend/models/memory.py            # NEW — EpisodicMemory, SemanticMemory, ProceduralMemory
modules/backend/repositories/memory.py      # NEW — vector search, deduplication
modules/backend/tasks/memory_extraction.py  # NEW — background task for fact extraction
```

---

## Section 6: Approval and Escalation

### Unified Responder Pattern

Approval requests use the same mechanism regardless of whether a human, AI agent, or automated rule responds. The `ApprovalRequestedEvent` is published to the event bus. Any subscriber that can handle it responds with an `ApprovalResponseEvent`.

```python
# modules/backend/agents/coordinator/approval.py
from uuid import UUID
from modules.backend.events.types import ApprovalRequestedEvent, ApprovalResponseEvent
from modules.backend.events.bus import EventBus


async def request_approval(
    session_id: UUID,
    agent_id: str,
    action: str,
    context: dict,
    event_bus: EventBus,
    timeout_seconds: int = 14400,  # 4 hours default
) -> ApprovalResponseEvent:
    """Request approval and wait for a response.

    In Tier 3 (interactive session): blocks on Redis Pub/Sub.
    In Tier 4 (Temporal workflow): uses Temporal Signal + wait_condition.
    """
    request = ApprovalRequestedEvent(
        session_id=session_id,
        source=f"agent:{agent_id}",
        agent_id=agent_id,
        action=action,
        context=context,
        timeout_seconds=timeout_seconds,
    )
    await event_bus.publish(request)

    # Wait for response (implementation varies by tier)
    response = await _wait_for_approval(session_id, request.approval_request_id, timeout_seconds)
    return response
```

### Temporal Integration for Durable Approvals

For Tier 4 workflows, approvals use Temporal Signals — they survive crashes, restarts, and multi-day waits.

```python
# modules/backend/agents/coordinator/temporal_workflow.py
from temporalio import workflow
from dataclasses import dataclass


@dataclass
class ApprovalDecision:
    decision: str               # "approved", "rejected", "modified"
    responder_type: str         # "human", "ai_agent", "automated_rule"
    responder_id: str
    reason: str | None = None
    modified_params: dict | None = None


@workflow.defn
class AgentPlanWorkflow:
    def __init__(self):
        self._approval: ApprovalDecision | None = None
        self._plan_modifications: list[dict] = []

    @workflow.signal
    async def submit_approval(self, decision: ApprovalDecision) -> None:
        """Receive approval from any source: human, AI, or automated rule."""
        self._approval = decision

    @workflow.signal
    async def modify_plan(self, modifications: dict) -> None:
        """Receive plan modifications from human or coordinator."""
        self._plan_modifications.append(modifications)

    @workflow.query
    def get_status(self) -> dict:
        """Read-only status for dashboards. Does not interrupt workflow."""
        return {
            "current_task": self._current_task,
            "progress_pct": self._progress_pct,
            "completed_tasks": self._completed,
            "blocked_tasks": self._blocked,
            "total_cost_usd": self._total_cost,
            "waiting_for_approval": self._approval is None and self._awaiting_approval,
        }

    @workflow.run
    async def run(self, plan_id: str) -> dict:
        # ... execute plan steps ...
        # When approval needed:
        self._awaiting_approval = True
        self._approval = None

        # Notify via Activity (Slack, email, webhook)
        await workflow.execute_activity(
            send_notification,
            args=[NotificationPayload(...)],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Wait indefinitely — survives crashes, deploys, restarts
        await workflow.wait_condition(lambda: self._approval is not None)
        self._awaiting_approval = False

        # Process the decision
        decision = self._approval
        # ... continue execution based on decision ...
```

### Escalation Chain

When an approval request goes unanswered or a task exceeds an agent's capability, escalate through a chain:

| Level | Responder | Timeout | Trigger |
|-------|-----------|---------|---------|
| 1 | Automated rules | Immediate | Low-risk actions matching predefined criteria |
| 2 | AI triage agent (Haiku) | 30 seconds | Medium-risk, can assess with fast model |
| 3 | AI reviewer (Sonnet) | 2 minutes | Complex decisions needing reasoning |
| 4 | Human (via Slack/email) | 4 hours | High-risk, ambiguous, or budget-exceeding |
| 5 | Human manager | 24 hours | Escalation after Level 4 timeout |

### Notification Activities

```python
# modules/backend/agents/coordinator/notifications.py
from temporalio import activity
from dataclasses import dataclass


@dataclass
class NotificationPayload:
    channel: str               # "slack", "email", "webhook"
    recipient: str             # channel ID, email address, or webhook URL
    title: str
    body: str
    action_url: str            # URL to approve/reject
    urgency: str = "normal"    # "low", "normal", "high", "critical"


@activity.defn
async def send_notification(payload: NotificationPayload) -> bool:
    """Send notification via configured channel. Runs as Temporal Activity."""
    if payload.channel == "slack":
        return await _send_slack(payload)
    elif payload.channel == "email":
        return await _send_email(payload)
    elif payload.channel == "webhook":
        return await _send_webhook(payload)
    return False
```

### Anti-Patterns

- Do not make approval a blocking HTTP request. Approvals are asynchronous events. The caller subscribes to events and handles the response when it arrives.
- Do not hard-code responder types. The unified responder pattern means any capable entity can respond. Don't build separate code paths for human vs. AI approval.
- Do not assume notifications will be delivered instantly. Use durable timers (Temporal) for escalation, not in-memory timers that die with the process.

### Files Involved

```
modules/backend/agents/coordinator/approval.py          # NEW — request_approval function
modules/backend/agents/coordinator/temporal_workflow.py  # NEW — Temporal workflow with Signals/Queries
modules/backend/agents/coordinator/notifications.py      # NEW — notification Activities
modules/backend/agents/coordinator/escalation.py         # NEW — escalation chain logic
```

---

## Section 7: Observability

### Event-Native Observability

The event bus provides observability by default. Every agent action, tool call, and decision is an event with a timestamp, session ID, and source. Subscribe to the event bus for real-time monitoring; query PostgreSQL for historical analysis.

### Temporal Queries for Progress Checks

For Tier 4 workflows, Temporal Queries provide synchronous, read-only state inspection without interrupting execution:

```python
# modules/backend/api/v1/endpoints/plans.py

@router.get("/plans/{plan_id}/status")
async def get_plan_status(plan_id: str):
    """Check in on a running plan. Uses Temporal Query — does not interrupt the workflow."""
    handle = await temporal_client.get_workflow_handle(f"plan-{plan_id}")
    status = await handle.query(AgentPlanWorkflow.get_status)
    return ApiResponse(success=True, data=status)
```

### Trace Integration

Use Pydantic Logfire for native PydanticAI tracing, or Langfuse for broader LLM observability:

| Tool | Integration | License | Self-hostable | Use when |
|------|------------|---------|---------------|----------|
| Pydantic Logfire | Native PydanticAI + OpenTelemetry | Commercial | No | You want zero-config tracing for PydanticAI agents |
| Langfuse | OpenTelemetry SDK | MIT | Yes | You want self-hosted, open-source LLM observability |
| Arize Phoenix | OpenTelemetry SDK | Elastic 2.0 | Yes | You want open-source with strong evaluation features |

### Cost Dashboard Data

The `session.cost.updated` events feed a cost dashboard. Query the `task_attempts` table for per-model, per-agent, per-task cost breakdowns.

```sql
-- Cost by model across all sessions in the last 7 days
SELECT
    model,
    COUNT(*) as call_count,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    SUM(cost_usd) as total_cost
FROM task_attempts
WHERE started_at > now() - interval '7 days'
GROUP BY model
ORDER BY total_cost DESC;
```

### Plan Decision Audit Trail

The `plan_decisions` table provides a complete audit log of every coordinator decision. This is critical for debugging, compliance, and understanding why an agent took a particular path.

### Files Involved

```
modules/backend/api/v1/endpoints/plans.py   # MODIFY — add status endpoint
config/settings/observability.yaml          # MODIFY — add Logfire/Langfuse config
```

---

## Module Structure After Adoption

```
modules/
├── backend/
│   ├── api/
│   │   └── v1/
│   │       └── endpoints/
│   │           ├── sessions.py          # NEW — session CRUD + message endpoint (SSE)
│   │           └── plans.py             # MODIFY — add session-based plan endpoints, status
│   ├── agents/
│   │   └── coordinator/
│   │       ├── handler.py               # NEW — handle() streaming coordinator
│   │       ├── router.py                # NEW — agent routing
│   │       ├── cost.py                  # NEW — budget enforcement
│   │       ├── approval.py              # NEW — approval request/response
│   │       ├── escalation.py            # NEW — escalation chain
│   │       ├── notifications.py         # NEW — Temporal notification Activities
│   │       └── temporal_workflow.py      # NEW — AgentPlanWorkflow
│   ├── events/
│   │   ├── __init__.py                  # NEW — public exports
│   │   ├── types.py                     # NEW — all event type definitions
│   │   └── bus.py                       # NEW — Redis Pub/Sub EventBus
│   ├── models/
│   │   ├── session.py                   # NEW — Session, SessionChannel
│   │   ├── plan.py                      # NEW — Plan, Task, TaskDependency, TaskAttempt, PlanDecision
│   │   └── memory.py                    # NEW — EpisodicMemory, SemanticMemory, ProceduralMemory
│   ├── schemas/
│   │   ├── session.py                   # NEW — SessionCreate, SessionResponse, SessionMessage
│   │   └── plan.py                      # NEW — PlanCreate, TaskStatus, PlanRevision
│   ├── services/
│   │   ├── session.py                   # NEW — SessionService
│   │   ├── plan.py                      # NEW — PlanService with DAG management
│   │   └── memory.py                    # NEW — MemoryService
│   ├── repositories/
│   │   ├── session.py                   # NEW — SessionRepository
│   │   ├── plan.py                      # NEW — PlanRepository
│   │   └── memory.py                    # NEW — MemoryRepository (pgvector search)
│   └── tasks/
│       └── memory_extraction.py         # NEW — background fact extraction
├── telegram/
│   └── session_handler.py               # MODIFY — consume event stream from handle()
├── tui/
│   └── session_panel.py                 # MODIFY — render events in TUI panels
config/
└── settings/
    ├── sessions.yaml                    # NEW — session config (TTL, budget defaults)
    └── temporal.yaml                    # NEW — Temporal connection config
tests/
├── unit/
│   ├── test_event_bus.py                # NEW — event serialization, bus publish/subscribe
│   ├── test_session_service.py          # NEW — session lifecycle, cost tracking
│   ├── test_plan_service.py             # NEW — DAG traversal, ready-task query, plan revision
│   └── test_memory_service.py           # NEW — context assembly, summary compression
├── integration/
│   ├── test_coordinator_flow.py         # NEW — full handle() → events → channel rendering
│   ├── test_approval_flow.py            # NEW — approval request → response → resume
│   └── test_temporal_workflow.py        # NEW — Temporal workflow with signals and queries
└── e2e/
    └── test_session_e2e.py              # NEW — create session → send messages → verify events
```

### Configuration

**`config/settings/sessions.yaml`:**

```yaml
# =============================================================================
# Session Configuration
# =============================================================================
sessions:
  default_ttl_hours: 24                  # Sessions expire after 24h of inactivity
  max_ttl_hours: 168                     # Hard limit: 7 days
  default_cost_budget_usd: 50.00         # Default per-session cost limit
  max_cost_budget_usd: 500.00            # Hard limit on cost budget
  cleanup_interval_minutes: 60           # Run expired session cleanup every hour

event_bus:
  transport: redis                       # "redis" (pub/sub) or "memory" (testing)
  channel_prefix: "session"

memory:
  rolling_summary:
    compression_trigger_messages: 20     # Compress when history exceeds this
    max_summary_tokens: 8000
    summarization_model: "anthropic:claude-haiku-4-5-20251001"
  semantic:
    embedding_model: "text-embedding-3-small"
    similarity_threshold: 0.85           # For deduplication
    max_retrieved_memories: 5
```

**`config/settings/temporal.yaml`:**

```yaml
# =============================================================================
# Temporal Configuration (Tier 4 only)
# =============================================================================
temporal:
  enabled: false                         # Feature flag — enable when needed
  server_url: "localhost:7233"
  namespace: "default"
  task_queue: "agent-plans"
  worker_count: 4
  workflow_execution_timeout_days: 30    # Max workflow duration
```

---

## Adoption Checklist

### Phase 1: Event Bus and Session Model (Start Here)

- [ ] Install `redis>=5.0` (if not already present for Taskiq)
- [ ] Create `modules/backend/events/` with `types.py` and `bus.py`
- [ ] Create `modules/backend/models/session.py` with Session and SessionChannel
- [ ] Create `modules/backend/services/session.py` with SessionService
- [ ] Create `modules/backend/schemas/session.py`
- [ ] Run Alembic migration for `sessions` and `session_channels` tables
- [ ] Add `sessions.yaml` to `config/settings/`
- [ ] Write unit tests for event serialization and session lifecycle

### Phase 2: Streaming Coordinator

- [ ] Create `modules/backend/agents/coordinator/handler.py` with `handle()`
- [ ] Create `modules/backend/agents/coordinator/router.py` with agent registry
- [ ] Create `modules/backend/agents/coordinator/cost.py` with budget enforcement
- [ ] Create `modules/backend/api/v1/endpoints/sessions.py` with SSE streaming
- [ ] Write integration test: send message → receive event stream → verify events
- [ ] Modify Telegram adapter to consume event stream from `handle()`

### Phase 3: Plan Management

- [ ] Create `modules/backend/models/plan.py` with Plan, Task, TaskDependency, TaskAttempt, PlanDecision
- [ ] Run Alembic migration for plan tables
- [ ] Create `modules/backend/services/plan.py` with DAG traversal and plan revision
- [ ] Write unit tests for ready-task query and plan revision logic
- [ ] Add plan events to event bus

### Phase 4: Memory Architecture

- [ ] Install `pgvector` extension in PostgreSQL
- [ ] Create `modules/backend/models/memory.py` with memory models
- [ ] Create `modules/backend/services/memory.py` with context assembly and compression
- [ ] Create `modules/backend/tasks/memory_extraction.py` as background task
- [ ] Write tests for context window assembly and rolling summary

### Phase 5: Approval Gates

- [ ] Create `modules/backend/agents/coordinator/approval.py`
- [ ] Create `modules/backend/agents/coordinator/escalation.py`
- [ ] Create `modules/backend/agents/coordinator/notifications.py`
- [ ] Write integration test: approval request → signal → resume

### Phase 6: Temporal Integration (Tier 4 Only)

- [ ] Install `temporalio>=1.7` and `pydantic-ai[temporal]`
- [ ] Create `modules/backend/agents/coordinator/temporal_workflow.py`
- [ ] Add `temporal.yaml` to `config/settings/`
- [ ] Write Temporal workflow test with signals and queries
- [ ] Deploy Temporal Server (or use Temporal Cloud)

---

## Glossary

| Term | Definition |
|------|-----------|
| **Session** | A persistent bidirectional context carrying conversation history, active agents, cost tracking, and channel bindings. Outlives any individual request or connection. |
| **Event** | A typed, timestamped record of an action within a session. Published to the event bus and consumed by channel adapters. |
| **Event Bus** | Redis Pub/Sub transport for real-time event delivery within the application. Not durable — use Temporal for crash recovery. |
| **Coordinator** | The `handle()` function that routes messages to agents, enforces budgets, manages approvals, and yields events. Infrastructure, not intelligence. |
| **Plan** | A mutable DAG of tasks stored in PostgreSQL. Decomposed from a goal by the coordinator agent. Versioned and auditable. |
| **Rolling Summary** | A compressed representation of conversation history, anchored to a message index, updated incrementally. Preserves intent, actions, artifacts, and identifiers. |
| **Unified Responder** | Pattern where approval requests accept responses from humans, AI agents, or automated rules identically. The architecture does not care about the source. |
| **Tier** | One of four graduated complexity levels: stateless CRUD, stateless agent call, interactive session, long-running autonomous. |

---

## Out of Scope

- Stateless CRUD endpoints (covered by 03-backend-architecture.md — unchanged)
- Agent definitions and tool registration (covered by 26-agentic-pydanticai.md)
- MCP server setup and A2A protocol (covered by 27-agent-first-infrastructure.md)
- TUI panel layout and rendering (covered by 28-tui-architecture.md)
- Channel adapter registration and gateway security (covered by 29-multi-channel-gateway.md)
- Service factory and adapter patterns (covered by 30-ai-first-interface-design.md)
- Frontend architecture (covered by 07-frontend-architecture.md)

---

## Related Documentation

- [03-backend-architecture.md](03-backend-architecture.md) — Service layer, repository pattern (unchanged by this module)
- [06-event-architecture.md](06-event-architecture.md) — Event primitives (extended with session events)
- [25-agentic-architecture.md](25-agentic-architecture.md) — Agent concepts, orchestration patterns
- [26-agentic-pydanticai.md](26-agentic-pydanticai.md) — PydanticAI agent implementation
- [27-agent-first-infrastructure.md](27-agent-first-infrastructure.md) — MCP, A2A, agent identity
- [28-tui-architecture.md](28-tui-architecture.md) — TUI rendering (becomes event consumer)
- [29-multi-channel-gateway.md](29-multi-channel-gateway.md) — Channel adapters (become event subscribers)
- [30-ai-first-interface-design.md](30-ai-first-interface-design.md) — Service factory, discovery endpoints
