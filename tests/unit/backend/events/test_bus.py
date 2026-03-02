"""
Unit Tests for Session Event Bus.

Tests SessionEventBus publish/subscribe against real Redis (P12).
"""

import asyncio
import json
import uuid

import pytest
from redis.asyncio import Redis as AsyncRedis

from modules.backend.events.bus import SessionEventBus
from modules.backend.events.types import AgentThinkingEvent, UserMessageEvent


SESSION_ID = uuid.uuid4()


@pytest.fixture
def bus(redis: AsyncRedis) -> SessionEventBus:
    """Create a SessionEventBus backed by real Redis."""
    return SessionEventBus(redis)


class TestPublish:
    """Test event publishing to real Redis Pub/Sub."""

    @pytest.mark.asyncio
    async def test_publish_sends_json_to_channel(self, bus: SessionEventBus, redis: AsyncRedis):
        """Published event should be valid JSON on the correct channel."""
        event = AgentThinkingEvent(
            session_id=SESSION_ID,
            source="agent:health",
            agent_id="system.health.agent",
        )

        # Subscribe first so we can verify the message arrives
        pubsub = redis.pubsub()
        channel = f"session:{SESSION_ID}"
        await pubsub.subscribe(channel)
        # Consume the subscribe confirmation message
        await pubsub.get_message(timeout=1.0)

        await bus.publish(event)

        message = await pubsub.get_message(timeout=2.0)
        assert message is not None
        assert message["type"] == "message"

        data = json.loads(message["data"])
        assert data["event_type"] == "agent.thinking.started"
        assert data["agent_id"] == "system.health.agent"
        assert data["session_id"] == str(SESSION_ID)

        await pubsub.unsubscribe(channel)
        await pubsub.close()

    @pytest.mark.asyncio
    async def test_publish_uses_configured_channel_prefix(self, bus: SessionEventBus, redis: AsyncRedis):
        """Channel name should follow {prefix}:{session_id} pattern."""
        sid = uuid.uuid4()
        event = AgentThinkingEvent(
            session_id=sid,
            source="agent:health",
            agent_id="system.health.agent",
        )
        expected_channel = f"session:{sid}"

        pubsub = redis.pubsub()
        await pubsub.subscribe(expected_channel)
        await pubsub.get_message(timeout=1.0)

        await bus.publish(event)

        message = await pubsub.get_message(timeout=2.0)
        assert message is not None
        assert message["channel"].decode() == expected_channel

        await pubsub.unsubscribe(expected_channel)
        await pubsub.close()


class TestSubscribe:
    """Test event subscription from real Redis Pub/Sub."""

    @pytest.mark.asyncio
    async def test_subscribe_receives_typed_event(self, bus: SessionEventBus, redis: AsyncRedis):
        """Subscribed events should deserialize to the correct subclass."""
        sid = uuid.uuid4()
        event = UserMessageEvent(
            session_id=sid,
            source="human",
            content="Hello agent",
            channel="tui",
        )

        received: list = []

        async def collect_events():
            async for evt in bus.subscribe(sid):
                received.append(evt)
                break  # Only need one event

        # Start subscriber in background
        task = asyncio.create_task(collect_events())

        # Give subscriber time to connect
        await asyncio.sleep(0.1)

        # Publish the event
        await bus.publish(event)

        # Wait for subscriber to receive it
        await asyncio.wait_for(task, timeout=3.0)

        assert len(received) == 1
        assert isinstance(received[0], UserMessageEvent)
        assert received[0].content == "Hello agent"
        assert received[0].channel == "tui"
        assert received[0].session_id == sid

    @pytest.mark.asyncio
    async def test_subscribe_receives_multiple_events_in_order(self, bus: SessionEventBus, redis: AsyncRedis):
        """Multiple events published to the same session arrive in order."""
        sid = uuid.uuid4()
        events = [
            AgentThinkingEvent(session_id=sid, source="agent:health", agent_id="agent-1"),
            AgentThinkingEvent(session_id=sid, source="agent:health", agent_id="agent-2"),
            AgentThinkingEvent(session_id=sid, source="agent:health", agent_id="agent-3"),
        ]

        received: list = []

        async def collect_events():
            async for evt in bus.subscribe(sid):
                received.append(evt)
                if len(received) >= 3:
                    break

        task = asyncio.create_task(collect_events())
        await asyncio.sleep(0.1)

        for event in events:
            await bus.publish(event)

        await asyncio.wait_for(task, timeout=3.0)

        assert len(received) == 3
        assert [e.agent_id for e in received] == ["agent-1", "agent-2", "agent-3"]
