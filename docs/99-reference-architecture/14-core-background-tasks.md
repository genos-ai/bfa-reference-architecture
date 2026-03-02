# 14 - Background Tasks and Scheduling

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-02-11*

## Changelog

- 1.0.0 (2026-02-11): Extracted from 03-backend-architecture.md into dedicated document

---

## Purpose

This document defines standards for background task processing and scheduled job execution. Background tasks handle work that shouldn't block HTTP responses, while scheduled tasks run automatically based on time.

---

## Context

HTTP requests have a time budget. When an operation takes too long — sending emails, processing uploads, running reports, syncing with external services — it must move to a background task so the API response isn't delayed. Without a standard approach, projects end up with a mix of ad-hoc threads, cron jobs, and inline processing that is impossible to monitor or retry reliably.

Taskiq with Redis was chosen because it is async-native (matching FastAPI), uses a single system for both on-demand tasks (triggered by API calls) and scheduled tasks (cron-based), supports full type hints and dependency injection, and can be tested without Redis by calling task functions directly. The key constraint is that all tasks must be idempotent — safe to execute multiple times — because at-least-once delivery means a task may be retried after a worker crash or timeout.

The single-scheduler-instance rule (only one scheduler process runs, ever) prevents the duplicate execution problem that plagues cron-based systems. This document was extracted from backend architecture (03) into its own standard because background task patterns touch deployment (15, 16), observability (10), and integration modules like Telegram (25) — enough cross-cutting concerns to justify dedicated guidance.

---

## Standard: Taskiq with Redis

Background tasks use Taskiq with Redis as the message broker.

Rationale:
- Async-native (matches FastAPI)
- Excellent performance
- Single system for both on-demand and scheduled tasks
- Full type hints and dependency injection support
- Testable without Redis (call functions directly)

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   API       │     │  Scheduler  │     │   Worker    │
│  Endpoint   │     │  (cron)     │     │  Process    │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │  .kiq()           │  scheduled        │  executes
       │                   │                   │
       └───────────────────┴───────────────────┘
                           │
                    ┌──────▼──────┐
                    │    Redis    │
                    │   (Queue)   │
                    └─────────────┘
```

Components:
- **API/Service**: Dispatches on-demand tasks via `.kiq()`
- **Scheduler**: Sends scheduled tasks to queue based on cron expressions
- **Worker**: Executes tasks from the queue
- **Redis**: Message broker and result storage

---

## Task Types

### On-Demand Tasks

Tasks triggered by application code (API endpoints, services, other tasks).

Use cases:
- Send email after user registration
- Process uploaded file
- Generate report on request
- Sync data with external service

### Scheduled Tasks

Tasks that run automatically on a time-based schedule.

Use cases:
- Daily cleanup of expired records
- Hourly health checks
- Weekly report generation
- Periodic metrics aggregation

---

## On-Demand Tasks

### Task Definition

Define tasks as async functions in `modules/backend/tasks/example.py`:

```python
async def send_notification(
    user_id: str,
    message: str,
    channel: str = "email",
) -> dict[str, Any]:
    """
    Send a notification to a user.

    Args:
        user_id: Target user ID
        message: Notification message
        channel: Delivery channel (email, sms, push)

    Returns:
        Dict with delivery status and timestamp
    """
    # Implementation
    await email_service.send(user_id, message)
    
    return {
        "status": "delivered",
        "user_id": user_id,
        "channel": channel,
        "sent_at": utc_now().isoformat(),
    }
```

### Task Configuration

Configure retry behavior and metadata in `TASK_CONFIG`:

```python
TASK_CONFIG = {
    "send_notification": {
        "retry_on_error": True,
        "max_retries": 3,
        "description": "Send notifications to users via various channels",
    },
    "process_data": {
        "retry_on_error": True,
        "max_retries": 2,
        "description": "Process data with various operations",
    },
}
```

### Dispatching Tasks

```python
from modules.backend.tasks import register_tasks

# Register tasks with broker (requires Redis)
tasks = register_tasks()

# Fire and forget (don't wait for result)
await tasks["send_notification"].kiq(
    user_id="123",
    message="Welcome!",
    channel="email",
)

# Wait for result
task = await tasks["process_data"].kiq(data={"key": "value"})
result = await task.wait_result(timeout=30)

# In API endpoint
@router.post("/items/{item_id}/process")
async def trigger_processing(item_id: str):
    task = await tasks["process_data"].kiq(data={"item_id": item_id})
    return {"task_id": task.task_id}
```

---

## Scheduled Tasks

### Schedule Configuration

Define scheduled tasks in `modules/backend/tasks/scheduled.py`:

```python
SCHEDULED_TASKS = {
    "daily_cleanup": {
        "function": daily_cleanup,
        "schedule": [{"cron": "0 2 * * *"}],  # Daily at 2 AM UTC
        "retry_on_error": False,
        "description": "Clean up expired records daily",
    },
    "hourly_health_check": {
        "function": hourly_health_check,
        "schedule": [{"cron": "0 * * * *"}],  # Every hour at minute 0
        "retry_on_error": False,
        "description": "Check external service health",
    },
    "weekly_report_generation": {
        "function": weekly_report_generation,
        "schedule": [{"cron": "0 6 * * 0"}],  # Sunday at 6 AM UTC
        "retry_on_error": True,
        "max_retries": 2,
        "description": "Generate weekly summary reports",
    },
    "metrics_aggregation": {
        "function": metrics_aggregation,
        "schedule": [{"cron": "*/15 * * * *"}],  # Every 15 minutes
        "retry_on_error": False,
        "description": "Aggregate metrics for dashboards",
    },
}
```

### Cron Format

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, Sun=0)
│ │ │ │ │
* * * * *
```

Common patterns:

| Pattern | Meaning |
|---------|---------|
| `0 2 * * *` | Daily at 2:00 AM |
| `0 * * * *` | Every hour at minute 0 |
| `*/15 * * * *` | Every 15 minutes |
| `0 0 * * 0` | Weekly on Sunday at midnight |
| `0 6 1 * *` | Monthly on 1st at 6:00 AM |
| `0 0 1 1 *` | Yearly on January 1st at midnight |

### Timezone Handling

All scheduled times are in **UTC**. This ensures consistent behavior regardless of server location or daylight saving time changes.

If you need local time scheduling, calculate the UTC equivalent:
```python
# For 2 AM Eastern Time (UTC-5), use 7 AM UTC
"schedule": [{"cron": "0 7 * * *"}]
```

---

## Running Workers and Scheduler

### CLI Commands

```bash
# Start worker (executes tasks from queue)
python cli.py --service worker --workers 2

# Start scheduler (sends scheduled tasks to queue)
python cli.py --service scheduler

# Or directly with taskiq
taskiq worker modules.backend.tasks.broker:broker --workers 2
taskiq scheduler modules.backend.tasks.scheduler:scheduler
```

### Deployment Configuration

**Development:**
```bash
# Terminal 1: Worker
python cli.py --service worker --verbose

# Terminal 2: Scheduler
python cli.py --service scheduler --verbose
```

**Production:**
- Run workers as separate processes (systemd, Docker, etc.)
- Scale workers horizontally based on queue depth
- Run exactly ONE scheduler instance

### Important: Single Scheduler Instance

**WARNING:** Run only ONE scheduler instance. Multiple schedulers will cause duplicate task execution.

If you need scheduler high availability, use a leader election mechanism or rely on the scheduler's crash recovery (tasks missed during downtime will not be retroactively executed).

---

## Task Categories and Retry Policies

| Category | Example | Retry Policy | Rationale |
|----------|---------|--------------|-----------|
| Critical | Payment processing | 3 retries, exponential backoff | Must complete, failures are costly |
| Standard | Report generation | 2 retries | Important but can be manually retriggered |
| Scheduled | Data cleanup | No retry | Runs on next schedule anyway |
| Batch | Bulk operations | No retry | Manual intervention preferred |

### Exponential Backoff

For tasks with retries, use exponential backoff to avoid overwhelming failed services:

```python
# Retry delays: 1s, 2s, 4s, 8s, 16s...
# Taskiq handles this automatically when retry_on_error=True
```

---

## Idempotency

All tasks must be idempotent - safe to execute multiple times with the same result.

### Why Idempotency Matters

Tasks may be executed multiple times due to:
- Worker crashes after execution but before acknowledgment
- Network issues causing duplicate delivery
- Manual retries

### Implementing Idempotency

```python
async def process_payment(payment_id: str, idempotency_key: str):
    """
    Process a payment idempotently.
    
    Uses idempotency_key to prevent duplicate processing.
    """
    # Check if already processed
    if await already_processed(idempotency_key):
        logger.info("Payment already processed", extra={"key": idempotency_key})
        return {"status": "already_processed"}
    
    # Process payment
    result = await execute_payment(payment_id)
    
    # Mark as processed
    await mark_processed(idempotency_key)
    
    return result
```

### Idempotency Strategies

| Strategy | Use When |
|----------|----------|
| Idempotency key in database | Payment processing, order creation |
| Check current state | Status updates, toggles |
| Upsert operations | Data sync, cache updates |
| Natural idempotency | Read-only operations, logging |

---

## Testing Tasks

### Unit Testing (Without Redis)

Import task functions directly and call as regular async functions:

```python
import pytest
from modules.backend.tasks.example import send_notification

class TestSendNotification:
    @pytest.mark.asyncio
    async def test_returns_delivery_status(self):
        result = await send_notification(
            user_id="123",
            message="Test",
            channel="email",
        )
        
        assert result["status"] == "delivered"
        assert result["user_id"] == "123"
```

### Integration Testing (With Redis)

For testing the full task flow:

```python
import pytest
from modules.backend.tasks import register_tasks

@pytest.fixture
async def tasks():
    """Register tasks with test broker."""
    return register_tasks()

class TestTaskIntegration:
    @pytest.mark.asyncio
    async def test_task_dispatch_and_result(self, tasks):
        task = await tasks["process_data"].kiq(data={"key": "value"})
        result = await task.wait_result(timeout=10)
        
        assert result["status"] == "completed"
```

---

## Monitoring and Observability

### Logging

All tasks should log:
- Task start with parameters
- Task completion with result summary
- Errors with full context

```python
async def my_task(item_id: str) -> dict:
    logger.info("Starting task", extra={"item_id": item_id})
    
    try:
        result = await process(item_id)
        logger.info("Task completed", extra={"item_id": item_id, "status": "success"})
        return result
    except Exception as e:
        logger.error("Task failed", extra={"item_id": item_id, "error": str(e)})
        raise
```

### Metrics to Track

| Metric | Description |
|--------|-------------|
| Queue depth | Number of pending tasks |
| Task duration | Time from dispatch to completion |
| Success rate | Percentage of tasks completing successfully |
| Retry rate | Percentage of tasks requiring retries |
| Worker utilization | Percentage of worker capacity in use |

### Alerting

Set up alerts for:
- Queue depth exceeding threshold (tasks backing up)
- High failure rate (> 5% of tasks failing)
- Worker processes down
- Scheduler process down
- Tasks exceeding expected duration

---

## Common Patterns

### Fire and Forget

For tasks where you don't need the result:

```python
# Don't await the result
await tasks["send_notification"].kiq(user_id=user.id, message="Welcome!")
# Continue immediately
```

### Task Chaining

For multi-step workflows:

```python
async def step_one(data: dict) -> dict:
    result = await process_step_one(data)
    # Dispatch next step
    await tasks["step_two"].kiq(data=result)
    return result

async def step_two(data: dict) -> dict:
    result = await process_step_two(data)
    # Dispatch final step
    await tasks["step_three"].kiq(data=result)
    return result
```

### Batch Processing

For processing large datasets:

```python
async def process_batch(items: list[str], batch_size: int = 100) -> dict:
    """Process items in batches to avoid memory issues."""
    processed = 0
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        await process_items(batch)
        processed += len(batch)
        
        logger.info(
            "Batch progress",
            extra={"processed": processed, "total": len(items)},
        )
    
    return {"processed": processed}
```

---

## Troubleshooting

### Tasks Not Executing

1. Check worker is running: `python cli.py --service worker`
2. Check Redis connection: Verify `REDIS_URL` in config
3. Check task registration: Look for registration logs on worker startup
4. Check queue: Use Redis CLI to inspect queue contents

### Scheduled Tasks Not Running

1. Check scheduler is running: `python cli.py --service scheduler`
2. Verify only ONE scheduler instance is running
3. Check cron expression syntax
4. Check scheduled task registration logs

### Tasks Failing

1. Check worker logs for error details
2. Verify task function works in isolation (unit test)
3. Check for resource issues (database connections, memory)
4. Review retry configuration

### High Queue Depth

1. Scale up workers: `--workers N`
2. Check for slow tasks blocking workers
3. Review task priorities
4. Consider separate queues for different task types
