"""Tests for TuiEventBus — backend-to-Textual event bridge."""

from unittest.mock import MagicMock, patch

import pytest

from modules.clients.tui.messages import SessionEventReceived
from modules.clients.tui.services.event_listener import TuiEventBus


class TestTuiEventBus:
    @pytest.mark.asyncio
    async def test_publish_posts_message_to_app(self):
        """publish() should call app.post_message with a SessionEventReceived."""
        app = MagicMock()
        bus = TuiEventBus(app)

        event = MagicMock()
        event.event_type = "agent.thinking.started"

        await bus.publish(event)

        app.post_message.assert_called_once()
        msg = app.post_message.call_args[0][0]
        assert isinstance(msg, SessionEventReceived)
        assert msg.event is event

    @pytest.mark.asyncio
    async def test_publish_handles_app_error_gracefully(self):
        """If post_message raises, publish should not propagate the exception."""
        app = MagicMock()
        app.post_message.side_effect = RuntimeError("App not running")
        bus = TuiEventBus(app)

        event = MagicMock()
        event.event_type = "test.event"

        # Should not raise
        await bus.publish(event)

    @pytest.mark.asyncio
    async def test_publish_multiple_events(self):
        """Each publish call should post a separate message."""
        app = MagicMock()
        bus = TuiEventBus(app)

        for i in range(5):
            event = MagicMock()
            event.event_type = f"event.{i}"
            await bus.publish(event)

        assert app.post_message.call_count == 5
