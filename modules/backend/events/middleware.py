"""
Event Observability Middleware.

Cross-cutting middleware for FastStream consumers (domain events via Redis
Streams). Binds structlog context for correlation and measures processing
duration.

This middleware applies to FastStream domain event consumers, not the
session event bus (which is raw Redis Pub/Sub).
"""

import time
from typing import Any, Callable

import structlog

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class EventObservabilityMiddleware:
    """FastStream middleware that binds correlation context and logs duration."""

    def __init__(self, msg: Any | None = None, /, **kwargs: Any) -> None:
        self.msg = msg
        self._start_time: float | None = None

    async def on_receive(self) -> None:
        """Bind correlation context when a message is received."""
        self._start_time = time.monotonic()

        if isinstance(self.msg, dict):
            event_id = self.msg.get("event_id", "")
            correlation_id = self.msg.get("correlation_id", "")
            event_type = self.msg.get("event_type", "")
        else:
            event_id = ""
            correlation_id = ""
            event_type = ""

        structlog.contextvars.bind_contextvars(
            source="events",
            event_id=event_id,
            correlation_id=correlation_id,
            event_type=event_type,
        )

    async def after_processed(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: Any | None = None,
    ) -> bool | None:
        """Log duration and clear context after processing."""
        duration_ms = 0.0
        if self._start_time is not None:
            duration_ms = (time.monotonic() - self._start_time) * 1000

        if exc_val is not None:
            logger.error(
                "Event processing failed",
                extra={"duration_ms": round(duration_ms, 2), "error": str(exc_val)},
            )
        else:
            logger.debug(
                "Event processed",
                extra={"duration_ms": round(duration_ms, 2)},
            )

        structlog.contextvars.unbind_contextvars(
            "event_id", "correlation_id", "event_type",
        )
        return False

    async def __aenter__(self) -> "EventObservabilityMiddleware":
        await self.on_receive()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: Any | None = None,
    ) -> bool | None:
        return await self.after_processed(exc_type, exc_val, exc_tb)

    async def consume_scope(
        self,
        call_next: Callable,
        msg: Any,
    ) -> Any:
        """Wrap consumer execution with observability context."""
        self.msg = msg
        await self.on_receive()

        exc_val: BaseException | None = None
        try:
            result = await call_next(msg)
        except Exception as e:
            exc_val = e
            raise
        finally:
            await self.after_processed(type(exc_val) if exc_val else None, exc_val)

        return result
