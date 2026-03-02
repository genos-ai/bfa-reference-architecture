"""
Domain Event Publisher.

Base publisher class that gates on the events_publish_enabled feature flag
and handles common publishing logic for domain events on Redis Streams.

Domain-specific publishers will extend this as services start emitting
events in later phases.
"""

from modules.backend.core.logging import get_logger
from modules.backend.events.schemas import EventEnvelope

logger = get_logger(__name__)


class EventPublisher:
    """Publish domain events to Redis Streams, gated by feature flag."""

    async def publish(self, stream: str, event: EventEnvelope) -> None:
        """
        Publish a domain event if the feature flag is enabled.

        When events_publish_enabled is False, the event is silently
        skipped — no broker connection is attempted.

        Args:
            stream: Redis Stream name (e.g. "notes:note-created").
            event: Event envelope to publish.
        """
        from modules.backend.core.config import get_app_config

        if not get_app_config().features.events_publish_enabled:
            return

        from modules.backend.events.broker import get_event_broker

        broker = get_event_broker()
        await broker.publish(event.model_dump(), stream=stream)
        logger.debug(
            "Event published",
            extra={
                "stream": stream,
                "event_type": event.event_type,
                "event_id": event.event_id,
            },
        )
