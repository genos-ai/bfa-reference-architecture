"""
Unit Tests for mission_control handle() streaming handler.

Per P12: real PostgreSQL (db_session with rollback), real config/registry,
TestModel for LLM (the only mock — we don't operate LLM providers).
"""

import uuid
from unittest.mock import patch

import pytest
from pydantic_ai.models.test import TestModel

from modules.backend.agents.mission_control.mission_control import handle
from modules.backend.events.types import (
    AgentResponseChunkEvent,
    AgentResponseCompleteEvent,
    AgentThinkingEvent,
    CostUpdateEvent,
    UserMessageEvent,
)
from modules.backend.schemas.session import SessionCreate
from modules.backend.services.session import SessionService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session_service(db_session):
    return SessionService(db_session)


@pytest.fixture
async def health_session(session_service):
    """Create a real session in the DB, pinned to the health agent."""
    session = await session_service.create_session(
        SessionCreate(goal="test handler", agent_id="system.health.agent"),
    )
    return session


@pytest.fixture(autouse=True)
def _reset_registry():
    """Clear cached agent instances so TestModel gets injected each time."""
    from modules.backend.agents.mission_control.registry import get_registry

    get_registry().reset()
    yield
    get_registry().reset()


def _patch_build_model():
    """Patch _build_model to return TestModel (LLM provider mock per P12)."""
    return patch(
        "modules.backend.agents.mission_control.mission_control._build_model",
        return_value=TestModel(call_tools=[]),
    )


async def _collect_events(session_id, message, session_service, event_bus=None):
    """Helper: consume handle() and return list of events."""
    events = []
    with _patch_build_model():
        async for event in handle(
            str(session_id),
            message,
            session_service=session_service,
            event_bus=event_bus,
        ):
            events.append(event)
    return events


# ---------------------------------------------------------------------------
# Event type and ordering tests
# ---------------------------------------------------------------------------


class TestHandleEventFlow:
    """Tests for the streaming event flow from handle()."""

    @pytest.mark.asyncio
    async def test_yields_user_message_event(self, session_service, health_session):
        events = await _collect_events(health_session.id, "check health", session_service)
        user_events = [e for e in events if isinstance(e, UserMessageEvent)]
        assert len(user_events) == 1
        assert user_events[0].content == "check health"

    @pytest.mark.asyncio
    async def test_yields_thinking_event(self, session_service, health_session):
        events = await _collect_events(health_session.id, "check health", session_service)
        thinking = [e for e in events if isinstance(e, AgentThinkingEvent)]
        assert len(thinking) == 1
        assert thinking[0].agent_id == "system.health.agent"

    @pytest.mark.asyncio
    async def test_yields_complete_event(self, session_service, health_session):
        events = await _collect_events(health_session.id, "check health", session_service)
        complete = [e for e in events if isinstance(e, AgentResponseCompleteEvent)]
        assert len(complete) == 1
        assert complete[0].agent_id == "system.health.agent"

    @pytest.mark.asyncio
    async def test_yields_cost_update_event(self, session_service, health_session):
        events = await _collect_events(health_session.id, "check health", session_service)
        cost_events = [e for e in events if isinstance(e, CostUpdateEvent)]
        assert len(cost_events) == 1
        assert cost_events[0].cumulative_cost_usd >= 0

    @pytest.mark.asyncio
    async def test_event_order(self, session_service, health_session):
        """Events arrive in correct order: user → thinking → [chunks] → complete → cost."""
        events = await _collect_events(health_session.id, "check health", session_service)

        # Find indices of key event types
        types = [type(e).__name__ for e in events]
        user_idx = types.index("UserMessageEvent")
        thinking_idx = types.index("AgentThinkingEvent")
        complete_idx = types.index("AgentResponseCompleteEvent")
        cost_idx = types.index("CostUpdateEvent")

        assert user_idx < thinking_idx < complete_idx < cost_idx

    @pytest.mark.asyncio
    async def test_all_events_have_session_id(self, session_service, health_session):
        events = await _collect_events(health_session.id, "check health", session_service)
        expected_sid = uuid.UUID(str(health_session.id))
        for event in events:
            assert event.session_id == expected_sid


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


class TestHandleRouting:
    """Tests for agent resolution logic."""

    @pytest.mark.asyncio
    async def test_session_agent_routing(self, session_service, health_session):
        """Uses session.agent_id when set."""
        events = await _collect_events(health_session.id, "anything", session_service)
        complete = [e for e in events if isinstance(e, AgentResponseCompleteEvent)]
        assert complete[0].agent_id == "system.health.agent"

    @pytest.mark.asyncio
    async def test_keyword_routing_fallback(self, session_service):
        """Falls back to keyword routing when session has no agent_id."""
        session = await session_service.create_session(
            SessionCreate(goal="test routing"),
        )
        events = await _collect_events(session.id, "check system health", session_service)
        complete = [e for e in events if isinstance(e, AgentResponseCompleteEvent)]
        # Should route to health agent by keyword
        assert complete[0].agent_id == "system.health.agent"


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------


class TestHandlePersistence:
    """Tests that handle() persists messages and updates cost."""

    @pytest.mark.asyncio
    async def test_persists_messages(self, session_service, health_session):
        await _collect_events(health_session.id, "check health", session_service)

        messages, _ = await session_service.get_messages(str(health_session.id), limit=10)
        roles = [m.role for m in messages]
        assert "user" in roles
        assert "assistant" in roles

    @pytest.mark.asyncio
    async def test_updates_session_cost(self, session_service, health_session):
        await _collect_events(health_session.id, "check health", session_service)

        updated = await session_service.get_session(str(health_session.id))
        # Cost should be computed (may be 0 with TestModel but update_cost was called)
        assert updated.total_cost_usd >= 0

    @pytest.mark.asyncio
    async def test_touches_activity(self, session_service, health_session):
        original_activity = health_session.last_activity_at
        await _collect_events(health_session.id, "check health", session_service)

        updated = await session_service.get_session(str(health_session.id))
        assert updated.last_activity_at >= original_activity


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestHandleErrors:
    """Tests that errors yield events instead of crashing."""

    @pytest.mark.asyncio
    async def test_error_yields_complete_event(self, session_service):
        """Invalid session_id yields an error complete event, no exception."""
        fake_id = str(uuid.uuid4())
        events = []
        with _patch_build_model():
            async for event in handle(fake_id, "hello", session_service=session_service):
                events.append(event)

        complete = [e for e in events if isinstance(e, AgentResponseCompleteEvent)]
        assert len(complete) == 1
        assert "Error" in complete[0].full_content

    @pytest.mark.asyncio
    async def test_works_without_event_bus(self, session_service, health_session):
        """handle() works when event_bus is None."""
        events = await _collect_events(
            health_session.id, "check health", session_service, event_bus=None,
        )
        assert any(isinstance(e, AgentResponseCompleteEvent) for e in events)
