"""
Unit Tests for Session Event Hierarchy.

Tests all SessionEvent subclasses, the event type registry,
and the deserialize_event function.
"""

import uuid

import pytest

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

SESSION_ID = uuid.uuid4()


class TestSessionEventDefaults:
    """Test that base SessionEvent auto-generates required fields."""

    def test_event_id_is_generated(self):
        event = SessionEvent(
            event_type="test", session_id=SESSION_ID, source="test"
        )
        assert isinstance(event.event_id, uuid.UUID)

    def test_timestamp_is_populated(self):
        event = SessionEvent(
            event_type="test", session_id=SESSION_ID, source="test"
        )
        assert event.timestamp is not None

    def test_tier4_fields_present(self):
        event = SessionEvent(
            event_type="test", session_id=SESSION_ID, source="test"
        )
        assert event.correlation_id is None
        assert event.trace_id is None
        assert event.session_id == SESSION_ID

    def test_metadata_defaults_to_empty_dict(self):
        event = SessionEvent(
            event_type="test", session_id=SESSION_ID, source="test"
        )
        assert event.metadata == {}


class TestUserEvents:
    """Test user event subclasses."""

    def test_user_message_event(self):
        event = UserMessageEvent(
            session_id=SESSION_ID,
            source="human",
            content="Hello",
            channel="telegram",
        )
        assert event.event_type == "user.message.sent"
        assert event.content == "Hello"
        assert event.channel == "telegram"
        assert event.attachments == []

    def test_user_approval_event(self):
        event = UserApprovalEvent(
            session_id=SESSION_ID,
            source="human",
            decision="approve",
            approval_request_id="req-123",
        )
        assert event.event_type == "user.approval.granted"
        assert event.decision == "approve"
        assert event.approval_request_id == "req-123"


class TestAgentEvents:
    """Test agent event subclasses."""

    def test_agent_thinking_event(self):
        event = AgentThinkingEvent(
            session_id=SESSION_ID,
            source="agent:health",
            agent_id="system.health.agent",
        )
        assert event.event_type == "agent.thinking.started"
        assert event.agent_id == "system.health.agent"

    def test_agent_tool_call_event(self):
        event = AgentToolCallEvent(
            session_id=SESSION_ID,
            source="agent:health",
            agent_id="system.health.agent",
            tool_name="check_system_health",
            tool_args={"verbose": True},
        )
        assert event.event_type == "agent.tool.called"
        assert event.tool_name == "check_system_health"
        assert event.tool_args == {"verbose": True}
        assert event.tool_call_id

    def test_agent_tool_result_event(self):
        event = AgentToolResultEvent(
            session_id=SESSION_ID,
            source="agent:health",
            agent_id="system.health.agent",
            tool_name="check_system_health",
            tool_call_id="tc-1",
            result="All healthy",
        )
        assert event.event_type == "agent.tool.returned"
        assert event.status == "success"
        assert event.error_detail is None

    def test_agent_response_chunk_event(self):
        event = AgentResponseChunkEvent(
            session_id=SESSION_ID,
            source="agent:health",
            agent_id="system.health.agent",
            content="partial response",
        )
        assert event.event_type == "agent.response.chunk"
        assert event.is_final is False

    def test_agent_response_complete_event(self):
        event = AgentResponseCompleteEvent(
            session_id=SESSION_ID,
            source="agent:health",
            agent_id="system.health.agent",
            full_content="All systems healthy",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            model="haiku",
        )
        assert event.event_type == "agent.response.complete"
        assert event.input_tokens == 100
        assert event.output_tokens == 50
        assert event.cost_usd == 0.001
        assert event.model == "haiku"


class TestApprovalEvents:
    """Test approval event subclasses."""

    def test_approval_requested_event(self):
        event = ApprovalRequestedEvent(
            session_id=SESSION_ID,
            source="agent:qa",
            agent_id="code.quality.agent",
            action="apply_fix",
            context={"file": "main.py"},
            allowed_decisions=["approve", "deny", "modify"],
        )
        assert event.event_type == "agent.approval.requested"
        assert event.approval_request_id
        assert "approve" in event.allowed_decisions
        assert event.timeout_seconds == 300

    def test_approval_response_event(self):
        event = ApprovalResponseEvent(
            session_id=SESSION_ID,
            source="system",
            approval_request_id="req-123",
            decision="approve",
            responder_type="human",
        )
        assert event.event_type == "approval.response.received"
        assert event.responder_id is None


class TestPlanEvents:
    """Test plan event subclasses."""

    def test_plan_created_event(self):
        event = PlanCreatedEvent(
            session_id=SESSION_ID,
            source="agent:pm",
            plan_id="plan-1",
            goal="Deploy to production",
            step_count=5,
        )
        assert event.event_type == "plan.created"
        assert event.step_count == 5

    def test_plan_step_started_event(self):
        event = PlanStepStartedEvent(
            session_id=SESSION_ID,
            source="system",
            plan_id="plan-1",
            step_id="step-1",
            step_name="Run tests",
            assigned_agent="code.quality.agent",
        )
        assert event.event_type == "plan.step.started"

    def test_plan_step_completed_event(self):
        event = PlanStepCompletedEvent(
            session_id=SESSION_ID,
            source="system",
            plan_id="plan-1",
            step_id="step-1",
            result_summary="All tests passed",
            status="success",
        )
        assert event.event_type == "plan.step.completed"

    def test_plan_revised_event(self):
        event = PlanRevisedEvent(
            session_id=SESSION_ID,
            source="agent:pm",
            plan_id="plan-1",
            revision_reason="Test failure requires fix",
            steps_added=2,
            steps_removed=0,
            steps_modified=1,
        )
        assert event.event_type == "plan.revised"
        assert event.steps_added == 2


class TestCostUpdateEvent:
    """Test cost update event."""

    def test_cost_update_event(self):
        event = CostUpdateEvent(
            session_id=SESSION_ID,
            source="system",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.01,
            cumulative_cost_usd=0.05,
            budget_remaining_usd=9.95,
            model="haiku",
        )
        assert event.event_type == "session.cost.updated"
        assert event.cumulative_cost_usd == 0.05
        assert event.budget_remaining_usd == 9.95


class TestEventTypeMap:
    """Test the event type registry."""

    def test_all_subclasses_have_entries(self):
        """Every concrete SessionEvent subclass should be in EVENT_TYPE_MAP."""
        subclasses = [
            UserMessageEvent,
            UserApprovalEvent,
            AgentThinkingEvent,
            AgentToolCallEvent,
            AgentToolResultEvent,
            AgentResponseChunkEvent,
            AgentResponseCompleteEvent,
            ApprovalRequestedEvent,
            ApprovalResponseEvent,
            PlanCreatedEvent,
            PlanStepStartedEvent,
            PlanStepCompletedEvent,
            PlanRevisedEvent,
            CostUpdateEvent,
        ]
        for cls in subclasses:
            event_type = cls.model_fields["event_type"].default
            assert event_type in EVENT_TYPE_MAP, f"{cls.__name__} missing from EVENT_TYPE_MAP"
            assert EVENT_TYPE_MAP[event_type] is cls

    def test_registry_has_nineteen_entries(self):
        assert len(EVENT_TYPE_MAP) == 19


class TestDeserializeEvent:
    """Test the deserialize_event function."""

    def test_known_type_returns_correct_subclass(self):
        data = {
            "event_type": "agent.thinking.started",
            "session_id": str(SESSION_ID),
            "source": "agent:health",
            "agent_id": "system.health.agent",
        }
        event = deserialize_event(data)
        assert isinstance(event, AgentThinkingEvent)
        assert event.agent_id == "system.health.agent"

    def test_unknown_type_falls_back_to_base(self):
        data = {
            "event_type": "custom.unknown.event",
            "session_id": str(SESSION_ID),
            "source": "test",
        }
        event = deserialize_event(data)
        assert isinstance(event, SessionEvent)
        assert event.event_type == "custom.unknown.event"

    def test_missing_event_type_returns_none(self):
        data = {"source": "test", "session_id": str(SESSION_ID)}
        event = deserialize_event(data)
        assert event is None

    def test_invalid_data_returns_none(self):
        data = {"event_type": "agent.thinking.started", "bad_field": True}
        event = deserialize_event(data)
        assert event is None
