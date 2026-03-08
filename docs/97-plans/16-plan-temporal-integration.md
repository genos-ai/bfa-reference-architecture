# Implementation Plan: Temporal Integration (Durable Execution)

*Created: 2026-03-04*
*Revised: 2026-03-07 — rewritten after full codebase assessment against Plans 12-15*
*Status: Done*
*Phase: 7 of 8 (AI-First Platform Build)*
*Depends on: Phase 1-6 (Event Bus, Sessions, Streaming Mission Control, Mission Control Dispatch, Verification Pipeline, Plan Persistence)*
*Blocked by: Phase 6*

---

## Summary

Wrap mission execution in Temporal workflows for Tier 4 (long-running autonomous tasks spanning hours/days/weeks). Temporal provides crash recovery, durable human-in-the-loop via Signals, progress inspection via Queries, and durable timers for escalation chains.

PydanticAI v1.63.0 ships native Temporal integration via `pydantic_ai.durable_exec.temporal.TemporalAgent`. Both `pydantic-ai` and `temporalio` (v1.20.0) are already installed in the `bfa` conda environment.

**Critical rule: Temporal owns orchestration state. PostgreSQL owns domain state. Never mix them.** Temporal stores workflow position, retry counts, signal queues. PostgreSQL stores conversations, memories, missions, decisions. Temporal Activities read/write PostgreSQL. Never store large data in Temporal's event history — it bloats replay.

This phase activates Tier 4 autonomy. Tiers 1-3 continue to work without Temporal. Temporal is behind a feature flag (`temporal.enabled = false` by default).

**Dev mode: breaking changes allowed.** This is a new subsystem — no backward-compatibility constraints.

## Context

- Research: `docs/98-research/09-Building autonomous AI agents that run for weeks.md`
- Workflow spec: `docs/98-research/11-bfa-workflow-architecture-specification.md`
- Reference architecture: `docs/99-reference-architecture/46-event-session-architecture.md`
- PydanticAI native integration: `pydantic_ai.durable_exec.temporal.TemporalAgent` (confirmed installed, v1.63.0)
- Mission Control's `handle_mission()` in `mission_control.py` accepts service objects as parameters — this is what makes it Temporal-ready
- The `MissionPersistenceService` from Plan 15 manages all domain state in PostgreSQL — Activities call its methods
- The dispatch loop from Plan 13 (`dispatch.py`) orchestrates agent execution with topological sort, retry-with-feedback, and 3-tier verification
- The `persistence_bridge.py` converts in-memory `MissionOutcome` to persisted `MissionRecord` — best-effort, non-blocking
- `get_async_session()` context manager exists in `database.py` for standalone DB sessions
- `get_mission_status()` exists on `MissionPersistenceService` for progress queries

## Codebase Assessment — What Exists Today

### Mission Control Execution Flow (Plans 12-14)

```
handle_mission(mission_brief, session_service, event_bus, roster_name, budget)
  ├── load_roster(roster_name) → Roster
  ├── [PLANNING LOOP - max 3 attempts]
  │   ├── _call_planning_agent(prompt, roster, upstream_context)
  │   ├── Parse JSON → TaskPlan (Pydantic validation)
  │   └── validate_plan(plan, roster, budget) — 11 rules
  ├── dispatch(plan, roster, execute_agent_fn, budget) → MissionOutcome
  │   ├── topological_sort(plan) → layers of task_ids
  │   ├── [FOR EACH LAYER]
  │   │   ├── [PARALLEL: _execute_with_retry() per task]
  │   │   │   ├── execute_task() → agent output
  │   │   │   ├── verify_task() → VerificationResult (3-tier)
  │   │   │   └── retry with feedback if verification fails
  │   │   └── Collect TaskResults
  │   └── Determine MissionStatus (SUCCESS/PARTIAL/FAILED)
  ├── persist_mission_results() — best-effort via persistence_bridge.py
  └── Return MissionOutcome
```

### Key Types

| Type | Location | Purpose |
|------|----------|---------|
| `TaskPlan` | `schemas/task_plan.py` | DAG of tasks with deps, verification config |
| `TaskDefinition` | `schemas/task_plan.py` | Single task: agent, instructions, inputs, verification |
| `MissionOutcome` | `mission_control/outcome.py` | Final result: status, task_results, cost |
| `TaskResult` | `mission_control/outcome.py` | Per-task: status, output, verification, retry_history |
| `Roster` | `mission_control/roster.py` | Agent list with constraints, interfaces |
| `VerificationResult` | `mission_control/verification.py` | 3-tier verification outcome |
| `MissionRecord` | `models/mission_record.py` | PostgreSQL audit record (immutable JSONB) |

### Persistence Model (Plan 15)

Plan 15 stores execution artifacts as **immutable audit records**. There is no mutable task state machine in PostgreSQL. The dispatch loop runs in memory; results are persisted after completion.

**Tables:** `mission_records`, `task_executions`, `task_attempts`, `mission_decisions`

**MissionPersistenceService methods:**
- Write: `save_mission()`, `save_task_execution()`, `save_attempt()`, `save_decision()`
- Read: `get_mission()`, `list_missions()`, `get_decisions()`, `get_cost_breakdown()`, `get_mission_status()`, `get_missions_by_session()`, `get_replan_chain()`

### Event System

Two transports:
- **SessionEventBus** (Redis Pub/Sub): Real-time ephemeral events (agent thinking, tool calls, response chunks)
- **EventPublisher** (Redis Streams/FastStream): Durable domain events (session lifecycle)

**SessionEvent types relevant to Temporal:**
- `ApprovalRequestedEvent`: approval_request_id, agent_id, action, context, timeout_seconds
- `ApprovalResponseEvent`: decision, responder_type, responder_id, reason

### Database Session Patterns

- `DbSession` (FastAPI dependency): Auto-commits, for endpoints
- `get_async_session()`: Standalone context manager, manual commit, for Activities and background tasks

## What to Build

### New Files

| File | Lines (est.) | Purpose |
|------|-------------|---------|
| `config/settings/temporal.yaml` | ~20 | Temporal config with feature flag |
| `modules/backend/temporal/__init__.py` | 1 | Package init |
| `modules/backend/temporal/models.py` | ~120 | Dataclass DTOs for workflow I/O |
| `modules/backend/temporal/client.py` | ~40 | Feature-flag-gated client factory |
| `modules/backend/temporal/activities.py` | ~180 | Activities: execute_mission, persist, notify |
| `modules/backend/temporal/workflow.py` | ~200 | AgentMissionWorkflow with Signals/Queries |
| `modules/backend/temporal/worker.py` | ~40 | Worker setup and CLI entry |
| `modules/backend/agents/mission_control/approval.py` | ~60 | Tier 3 approval (event bus) |
| `modules/backend/agents/mission_control/escalation.py` | ~130 | 4-level deterministic escalation chain |
| `tests/unit/backend/temporal/__init__.py` | 0 | Package init |
| `tests/unit/backend/temporal/test_models.py` | ~50 | DTO serialization tests |
| `tests/unit/backend/temporal/test_client.py` | ~30 | Feature flag gating tests |
| `tests/unit/backend/temporal/test_activities.py` | ~80 | Activity unit tests |
| `tests/unit/backend/temporal/test_workflow.py` | ~100 | Workflow tests with WorkflowEnvironment |
| `tests/unit/backend/agents/mission_control/test_approval.py` | ~40 | Approval module tests |
| `tests/unit/backend/agents/mission_control/test_escalation.py` | ~90 | Escalation chain tests |

### Modified Files

| File | Change |
|------|--------|
| `modules/backend/core/config_schema.py` | Add `TemporalSchema` |
| `modules/backend/core/config.py` | Register temporal config in `AppConfig` |
| `modules/backend/api/v1/endpoints/missions.py` | Add execute, approve, status endpoints |
| `requirements.txt` | Add `temporalio>=1.20.0` (already installed, pin for reproducibility) |

**Total**: ~1,180 lines across 20 files (16 new, 4 modified)

## Key Design Decisions

### 1. The Activity wraps `handle_mission()`, not individual tasks

The original Plan 16 assumed a mutable task state machine in PostgreSQL (`start_task`, `complete_task`, `fail_task`, `promote_ready_tasks`). This doesn't exist and contradicts our architecture.

**Our architecture**: The dispatch loop (`dispatch.py`) runs the entire task DAG in memory — topological sort, parallel execution, retry-with-feedback, verification — and returns a `MissionOutcome`. Persistence is best-effort afterward.

**Correct Temporal mapping**: The `execute_mission` Activity calls `handle_mission()` which runs the full dispatch loop. This is one Activity, not one Activity per task. The dispatch loop already handles:
- DAG execution with `asyncio.gather` for parallelism
- Per-task retry with verification feedback
- Budget enforcement
- Cost aggregation

Splitting into per-task Activities would require rewriting the dispatch loop and creating a mutable task state machine — unnecessary complexity that breaks the existing architecture.

**When to split into per-task Activities (future)**: Only when individual tasks need to survive worker crashes independently (e.g., a 6-hour code generation task). For now, mission-level durability is sufficient.

### 2. Workflow handles mission lifecycle, not task lifecycle

```
AgentMissionWorkflow.run(input)
  ├── execute_mission Activity → MissionOutcome (runs full dispatch loop)
  ├── persist_results Activity → saves to PostgreSQL
  ├── If needs_approval: wait for Signal
  │   ├── send_notification Activity
  │   └── escalation timer (durable)
  └── Return WorkflowStatus
```

### 3. TemporalAgent wrapping is opt-in per agent (future step)

PydanticAI's `TemporalAgent` wraps individual agents so their model calls and tool executions become Activities. This is powerful but adds complexity. For the initial implementation, we run agents normally inside the `execute_mission` Activity. The Activity itself provides crash recovery at the mission level.

**Future enhancement**: Wrap long-running agents (e.g., code generation, research) with `TemporalAgent` for sub-task durability. This is additive and doesn't require architecture changes.

### 4. Feature flag controls the execution path

```python
if config.temporal.enabled:
    # Start Temporal workflow → Activity calls handle_mission()
    handle = await client.start_workflow(AgentMissionWorkflow.run, ...)
else:
    # Direct execution → handle_mission() called inline
    outcome = await handle_mission(...)
```

### 5. Approval bridges Tier 3 (event bus) and Tier 4 (Temporal Signal)

- **Tier 3**: `request_approval()` publishes `ApprovalRequestedEvent` to Redis Pub/Sub, waits for `ApprovalResponseEvent`
- **Tier 4**: Workflow calls `await workflow.wait_condition()`, resumes when `submit_approval` Signal arrives
- Both use the same `ApprovalDecision` dataclass

### 6. Escalation chain is 100% deterministic (P2)

No LLM calls. Four levels:
1. Low-risk rules (immediate): read-only actions, low cost
2. Risk matrix (immediate): medium-complexity with configurable thresholds
3. Human (4h timeout): Slack/email notification
4. Manager (24h timeout): escalation after Level 3 timeout

### 7. Dataclass DTOs for all workflow I/O

Temporal requires serializable inputs/outputs. ORM objects (`MissionRecord`) are never passed through Temporal. Dataclasses with primitive types serve as the translation layer.

## Success Criteria

- [ ] Temporal workflow executes a mission via `handle_mission()` Activity
- [ ] Workflow survives worker restart and resumes from last completed Activity
- [ ] Human approval via Signal pauses workflow, resumes when Signal received
- [ ] Query returns current mission status without interrupting execution
- [ ] Escalation chain triggers notifications with durable timers
- [ ] Feature flag controls whether missions execute via Temporal or directly
- [ ] Tier 3 (interactive sessions) continues to work without Temporal enabled
- [ ] Config loads from `temporal.yaml` with defaults
- [ ] Workflow returns `WorkflowStatus` as final output
- [ ] All tests pass (including Temporal test environment)

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Ensure conda env | `export PATH="/opt/anaconda3/envs/bfa/bin:/usr/bin:/bin:$PATH"` |
| 0.2 | Verify clean state | `git status` — commit if needed |

---

### Step 1: Dependencies

Pin `temporalio` in `requirements.txt` (already installed):

```
temporalio>=1.20.0
```

**Verification**: `python -c "import temporalio; print(temporalio.__version__)"` — should print `1.20.0`

---

### Step 2: Temporal Configuration

**File**: `config/settings/temporal.yaml` (NEW)

```yaml
# =============================================================================
# Temporal Configuration (Tier 4 - Durable Execution)
# =============================================================================
enabled: false
server_url: "localhost:7233"
namespace: "default"
task_queue: "agent-missions"
workflow_execution_timeout_days: 30
activity_start_to_close_seconds: 600
activity_retry_max_attempts: 3
approval_timeout_seconds: 14400
escalation_timeout_seconds: 86400
notification_timeout_seconds: 30
```

**File**: `modules/backend/core/config_schema.py` — Add `TemporalSchema`:

```python
class TemporalSchema(_StrictBase):
    """Temporal integration configuration (Tier 4 durable execution)."""

    enabled: bool = False
    server_url: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "agent-missions"
    workflow_execution_timeout_days: int = 30
    activity_start_to_close_seconds: int = 600
    activity_retry_max_attempts: int = 3
    approval_timeout_seconds: int = 14400
    escalation_timeout_seconds: int = 86400
    notification_timeout_seconds: int = 30
```

**File**: `modules/backend/core/config.py` — Register in `AppConfig`:

```python
# In __init__:
self._temporal = _load_validated_optional(TemporalSchema, "temporal.yaml")

# Property:
@property
def temporal(self) -> TemporalSchema:
    """Temporal integration settings."""
    return self._temporal
```

**Verification**: `python -c "from modules.backend.core.config import get_app_config; print(get_app_config().temporal.enabled)"` — should print `False`.

**Tests**: `tests/unit/backend/config/test_config_temporal.py`

```python
class TestTemporalConfig:
    def test_defaults(self):
        config = TemporalSchema()
        assert config.enabled is False
        assert config.server_url == "localhost:7233"
        assert config.task_queue == "agent-missions"

    def test_strict_rejects_unknown(self):
        with pytest.raises(Exception):
            TemporalSchema(unknown_field="oops")
```

---

### Step 3: Temporal Data Models

**File**: `modules/backend/temporal/models.py` (NEW)

Dataclasses for workflow inputs, outputs, and signals. Serializable — no ORM objects.

```python
"""
Temporal workflow data models.

Serializable dataclasses for workflow inputs, outputs, and signals.
No ORM objects — Temporal serializes these as JSON. Activities convert
between these DTOs and domain objects.
"""

from dataclasses import dataclass, field


@dataclass
class MissionWorkflowInput:
    """Input to start an AgentMissionWorkflow."""

    mission_id: str
    session_id: str
    mission_brief: str
    roster_name: str = "default"
    mission_budget_usd: float = 10.0


@dataclass
class MissionExecutionResult:
    """Output from the execute_mission Activity.

    Carries the serialized MissionOutcome from dispatch.
    """

    mission_id: str
    status: str  # "success", "partial", "failed"
    total_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    task_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    outcome_json: dict = field(default_factory=dict)


@dataclass
class ApprovalDecision:
    """Input from a Signal: human/AI/rule approval decision."""

    decision: str  # "approved", "rejected", "modified"
    responder_type: str  # "human", "ai_agent", "automated_rule"
    responder_id: str
    reason: str | None = None


@dataclass
class MissionModification:
    """Input from a Signal: mission modification mid-execution."""

    instruction: str = ""
    reasoning: str = ""


@dataclass
class WorkflowStatus:
    """Output from a Query: current workflow state."""

    mission_id: str
    workflow_status: str = "pending"  # "pending", "running", "completed", "failed", "waiting_approval"
    mission_status: str | None = None  # MissionOutcome status once available
    total_cost_usd: float = 0.0
    waiting_for_approval: bool = False
    error: str | None = None


@dataclass
class NotificationPayload:
    """Input for the send_notification Activity."""

    channel: str  # "slack", "email", "webhook"
    recipient: str
    title: str
    body: str
    action_url: str
    urgency: str = "normal"  # "low", "normal", "high", "critical"
```

**Design note**: `MissionWorkflowInput` carries everything needed to call `handle_mission()`. `MissionExecutionResult` carries the serialized outcome — not the full `MissionOutcome` Pydantic model (which isn't a dataclass).

---

### Step 4: Temporal Client

**File**: `modules/backend/temporal/client.py` (NEW)

```python
"""
Temporal Client Factory.

Provides a cached Temporal client connection. Gated by the
temporal.enabled feature flag — raises RuntimeError if Temporal
is not enabled.
"""

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

_client = None


def get_temporal_config():
    """Get Temporal config, raising if not enabled."""
    config = get_app_config().temporal
    if not config.enabled:
        raise RuntimeError(
            "Temporal is not enabled. Set temporal.enabled=true "
            "in config/settings/temporal.yaml to use Tier 4 features."
        )
    return config


async def get_temporal_client():
    """Create and return a connected Temporal client.

    Raises RuntimeError if temporal.enabled is False.
    Caches the client after first connection.
    """
    global _client
    if _client is not None:
        return _client

    from temporalio.client import Client

    config = get_temporal_config()

    _client = await Client.connect(
        config.server_url,
        namespace=config.namespace,
    )

    logger.info(
        "Temporal client connected",
        extra={
            "server_url": config.server_url,
            "namespace": config.namespace,
        },
    )

    return _client
```

---

### Step 5: Temporal Activities

**File**: `modules/backend/temporal/activities.py` (NEW)

Activities are non-deterministic operations. Each Activity is idempotent and safe to retry.

```python
"""
Temporal Activities.

Non-deterministic operations that run outside the Workflow's
deterministic replay. Each Activity is idempotent and safe to retry.
Activities receive IDs and brief strings, not large objects.
"""

from temporalio import activity

from modules.backend.core.logging import get_logger
from modules.backend.temporal.models import (
    MissionExecutionResult,
    MissionWorkflowInput,
    NotificationPayload,
)

logger = get_logger(__name__)


@activity.defn
async def execute_mission(input: MissionWorkflowInput) -> MissionExecutionResult:
    """Execute a full mission via handle_mission().

    This is the critical Activity — it bridges Temporal and Mission Control.
    The dispatch loop (Plan 13) runs inside this Activity with full middleware:
    topological DAG execution, retry-with-feedback, 3-tier verification,
    cost tracking, and budget enforcement.

    On Temporal retry (worker crash), the entire mission re-executes.
    This is acceptable because missions are idempotent at the outcome level —
    re-running produces equivalent results (possibly different cost).
    """
    from modules.backend.agents.mission_control.mission_control import handle_mission
    from modules.backend.core.database import get_async_session
    from modules.backend.services.session import SessionService

    activity.logger.info(
        "Starting mission execution",
        extra={
            "mission_id": input.mission_id,
            "roster": input.roster_name,
            "budget": input.mission_budget_usd,
        },
    )

    async with get_async_session() as db:
        session_service = SessionService(db)

        try:
            outcome = await handle_mission(
                mission_id=input.mission_id,
                mission_brief=input.mission_brief,
                session_service=session_service,
                event_bus=None,  # No real-time streaming in Tier 4
                roster_name=input.roster_name,
                mission_budget_usd=input.mission_budget_usd,
            )

            # Serialize MissionOutcome for Temporal event history
            outcome_dict = outcome.model_dump()

            success_count = sum(
                1 for r in outcome.task_results if r.status.value == "success"
            )
            failed_count = sum(
                1 for r in outcome.task_results if r.status.value != "success"
            )

            return MissionExecutionResult(
                mission_id=input.mission_id,
                status=outcome.status.value,
                total_cost_usd=outcome.total_cost_usd,
                total_duration_seconds=outcome.total_duration_seconds,
                task_count=len(outcome.task_results),
                success_count=success_count,
                failed_count=failed_count,
                outcome_json=outcome_dict,
            )

        except Exception as e:
            activity.logger.error(
                "Mission execution failed",
                extra={"mission_id": input.mission_id, "error": str(e)},
            )
            return MissionExecutionResult(
                mission_id=input.mission_id,
                status="failed",
                outcome_json={"error": str(e)},
            )


@activity.defn
async def persist_mission_outcome(
    mission_id: str,
    session_id: str,
    roster_name: str,
    outcome_json: dict,
) -> bool:
    """Persist mission results to PostgreSQL. Best-effort."""
    from modules.backend.agents.mission_control.outcome import MissionOutcome
    from modules.backend.agents.mission_control.persistence_bridge import (
        persist_mission_results,
    )
    from modules.backend.core.database import get_async_session

    try:
        outcome = MissionOutcome.model_validate(outcome_json)
        async with get_async_session() as db:
            await persist_mission_results(
                outcome,
                session_id=session_id,
                roster_name=roster_name,
                task_plan_json=outcome_json.get("task_plan_reference"),
                thinking_trace=outcome_json.get("planning_trace_reference"),
                db_session=db,
            )
            await db.commit()
        return True
    except Exception as e:
        activity.logger.error(
            "Failed to persist mission results",
            extra={"mission_id": mission_id, "error": str(e)},
        )
        return False


@activity.defn
async def send_notification(payload: NotificationPayload) -> bool:
    """Send notification via configured channel.

    Stub implementations — integrate with real Slack/email/webhook SDKs
    when needed. Logs the notification for now.
    """
    activity.logger.info(
        "Notification sent",
        extra={
            "channel": payload.channel,
            "recipient": payload.recipient,
            "title": payload.title,
            "urgency": payload.urgency,
        },
    )
    return True
```

**Design notes**:
- `execute_mission` calls `handle_mission()` which runs the full dispatch loop. This is one Activity per mission, not per task. The dispatch loop handles parallelism, retries, and verification internally.
- `persist_mission_outcome` deserializes the outcome JSON back to `MissionOutcome` and calls the existing `persist_mission_results()` bridge.
- Each Activity creates its own DB session via `get_async_session()`.
- `send_notification` is a stub — implement with Slack SDK when needed.

---

### Step 6: Temporal Workflow

**File**: `modules/backend/temporal/workflow.py` (NEW)

```python
"""
Agent Mission Workflow.

Temporal Workflow that executes a mission and handles lifecycle:
planning, execution, persistence, approval, and escalation.

Key rules:
- Workflow code is deterministic — no I/O, no random, no datetime.now()
- All side effects happen in Activities
- Temporal owns orchestration state (position, signals, timers)
- PostgreSQL owns domain state (missions, tasks, decisions)
"""

from datetime import timedelta

from temporalio import workflow

from modules.backend.temporal.models import (
    ApprovalDecision,
    MissionWorkflowInput,
    NotificationPayload,
    WorkflowStatus,
)

with workflow.unsafe.imports_passed_through():
    from modules.backend.temporal import activities


@workflow.defn
class AgentMissionWorkflow:
    """Execute a mission as a Temporal Workflow.

    Flow:
    1. Execute mission via handle_mission() Activity
    2. Persist results to PostgreSQL Activity
    3. If approval needed (future): wait for Signal
    4. Return WorkflowStatus
    """

    def __init__(self) -> None:
        self._approval: ApprovalDecision | None = None
        self._status = WorkflowStatus(mission_id="")

    # ---- Signals ----

    @workflow.signal
    async def submit_approval(self, decision: ApprovalDecision) -> None:
        """Receive approval from any source: human, AI, or automated rule."""
        self._approval = decision
        self._status.waiting_for_approval = False

    # ---- Queries ----

    @workflow.query
    def get_status(self) -> WorkflowStatus:
        """Read-only status for dashboards. Does not interrupt workflow."""
        return self._status

    # ---- Main workflow ----

    @workflow.run
    async def run(self, input: MissionWorkflowInput) -> WorkflowStatus:
        """Execute a mission with durable execution guarantees."""
        self._status.mission_id = input.mission_id
        self._status.workflow_status = "running"

        activity_timeout = timedelta(
            seconds=max(input.mission_budget_usd * 120, 600)
        )
        notification_timeout = timedelta(seconds=30)

        # Step 1: Execute the mission
        result = await workflow.execute_activity(
            activities.execute_mission,
            input,
            start_to_close_timeout=activity_timeout,
            retry_policy=workflow.RetryPolicy(
                maximum_attempts=2,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=60),
                non_retryable_error_types=["BudgetExceededError"],
            ),
        )

        self._status.mission_status = result.status
        self._status.total_cost_usd = result.total_cost_usd

        # Step 2: Persist results (best-effort)
        await workflow.execute_activity(
            activities.persist_mission_outcome,
            args=[
                input.mission_id,
                input.session_id,
                input.roster_name,
                result.outcome_json,
            ],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=workflow.RetryPolicy(maximum_attempts=3),
        )

        # Step 3: If mission failed, optionally wait for approval to retry
        if result.status == "failed" and result.failed_count > 0:
            self._status.workflow_status = "waiting_approval"
            self._status.waiting_for_approval = True

            # Notify about failure
            await workflow.execute_activity(
                activities.send_notification,
                NotificationPayload(
                    channel="webhook",
                    recipient="admin",
                    title=f"Mission failed: {input.mission_id[:8]}",
                    body=(
                        f"Mission '{input.mission_brief[:100]}' failed. "
                        f"{result.failed_count}/{result.task_count} tasks failed. "
                        f"Cost: ${result.total_cost_usd:.2f}"
                    ),
                    action_url=f"/api/v1/missions/{input.mission_id}",
                    urgency="high",
                ),
                start_to_close_timeout=notification_timeout,
            )

            # Wait for approval with escalation
            await self._wait_for_approval_with_escalation(
                input, notification_timeout,
            )

            # If approved, retry the mission
            if self._approval and self._approval.decision == "approved":
                self._status.workflow_status = "running"
                self._approval = None

                retry_result = await workflow.execute_activity(
                    activities.execute_mission,
                    input,
                    start_to_close_timeout=activity_timeout,
                    retry_policy=workflow.RetryPolicy(maximum_attempts=1),
                )

                self._status.mission_status = retry_result.status
                self._status.total_cost_usd += retry_result.total_cost_usd

                # Persist retry results
                await workflow.execute_activity(
                    activities.persist_mission_outcome,
                    args=[
                        input.mission_id,
                        input.session_id,
                        input.roster_name,
                        retry_result.outcome_json,
                    ],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=workflow.RetryPolicy(maximum_attempts=3),
                )

        # Final status
        self._status.workflow_status = (
            "completed" if self._status.mission_status in ("success", "partial")
            else "failed"
        )

        return self._status

    async def _wait_for_approval_with_escalation(
        self,
        input: MissionWorkflowInput,
        notification_timeout: timedelta,
    ) -> None:
        """Wait for approval with durable escalation timer.

        4 hours → re-notify with critical urgency.
        24 hours → give up waiting.
        """
        # Wait up to 4 hours
        try:
            await workflow.wait_condition(
                lambda: self._approval is not None,
                timeout=timedelta(hours=4),
            )
            return
        except TimeoutError:
            pass

        # Escalate: re-notify with critical urgency
        await workflow.execute_activity(
            activities.send_notification,
            NotificationPayload(
                channel="webhook",
                recipient="admin",
                title=f"ESCALATION: Mission {input.mission_id[:8]}",
                body="Approval pending for 4 hours. Escalating.",
                action_url=f"/api/v1/missions/{input.mission_id}",
                urgency="critical",
            ),
            start_to_close_timeout=notification_timeout,
        )

        # Wait up to 24 hours total
        try:
            await workflow.wait_condition(
                lambda: self._approval is not None,
                timeout=timedelta(hours=20),
            )
        except TimeoutError:
            # Give up — mark as failed
            self._status.workflow_status = "failed"
            self._status.error = "Approval timed out after 24 hours"
```

**Design notes**:
- The workflow is simple: execute mission → persist → optionally wait for approval → return status.
- `activity_timeout` scales with budget — more expensive missions get more time.
- The escalation timer uses `workflow.wait_condition(timeout=...)` — durable, survives crashes.
- `max_iterations` safety limit is not needed because the workflow has a bounded structure (no unbounded loop).

---

### Step 7: Temporal Worker

**File**: `modules/backend/temporal/worker.py` (NEW)

```python
"""
Temporal Worker.

Starts a Temporal Worker that executes AgentMissionWorkflow and its
Activities. Run via CLI: python -m modules.backend.temporal.worker
"""

import asyncio

from temporalio.worker import Worker

from modules.backend.core.logging import get_logger
from modules.backend.temporal.activities import (
    execute_mission,
    persist_mission_outcome,
    send_notification,
)
from modules.backend.temporal.client import get_temporal_client, get_temporal_config
from modules.backend.temporal.workflow import AgentMissionWorkflow

logger = get_logger(__name__)


async def start_worker() -> None:
    """Start the Temporal Worker."""
    config = get_temporal_config()
    client = await get_temporal_client()

    worker = Worker(
        client,
        task_queue=config.task_queue,
        workflows=[AgentMissionWorkflow],
        activities=[
            execute_mission,
            persist_mission_outcome,
            send_notification,
        ],
    )

    logger.info(
        "Temporal worker starting",
        extra={"task_queue": config.task_queue},
    )

    await worker.run()


def main() -> None:
    """Entry point for running the worker."""
    asyncio.run(start_worker())


if __name__ == "__main__":
    main()
```

---

### Step 8: Approval Module

**File**: `modules/backend/agents/mission_control/approval.py` (NEW)

Tier 3 approval (event bus). Tier 4 uses Temporal Signals (handled by workflow).

```python
"""
Approval Request Module.

Provides request_approval() for Tier 3 (Redis event bus).
In Tier 4, approval is handled by the workflow via Temporal Signals —
this function should not be called in Tier 4.
"""

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


async def request_approval(
    mission_id: str,
    task_id: str,
    action: str,
    context: dict,
    timeout_seconds: int = 14400,
) -> dict:
    """Request approval via event bus (Tier 3 only).

    In Tier 4, the workflow handles approval via Temporal Signals.
    """
    config = get_app_config()

    if config.temporal.enabled:
        raise RuntimeError(
            "request_approval() should not be called in Tier 4. "
            "The workflow handles approval via Temporal Signals."
        )

    logger.info(
        "Approval requested (Tier 3)",
        extra={
            "mission_id": mission_id,
            "task_id": task_id,
            "action": action,
        },
    )

    # Stub: auto-approve in dev mode
    # Future: publish ApprovalRequestedEvent to event bus,
    # wait for ApprovalResponseEvent
    return {
        "decision": "approved",
        "responder_type": "automated_rule",
        "responder_id": "auto_approve_dev_mode",
        "reason": "Auto-approved in dev mode (Tier 3 stub)",
    }
```

---

### Step 9: Escalation Chain

**File**: `modules/backend/agents/mission_control/escalation.py` (NEW)

```python
"""
Escalation Chain.

Deterministic escalation path when approval goes unanswered
or a task exceeds an agent's capability.

P2 PRINCIPLE: Deterministic over Non-Deterministic.
All escalation logic is rule-based. No LLM calls.

Levels:
1. Low-risk rules (immediate) — read-only, low cost
2. Risk matrix (immediate) — configurable thresholds
3. Human (4h timeout) — Slack/email notification
4. Manager (24h timeout) — escalation after Level 3 timeout
"""

from dataclasses import dataclass, field

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EscalationLevel:
    """A single level in the escalation chain."""

    level: int
    responder_type: str
    timeout_seconds: int
    description: str


ESCALATION_CHAIN = [
    EscalationLevel(
        level=1,
        responder_type="automated_rule_low_risk",
        timeout_seconds=0,
        description="Deterministic rules for low-risk actions",
    ),
    EscalationLevel(
        level=2,
        responder_type="automated_rule_medium_risk",
        timeout_seconds=0,
        description="Risk matrix for medium-complexity actions",
    ),
    EscalationLevel(
        level=3,
        responder_type="human",
        timeout_seconds=14400,
        description="Human review via Slack/email",
    ),
    EscalationLevel(
        level=4,
        responder_type="human_manager",
        timeout_seconds=86400,
        description="Manager escalation",
    ),
]


def get_escalation_level(current_level: int) -> EscalationLevel | None:
    """Get the escalation level by number."""
    for level in ESCALATION_CHAIN:
        if level.level == current_level:
            return level
    return None


def get_next_escalation(current_level: int) -> EscalationLevel | None:
    """Get the next escalation level. None if at highest."""
    for level in ESCALATION_CHAIN:
        if level.level == current_level + 1:
            return level
    return None


# ---- Risk classification (P2: all deterministic) ----

LOW_RISK_ACTIONS = frozenset({
    "read_file", "list_files", "get_status", "get_mission_status",
    "list_available_agents",
})

MEDIUM_RISK_ACTIONS = frozenset({
    "invoke_agent", "apply_fix", "run_tests", "create_mission",
    "revise_mission",
})


@dataclass
class RiskThresholds:
    """Configurable thresholds for deterministic risk classification."""

    max_auto_approve_cost_usd: float = 1.00
    max_medium_approve_cost_usd: float = 10.00
    max_auto_approve_retries: int = 3
    allowed_retry_actions: frozenset[str] = field(
        default_factory=lambda: frozenset({
            "invoke_agent", "apply_fix", "run_tests",
        })
    )


_thresholds = RiskThresholds()


async def evaluate_automated_rules(
    action: str,
    context: dict,
) -> dict | None:
    """Level 1: Check if action can be auto-approved by low-risk rules.

    Returns approval decision if rules match, None to escalate.
    """
    if action in LOW_RISK_ACTIONS:
        return {
            "decision": "approved",
            "responder_type": "automated_rule",
            "responder_id": "rule:low_risk_action",
            "reason": f"Auto-approved: '{action}' is a low-risk action",
        }

    cost = context.get("estimated_cost_usd", 0)
    if cost < _thresholds.max_auto_approve_cost_usd:
        return {
            "decision": "approved",
            "responder_type": "automated_rule",
            "responder_id": "rule:low_cost",
            "reason": (
                f"Auto-approved: estimated cost ${cost:.2f} "
                f"< ${_thresholds.max_auto_approve_cost_usd:.2f}"
            ),
        }

    if (
        context.get("is_retry")
        and action in _thresholds.allowed_retry_actions
        and context.get("retry_count", 0) <= _thresholds.max_auto_approve_retries
    ):
        return {
            "decision": "approved",
            "responder_type": "automated_rule",
            "responder_id": "rule:retry_auto_approve",
            "reason": (
                f"Auto-approved: retry {context['retry_count']} "
                f"of previously approved '{action}'"
            ),
        }

    return None


async def evaluate_risk_matrix(
    action: str,
    context: dict,
) -> dict | None:
    """Level 2: Risk matrix for medium-complexity decisions.

    Deterministic classification based on action type, cost, agent
    permissions, and error category.
    """
    cost = context.get("estimated_cost_usd", 0)

    if (
        action in MEDIUM_RISK_ACTIONS
        and cost < _thresholds.max_medium_approve_cost_usd
    ):
        agent = context.get("agent_name", "")
        allowed = context.get("allowed_agents", set())
        if agent in allowed or not agent:
            return {
                "decision": "approved",
                "responder_type": "automated_rule",
                "responder_id": "rule:risk_matrix_medium",
                "reason": (
                    f"Risk matrix approved: '{action}' with cost "
                    f"${cost:.2f} within medium threshold"
                ),
            }

    error_category = context.get("error_category")
    safe_error_categories = {"timeout", "rate_limit", "transient_network"}
    if error_category in safe_error_categories:
        return {
            "decision": "approved",
            "responder_type": "automated_rule",
            "responder_id": "rule:safe_error_category",
            "reason": (
                f"Risk matrix approved: error category "
                f"'{error_category}' is transient/recoverable"
            ),
        }

    return None
```

---

### Step 10: Update Mission API Endpoints

**File**: `modules/backend/api/v1/endpoints/missions.py` — Add 3 new endpoints:

```python
@router.post(
    "/{mission_id}/execute",
    response_model=ApiResponse[dict],
    summary="Execute a mission",
    description="Start mission execution. Uses Temporal workflow if enabled, "
                "otherwise returns error (direct execution uses session streaming).",
)
async def execute_mission(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
    mission_brief: str = "",
    roster_name: str = "default",
    mission_budget_usd: float = 10.0,
) -> ApiResponse[dict]:
    """Start mission execution via Temporal workflow."""
    from modules.backend.core.config import get_app_config

    config = get_app_config()

    if not config.temporal.enabled:
        return ApiResponse(data={
            "error": "temporal_not_enabled",
            "message": "Temporal is not enabled. Use session streaming for "
                       "direct execution, or enable Temporal for durable execution.",
        })

    from modules.backend.temporal.client import get_temporal_client
    from modules.backend.temporal.models import MissionWorkflowInput
    from modules.backend.temporal.workflow import AgentMissionWorkflow

    client = await get_temporal_client()

    handle = await client.start_workflow(
        AgentMissionWorkflow.run,
        MissionWorkflowInput(
            mission_id=mission_id,
            session_id=mission_id,  # Use mission_id as session_id for standalone
            mission_brief=mission_brief,
            roster_name=roster_name,
            mission_budget_usd=mission_budget_usd,
        ),
        id=f"mission-{mission_id}",
        task_queue=config.temporal.task_queue,
    )

    return ApiResponse(data={
        "workflow_id": handle.id,
        "mission_id": mission_id,
        "status": "started",
    })


@router.post(
    "/{mission_id}/approve",
    response_model=ApiResponse[dict],
    summary="Submit approval for a mission",
    description="Send an approval decision to a waiting Temporal workflow.",
)
async def submit_approval(
    mission_id: str,
    decision: str,
    responder_id: str,
    reason: str | None = None,
    request_id: RequestId = None,
) -> ApiResponse[dict]:
    """Submit approval via Temporal Signal."""
    from modules.backend.core.config import get_app_config

    config = get_app_config()
    if not config.temporal.enabled:
        return ApiResponse(data={
            "error": "temporal_not_enabled",
            "message": "Approval signals require Temporal.",
        })

    from modules.backend.temporal.client import get_temporal_client
    from modules.backend.temporal.models import ApprovalDecision
    from modules.backend.temporal.workflow import AgentMissionWorkflow

    client = await get_temporal_client()
    handle = client.get_workflow_handle(f"mission-{mission_id}")

    await handle.signal(
        AgentMissionWorkflow.submit_approval,
        ApprovalDecision(
            decision=decision,
            responder_type="human",
            responder_id=responder_id,
            reason=reason,
        ),
    )

    return ApiResponse(data={
        "mission_id": mission_id,
        "decision": decision,
        "status": "signal_sent",
    })


@router.get(
    "/{mission_id}/status",
    response_model=ApiResponse[dict],
    summary="Get mission execution status",
    description="Returns status from Temporal Query if enabled, "
                "otherwise from PostgreSQL.",
)
async def get_mission_status(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[dict]:
    """Get mission status — Temporal Query or DB fallback."""
    from modules.backend.core.config import get_app_config

    config = get_app_config()

    if config.temporal.enabled:
        try:
            from modules.backend.temporal.client import get_temporal_client
            from modules.backend.temporal.workflow import AgentMissionWorkflow

            client = await get_temporal_client()
            handle = client.get_workflow_handle(f"mission-{mission_id}")
            status = await handle.query(AgentMissionWorkflow.get_status)
            return ApiResponse(data={
                "source": "temporal",
                "mission_id": status.mission_id,
                "workflow_status": status.workflow_status,
                "mission_status": status.mission_status,
                "total_cost_usd": status.total_cost_usd,
                "waiting_for_approval": status.waiting_for_approval,
                "error": status.error,
            })
        except Exception:
            pass  # Fall through to DB query

    # Fallback: direct DB query
    from modules.backend.services.mission_persistence import (
        MissionPersistenceService,
    )

    service = MissionPersistenceService(db)
    try:
        status = await service.get_mission_status(mission_id)
        return ApiResponse(data={"source": "database", **status})
    except Exception:
        from modules.backend.core.exceptions import NotFoundError
        raise NotFoundError(f"Mission '{mission_id}' not found")
```

---

### Step 11: Tests

**File**: `tests/unit/backend/temporal/test_models.py` (NEW)

```python
"""Tests for Temporal data models — serialization correctness."""

from modules.backend.temporal.models import (
    ApprovalDecision,
    MissionExecutionResult,
    MissionWorkflowInput,
    WorkflowStatus,
)


class TestWorkflowModels:
    def test_mission_workflow_input(self):
        inp = MissionWorkflowInput(
            mission_id="abc", session_id="def", mission_brief="Do stuff",
        )
        assert inp.mission_id == "abc"
        assert inp.roster_name == "default"
        assert inp.mission_budget_usd == 10.0

    def test_mission_execution_result_defaults(self):
        result = MissionExecutionResult(mission_id="abc", status="success")
        assert result.total_cost_usd == 0.0
        assert result.outcome_json == {}

    def test_approval_decision(self):
        decision = ApprovalDecision(
            decision="approved",
            responder_type="human",
            responder_id="user_123",
            reason="Looks good",
        )
        assert decision.decision == "approved"

    def test_workflow_status_defaults(self):
        status = WorkflowStatus(mission_id="abc")
        assert status.workflow_status == "pending"
        assert status.waiting_for_approval is False
        assert status.mission_status is None
```

**File**: `tests/unit/backend/temporal/test_client.py` (NEW)

```python
"""Tests for Temporal client factory — feature flag gating."""

import pytest
from unittest.mock import patch, MagicMock

from modules.backend.temporal.client import get_temporal_config


class TestTemporalConfig:
    def test_raises_when_not_enabled(self):
        with patch(
            "modules.backend.temporal.client.get_app_config",
        ) as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.temporal.enabled = False
            mock_config.return_value = mock_cfg

            with pytest.raises(RuntimeError, match="not enabled"):
                get_temporal_config()

    def test_returns_config_when_enabled(self):
        with patch(
            "modules.backend.temporal.client.get_app_config",
        ) as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.temporal.enabled = True
            mock_cfg.temporal.server_url = "localhost:7233"
            mock_config.return_value = mock_cfg

            config = get_temporal_config()
            assert config.server_url == "localhost:7233"
```

**File**: `tests/unit/backend/temporal/test_activities.py` (NEW)

```python
"""Tests for Temporal Activities — unit tests without Temporal server."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from modules.backend.temporal.models import (
    MissionWorkflowInput,
    NotificationPayload,
)


class TestSendNotification:
    @pytest.mark.asyncio
    async def test_returns_true(self):
        from modules.backend.temporal.activities import send_notification

        result = await send_notification(
            NotificationPayload(
                channel="webhook",
                recipient="admin",
                title="Test",
                body="Test body",
                action_url="/test",
            )
        )
        assert result is True


class TestExecuteMission:
    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        """execute_mission should return MissionExecutionResult."""
        from modules.backend.temporal.activities import execute_mission

        mock_outcome = MagicMock()
        mock_outcome.status.value = "success"
        mock_outcome.total_cost_usd = 0.05
        mock_outcome.total_duration_seconds = 1.5
        mock_outcome.task_results = []
        mock_outcome.model_dump.return_value = {"status": "success"}

        mock_session = AsyncMock()

        with (
            patch(
                "modules.backend.temporal.activities.handle_mission",
                return_value=mock_outcome,
            ),
            patch(
                "modules.backend.temporal.activities.get_async_session",
            ) as mock_get_session,
            patch(
                "modules.backend.temporal.activities.SessionService",
            ),
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(
                return_value=False,
            )

            result = await execute_mission(
                MissionWorkflowInput(
                    mission_id="test-1",
                    session_id="sess-1",
                    mission_brief="Test mission",
                )
            )

            assert result.status == "success"
            assert result.total_cost_usd == 0.05

    @pytest.mark.asyncio
    async def test_returns_failed_on_exception(self):
        """execute_mission should return failed result on exception."""
        from modules.backend.temporal.activities import execute_mission

        mock_session = AsyncMock()

        with (
            patch(
                "modules.backend.temporal.activities.handle_mission",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "modules.backend.temporal.activities.get_async_session",
            ) as mock_get_session,
            patch(
                "modules.backend.temporal.activities.SessionService",
            ),
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(
                return_value=False,
            )

            result = await execute_mission(
                MissionWorkflowInput(
                    mission_id="test-1",
                    session_id="sess-1",
                    mission_brief="Test mission",
                )
            )

            assert result.status == "failed"
            assert "boom" in result.outcome_json["error"]
```

**File**: `tests/unit/backend/agents/mission_control/test_approval.py` (NEW)

```python
"""Tests for the approval module."""

import pytest
from unittest.mock import patch, MagicMock


class TestRequestApproval:
    @pytest.mark.asyncio
    async def test_tier3_auto_approves_in_dev_mode(self):
        from modules.backend.agents.mission_control.approval import (
            request_approval,
        )

        with patch(
            "modules.backend.agents.mission_control.approval.get_app_config",
        ) as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.temporal.enabled = False
            mock_config.return_value = mock_cfg

            result = await request_approval(
                mission_id="test-mission",
                task_id="test-task",
                action="read_file",
                context={},
            )
            assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_raises_in_tier4(self):
        from modules.backend.agents.mission_control.approval import (
            request_approval,
        )

        with patch(
            "modules.backend.agents.mission_control.approval.get_app_config",
        ) as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.temporal.enabled = True
            mock_config.return_value = mock_cfg

            with pytest.raises(RuntimeError, match="Tier 4"):
                await request_approval(
                    mission_id="m", task_id="t", action="a", context={},
                )
```

**File**: `tests/unit/backend/agents/mission_control/test_escalation.py` (NEW)

```python
"""Tests for escalation chain logic."""

import pytest


class TestEscalationChain:
    def test_four_levels_exist(self):
        from modules.backend.agents.mission_control.escalation import (
            ESCALATION_CHAIN,
        )

        assert len(ESCALATION_CHAIN) == 4
        assert ESCALATION_CHAIN[0].level == 1
        assert ESCALATION_CHAIN[-1].level == 4
        for level in ESCALATION_CHAIN:
            assert "ai_" not in level.responder_type

    def test_get_next_escalation(self):
        from modules.backend.agents.mission_control.escalation import (
            get_next_escalation,
        )

        next_level = get_next_escalation(1)
        assert next_level is not None
        assert next_level.level == 2

    def test_get_next_escalation_at_max(self):
        from modules.backend.agents.mission_control.escalation import (
            get_next_escalation,
        )

        assert get_next_escalation(4) is None

    @pytest.mark.asyncio
    async def test_automated_rules_approve_low_risk(self):
        from modules.backend.agents.mission_control.escalation import (
            evaluate_automated_rules,
        )

        result = await evaluate_automated_rules("read_file", {})
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_automated_rules_approve_low_cost(self):
        from modules.backend.agents.mission_control.escalation import (
            evaluate_automated_rules,
        )

        result = await evaluate_automated_rules(
            "invoke_agent", {"estimated_cost_usd": 0.50},
        )
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_automated_rules_approve_retries(self):
        from modules.backend.agents.mission_control.escalation import (
            evaluate_automated_rules,
        )

        result = await evaluate_automated_rules(
            "invoke_agent", {"is_retry": True, "retry_count": 1},
        )
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_automated_rules_skip_high_risk(self):
        from modules.backend.agents.mission_control.escalation import (
            evaluate_automated_rules,
        )

        result = await evaluate_automated_rules(
            "deploy_to_production", {"estimated_cost_usd": 100.0},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_risk_matrix_approves_medium_risk(self):
        from modules.backend.agents.mission_control.escalation import (
            evaluate_risk_matrix,
        )

        result = await evaluate_risk_matrix(
            "invoke_agent",
            {
                "estimated_cost_usd": 5.0,
                "allowed_agents": {"code.qa.agent"},
                "agent_name": "code.qa.agent",
            },
        )
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_risk_matrix_escalates_high_cost(self):
        from modules.backend.agents.mission_control.escalation import (
            evaluate_risk_matrix,
        )

        result = await evaluate_risk_matrix(
            "invoke_agent", {"estimated_cost_usd": 50.0},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_risk_matrix_approves_safe_errors(self):
        from modules.backend.agents.mission_control.escalation import (
            evaluate_risk_matrix,
        )

        result = await evaluate_risk_matrix(
            "unknown_action", {"error_category": "timeout"},
        )
        assert result is not None
        assert result["decision"] == "approved"
```

---

### Step 12: Verify and Commit

| # | Task | Command/Notes |
|---|------|---------------|
| 12.1 | Run all existing tests | `python -m pytest tests/ -x -q` — ensure nothing broken |
| 12.2 | Run Temporal model tests | `python -m pytest tests/unit/backend/temporal/ -v` |
| 12.3 | Run approval/escalation tests | `python -m pytest tests/unit/backend/agents/mission_control/test_approval.py tests/unit/backend/agents/mission_control/test_escalation.py -v` |
| 12.4 | Run full test suite | `python -m pytest tests/ -q` — all green |
| 12.5 | Verify config loading | `python -c "from modules.backend.core.config import get_app_config; print(get_app_config().temporal.enabled)"` |
| 12.6 | Verify feature flag gating | `python -c "from modules.backend.temporal.client import get_temporal_config"` — should raise RuntimeError |
| 12.7 | Commit | `git commit -m "Implement Plan 16: Temporal integration with durable mission execution"` |
| 12.8 | Update plan status | Change status to Done |

---

## Files Created/Modified Summary

| File | Action | Lines (est.) |
|------|--------|-------------|
| `config/settings/temporal.yaml` | **Created** | ~15 |
| `modules/backend/core/config_schema.py` | Modified | +12 |
| `modules/backend/core/config.py` | Modified | +8 |
| `modules/backend/temporal/__init__.py` | **Created** | 1 |
| `modules/backend/temporal/models.py` | **Created** | ~90 |
| `modules/backend/temporal/client.py` | **Created** | ~50 |
| `modules/backend/temporal/activities.py` | **Created** | ~130 |
| `modules/backend/temporal/workflow.py` | **Created** | ~180 |
| `modules/backend/temporal/worker.py` | **Created** | ~45 |
| `modules/backend/agents/mission_control/approval.py` | **Created** | ~55 |
| `modules/backend/agents/mission_control/escalation.py` | **Created** | ~160 |
| `modules/backend/api/v1/endpoints/missions.py` | Modified | +95 |
| `requirements.txt` | Modified | +1 |
| `tests/unit/backend/temporal/__init__.py` | **Created** | 0 |
| `tests/unit/backend/temporal/test_models.py` | **Created** | ~35 |
| `tests/unit/backend/temporal/test_client.py` | **Created** | ~30 |
| `tests/unit/backend/temporal/test_activities.py` | **Created** | ~90 |
| `tests/unit/backend/agents/mission_control/test_approval.py` | **Created** | ~40 |
| `tests/unit/backend/agents/mission_control/test_escalation.py` | **Created** | ~90 |

**Total**: ~1,130 lines across 19 files (15 new, 4 modified)

---

## Anti-Patterns — Do NOT

| Anti-pattern | Why prohibited |
|-------------|---------------|
| One Activity per task with mutable task state in PostgreSQL | Our persistence model stores immutable JSONB audit records. The dispatch loop runs in memory. Creating a mutable task state machine contradicts Plan 15's architecture. |
| Storing MissionOutcome Pydantic models in Temporal event history | Temporal requires serializable dataclasses. Use DTOs (MissionExecutionResult) that carry primitive types. |
| Database access in Workflow code | Workflows are deterministic. Database access is non-deterministic. All DB operations happen in Activities. |
| `datetime.now()` in Workflow code | Non-deterministic. Use `workflow.now()` for deterministic timestamps. |
| Mixing Temporal state with PostgreSQL state | Temporal owns orchestration (position, retries, signals). PostgreSQL owns domain (missions, tasks, decisions). |
| In-memory timers for escalation | In-memory timers die with the process. Use Temporal's durable timers via `workflow.wait_condition(timeout=...)`. |
| Calling request_approval() in Tier 4 | In Tier 4, the workflow handles approval via Signals. |
| Wrapping all agents with TemporalAgent in v1 | Adds complexity. Start with mission-level durability (one Activity per mission). Add per-agent wrapping later for long-running tasks. |

---

## Future Enhancements (Not in This Plan)

1. **Per-agent TemporalAgent wrapping**: Wrap long-running agents with `TemporalAgent` for sub-task crash recovery. Requires the dispatch loop to integrate with `TemporalAgent.temporal_activities`.

2. **Real notification channels**: Implement Slack SDK, email, and webhook integrations in `send_notification`.

3. **Mission re-plan via Signal**: Send a `MissionModification` Signal to modify the mission mid-execution. Requires the workflow to re-invoke the Planning Agent.

4. **Parallel mission execution**: Start multiple missions as child workflows for Playbook orchestration.

5. **Temporal Search Attributes**: Add custom search attributes (roster_name, status, cost) for Temporal's visibility queries.
