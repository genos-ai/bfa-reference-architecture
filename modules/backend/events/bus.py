"""
Session Event Bus.

Redis Pub/Sub wrapper for real-time session event delivery. This is NOT
FastStream Streams — it uses Redis Pub/Sub for ephemeral, sub-millisecond
event delivery to connected channels (TUI, WebSocket, etc.).

Channel naming: {prefix}:{session_id} (e.g. session:<uuid>)
"""

import asyncio
import uuid
from collections.abc import AsyncIterator

from redis.asyncio import Redis

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger

from modules.backend.events.types import SessionEvent, deserialize_event

logger = get_logger(__name__)


class SessionEventBus:
    """Publish and subscribe to real-time session events via Redis Pub/Sub."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._prefix = get_app_config().events.channel_prefix

    def _channel_name(self, session_id: uuid.UUID) -> str:
        """Build the Pub/Sub channel name for a session."""
        return f"{self._prefix}:{session_id}"

    async def publish(self, event: SessionEvent) -> None:
        """
        Publish an event to the session's Pub/Sub channel.

        Args:
            event: Session event to publish.
        """
        channel = self._channel_name(event.session_id)
        payload = event.model_dump_json()
        await self._redis.publish(channel, payload)
        logger.debug(
            "Session event published",
            extra={
                "channel": channel,
                "event_type": event.event_type,
                "event_id": str(event.event_id),
            },
        )

    async def subscribe(self, session_id: uuid.UUID) -> AsyncIterator[SessionEvent]:
        """
        Subscribe to all events for a session.

        Yields events as they arrive. Cleans up the subscription on exit.

        Args:
            session_id: Session to subscribe to.

        Yields:
            Deserialized SessionEvent instances.
        """
        channel = self._channel_name(session_id)
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        logger.debug("Subscribed to session channel", extra={"channel": channel})

        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    await asyncio.sleep(0.01)
                    continue

                if message["type"] != "message":
                    continue

                import json
                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Invalid JSON in session event", extra={"channel": channel})
                    continue

                event = deserialize_event(data)
                if event is not None:
                    yield event
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            logger.debug("Unsubscribed from session channel", extra={"channel": channel})
