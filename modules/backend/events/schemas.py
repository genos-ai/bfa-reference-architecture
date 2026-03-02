"""
Domain Event Envelope.

Base schema for domain events published to Redis Streams via FastStream.
These are durable events with consumer groups and dead-letter queues,
used for inter-module communication.

Event type naming: {domain}.{entity}.{action} (e.g. notes.note.created)
Stream naming:     {domain}:{entity}-{action} (e.g. notes:note-created)

All envelopes include Tier 4 fields (correlation_id, trace_id, session_id)
from day one.
"""

import uuid

from pydantic import BaseModel, Field

from modules.backend.core.utils import utc_now


class EventEnvelope(BaseModel):
    """Base envelope for domain events on Redis Streams."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    event_version: int = 1
    timestamp: str = Field(default_factory=lambda: utc_now().isoformat())
    source: str
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str | None = None
    session_id: str | None = None
    payload: dict = Field(default_factory=dict)
