"""TuiEventBus — bridges backend event publishing to Textual's message loop.

Implements EventBusProtocol so dispatch/helpers can publish events
that arrive as Textual Messages in the App's event loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from modules.backend.agents.mission_control.models import EventBusProtocol
from modules.backend.core.logging import get_logger
from modules.backend.events.types import SessionEvent

if TYPE_CHECKING:
    from textual.app import App

logger = get_logger(__name__)


class TuiEventBus(EventBusProtocol):
    """EventBusProtocol implementation that posts to a Textual App.

    When dispatch() or helpers call ``await event_bus.publish(event)``,
    this converts the SessionEvent into a Textual Message and posts it
    to the App's message queue. Since dispatch runs in the same asyncio
    event loop as Textual (via @work(thread=False)), the message is
    delivered on the next event loop iteration.
    """

    def __init__(self, app: App) -> None:
        self._app = app

    async def publish(self, event: SessionEvent) -> None:
        """Post a SessionEvent to the Textual App as a message."""
        from modules.clients.tui.messages import SessionEventReceived

        try:
            self._app.post_message(SessionEventReceived(event=event))
        except Exception:
            logger.debug(
                "Failed to post event to TUI",
                extra={"event_type": event.event_type},
                exc_info=True,
            )
