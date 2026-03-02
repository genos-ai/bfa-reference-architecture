"""
Session Event Hierarchy.

Real-time agent lifecycle events published via Redis Pub/Sub within a session.
These are ephemeral — not persisted by the event bus. PostgreSQL persistence
happens via the session/memory layer (Phase 2).

All session events extend SessionEvent (not EventEnvelope — different base,
different transport, different purpose).

Event type registry maps event_type strings to Pydantic model classes
for type-safe deserialization.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now

logger = get_logger(__name__)


# =============================================================================
# Base
# =============================================================================


class SessionEvent(BaseModel):
    """Base class for all session lifecycle events."""

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str
    session_id: uuid.UUID
    timestamp: datetime = Field(default_factory=utc_now)
    source: str
    correlation_id: str | None = None
    trace_id: str | None = None
    metadata: dict = Field(default_factory=dict)


# =============================================================================
# User Events
# =============================================================================


class UserMessageEvent(SessionEvent):
    """User sent a message to the session."""

    event_type: str = "user.message.sent"
    content: str
    channel: str
    attachments: list[str] = Field(default_factory=list)


class UserApprovalEvent(SessionEvent):
    """User responded to an approval request."""

    event_type: str = "user.approval.granted"
    decision: str
    approval_request_id: str
    reason: str | None = None
    modified_params: dict = Field(default_factory=dict)


# =============================================================================
# Agent Events
# =============================================================================


class AgentThinkingEvent(SessionEvent):
    """Agent started processing (thinking indicator)."""

    event_type: str = "agent.thinking.started"
    agent_id: str


class AgentToolCallEvent(SessionEvent):
    """Agent invoked a tool."""

    event_type: str = "agent.tool.called"
    agent_id: str
    tool_name: str
    tool_args: dict = Field(default_factory=dict)
    tool_call_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class AgentToolResultEvent(SessionEvent):
    """Tool returned a result to the agent."""

    event_type: str = "agent.tool.returned"
    agent_id: str
    tool_name: str
    tool_call_id: str
    result: str | None = None
    status: str = "success"
    error_detail: str | None = None


class AgentResponseChunkEvent(SessionEvent):
    """Streaming response chunk from agent."""

    event_type: str = "agent.response.chunk"
    agent_id: str
    content: str
    is_final: bool = False


class AgentResponseCompleteEvent(SessionEvent):
    """Agent completed its full response."""

    event_type: str = "agent.response.complete"
    agent_id: str
    full_content: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""


# =============================================================================
# Approval Events
# =============================================================================


class ApprovalRequestedEvent(SessionEvent):
    """Agent requests human-in-the-loop approval."""

    event_type: str = "agent.approval.requested"
    approval_request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    action: str
    context: dict = Field(default_factory=dict)
    allowed_decisions: list[str] = Field(default_factory=lambda: ["approve", "deny"])
    responder_options: list[str] = Field(default_factory=list)
    timeout_seconds: int = 300


class ApprovalResponseEvent(SessionEvent):
    """Approval decision received (from human or auto-policy)."""

    event_type: str = "approval.response.received"
    approval_request_id: str
    decision: str
    responder_type: str = "human"
    responder_id: str | None = None
    reason: str | None = None
    modified_params: dict = Field(default_factory=dict)


# =============================================================================
# Plan Events
# =============================================================================


class PlanCreatedEvent(SessionEvent):
    """Multi-step plan was created."""

    event_type: str = "plan.created"
    plan_id: str
    goal: str
    step_count: int


class PlanStepStartedEvent(SessionEvent):
    """A plan step started execution."""

    event_type: str = "plan.step.started"
    plan_id: str
    step_id: str
    step_name: str
    assigned_agent: str


class PlanStepCompletedEvent(SessionEvent):
    """A plan step completed."""

    event_type: str = "plan.step.completed"
    plan_id: str
    step_id: str
    result_summary: str
    status: str


class PlanRevisedEvent(SessionEvent):
    """Plan was revised mid-execution."""

    event_type: str = "plan.revised"
    plan_id: str
    revision_reason: str
    steps_added: int = 0
    steps_removed: int = 0
    steps_modified: int = 0


# =============================================================================
# Cost Events
# =============================================================================


class CostUpdateEvent(SessionEvent):
    """Session cost was updated after an LLM call."""

    event_type: str = "session.cost.updated"
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cumulative_cost_usd: float
    budget_remaining_usd: float | None = None
    model: str
    source_event_type: str = ""


# =============================================================================
# Event Type Registry
# =============================================================================


EVENT_TYPE_MAP: dict[str, type[SessionEvent]] = {
    "user.message.sent": UserMessageEvent,
    "user.approval.granted": UserApprovalEvent,
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


def deserialize_event(data: dict) -> SessionEvent | None:
    """
    Deserialize a dict into the correct SessionEvent subclass.

    Looks up event_type in the registry. Falls back to base SessionEvent
    for unknown types. Returns None if data is invalid.

    Args:
        data: Dictionary with event fields including event_type.

    Returns:
        Typed SessionEvent instance, or None if deserialization fails.
    """
    event_type = data.get("event_type")
    if not event_type:
        logger.warning("Missing event_type in event data", extra={"data_keys": list(data.keys())})
        return None

    event_cls = EVENT_TYPE_MAP.get(event_type, SessionEvent)
    try:
        return event_cls(**data)
    except Exception:
        logger.warning(
            "Failed to deserialize event",
            extra={"event_type": event_type},
            exc_info=True,
        )
        return None
