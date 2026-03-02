"""
FastStream Redis Broker.

Lazy-initialized broker and FastStream application for the event worker
process. Follows the same pattern as modules/backend/tasks/broker.py.

Usage:
    # Get broker singleton
    from modules.backend.events.broker import get_event_broker

    # Start worker process
    python cli.py --service event-worker

    # Or directly with faststream
    faststream run modules.backend.events.broker:create_event_app --factory
"""

from typing import TYPE_CHECKING

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from faststream import FastStream
    from faststream.redis import RedisBroker


_broker: "RedisBroker | None" = None
_app: "FastStream | None" = None


def create_event_broker() -> "RedisBroker":
    """
    Create a new FastStream Redis broker.

    Configuration loaded from config/settings/database.yaml (Redis connection)
    and config/settings/events.yaml (event bus settings).

    Returns:
        Configured RedisBroker instance.
    """
    from faststream.redis import RedisBroker as _RedisBroker

    from modules.backend.core.config import get_redis_url

    redis_url = get_redis_url()
    broker = _RedisBroker(url=redis_url)

    logger.debug("FastStream event broker created", extra={"url": "redis://***"})
    return broker


def get_event_broker() -> "RedisBroker":
    """
    Get the broker singleton, creating it if necessary.

    Returns:
        Configured broker instance.
    """
    global _broker
    if _broker is None:
        _broker = create_event_broker()
    return _broker


def create_event_app() -> "FastStream":
    """
    Create the FastStream application for the event worker process.

    Attaches observability middleware and imports consumer modules
    to register their subscribers.

    Returns:
        Configured FastStream application.
    """
    from faststream import FastStream as _FastStream

    from modules.backend.events.middleware import EventObservabilityMiddleware

    global _app
    if _app is not None:
        return _app

    broker = get_event_broker()
    broker.middlewares = (EventObservabilityMiddleware,)

    _app = _FastStream(broker)

    logger.info("FastStream event application created")
    return _app
