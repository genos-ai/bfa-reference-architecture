# Implementation Plan: Event Bus (FastStream + Redis Streams)

*Created: 2026-03-02*
*Status: Complete*
*Phase: 1 of 6 (AI-First Platform Build)*
*Depends on: Nothing — this is the foundation*
*Blocked by: Nothing*

---

## Summary

Build the event infrastructure using FastStream with Redis Streams as the transport. This is the backbone of the platform — every action (human message, agent thought, tool call, approval request, cost update, plan step) becomes a typed event on the bus. Channels consume these events and render them in their native format.

Two event systems for two jobs:
- **Domain events** (FastStream + Redis Streams): durable, consumer groups, DLQ, acknowledgement. For inter-module communication (`notes.note.created`).
- **Session events** (Redis Pub/Sub via FastStream): ephemeral, real-time, sub-millisecond. For agent lifecycle events within a session (`agent.thinking.started`, `agent.response.chunk`).

All event schemas must include Tier 4 fields from day one: `correlation_id`, `trace_id`, `session_id`. No retrofitting.

## Context

- Reference architecture: BFF repo `genos-ai/bff-python-reference-architecture` doc 35 (Section 2: Event Bus)
- Local doc: `docs/99-reference-architecture/46-event-session-architecture.md` (Section 2)
- FastStream implementation pattern: BFF Cursor transcript `48f394cf` (steps 15-20: broker, schemas, middleware, publishers, consumers)
- Research: `docs/98-research/09-Building autonomous AI agents that run for weeks.md`

## Key Design Decisions

- FastStream provides unified API across Redis/Kafka/NATS — future-proof transport swapping
- `EventEnvelope` is the base schema for domain events; `SessionEvent` is the base for session lifecycle events
- Feature flag `events_publish_enabled` gates publishing — no breaking changes to existing code
- ObservabilityMiddleware binds `correlation_id`, `event_type`, `source` to structlog context for every consumed event
- Event type registry maps `event_type` strings to Pydantic model classes for deserialization
- `"events"` added to `VALID_SOURCES` in `modules/backend/core/logging.py` for log filtering

## Success Criteria

- [ ] FastStream broker connects to Redis, publishes and consumes events
- [ ] All event types serialize/deserialize correctly with Tier 4 fields present
- [ ] Session event bus publishes and subscribes to per-session channels
- [ ] Middleware logs correlation context for every consumed event
- [ ] Feature flag disables publishing without errors
- [ ] CLI `--service event-worker` starts FastStream consumer
- [ ] Existing 65 tests still pass (no breaking changes)
- [ ] New tests cover event serialization, bus pub/sub, middleware, and publisher feature flag

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Commit any uncommitted work | `git status`, then commit if needed |
| 0.2 | Create feature branch | `git checkout -b feature/event-bus` |

---

### Step 1: Add FastStream dependency

**File:** `requirements.txt`

Add `faststream[redis]>=0.5.0` to the dependencies. Place it in the Redis/Background Tasks section near `redis>=5.0.0` and `taskiq>=0.11.0`.

**Verify:** `pip install -r requirements.txt` completes without errors.

---

### Step 2: Add feature flag

**File:** `modules/backend/core/config_schema.py`

Add `events_publish_enabled: bool = False` to the `FeaturesSchema` class. This follows the existing pattern — all new features are disabled by default (secure by default, P8).

**File:** `config/settings/features.yaml`

Add `events_publish_enabled: false` under the features section.

**Verify:** `get_app_config().features.events_publish_enabled` returns `False`.

---

### Step 3: Add events config schema and YAML

**File:** `modules/backend/core/config_schema.py`

Add a new `EventsSchema` class following the existing `_StrictBase` pattern:

```python
class EventsStreamSchema(_StrictBase):
    maxlen: int = 10000                    # Redis Stream MAXLEN cap
    consumer_group: str = "bfa-workers"    # Default consumer group name

class EventsSchema(_StrictBase):
    transport: str = "redis"               # "redis" or "memory" (testing)
    channel_prefix: str = "session"        # Prefix for session pub/sub channels
    streams: dict[str, EventsStreamSchema] = {}  # Per-stream overrides
    consumer_timeout_ms: int = 5000        # Consumer poll timeout
    dlq_enabled: bool = True               # Dead letter queue
    dlq_prefix: str = "dlq"               # DLQ stream prefix
```

Register `EventsSchema` in `AppConfig` class, loaded from `events.yaml`, with a fallback to defaults if the file doesn't exist (since this is a new optional config).

**File:** `config/settings/events.yaml` (NEW)

```yaml
# =============================================================================
# Event Bus Configuration
# =============================================================================
#   Controls the FastStream event bus, stream sizing, and consumer behavior.
#   Transport: "redis" for production, "memory" for testing.

transport: redis
channel_prefix: session

streams:
  default:
    maxlen: 10000
    consumer_group: bfa-workers

consumer_timeout_ms: 5000
dlq_enabled: true
dlq_prefix: dlq
```

**Verify:** Config loads without error, `get_app_config().events` returns populated schema.

---

### Step 4: Add `"events"` to VALID_SOURCES

**File:** `modules/backend/core/logging.py`

Add `"events"` to the `VALID_SOURCES` frozenset. This allows log filtering by source for all event-related log records.

Current: `frozenset({"web", "cli", "tui", "mobile", "telegram", "api", "tasks", "internal"})`
New: `frozenset({"web", "cli", "tui", "mobile", "telegram", "api", "tasks", "internal", "events"})`

---

### Step 5: Create `events/__init__.py`

**File:** `modules/backend/events/__init__.py` (NEW)

```python
"""Event architecture — FastStream with Redis Streams."""
```

Minimal. Public exports will be added as modules are created.

---

### Step 6: Create `events/broker.py`

**File:** `modules/backend/events/broker.py` (NEW, ~80 lines)

FastStream RedisBroker setup with lazy initialization. Follows the same pattern as `modules/backend/tasks/broker.py` (lazy global with factory function).

**Functions:**
- `create_event_broker() -> RedisBroker` — creates a new broker using `get_redis_url()` from `modules.backend.core.config`
- `get_event_broker() -> RedisBroker` — lazy-initialized global singleton
- `create_event_app() -> FastStream` — creates the FastStream application for the event worker process, registers middleware and consumers

**Key patterns:**
- Import `get_redis_url` inside function body (lazy, avoids circular imports — same pattern as `tasks/broker.py`)
- Module-level `_broker: RedisBroker | None = None` and `_app: FastStream | None = None`
- `create_event_app()` attaches `EventObservabilityMiddleware` to the broker and triggers consumer module imports to register subscribers

**Verify:** `get_event_broker()` returns a valid `RedisBroker` instance.

---

### Step 7: Create `events/schemas.py` — Domain Event Envelope

**File:** `modules/backend/events/schemas.py` (NEW, ~50 lines)

The `EventEnvelope` is the base schema for **domain events** (inter-module communication). These are durable events published to Redis Streams with consumer groups.

```python
class EventEnvelope(BaseModel):
    event_id: str         # Auto-generated UUID
    event_type: str       # Dot notation: domain.entity.action (e.g. "notes.note.created")
    event_version: int    # Schema version for forward compatibility (default: 1)
    timestamp: str        # ISO 8601 UTC from utc_now().isoformat()
    source: str           # Service/module that published (e.g. "note-service")
    correlation_id: str   # Request/session ID for tracing
    trace_id: str | None  # OpenTelemetry trace ID (optional)
    session_id: str | None  # Session ID for Tier 3/4 events (optional)
    payload: dict         # Event-specific data
```

**Naming conventions:**
- `event_type`: `{domain}.{entity}.{action}` in dot notation (e.g. `notes.note.created`)
- Stream name: `{domain}:{entity}-{action}` in colon-separated format (e.g. `notes:note-created`)

No domain-specific event subclasses in this step — those will be added as domains publish events (Phase 2+ when services emit session events). The envelope is sufficient for now.

---

### Step 8: Create `events/types.py` — Session Event Hierarchy

**File:** `modules/backend/events/types.py` (NEW, ~200 lines)

Session events are the real-time agent lifecycle events published via Redis Pub/Sub within a session. These are ephemeral — not persisted by the event bus (PostgreSQL persists what matters via the session/memory layer in Phase 2).

All session events extend `SessionEvent` (not `EventEnvelope` — different base, different transport, different purpose).

**Base class:**

```python
class SessionEvent(BaseModel):
    event_id: UUID            # Auto-generated
    event_type: str           # e.g. "agent.response.chunk"
    session_id: UUID          # Which session this belongs to
    timestamp: datetime       # utc_now()
    source: str               # "human", "agent:<agent_id>", "system"
    correlation_id: str | None = None  # For tracing across services
    trace_id: str | None = None       # OpenTelemetry trace ID
    metadata: dict = {}       # Extensible key-value pairs
```

**Event classes to create (all extend SessionEvent):**

User events:
- `UserMessageEvent` — `event_type="user.message.sent"`, fields: `content`, `channel`, `attachments`
- `UserApprovalEvent` — `event_type="user.approval.granted"`, fields: `decision`, `approval_request_id`, `reason`, `modified_params`

Agent events:
- `AgentThinkingEvent` — `event_type="agent.thinking.started"`, fields: `agent_id`
- `AgentToolCallEvent` — `event_type="agent.tool.called"`, fields: `agent_id`, `tool_name`, `tool_args`, `tool_call_id`
- `AgentToolResultEvent` — `event_type="agent.tool.returned"`, fields: `agent_id`, `tool_name`, `tool_call_id`, `result`, `status`, `error_detail`
- `AgentResponseChunkEvent` — `event_type="agent.response.chunk"`, fields: `agent_id`, `content`, `is_final`
- `AgentResponseCompleteEvent` — `event_type="agent.response.complete"`, fields: `agent_id`, `full_content`, `input_tokens`, `output_tokens`, `cost_usd`, `model`

Approval events:
- `ApprovalRequestedEvent` — `event_type="agent.approval.requested"`, fields: `approval_request_id`, `agent_id`, `action`, `context`, `allowed_decisions`, `responder_options`, `timeout_seconds`
- `ApprovalResponseEvent` — `event_type="approval.response.received"`, fields: `approval_request_id`, `decision`, `responder_type`, `responder_id`, `reason`, `modified_params`

Plan events:
- `PlanCreatedEvent` — `event_type="plan.created"`, fields: `plan_id`, `goal`, `step_count`
- `PlanStepStartedEvent` — `event_type="plan.step.started"`, fields: `plan_id`, `step_id`, `step_name`, `assigned_agent`
- `PlanStepCompletedEvent` — `event_type="plan.step.completed"`, fields: `plan_id`, `step_id`, `result_summary`, `status`
- `PlanRevisedEvent` — `event_type="plan.revised"`, fields: `plan_id`, `revision_reason`, `steps_added`, `steps_removed`, `steps_modified`

Cost events:
- `CostUpdateEvent` — `event_type="session.cost.updated"`, fields: `input_tokens`, `output_tokens`, `cost_usd`, `cumulative_cost_usd`, `budget_remaining_usd`, `model`, `source_event_type`

**Event type registry:**

```python
EVENT_TYPE_MAP: dict[str, type[SessionEvent]] = {
    "user.message.sent": UserMessageEvent,
    "agent.thinking.started": AgentThinkingEvent,
    # ... all event types mapped
}
```

Plus a `deserialize_event(data: dict) -> SessionEvent | None` function that looks up the event type in the registry and validates.

**Reference:** BFF doc 35 Section 2 event types, local doc 46 Section 2.

---

### Step 9: Create `events/bus.py` — Session Event Bus

**File:** `modules/backend/events/bus.py` (NEW, ~80 lines)

Redis Pub/Sub wrapper for real-time session event delivery. This is **not** FastStream Streams — it's Redis Pub/Sub for ephemeral, sub-millisecond event delivery to connected channels.

**Class: `SessionEventBus`**

```python
class SessionEventBus:
    def __init__(self, redis: Redis):
        self._redis = redis

    async def publish(self, event: SessionEvent) -> None:
        """Publish event to session channel: session:{session_id}"""

    async def subscribe(self, session_id: UUID) -> AsyncIterator[SessionEvent]:
        """Subscribe to all events for a session. Yields events as they arrive."""
```

**Key details:**
- Channel naming: `session:{session_id}` (prefix from events.yaml `channel_prefix`)
- `publish()`: serializes event with `model_dump_json()`, publishes to Redis Pub/Sub channel
- `subscribe()`: creates a Redis pubsub subscription, yields deserialized `SessionEvent` objects, cleans up on exit
- Uses `deserialize_event()` from `events/types.py` for type-safe deserialization
- Logs via `get_logger(__name__)` with `source="events"`

**FastAPI dependency:**

Add to `modules/backend/core/dependencies.py`:

```python
async def get_event_bus() -> SessionEventBus:
    """FastAPI dependency for session event bus."""
    from redis.asyncio import Redis
    from modules.backend.core.config import get_redis_url
    from modules.backend.events.bus import SessionEventBus
    redis = Redis.from_url(get_redis_url())
    return SessionEventBus(redis)
```

**Verify:** Publish an event, subscribe to session channel, receive event with correct type.

---

### Step 10: Create `events/middleware.py`

**File:** `modules/backend/events/middleware.py` (NEW, ~60 lines)

Cross-cutting middleware for all FastStream consumers (domain events via Redis Streams). Binds structlog context for correlation and measures processing duration.

**Class: `EventObservabilityMiddleware(BaseMiddleware)`**

Methods:
- `on_consume(msg)` — extracts `event_id`, `correlation_id`, `event_type` from the message dict, binds to `structlog.contextvars`, records start time
- `after_consume(err)` — calculates duration, logs success or failure with duration_ms, unbinds context vars

**Import:** `from faststream import BaseMiddleware`

**Note:** This middleware applies to FastStream domain event consumers, not the session event bus (which is raw Redis Pub/Sub).

---

### Step 11: Create `events/publishers.py`

**File:** `modules/backend/events/publishers.py` (NEW, ~60 lines)

Base publisher class that gates on the feature flag and handles common publishing logic.

**Class: `EventPublisher`**

```python
class EventPublisher:
    async def publish(self, stream: str, event: EventEnvelope) -> None:
        """Publish domain event if feature flag enabled."""
        from modules.backend.core.config import get_app_config
        if not get_app_config().features.events_publish_enabled:
            return
        from modules.backend.events.broker import get_event_broker
        broker = get_event_broker()
        await broker.publish(event.model_dump(), channel=stream)
        logger.debug("Event published", extra={
            "stream": stream,
            "event_type": event.event_type,
            "event_id": event.event_id,
        })
```

**Helper function:**

```python
def _get_trace_id() -> str | None:
    """Extract current OpenTelemetry trace ID if available. Returns None if OTel not installed."""
```

No domain-specific publishers yet — they'll be created as services start emitting events. The base class and feature flag pattern are what matter now.

---

### Step 12: Update `events/__init__.py` with public exports

**File:** `modules/backend/events/__init__.py`

Update with all public exports:

```python
"""Event architecture — FastStream with Redis Streams."""

from modules.backend.events.bus import SessionEventBus
from modules.backend.events.schemas import EventEnvelope
from modules.backend.events.types import (
    SessionEvent,
    UserMessageEvent,
    AgentThinkingEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    AgentResponseChunkEvent,
    AgentResponseCompleteEvent,
    ApprovalRequestedEvent,
    ApprovalResponseEvent,
    CostUpdateEvent,
    PlanCreatedEvent,
    PlanStepStartedEvent,
    PlanStepCompletedEvent,
    PlanRevisedEvent,
    EVENT_TYPE_MAP,
    deserialize_event,
)

__all__ = [
    "SessionEventBus",
    "EventEnvelope",
    "SessionEvent",
    "UserMessageEvent",
    # ... all event types
    "EVENT_TYPE_MAP",
    "deserialize_event",
]
```

---

### Step 13: Add event-worker CLI service

**File:** `modules/backend/cli/event_worker.py` (NEW, ~30 lines)

```python
"""Event consumer worker — runs FastStream with Redis Streams consumers."""

def run_event_worker(logger):
    """Start the FastStream event consumer worker."""
    import subprocess, sys
    logger.info("Starting event worker")
    subprocess.run([
        sys.executable, "-m", "faststream",
        "run", "modules.backend.events.broker:create_event_app",
        "--factory",
    ])
```

**File:** `cli.py`

Add `"event-worker"` to the service choices and `LONG_RUNNING_SERVICES`. Add the elif branch:

```python
elif service == "event-worker":
    from modules.backend.cli.event_worker import run_event_worker
    run_event_worker(logger)
```

**Verify:** `python cli.py --service event-worker` starts the FastStream consumer process.

---

### Step 14: Write tests

**File:** `tests/unit/backend/events/__init__.py` (NEW, empty)

**File:** `tests/unit/backend/events/test_schemas.py` (NEW, ~60 lines)

Test `EventEnvelope` and domain event serialization:
- `test_event_envelope_defaults` — event_id generated, timestamp populated, event_version=1
- `test_event_envelope_roundtrip` — serialize to dict/JSON and back, all fields preserved
- `test_event_envelope_session_id` — session_id and correlation_id fields present and optional

**File:** `tests/unit/backend/events/test_types.py` (NEW, ~120 lines)

Test all `SessionEvent` subclasses:
- `test_session_event_defaults` — event_id generated, timestamp populated, tier 4 fields present
- `test_user_message_event` — correct event_type, content, channel fields
- `test_agent_thinking_event` — correct event_type, agent_id
- `test_agent_tool_call_event` — correct event_type, tool_name, tool_args
- `test_agent_response_chunk_event` — correct event_type, content, is_final
- `test_agent_response_complete_event` — correct event_type, tokens, cost fields
- `test_approval_requested_event` — correct event_type, allowed_decisions, responder_options
- `test_plan_created_event` — correct event_type, goal, step_count
- `test_cost_update_event` — correct event_type, cumulative fields
- `test_deserialize_event_known_type` — deserializes to correct subclass
- `test_deserialize_event_unknown_type` — falls back to base SessionEvent
- `test_deserialize_event_invalid_data` — returns None, logs warning
- `test_event_type_map_complete` — every SessionEvent subclass has an entry in EVENT_TYPE_MAP

**File:** `tests/unit/backend/events/test_bus.py` (NEW, ~60 lines)

Test `SessionEventBus` with a mock Redis:
- `test_publish_serializes_and_sends` — event serialized to JSON, published to correct channel
- `test_publish_channel_naming` — channel is `session:{session_id}`
- `test_subscribe_deserializes_events` — mock pubsub yields messages, bus yields typed SessionEvent objects

**File:** `tests/unit/backend/events/test_publishers.py` (NEW, ~40 lines)

Test `EventPublisher` feature flag gating:
- `test_publish_when_enabled` — event published to broker
- `test_publish_when_disabled` — event silently skipped, no broker call
- `test_publish_logs_event_metadata` — debug log includes stream, event_type, event_id

**File:** `tests/unit/backend/events/test_config.py` (NEW, ~30 lines)

Test `EventsSchema` config loading:
- `test_events_config_defaults` — transport=redis, dlq_enabled=True, etc.
- `test_events_config_from_yaml` — loads from events.yaml correctly
- `test_events_config_strict` — unknown keys rejected (extra=forbid)

---

### Step 15: Verify existing tests pass

Run the full test suite to confirm no regressions:

```bash
python -m pytest tests/unit -v
```

All 65 existing tests plus new event tests must pass.

---

### Step 16: Cleanup and review

- Verify no hardcoded values (all config from YAML)
- Verify all imports are absolute (`from modules.backend.events...`)
- Verify all logging uses `get_logger(__name__)`
- Verify all datetimes use `utc_now()` from `modules.backend.core.utils`
- Verify `__init__.py` files are minimal (exports only)
- Verify no file exceeds 500 lines (target ~100-200 per file)

---

## Files Summary

| Category | File | Action | Est. Lines |
|----------|------|--------|-----------|
| Dependencies | `requirements.txt` | Modify | +1 |
| Config schema | `modules/backend/core/config_schema.py` | Modify | +20 |
| Config YAML | `config/settings/events.yaml` | New | ~20 |
| Feature flag | `config/settings/features.yaml` | Modify | +1 |
| Logging | `modules/backend/core/logging.py` | Modify | +1 (VALID_SOURCES) |
| Dependencies | `modules/backend/core/dependencies.py` | Modify | +10 |
| Events | `modules/backend/events/__init__.py` | New | ~30 |
| Events | `modules/backend/events/broker.py` | New | ~80 |
| Events | `modules/backend/events/schemas.py` | New | ~50 |
| Events | `modules/backend/events/types.py` | New | ~200 |
| Events | `modules/backend/events/bus.py` | New | ~80 |
| Events | `modules/backend/events/middleware.py` | New | ~60 |
| Events | `modules/backend/events/publishers.py` | New | ~60 |
| CLI | `modules/backend/cli/event_worker.py` | New | ~30 |
| CLI | `cli.py` | Modify | +5 |
| Tests | `tests/unit/backend/events/test_schemas.py` | New | ~60 |
| Tests | `tests/unit/backend/events/test_types.py` | New | ~120 |
| Tests | `tests/unit/backend/events/test_bus.py` | New | ~60 |
| Tests | `tests/unit/backend/events/test_publishers.py` | New | ~40 |
| Tests | `tests/unit/backend/events/test_config.py` | New | ~30 |
| **Total** | **20 files** | **12 new, 8 modified** | **~960** |

---

## Anti-Patterns (Do NOT)

- Do not use the event bus for inter-module communication that doesn't involve sessions or domain events. Direct service calls are fine for synchronous operations.
- Do not persist every session event to PostgreSQL. Session events are ephemeral (Redis Pub/Sub). Only events that matter for history or audit are persisted by the session/memory layer (Phase 2).
- Do not put business logic in event handlers. Event consumers render or forward events — they do not make domain decisions.
- Do not use raw `redis` Pub/Sub outside of `SessionEventBus`. All event publishing goes through the bus or publisher classes.
- Do not import `logging` directly. Use `from modules.backend.core.logging import get_logger`.
- Do not use `datetime.utcnow()`. Use `from modules.backend.core.utils import utc_now`.
- Do not hardcode Redis URLs, stream names, or timeouts. All from config.

---
