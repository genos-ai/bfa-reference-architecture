"""
Unit Tests for Domain Event Publisher.

Tests feature flag gating against real config (P12).
The publisher reads the real feature flag from config/settings/features.yaml.
Only the FastStream broker is mocked because it requires a running broker
connection — the feature flag gating logic is the system under test.
"""

from unittest.mock import AsyncMock, patch

import pytest

from modules.backend.core.config import get_app_config
from modules.backend.events.publishers import EventPublisher
from modules.backend.events.schemas import EventEnvelope


@pytest.fixture(autouse=True)
def _clear_config_cache():
    """Clear lru_cache so tests get a fresh config load."""
    get_app_config.cache_clear()
    yield
    get_app_config.cache_clear()


class TestEventPublisher:
    """Test EventPublisher feature flag gating."""

    @pytest.mark.asyncio
    async def test_publish_skips_silently_when_flag_disabled(self):
        """
        With events_publish_enabled=false (the default in features.yaml),
        publishing does nothing — no broker connection is attempted.
        """
        publisher = EventPublisher()
        event = EventEnvelope(
            event_type="notes.note.created",
            source="note-service",
            payload={"note_id": "abc"},
        )

        # Verify the real config has the flag disabled
        config = get_app_config()
        assert config.features.events_publish_enabled is False

        # If the publisher tried to use the broker, this patch would detect it
        with patch("modules.backend.events.broker.get_event_broker") as mock_broker_fn:
            await publisher.publish("notes:note-created", event)
            mock_broker_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_calls_broker_when_flag_enabled(self):
        """
        When feature flag is enabled, the publisher forwards the event
        to the FastStream broker with the correct stream name.
        """
        publisher = EventPublisher()
        event = EventEnvelope(
            event_type="notes.note.created",
            source="note-service",
            payload={"note_id": "abc"},
        )

        # Temporarily enable the flag via config override
        config = get_app_config()
        original_value = config.features.events_publish_enabled
        object.__setattr__(config.features, "events_publish_enabled", True)

        try:
            mock_broker = AsyncMock()
            with patch("modules.backend.events.broker.get_event_broker", return_value=mock_broker):
                await publisher.publish("notes:note-created", event)
                mock_broker.publish.assert_called_once()
                call_kwargs = mock_broker.publish.call_args
                assert call_kwargs[1]["stream"] == "notes:note-created"
        finally:
            object.__setattr__(config.features, "events_publish_enabled", original_value)

    @pytest.mark.asyncio
    async def test_publish_sends_serialized_envelope(self):
        """The broker receives the event as a dict with all envelope fields."""
        publisher = EventPublisher()
        event = EventEnvelope(
            event_type="notes.note.created",
            source="note-service",
            session_id="sess-123",
            payload={"title": "Test Note"},
        )

        config = get_app_config()
        object.__setattr__(config.features, "events_publish_enabled", True)

        try:
            mock_broker = AsyncMock()
            with patch("modules.backend.events.broker.get_event_broker", return_value=mock_broker):
                await publisher.publish("notes:note-created", event)
                published_data = mock_broker.publish.call_args[0][0]
                assert published_data["event_type"] == "notes.note.created"
                assert published_data["source"] == "note-service"
                assert published_data["session_id"] == "sess-123"
                assert published_data["payload"]["title"] == "Test Note"
                assert "event_id" in published_data
                assert "correlation_id" in published_data
                assert "timestamp" in published_data
        finally:
            object.__setattr__(config.features, "events_publish_enabled", False)
