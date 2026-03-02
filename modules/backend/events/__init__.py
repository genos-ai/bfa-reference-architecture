"""Event architecture — FastStream with Redis Streams."""

from modules.backend.events.bus import SessionEventBus
from modules.backend.events.publishers import EventPublisher
from modules.backend.events.schemas import EventEnvelope
from modules.backend.events.types import (
    EVENT_TYPE_MAP,
    AgentResponseChunkEvent,
    AgentResponseCompleteEvent,
    AgentThinkingEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    ApprovalRequestedEvent,
    ApprovalResponseEvent,
    CostUpdateEvent,
    PlanCreatedEvent,
    PlanRevisedEvent,
    PlanStepCompletedEvent,
    PlanStepStartedEvent,
    SessionEvent,
    UserApprovalEvent,
    UserMessageEvent,
    deserialize_event,
)

__all__ = [
    "SessionEventBus",
    "EventPublisher",
    "EventEnvelope",
    "SessionEvent",
    "UserMessageEvent",
    "UserApprovalEvent",
    "AgentThinkingEvent",
    "AgentToolCallEvent",
    "AgentToolResultEvent",
    "AgentResponseChunkEvent",
    "AgentResponseCompleteEvent",
    "ApprovalRequestedEvent",
    "ApprovalResponseEvent",
    "CostUpdateEvent",
    "PlanCreatedEvent",
    "PlanStepStartedEvent",
    "PlanStepCompletedEvent",
    "PlanRevisedEvent",
    "EVENT_TYPE_MAP",
    "deserialize_event",
]
