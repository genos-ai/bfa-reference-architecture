# 06 - Event Architecture (Optional Module)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic event architecture standard

---

## Module Status: Optional

This module is **optional**. Adopt when your project needs:
- Asynchronous event processing
- Real-time updates to clients
- Decoupled service communication
- Event-driven workflows

For simple request-response applications, this module is not required.

---

## Context

Synchronous request-response works for most interactions, but some operations shouldn't block the caller: sending notifications after an order is placed, updating search indexes after content changes, broadcasting state changes to multiple consumers, or triggering background workflows. This module exists for projects that need to decouple producers from consumers.

Redis Streams was chosen as the default because it provides reliable message delivery with consumer groups, is already present in most deployments (for caching and task queues via 19-background-tasks), and handles thousands of events per second — sufficient for the vast majority of projects. The upgrade path to NATS JetStream or Apache Kafka is defined but deferred until measurable scale requirements demand it.

The key architectural pattern is the transactional outbox: when an event must reliably accompany a database write (e.g., "order placed" after inserting the order), both are written in the same database transaction, and a relay process then publishes the event. This eliminates the dual-write problem where the database write succeeds but the event publish fails, leaving the system in an inconsistent state. This module provides the communication backbone for inter-module events (04), real-time client updates (07), and is a required dependency for the agentic architecture (25).

---

## Event-Driven Design

### When to Use Events

Events are appropriate for:
- Decoupling services that don't need synchronous responses
- Broadcasting state changes to multiple consumers
- Triggering background processing
- Real-time updates to clients
- Audit trail requirements

Events are not appropriate for:
- Operations requiring immediate response
- Operations requiring transaction guarantees across services
- Simple request-response patterns

### Event vs Command

**Events** describe something that happened (past tense):
- OrderPlaced
- UserCreated
- PaymentProcessed

**Commands** request an action (imperative):
- PlaceOrder
- CreateUser
- ProcessPayment

This architecture uses events for communication between services. Commands are internal to services.

---

## Messaging Infrastructure

### Standard: Redis Streams

Redis Streams handles event delivery for moderate scale (thousands of events per second).

Rationale:
- Already deployed for caching
- Consumer groups for reliable delivery
- Message acknowledgment
- Replay capability
- No additional infrastructure

### Channel Naming

Format: `{domain}:{event-type}`

Examples:
- `orders:order-placed`
- `users:user-created`
- `payments:payment-processed`

### Consumer Groups

Each consuming service creates a consumer group. Multiple instances of the same service share the consumer group (competing consumers pattern).

Consumer group naming: `{service-name}-{purpose}`

### Redis Streams Failure Modes

Understand these operational risks:

| Failure Mode | Impact | Mitigation |
|--------------|--------|------------|
| AOF sync gap | Up to 1 second data loss | Use `appendfsync always` for critical streams |
| Consumer crash | Messages stuck in Pending Entries List | Implement periodic `XAUTOCLAIM` |
| Memory exhaustion | Stream growth consumes RAM | Use `MAXLEN` to cap stream size |

**Stale message recovery:**
```python
# Reclaim messages from crashed consumers (run periodically)
await redis.xautoclaim(
    stream_name,
    group_name,
    consumer_name,
    min_idle_time=300000,  # 5 minutes idle
    count=100
)
```

### Upgrade Triggers

Consider migrating from Redis Streams when:
- Need sub-millisecond latency -> NATS JetStream
- Need multi-region distribution -> NATS JetStream
- Need exactly-once semantics -> Apache Kafka
- Need unbounded replay/audit -> Apache Kafka
- Processing >100K events/second sustained -> Apache Kafka

---

## Delivery Guarantees

### At-Least-Once Delivery

Default guarantee for all events. Consumers must be idempotent.

Implementation:
- Consumer acknowledges after processing
- Failed processing results in redelivery
- Idempotency key in event payload

### Exactly-Once Processing (When Required)

For critical operations:

1. Receive event
2. Check idempotency key against processed events table
3. If already processed, acknowledge and skip
4. Process within database transaction
5. Record idempotency key in same transaction
6. Acknowledge event

---

## Event Structure

### Envelope

All events use this envelope:

```json
{
  "event_id": "uuid",
  "event_type": "domain.entity.action",
  "event_version": 1,
  "timestamp": "2025-01-27T12:00:00Z",
  "source": "service-name",
  "correlation_id": "uuid",
  "payload": {}
}
```

### Field Definitions

| Field | Purpose |
|-------|---------|
| event_id | Unique identifier for this event instance |
| event_type | Dot-notation type (orders.order.placed) |
| event_version | Schema version for payload |
| timestamp | When event occurred (UTC) |
| source | Service that generated the event |
| correlation_id | Links related events across services |
| payload | Event-specific data |

### Versioning

Event schemas are versioned. Consumers must handle:
- Current version
- One previous version (during migration)

Breaking changes require new event type or major version increment.

---

## Transactional Outbox Pattern

### The Problem: Dual Write

When a service updates a database AND publishes an event, two systems can fail independently:

```python
# Failure scenario: Lost event
await db.commit()           # Success
await redis.publish(event)  # Fails (network issue)
# Result: Database updated but event never published
```

### The Solution: Transactional Outbox

Write the event to the **same database** as business data in a **single transaction**:

```sql
BEGIN TRANSACTION
  UPDATE orders SET status = 'confirmed' WHERE id = 123;
  INSERT INTO event_outbox (event_type, payload, created_at) 
    VALUES ('order.confirmed', '{"order_id": 123}', NOW());
COMMIT
```

A separate **relay process** reads the outbox and publishes to the event bus.

### When to Use

| Use Case | Need Outbox? |
|----------|--------------|
| Order placed, notify downstream | Yes |
| Critical state changes | Yes |
| Analytics events | No (eventual consistency OK) |
| Cache invalidation | No (idempotent, can retry) |

### Outbox Table Schema

```sql
CREATE TABLE event_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(255) NOT NULL,
    event_payload JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    published_at TIMESTAMP NULL,
    correlation_id UUID NULL
);

CREATE INDEX idx_outbox_unpublished ON event_outbox (created_at) 
    WHERE published_at IS NULL;
```

### Relay Process

Scheduled task polls outbox and publishes:

```python
@scheduler.cron("* * * * *")  # Every minute
@broker.task
async def publish_outbox_events():
    events = await db.fetch("""
        SELECT * FROM event_outbox 
        WHERE published_at IS NULL 
        ORDER BY created_at LIMIT 100
        FOR UPDATE SKIP LOCKED
    """)
    
    for event in events:
        await redis.xadd(f"events:{event['event_type']}", event['event_payload'])
        await db.execute(
            "UPDATE event_outbox SET published_at = NOW() WHERE id = $1",
            event['id']
        )
```

---

## Real-Time Data Patterns (Optional)

### WebSocket Integration

For real-time client updates:

1. Client connects to WebSocket endpoint
2. Server authenticates via token
3. Client sends subscription messages
4. Server adds client to relevant pub/sub channels
5. Events broadcast to client in real-time
6. Client disconnection cleans up subscriptions

### Message Types

Outbound (server to client):
- `data` - Payload data
- `status` - Connection status, errors
- `ack` - Acknowledgment of client message

Inbound (client to server):
- `subscribe` - Add subscription
- `unsubscribe` - Remove subscription
- `ping` - Keepalive

### Heartbeat/Keepalive

| Parameter | Value |
|-----------|-------|
| Server ping interval | 30 seconds |
| Client pong timeout | 10 seconds |
| Missed pongs before disconnect | 2 |

### Reconnection

Clients implement reconnection with exponential backoff:
- Initial delay: 1 second
- Maximum delay: 30 seconds
- Jitter to prevent thundering herd

---

## Periodic Task Patterns

### Scheduled Tasks

Use task timeout to prevent overlap:

```python
@scheduler.cron("*/15 * * * *")
@broker.task(timeout=840)  # 14 min timeout, 1 min buffer
async def periodic_task():
    await process_data()
```

### Failure Tolerance

Non-critical scheduled tasks:
- Single attempt per schedule
- Failures logged but not retried
- Next scheduled run proceeds normally

---

## Dead Letter Queue

Events that fail after maximum retries:
- Move to dead letter stream `dlq:{original-stream}`
- Alert operations team
- Manual investigation and replay if appropriate

---

## Audit Trail

### What to Audit

All events that represent:
- State changes to important entities
- User actions with business impact
- System decisions affecting users
- Security-relevant operations

### Audit Storage

Audit events stored in append-only table:
- Never deleted (retention policy applied separately)
- Never updated
- Indexed by entity, user, timestamp

---

## Adoption Checklist

When adopting this module:

- [ ] Define event types for your domain
- [ ] Set up Redis Streams configuration
- [ ] Implement event publisher utility
- [ ] Create event consumer framework
- [ ] Set up outbox table and relay (if needed)
- [ ] Configure dead letter queue handling
- [ ] Set up monitoring for consumer lag

### Optional Components Checklist

**WebSocket Real-Time:**
- [ ] Implement WebSocket endpoint
- [ ] Set up pub/sub subscriptions
- [ ] Implement heartbeat handling
- [ ] Document reconnection behavior

**Audit Trail:**
- [ ] Create audit event table
- [ ] Define auditable operations
- [ ] Set up retention policy

---

## Session Events (Extended by Doc 31)

When the project adopts `31-event-session-architecture.md`, the event system defined in this document becomes the transport layer for session events. Session events are a superset of the module events defined above — they follow the same envelope format, naming conventions, and Redis pub/sub transport, but add:

- **Session-scoped channels**: Events are published to `session:{session_id}` channels in addition to module-level channels. Channel adapters (Telegram, TUI, WebSocket) subscribe to session channels.
- **Typed event classes**: Doc 31 defines `SessionEvent` as the base class with 15+ typed subclasses (`UserMessageEvent`, `AgentThinkingEvent`, `AgentToolCallEvent`, `AgentResponseChunkEvent`, `ApprovalRequestedEvent`, `PlanCreatedEvent`, `CostUpdateEvent`, etc.). All extend the event envelope defined in this document.
- **Event deserialization registry**: A type-discriminated registry maps `event_type` strings to Pydantic event classes for safe deserialization from Redis.
- **Dual transport**: Redis pub/sub for real-time delivery (same as this document); Temporal event history for durable replay in Tier 4 long-running workflows.

The module-level event patterns in this document remain unchanged for non-session inter-module communication (e.g., `users.user.created`, `orders.order.completed`). Session events are for interactive operations only.

See `31-event-session-architecture.md`, Section 2 (Event Bus) for the complete event type hierarchy, deserialization registry, and transport configuration.

---

## Related Documentation

- [31-event-session-architecture.md](31-event-session-architecture.md) — Session-scoped events, typed event classes, streaming coordinator
