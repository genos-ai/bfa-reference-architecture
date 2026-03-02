# Implementation Plan: Temporal Integration (Durable Execution)

*Created: 2026-03-02*
*Status: Not Started*
*Phase: 6 of 6 (AI-First Platform Build)*
*Depends on: Phase 1-5 (Event Bus, Sessions, Coordinator, PM Agent, Plan Management)*
*Blocked by: Phase 5*

---

## Summary

Wrap plan execution in Temporal workflows for Tier 4 (long-running autonomous tasks spanning hours/days/weeks). Temporal provides crash recovery, durable human-in-the-loop via Signals, progress inspection via Queries, and durable timers for escalation chains. PydanticAI has native Temporal integration via `TemporalAgent`.

**Critical rule: Temporal owns orchestration state. PostgreSQL owns domain state. Never mix them.** Temporal stores workflow position, retry counts, signal queues. PostgreSQL stores conversations, memories, plans, decisions. Temporal Activities read/write PostgreSQL. Never store large data in Temporal's event history — it bloats replay.

This phase activates Tier 4 autonomy. Tiers 1-3 continue to work without Temporal. Temporal is behind a feature flag (`temporal.enabled = false` by default).

**Dev mode: breaking changes allowed.** This is a new subsystem — no backward-compatibility constraints.

## Context

- Research: `docs/98-research/09-Building autonomous AI agents that run for weeks.md` — comprehensive comparison of Temporal, DBOS, Inngest, Hatchet. Temporal recommended for production reliability.
- Reference architecture: `docs/99-reference-architecture/46-event-session-architecture.md` (Section 6: Approval and Escalation, Section 7: Observability)
- PydanticAI native integration: `pydantic_ai.durable_exec.temporal.TemporalAgent` wraps agents into Workflows + Activities
- Pydantic AI Temporal example repo: `pydantic/pydantic-ai-temporal-example`
- The coordinator's `handle()` from Phase 3 accepts service objects as parameters (not global state) — this is what makes it Temporal-ready
- The PlanService from Phase 5 manages all domain state in PostgreSQL — Temporal Activities call PlanService methods
- The PM agent from Phase 4 delegates via the coordinator — in Tier 4, the PM runs inside a Temporal Activity

## What to Build

- `config/settings/temporal.yaml` — Temporal connection config with feature flag
- `modules/backend/core/config_schema.py` — `TemporalSchema` config schema
- `modules/backend/core/config.py` — Register temporal config in `AppConfig`
- `modules/backend/temporal/__init__.py` — package init
- `modules/backend/temporal/client.py` — Temporal client factory with feature-flag gating
- `modules/backend/temporal/workflow.py` — `AgentPlanWorkflow` with plan execution loop, Signals (submit_approval, modify_plan), and Queries (get_status)
- `modules/backend/temporal/activities.py` — Temporal Activities: `execute_task`, `handle_failure`, `send_notification`, `promote_ready_tasks`
- `modules/backend/temporal/worker.py` — Temporal worker setup and lifecycle
- `modules/backend/temporal/models.py` — Dataclasses for workflow inputs/outputs (serializable, no ORM objects)
- `modules/backend/agents/coordinator/approval.py` — `request_approval()` that works for both Tier 3 (Redis event bus) and Tier 4 (Temporal Signal)
- `modules/backend/agents/coordinator/escalation.py` — Escalation chain logic: automated rule → AI Haiku → AI Sonnet → human → manager
- Update `modules/backend/api/v1/endpoints/plans.py` — Add workflow start endpoint and Temporal Query-based status endpoint
- CLI command for starting the Temporal worker
- Tests with Temporal test environment (`temporalio.testing.WorkflowEnvironment`)

## Key Design Decisions

- **`TemporalAgent` wrapper**: PydanticAI's native integration separates agent code into deterministic Workflows (control flow, decisions) and non-deterministic Activities (LLM calls, tool invocations, database access). The agent's `run()` method executes inside an Activity.
- **Temporal Signals for human-in-the-loop**: `await workflow.wait_condition()` can sleep for days. When a task requires approval, the workflow pauses. Any entity (human, AI agent, automated rule) can resume it by sending a Signal. Signals survive crashes and restarts.
- **Temporal Queries for progress**: Synchronous, read-only status check. The `/plans/{plan_id}/status` endpoint uses a Temporal Query when `temporal.enabled = true` and falls back to direct PostgreSQL query otherwise.
- **Unified responder pattern**: Signals accept input from humans, AI agents, or automated rules identically. The workflow doesn't care who approved — it only checks the `ApprovalDecision` dataclass.
- **Escalation chain with durable timers**: If no approval in 4 hours → re-notify with higher urgency. If no approval in 24 hours → escalate to manager. Durable timers (Temporal) replace in-memory timers that die with the process.
- **Feature flag**: `temporal.enabled = false` by default. All Tier 3 functionality (interactive sessions, streaming coordinator, plan management) works without Temporal. Tier 4 activates only when the flag is enabled and a Temporal server is available.
- **Workflow ID convention**: `plan-{plan_id}` — one workflow per plan. This allows querying workflow status by plan ID.
- **Activities are idempotent**: Every Activity (execute_task, handle_failure, send_notification) is safe to retry. They use the PlanService's state machine to prevent double-execution (a task already `in_progress` won't be started again).
- **No large data in Temporal event history**: Activities pass IDs (plan_id, task_id), not full data objects. Activities fetch from PostgreSQL and write back to PostgreSQL. Temporal only stores the IDs and return values.
- **Dataclass DTOs for workflow I/O**: Temporal requires serializable inputs/outputs. ORM objects (Plan, PlanTask) are not passed through Temporal — dataclasses with primitive types are used instead.

## Success Criteria

- [ ] Temporal workflow executes a multi-step plan, delegating to vertical agents via Activities
- [ ] Workflow survives worker restart and resumes from last completed Activity
- [ ] Human approval via Signal pauses workflow, resumes when Signal received
- [ ] Query returns current plan status without interrupting execution
- [ ] Escalation chain triggers notifications with durable timers
- [ ] Feature flag controls whether plans execute via Temporal or directly
- [ ] Tier 3 (interactive sessions) continues to work without Temporal enabled
- [ ] Config loads from `temporal.yaml` with defaults
- [ ] All tests pass (including Temporal test environment)

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Commit any uncommitted work | `git status`, then commit if needed |
| 0.2 | Create feature branch | `git checkout -b feature/temporal-integration` |

---

### Step 1: Dependencies

Install Temporal SDK and PydanticAI Temporal integration:

```bash
pip install temporalio>=1.7.0
pip install "pydantic-ai[temporal]"
```

Add to `requirements.txt` or `pyproject.toml` — whichever the project uses for dependency management.

**Note**: `temporalio` requires a Temporal Server for integration tests. For unit tests, the SDK includes `temporalio.testing.WorkflowEnvironment` which runs an in-process test server.

---

### Step 2: Temporal Configuration

**File**: `config/settings/temporal.yaml` (NEW)

```yaml
# =============================================================================
# Temporal Configuration (Tier 4 - Durable Execution)
# =============================================================================
# Available options:
#   enabled                       - Feature flag: enable Temporal integration (boolean)
#   server_url                    - Temporal Server gRPC address (string)
#   namespace                     - Temporal namespace (string)
#   task_queue                    - Task queue for agent plan workflows (string)
#   worker_count                  - Number of concurrent activity executors (integer)
#   workflow_execution_timeout_days - Maximum workflow duration in days (integer)
#   activity_start_to_close_seconds - Default activity timeout (integer)
#   activity_retry_max_attempts   - Max activity retry attempts (integer)
#   approval_timeout_seconds      - Default approval wait timeout (integer)
#   escalation_timeout_seconds    - Time before escalating unanswered approvals (integer)
#   notification_timeout_seconds  - Timeout for notification activities (integer)
# =============================================================================

enabled: false
server_url: "localhost:7233"
namespace: "default"
task_queue: "agent-plans"
worker_count: 4
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
    """Temporal integration configuration."""

    enabled: bool = False
    server_url: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "agent-plans"
    worker_count: int = 4
    workflow_execution_timeout_days: int = 30
    activity_start_to_close_seconds: int = 600
    activity_retry_max_attempts: int = 3
    approval_timeout_seconds: int = 14400
    escalation_timeout_seconds: int = 86400
    notification_timeout_seconds: int = 30
```

**File**: `modules/backend/core/config.py` — Register in `AppConfig`:

Add `temporal: TemporalSchema` field and load from `config/settings/temporal.yaml` using the existing `_load_validated()` pattern.

**Verification**: `python -c "from modules.backend.core.config import get_app_config; print(get_app_config().temporal.enabled)"` — should print `False`.

---

### Step 3: Temporal Data Models

**File**: `modules/backend/temporal/models.py` (NEW)

Dataclasses for workflow inputs, outputs, and signals. These are serializable — no ORM objects, no SQLAlchemy dependencies. Temporal serializes these as JSON in its event history.

```python
"""
Temporal workflow data models.

Serializable dataclasses for workflow inputs, outputs, and signals.
No ORM objects — Temporal serializes these as JSON. Activities convert
between these DTOs and domain objects (Plan, PlanTask).
"""

from dataclasses import dataclass, field


@dataclass
class PlanWorkflowInput:
    """Input to start an AgentPlanWorkflow."""

    plan_id: str
    session_id: str


@dataclass
class TaskExecutionInput:
    """Input for the execute_task Activity."""

    plan_id: str
    session_id: str
    task_id: str
    task_name: str
    assigned_agent: str
    input_data: dict | None = None


@dataclass
class TaskExecutionResult:
    """Output from the execute_task Activity."""

    task_id: str
    success: bool
    output_data: dict | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model: str | None = None


@dataclass
class ApprovalDecision:
    """Input from a Signal: human/AI/rule approval decision."""

    decision: str  # "approved", "rejected", "modified"
    responder_type: str  # "human", "ai_agent", "automated_rule"
    responder_id: str
    reason: str | None = None
    modified_params: dict | None = None


@dataclass
class PlanModification:
    """Input from a Signal: plan modification mid-execution."""

    tasks_to_add: list[dict] = field(default_factory=list)
    tasks_to_remove: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class WorkflowStatus:
    """Output from a Query: current workflow state."""

    plan_id: str
    plan_status: str
    current_task: str | None = None
    progress_pct: float = 0.0
    completed_tasks: list[str] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    blocked_tasks: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    waiting_for_approval: bool = False
    version: int = 1


@dataclass
class NotificationPayload:
    """Input for the send_notification Activity."""

    channel: str  # "slack", "email", "webhook"
    recipient: str  # channel ID, email address, or webhook URL
    title: str
    body: str
    action_url: str
    urgency: str = "normal"  # "low", "normal", "high", "critical"


@dataclass
class FailureHandlingInput:
    """Input for the handle_failure Activity."""

    plan_id: str
    task_id: str
    error: str


@dataclass
class FailureHandlingResult:
    """Output from the handle_failure Activity."""

    action: str  # "retried", "needs_revision", "revised", "needs_escalation"
    task_id: str
    success: bool = True
```

**Why dataclasses**: Temporal requires all workflow inputs/outputs to be serializable. SQLAlchemy models are not. These DTOs are the translation layer — Activities convert between DTOs and domain objects.

---

### Step 4: Temporal Client

**File**: `modules/backend/temporal/client.py` (NEW)

Temporal client factory with feature-flag gating:

```python
"""
Temporal Client Factory.

Provides a cached Temporal client connection. Gated by the
temporal.enabled feature flag — raises RuntimeError if Temporal
is not enabled.
"""

from functools import lru_cache

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
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
    """
    from temporalio.client import Client

    config = get_temporal_config()

    client = await Client.connect(
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

    return client
```

---

### Step 5: Temporal Activities

**File**: `modules/backend/temporal/activities.py` (NEW)

Activities are the non-deterministic operations: LLM calls, database access, notifications. Each Activity is idempotent and safe to retry.

```python
"""
Temporal Activities.

Non-deterministic operations that run outside the Workflow's
deterministic replay: LLM calls (via coordinator), database access
(via PlanService), and notifications.

Each Activity is idempotent — safe to retry on failure.
Activities receive IDs, fetch from PostgreSQL, and write back.
No large objects in Temporal event history.
"""

from temporalio import activity

from modules.backend.core.logging import get_logger
from modules.backend.temporal.models import (
    FailureHandlingInput,
    FailureHandlingResult,
    NotificationPayload,
    TaskExecutionInput,
    TaskExecutionResult,
)

logger = get_logger(__name__)


@activity.defn
async def execute_task(input: TaskExecutionInput) -> TaskExecutionResult:
    """Execute a single plan task by delegating to the assigned agent.

    1. Fetch task from PostgreSQL
    2. Start the task (status → in_progress)
    3. Execute the agent via the coordinator
    4. Complete or fail the task
    5. Return result DTO

    This Activity is the bridge between Temporal and the coordinator.
    The coordinator's handle() + collect() runs the agent with full
    middleware (cost tracking, budget enforcement, events).
    """
    from modules.backend.core.database import get_async_session
    from modules.backend.services.plan import PlanService

    async with get_async_session() as db:
        service = PlanService(db)

        try:
            # Start the task
            await service.start_task(input.task_id)
            await db.commit()
        except ValueError:
            # Task already in progress (idempotent — Activity retried)
            logger.warning(
                "Task already started (Activity retry)",
                extra={"task_id": input.task_id},
            )

        try:
            # Execute the agent through the coordinator (Phase 3 API)
            # Uses collect() which drains handle()'s AsyncIterator[SessionEvent]
            # into a synchronous result. This ensures full middleware applies:
            # cost tracking, budget enforcement, event publishing.
            from modules.backend.agents.coordinator.coordinator import collect

            user_input = (
                input.input_data.get("task", input.task_name)
                if input.input_data
                else input.task_name
            )

            result = await collect(
                session_id=input.session_id,
                message=user_input,
                agent_name=input.assigned_agent,
            )

            # Complete the task
            await service.complete_task(
                task_id=input.task_id,
                output_data={
                    "agent_name": result.agent_name,
                    "output": result.output,
                },
            )
            await db.commit()

            return TaskExecutionResult(
                task_id=input.task_id,
                success=True,
                output_data={
                    "agent_name": result.agent_name,
                    "output": result.output,
                },
            )

        except Exception as e:
            # Fail the task
            error_msg = str(e)
            await service.fail_task(
                task_id=input.task_id,
                error=error_msg,
            )
            await db.commit()

            return TaskExecutionResult(
                task_id=input.task_id,
                success=False,
                error=error_msg,
            )


@activity.defn
async def promote_ready_tasks(plan_id: str) -> list[str]:
    """Promote pending tasks with satisfied dependencies to 'ready'.

    Returns list of newly ready task IDs.
    """
    from modules.backend.core.database import get_async_session
    from modules.backend.services.plan import PlanService

    async with get_async_session() as db:
        service = PlanService(db)
        ready = await service.promote_ready_tasks(plan_id)
        await db.commit()
        return [t.id for t in ready]


@activity.defn
async def handle_task_failure(
    input: FailureHandlingInput,
) -> FailureHandlingResult:
    """Handle a failed task: retry, revision, or escalation.

    Returns the action taken so the workflow can decide next steps.
    """
    from modules.backend.core.database import get_async_session
    from modules.backend.services.plan import PlanService

    async with get_async_session() as db:
        service = PlanService(db)
        action = await service.handle_task_failure(
            plan_id=input.plan_id,
            task_id=input.task_id,
            error=input.error,
        )
        await db.commit()

        return FailureHandlingResult(
            action=action,
            task_id=input.task_id,
        )


@activity.defn
async def revise_plan_with_pm(
    input: FailureHandlingInput,
) -> FailureHandlingResult:
    """Invoke the PM agent to revise a plan after task failure (P8).

    The PM agent evaluates the failure context and calls
    PlanService.revise_plan() to modify remaining tasks while
    preserving completed work. This is an Activity (not workflow code)
    because it makes LLM calls and writes to PostgreSQL.
    """
    from modules.backend.agents.coordinator.coordinator import collect
    from modules.backend.core.database import get_async_session

    try:
        # Ask the PM agent to revise the plan
        revision_prompt = (
            f"Task '{input.task_id}' in plan '{input.plan_id}' failed "
            f"with error: {input.error}\n\n"
            f"Review the plan status, identify what went wrong, and "
            f"revise the remaining tasks. Use revise_plan to update "
            f"the plan. Preserve all completed work."
        )

        result = await collect(
            session_id=input.plan_id,  # Plan session
            message=revision_prompt,
            agent_name="horizontal.pm.agent",
        )

        return FailureHandlingResult(
            action="revised",
            task_id=input.task_id,
            success=True,
        )

    except Exception as e:
        logger.error(
            "Plan revision failed",
            extra={
                "plan_id": input.plan_id,
                "task_id": input.task_id,
                "error": str(e),
            },
        )
        return FailureHandlingResult(
            action="needs_escalation",
            task_id=input.task_id,
            success=False,
        )


@activity.defn
async def get_plan_status_activity(plan_id: str) -> dict:
    """Fetch plan status from PostgreSQL for workflow state updates."""
    from modules.backend.core.database import get_async_session
    from modules.backend.services.plan import PlanService

    async with get_async_session() as db:
        service = PlanService(db)
        return await service.get_plan_status(plan_id)


@activity.defn
async def send_notification(payload: NotificationPayload) -> bool:
    """Send notification via configured channel.

    Implementations for each channel would be added as needed.
    For now, logs the notification (sufficient for development).
    """
    logger.info(
        "Notification sent",
        extra={
            "channel": payload.channel,
            "recipient": payload.recipient,
            "title": payload.title,
            "urgency": payload.urgency,
        },
    )

    if payload.channel == "slack":
        return await _send_slack(payload)
    elif payload.channel == "email":
        return await _send_email(payload)
    elif payload.channel == "webhook":
        return await _send_webhook(payload)

    return True


async def _send_slack(payload: NotificationPayload) -> bool:
    """Send Slack notification. Stub — implement with Slack SDK."""
    logger.info("Slack notification (stub)", extra={"title": payload.title})
    return True


async def _send_email(payload: NotificationPayload) -> bool:
    """Send email notification. Stub — implement with email service."""
    logger.info("Email notification (stub)", extra={"title": payload.title})
    return True


async def _send_webhook(payload: NotificationPayload) -> bool:
    """Send webhook notification. Stub — implement with httpx."""
    logger.info(
        "Webhook notification (stub)", extra={"url": payload.action_url}
    )
    return True
```

**Design notes**:
- `execute_task` is the critical Activity — it bridges Temporal and the coordinator. It fetches the task from PostgreSQL, runs the agent, and writes results back.
- Each Activity creates its own database session (`get_async_session()`) — Activities run in separate threads/processes and cannot share sessions with the Workflow.
- `execute_task` is idempotent: if the task is already `in_progress` (Activity retried), it logs a warning and continues.
- Notification Activities are stubs — implement with actual Slack/email/webhook SDKs when needed.

---

### Step 6: Temporal Workflow

**File**: `modules/backend/temporal/workflow.py` (NEW)

The core workflow that executes a plan as a DAG:

```python
"""
Agent Plan Workflow.

Temporal Workflow that executes a plan's task DAG. Each task runs as
an Activity (non-deterministic: LLM calls, DB access). The workflow
handles Signals (approval, plan modification) and Queries (status).

Key rules:
- Workflow code is deterministic — no I/O, no random, no datetime.now()
- All side effects happen in Activities
- Temporal owns orchestration state (position, signals, timers)
- PostgreSQL owns domain state (plans, tasks, decisions)
"""

from datetime import timedelta

from temporalio import workflow

from modules.backend.temporal.models import (
    ApprovalDecision,
    FailureHandlingInput,
    NotificationPayload,
    PlanModification,
    PlanWorkflowInput,
    TaskExecutionInput,
    WorkflowStatus,
)

with workflow.unsafe.imports_passed_through():
    from modules.backend.temporal import activities


@workflow.defn
class AgentPlanWorkflow:
    """Execute a plan as a sequence of Temporal Activities.

    The workflow loop:
    1. Promote ready tasks (pending → ready)
    2. Execute ready tasks as Activities
    3. Handle results (success → promote next, failure → retry/revise)
    4. If approval needed, wait for Signal
    5. If plan modified via Signal, re-evaluate ready tasks
    6. Repeat until all tasks complete or plan fails
    """

    def __init__(self) -> None:
        self._approval: ApprovalDecision | None = None
        self._plan_modifications: list[PlanModification] = []
        self._awaiting_approval: bool = False
        self._status: WorkflowStatus = WorkflowStatus(plan_id="")
        self._should_recheck: bool = False

    # ---- Signals ----

    @workflow.signal
    async def submit_approval(self, decision: ApprovalDecision) -> None:
        """Receive approval from any source: human, AI, or automated rule."""
        self._approval = decision

    @workflow.signal
    async def modify_plan(self, modification: PlanModification) -> None:
        """Receive plan modifications from human or coordinator."""
        self._plan_modifications.append(modification)
        self._should_recheck = True

    # ---- Queries ----

    @workflow.query
    def get_status(self) -> WorkflowStatus:
        """Read-only status for dashboards. Does not interrupt workflow."""
        return self._status

    # ---- Main workflow ----

    @workflow.run
    async def run(self, input: PlanWorkflowInput) -> WorkflowStatus:
        """Execute the plan DAG until completion or failure."""
        self._status.plan_id = input.plan_id

        config = workflow.info().search_attributes or {}
        activity_timeout = timedelta(seconds=600)
        notification_timeout = timedelta(seconds=30)

        max_iterations = 100  # safety limit
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Apply any pending plan modifications
            for mod in self._plan_modifications:
                # Plan revision happens in an Activity (DB access)
                await workflow.execute_activity(
                    activities.get_plan_status_activity,
                    input.plan_id,
                    start_to_close_timeout=activity_timeout,
                )
            self._plan_modifications.clear()

            # Promote ready tasks
            ready_task_ids = await workflow.execute_activity(
                activities.promote_ready_tasks,
                input.plan_id,
                start_to_close_timeout=activity_timeout,
            )

            if not ready_task_ids:
                # No ready tasks — check if plan is complete
                status = await workflow.execute_activity(
                    activities.get_plan_status_activity,
                    input.plan_id,
                    start_to_close_timeout=activity_timeout,
                )
                self._update_status(status)

                if status["status"] in ("completed", "failed", "cancelled"):
                    break

                if self._awaiting_approval:
                    # Wait for approval Signal
                    await workflow.wait_condition(
                        lambda: self._approval is not None
                        or self._should_recheck
                    )

                    if self._approval:
                        self._awaiting_approval = False
                        self._approval = None
                        continue

                    if self._should_recheck:
                        self._should_recheck = False
                        continue

                # No ready tasks and not waiting — something is stuck
                # This shouldn't happen with a valid DAG, but handle it
                break

            # Execute ready tasks
            for task_id in ready_task_ids:
                # Fetch task details for the Activity input
                status = await workflow.execute_activity(
                    activities.get_plan_status_activity,
                    input.plan_id,
                    start_to_close_timeout=activity_timeout,
                )
                self._update_status(status)

                # Execute the task
                task_input = TaskExecutionInput(
                    plan_id=input.plan_id,
                    task_id=task_id,
                    task_name=f"task-{task_id[:8]}",
                    assigned_agent="",  # fetched from DB in Activity
                )

                result = await workflow.execute_activity(
                    activities.execute_task,
                    task_input,
                    start_to_close_timeout=activity_timeout,
                    retry_policy=workflow.RetryPolicy(
                        maximum_attempts=3,
                        initial_interval=timedelta(seconds=1),
                        maximum_interval=timedelta(seconds=60),
                    ),
                )

                if result.success:
                    self._status.completed_tasks.append(task_id)
                else:
                    # Handle failure
                    failure_result = await workflow.execute_activity(
                        activities.handle_task_failure,
                        FailureHandlingInput(
                            plan_id=input.plan_id,
                            task_id=task_id,
                            error=result.error or "Unknown error",
                        ),
                        start_to_close_timeout=activity_timeout,
                    )

                    if failure_result.action == "retried":
                        # Task was reset to ready — will be picked up
                        # in next iteration
                        pass
                    elif failure_result.action == "needs_revision":
                        self._status.failed_tasks.append(task_id)

                        # Invoke PM agent to revise the plan (P8)
                        revision_result = await workflow.execute_activity(
                            activities.revise_plan_with_pm,
                            FailureHandlingInput(
                                plan_id=input.plan_id,
                                task_id=task_id,
                                error=result.error or "Unknown error",
                            ),
                            start_to_close_timeout=timedelta(minutes=5),
                        )

                        if not revision_result.success:
                            # Revision failed — escalate to human
                            self._status.blocked_tasks.append(task_id)
                            self._awaiting_approval = True
                            self._status.waiting_for_approval = True
                    elif failure_result.action == "needs_escalation":
                        self._status.failed_tasks.append(task_id)
                        self._awaiting_approval = True
                        self._status.waiting_for_approval = True

                        # Send notification
                        await workflow.execute_activity(
                            activities.send_notification,
                            NotificationPayload(
                                channel="webhook",
                                recipient="admin",
                                title=f"Task escalation: {task_id[:8]}",
                                body=(
                                    f"Task failed after max retries. "
                                    f"Error: {result.error}"
                                ),
                                action_url=f"/api/v1/plans/{input.plan_id}",
                                urgency="high",
                            ),
                            start_to_close_timeout=notification_timeout,
                        )

                        # Set escalation timer
                        await self._escalation_timer(
                            input.plan_id, task_id, notification_timeout
                        )

        # Final status update
        final_status = await workflow.execute_activity(
            activities.get_plan_status_activity,
            input.plan_id,
            start_to_close_timeout=activity_timeout,
        )
        self._update_status(final_status)

        return self._status

    def _update_status(self, status_dict: dict) -> None:
        """Update workflow status from plan status dict."""
        self._status.plan_status = status_dict.get("status", "unknown")
        self._status.progress_pct = status_dict.get("progress_pct", 0.0)
        self._status.version = status_dict.get("version", 1)

    async def _escalation_timer(
        self,
        plan_id: str,
        task_id: str,
        notification_timeout: timedelta,
    ) -> None:
        """Set durable escalation timer.

        If no approval after 4 hours, re-notify with higher urgency.
        If no approval after 24 hours, escalate to manager.
        """
        # Wait 4 hours (or until approval arrives)
        try:
            await workflow.wait_condition(
                lambda: self._approval is not None,
                timeout=timedelta(hours=4),
            )
        except TimeoutError:
            # Re-notify with higher urgency
            await workflow.execute_activity(
                activities.send_notification,
                NotificationPayload(
                    channel="webhook",
                    recipient="admin",
                    title=f"REMINDER: Task escalation: {task_id[:8]}",
                    body="Approval still pending after 4 hours.",
                    action_url=f"/api/v1/plans/{plan_id}",
                    urgency="critical",
                ),
                start_to_close_timeout=notification_timeout,
            )
```

**Design notes**:
- The workflow is deterministic — no I/O, no random, no imports that have side effects. `workflow.unsafe.imports_passed_through()` is used for Activity imports (Temporal requirement).
- The main loop promotes ready tasks, executes them, handles failures, and repeats. This mirrors the DAG traversal from PlanService but with Temporal's durable execution guarantees.
- `_escalation_timer` uses `workflow.wait_condition` with a timeout — this is a durable timer that survives crashes.
- The `max_iterations` safety limit prevents infinite loops in case of bugs.
- The workflow currently executes tasks sequentially. Parallel execution (multiple Activities at once) can be added by using `asyncio.gather` on Activity futures — but sequential is safer for the initial implementation.

---

### Step 7: Temporal Worker

**File**: `modules/backend/temporal/worker.py` (NEW)

Worker setup and lifecycle:

```python
"""
Temporal Worker.

Starts a Temporal Worker that executes AgentPlanWorkflow and its
Activities. Run via CLI: python -m modules.backend.temporal.worker
"""

import asyncio

from temporalio.worker import Worker

from modules.backend.core.logging import get_logger
from modules.backend.temporal.activities import (
    execute_task,
    get_plan_status_activity,
    handle_task_failure,
    promote_ready_tasks,
    send_notification,
)
from modules.backend.temporal.client import get_temporal_client, get_temporal_config
from modules.backend.temporal.workflow import AgentPlanWorkflow

logger = get_logger(__name__)


async def start_worker() -> None:
    """Start the Temporal Worker."""
    config = get_temporal_config()
    client = await get_temporal_client()

    worker = Worker(
        client,
        task_queue=config.task_queue,
        workflows=[AgentPlanWorkflow],
        activities=[
            execute_task,
            promote_ready_tasks,
            handle_task_failure,
            get_plan_status_activity,
            send_notification,
        ],
    )

    logger.info(
        "Temporal worker starting",
        extra={
            "task_queue": config.task_queue,
            "worker_count": config.worker_count,
        },
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

**File**: `modules/backend/agents/coordinator/approval.py` (NEW)

Unified approval that works for both Tier 3 (event bus) and Tier 4 (Temporal Signal):

```python
"""
Approval Request Module.

Provides request_approval() that works for both Tier 3 (Redis event bus)
and Tier 4 (Temporal Signal). The caller doesn't need to know which
tier is active — the function checks the feature flag.
"""

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


async def request_approval(
    plan_id: str,
    task_id: str,
    action: str,
    context: dict,
    timeout_seconds: int = 14400,
) -> dict:
    """Request approval and return when a decision is received.

    In Tier 3: publishes an approval request event to the event bus
    and waits for a response event.

    In Tier 4: sends a notification Activity and waits for a
    Temporal Signal (handled by the workflow, not this function).

    For Tier 4, this function is NOT called directly — the workflow
    handles approval via Signals. This function is for Tier 3 only.
    """
    config = get_app_config()

    if config.temporal.enabled:
        # In Tier 4, approval is handled by the workflow via Signals.
        # This function should not be called in Tier 4.
        raise RuntimeError(
            "request_approval() should not be called in Tier 4. "
            "The workflow handles approval via Temporal Signals."
        )

    # Tier 3: event bus approval
    logger.info(
        "Approval requested (Tier 3)",
        extra={
            "plan_id": plan_id,
            "task_id": task_id,
            "action": action,
        },
    )

    # Publish approval request event
    # The event bus subscriber (channel adapter) presents this to the user
    # The user's response is published as an approval response event
    # For now, auto-approve (stub — implement with event bus when available)
    return {
        "decision": "approved",
        "responder_type": "automated_rule",
        "responder_id": "auto_approve_dev_mode",
        "reason": "Auto-approved in dev mode (Tier 3 stub)",
    }
```

---

### Step 9: Escalation Chain

**File**: `modules/backend/agents/coordinator/escalation.py` (NEW)

Escalation chain logic:

```python
"""
Escalation Chain.

Determines the escalation path when an approval request goes
unanswered or a task exceeds an agent's capability.

P2 PRINCIPLE: Deterministic over Non-Deterministic.
The escalation chain is entirely rule-based. No LLM calls.
Each level is a deterministic rule engine with increasingly broad
criteria. AI agents are NOT used for triage — a configurable risk
matrix handles medium-complexity cases that simple rules can't.
LLM-based evaluation would be non-deterministic, slow, and expensive
for what is fundamentally a classification problem with known inputs
(action type, cost, agent, retry count, error category).

Levels:
1. Low-risk rules (immediate) — read-only, low cost, retries
2. Medium-risk rules (immediate) — risk matrix with configurable thresholds
3. Human (Slack/email, 4h) — high-risk, ambiguous, novel actions
4. Human manager (24h) — escalation after Level 3 timeout
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
    """Get the escalation level by number.

    Returns None if the level doesn't exist.
    """
    for level in ESCALATION_CHAIN:
        if level.level == current_level:
            return level
    return None


def get_next_escalation(current_level: int) -> EscalationLevel | None:
    """Get the escalation level after the current one.

    Returns None if at the highest level.
    """
    for level in ESCALATION_CHAIN:
        if level.level == current_level + 1:
            return level
    return None


# ---- Risk classification (P2: all deterministic) ----

LOW_RISK_ACTIONS = frozenset({
    "read_file", "list_files", "get_status", "get_plan_status",
    "list_available_agents",
})

MEDIUM_RISK_ACTIONS = frozenset({
    "invoke_agent", "apply_fix", "run_tests", "create_plan",
    "revise_plan",
})

# Configurable thresholds for the risk matrix
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


# Default thresholds — override from config/settings/temporal.yaml
_thresholds = RiskThresholds()


async def evaluate_automated_rules(
    action: str,
    context: dict,
) -> dict | None:
    """Level 1: Check if an action can be auto-approved by low-risk rules.

    All checks are deterministic — no LLM calls.
    Returns an approval decision if rules match, None to escalate.
    """
    # Rule 1: Read-only operations are always safe
    if action in LOW_RISK_ACTIONS:
        return {
            "decision": "approved",
            "responder_type": "automated_rule",
            "responder_id": "rule:low_risk_action",
            "reason": f"Auto-approved: '{action}' is a low-risk action",
        }

    # Rule 2: Low cost operations
    cost = context.get("estimated_cost_usd", 0)
    if cost < _thresholds.max_auto_approve_cost_usd:
        return {
            "decision": "approved",
            "responder_type": "automated_rule",
            "responder_id": "rule:low_cost",
            "reason": f"Auto-approved: estimated cost ${cost:.2f} "
                      f"< ${_thresholds.max_auto_approve_cost_usd:.2f}",
        }

    # Rule 3: Retry of a previously approved action
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

    return None  # Escalate to Level 2


async def evaluate_risk_matrix(
    action: str,
    context: dict,
) -> dict | None:
    """Level 2: Risk matrix for medium-complexity decisions.

    Deterministic classification based on action type, cost, agent
    permissions, and error category. Handles the cases that are too
    complex for simple rules but don't need human judgment.
    """
    cost = context.get("estimated_cost_usd", 0)

    # Medium-risk actions within cost threshold
    if (
        action in MEDIUM_RISK_ACTIONS
        and cost < _thresholds.max_medium_approve_cost_usd
    ):
        agent = context.get("agent_name", "")
        # Agent must be in the plan's delegation allowlist
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

    # Known error categories that are safe to auto-handle
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

    return None  # Escalate to Level 3 (human)
```

---

### Step 10: Update Plan Endpoints for Temporal

**File**: `modules/backend/api/v1/endpoints/plans.py`

Add workflow start endpoint and Temporal Query-based status:

```python
@router.post(
    "/{plan_id}/execute",
    response_model=ApiResponse[dict],
    summary="Execute a plan",
    description="Start plan execution. Uses Temporal workflow if enabled, "
                "otherwise executes directly.",
)
async def execute_plan(
    plan_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[dict]:
    """Start plan execution."""
    from modules.backend.core.config import get_app_config

    config = get_app_config()

    if config.temporal.enabled:
        # Start a Temporal workflow
        from modules.backend.temporal.client import get_temporal_client
        from modules.backend.temporal.models import PlanWorkflowInput
        from modules.backend.temporal.workflow import AgentPlanWorkflow

        client = await get_temporal_client()

        # Get session_id from plan
        from modules.backend.services.plan import PlanService
        service = PlanService(db)
        plan = await service.get_plan(plan_id)
        if not plan:
            from modules.backend.core.exceptions import NotFoundError
            raise NotFoundError(f"Plan '{plan_id}' not found")

        handle = await client.start_workflow(
            AgentPlanWorkflow.run,
            PlanWorkflowInput(
                plan_id=plan_id,
                session_id=plan.session_id,
            ),
            id=f"plan-{plan_id}",
            task_queue=config.temporal.task_queue,
        )

        return ApiResponse(data={
            "workflow_id": handle.id,
            "plan_id": plan_id,
            "status": "started",
        })

    else:
        # Direct execution (Tier 3 — no Temporal)
        return ApiResponse(data={
            "plan_id": plan_id,
            "status": "direct_execution_not_implemented",
            "message": "Enable Temporal for plan execution, or "
                       "use the PM agent to execute tasks manually.",
        })


@router.post(
    "/{plan_id}/approve",
    response_model=ApiResponse[dict],
    summary="Submit approval for a plan task",
    description="Send an approval decision to a waiting workflow.",
)
async def submit_approval(
    plan_id: str,
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
            "error": "Temporal not enabled",
            "message": "Approval signals require Temporal.",
        })

    from modules.backend.temporal.client import get_temporal_client
    from modules.backend.temporal.models import ApprovalDecision
    from modules.backend.temporal.workflow import AgentPlanWorkflow

    client = await get_temporal_client()
    handle = client.get_workflow_handle(f"plan-{plan_id}")

    await handle.signal(
        AgentPlanWorkflow.submit_approval,
        ApprovalDecision(
            decision=decision,
            responder_type="human",
            responder_id=responder_id,
            reason=reason,
        ),
    )

    return ApiResponse(data={
        "plan_id": plan_id,
        "decision": decision,
        "status": "signal_sent",
    })
```

Also update the existing `get_plan_status` endpoint to use Temporal Query when enabled:

```python
@router.get("/{plan_id}/status", ...)
async def get_plan_status(plan_id, db, request_id):
    from modules.backend.core.config import get_app_config

    config = get_app_config()

    if config.temporal.enabled:
        try:
            from modules.backend.temporal.client import get_temporal_client
            from modules.backend.temporal.workflow import AgentPlanWorkflow

            client = await get_temporal_client()
            handle = client.get_workflow_handle(f"plan-{plan_id}")
            status = await handle.query(AgentPlanWorkflow.get_status)
            return ApiResponse(data=status)
        except Exception:
            pass  # Fall through to DB query if workflow not found

    # Fallback: direct DB query
    from modules.backend.services.plan import PlanService
    service = PlanService(db)
    status = await service.get_plan_status(plan_id)
    return ApiResponse(data=PlanStatusSummary(**status))
```

---

### Step 11: Tests

**File**: `tests/unit/backend/temporal/test_workflow.py` (NEW)

```python
"""
Temporal workflow tests.

Uses temporalio.testing.WorkflowEnvironment for an in-process
Temporal test server. No external Temporal Server needed.
"""

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from modules.backend.temporal.models import (
    ApprovalDecision,
    PlanWorkflowInput,
    WorkflowStatus,
)
from modules.backend.temporal.workflow import AgentPlanWorkflow


@pytest.fixture
async def temporal_env():
    """Create an in-process Temporal test environment."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


class TestAgentPlanWorkflow:
    """Tests for the AgentPlanWorkflow."""

    @pytest.fixture
    def mock_activities(self):
        """Create mock Activity implementations for testing."""
        from unittest.mock import AsyncMock

        from modules.backend.temporal.models import (
            FailureHandlingResult,
            TaskExecutionResult,
        )

        mock_promote = AsyncMock(return_value=["task-1"])
        mock_execute = AsyncMock(return_value=TaskExecutionResult(
            task_id="task-1",
            success=True,
            output_data={"output": "done"},
        ))
        mock_failure = AsyncMock(return_value=FailureHandlingResult(
            action="retried", task_id="task-1",
        ))
        mock_status = AsyncMock(return_value={
            "plan_id": "plan-1", "status": "active",
        })
        mock_notify = AsyncMock(return_value=True)
        mock_revise = AsyncMock(return_value=FailureHandlingResult(
            action="revised", task_id="task-1", success=True,
        ))

        return {
            "promote_ready_tasks": mock_promote,
            "execute_task": mock_execute,
            "handle_task_failure": mock_failure,
            "get_plan_status_activity": mock_status,
            "send_notification": mock_notify,
            "revise_plan_with_pm": mock_revise,
        }

    @pytest.mark.asyncio
    async def test_workflow_query_returns_status(
        self, temporal_env, mock_activities,
    ):
        """Query should return WorkflowStatus without interrupting."""
        async with Worker(
            temporal_env.client,
            task_queue="test-queue",
            workflows=[AgentPlanWorkflow],
            activities=list(mock_activities.values()),
        ):
            handle = await temporal_env.client.start_workflow(
                AgentPlanWorkflow.run,
                PlanWorkflowInput(plan_id="plan-1", session_id="sess-1"),
                id="test-plan-1",
                task_queue="test-queue",
            )

            # Query the workflow for status
            status = await handle.query(AgentPlanWorkflow.get_status)
            assert isinstance(status, WorkflowStatus)
            assert status.plan_id == "plan-1"

    @pytest.mark.asyncio
    async def test_approval_signal_resumes_workflow(
        self, temporal_env, mock_activities,
    ):
        """Signal should deliver approval and resume the workflow."""
        # Make promote return a task, execute return failure,
        # failure handler return needs_escalation (triggers approval wait)
        mock_activities["execute_task"].return_value = TaskExecutionResult(
            task_id="task-1", success=False, error="needs approval",
        )
        mock_activities["handle_task_failure"].return_value = (
            FailureHandlingResult(
                action="needs_escalation", task_id="task-1",
            )
        )
        # After approval, promote returns empty (plan complete)
        mock_activities["promote_ready_tasks"].side_effect = [
            ["task-1"], [],
        ]

        async with Worker(
            temporal_env.client,
            task_queue="test-queue",
            workflows=[AgentPlanWorkflow],
            activities=list(mock_activities.values()),
        ):
            handle = await temporal_env.client.start_workflow(
                AgentPlanWorkflow.run,
                PlanWorkflowInput(plan_id="plan-1", session_id="sess-1"),
                id="test-plan-approval",
                task_queue="test-queue",
            )

            # Send approval Signal
            await handle.signal(
                AgentPlanWorkflow.submit_approval,
                ApprovalDecision(
                    decision="approved",
                    responder_type="human",
                    responder_id="user-1",
                    reason="Looks good",
                ),
            )

    @pytest.mark.asyncio
    async def test_plan_modification_signal(
        self, temporal_env, mock_activities,
    ):
        """Plan modification Signal should be received by workflow."""
        from modules.backend.temporal.models import PlanModification

        async with Worker(
            temporal_env.client,
            task_queue="test-queue",
            workflows=[AgentPlanWorkflow],
            activities=list(mock_activities.values()),
        ):
            handle = await temporal_env.client.start_workflow(
                AgentPlanWorkflow.run,
                PlanWorkflowInput(plan_id="plan-1", session_id="sess-1"),
                id="test-plan-modify",
                task_queue="test-queue",
            )

            # Send modification Signal
            await handle.signal(
                AgentPlanWorkflow.modify_plan,
                PlanModification(
                    tasks_to_add=[{"name": "new-task"}],
                    tasks_to_remove=[],
                    reasoning="Adding recovery step",
                ),
            )


class TestWorkflowModels:
    """Tests for Temporal data models."""

    def test_plan_workflow_input_serializable(self):
        input = PlanWorkflowInput(plan_id="abc", session_id="def")
        assert input.plan_id == "abc"

    def test_approval_decision_serializable(self):
        decision = ApprovalDecision(
            decision="approved",
            responder_type="human",
            responder_id="user_123",
            reason="Looks good",
        )
        assert decision.decision == "approved"

    def test_workflow_status_defaults(self):
        status = WorkflowStatus(plan_id="abc")
        assert status.progress_pct == 0.0
        assert status.waiting_for_approval is False
        assert status.completed_tasks == []
```

**File**: `tests/unit/backend/temporal/test_activities.py` (NEW)

```python
"""
Temporal Activity tests.

Tests Activities in isolation — no Temporal server needed.
Activities are regular async functions that can be tested directly.
"""

import pytest

from modules.backend.temporal.models import (
    NotificationPayload,
)


class TestSendNotification:
    """Tests for the send_notification Activity."""

    @pytest.mark.asyncio
    async def test_send_notification_returns_true(self):
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


class TestGetPlanStatusActivity:
    """Tests for the get_plan_status_activity."""

    @pytest.mark.asyncio
    async def test_returns_status_dict(self, db_session):
        """Activity should return a dict with plan progress."""
        from modules.backend.models.plan import Plan, PlanTask
        from modules.backend.services.plan import PlanService

        # Create test plan with tasks
        plan = Plan(session_id="test-session", goal="Test goal")
        db_session.add(plan)
        await db_session.flush()
        await db_session.refresh(plan)

        task = PlanTask(
            plan_id=plan.id,
            name="test-task",
            assigned_agent="code.qa.agent",
        )
        db_session.add(task)
        await db_session.commit()

        service = PlanService(db_session)
        status = await service.get_plan_status(plan.id)

        assert status["plan_id"] == plan.id
        assert status["total_tasks"] == 1
        assert status["goal"] == "Test goal"
```

**File**: `tests/unit/backend/agents/coordinator/test_approval.py` (NEW)

```python
"""
Tests for the approval module.
"""

import pytest


class TestRequestApproval:
    """Tests for request_approval in Tier 3."""

    @pytest.mark.asyncio
    async def test_tier3_auto_approves_in_dev_mode(self):
        from modules.backend.agents.coordinator.approval import (
            request_approval,
        )

        result = await request_approval(
            plan_id="test-plan",
            task_id="test-task",
            action="read_file",
            context={},
        )
        assert result["decision"] == "approved"


class TestEscalationChain:
    """Tests for escalation chain logic."""

    def test_escalation_levels_exist(self):
        from modules.backend.agents.coordinator.escalation import (
            ESCALATION_CHAIN,
        )

        # 4 levels: low-risk rules, medium-risk matrix, human, manager
        assert len(ESCALATION_CHAIN) == 4
        assert ESCALATION_CHAIN[0].level == 1
        assert ESCALATION_CHAIN[-1].level == 4
        # No AI levels — all deterministic (P2)
        for level in ESCALATION_CHAIN:
            assert "ai_" not in level.responder_type

    def test_get_next_escalation(self):
        from modules.backend.agents.coordinator.escalation import (
            get_next_escalation,
        )

        next_level = get_next_escalation(1)
        assert next_level is not None
        assert next_level.level == 2

    def test_get_next_escalation_at_max(self):
        from modules.backend.agents.coordinator.escalation import (
            get_next_escalation,
        )

        next_level = get_next_escalation(4)
        assert next_level is None

    @pytest.mark.asyncio
    async def test_automated_rules_approve_low_risk(self):
        from modules.backend.agents.coordinator.escalation import (
            evaluate_automated_rules,
        )

        result = await evaluate_automated_rules("read_file", {})
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_automated_rules_approve_low_cost(self):
        from modules.backend.agents.coordinator.escalation import (
            evaluate_automated_rules,
        )

        result = await evaluate_automated_rules(
            "invoke_agent", {"estimated_cost_usd": 0.50}
        )
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_automated_rules_approve_retries(self):
        from modules.backend.agents.coordinator.escalation import (
            evaluate_automated_rules,
        )

        result = await evaluate_automated_rules(
            "invoke_agent", {"is_retry": True, "retry_count": 1}
        )
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_automated_rules_skip_high_risk(self):
        from modules.backend.agents.coordinator.escalation import (
            evaluate_automated_rules,
        )

        result = await evaluate_automated_rules(
            "deploy_to_production", {"estimated_cost_usd": 100.0}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_risk_matrix_approves_medium_risk(self):
        from modules.backend.agents.coordinator.escalation import (
            evaluate_risk_matrix,
        )

        result = await evaluate_risk_matrix(
            "invoke_agent",
            {"estimated_cost_usd": 5.0, "allowed_agents": {"code.qa.agent"},
             "agent_name": "code.qa.agent"},
        )
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_risk_matrix_escalates_high_cost(self):
        from modules.backend.agents.coordinator.escalation import (
            evaluate_risk_matrix,
        )

        result = await evaluate_risk_matrix(
            "invoke_agent",
            {"estimated_cost_usd": 50.0},
        )
        assert result is None  # Escalate to human
```

---

### Step 12: Verify and Commit

| # | Task | Command/Notes |
|---|------|---------------|
| 12.1 | Run all existing tests | `python -m pytest tests/ -x -q` — ensure nothing broken |
| 12.2 | Run Temporal model tests | `python -m pytest tests/unit/backend/temporal/test_workflow.py -v` |
| 12.3 | Run Activity tests | `python -m pytest tests/unit/backend/temporal/test_activities.py -v` |
| 12.4 | Run approval/escalation tests | `python -m pytest tests/unit/backend/agents/coordinator/test_approval.py -v` |
| 12.5 | Run full test suite | `python -m pytest tests/ -q` — all green |
| 12.6 | Verify config loading | `python -c "from modules.backend.core.config import get_app_config; print(get_app_config().temporal.enabled)"` |
| 12.7 | Verify feature flag gating | `python -c "from modules.backend.temporal.client import get_temporal_config"` — should raise RuntimeError |
| 12.8 | Commit | `git commit -m "Add Temporal integration: durable plan execution with Signals and Queries"` |

---

## Files Created/Modified Summary

| File | Action | Lines (est.) |
|------|--------|-------------|
| `config/settings/temporal.yaml` | **Created** | ~20 |
| `modules/backend/core/config_schema.py` | Modified | +15 |
| `modules/backend/core/config.py` | Modified | +5 |
| `modules/backend/temporal/__init__.py` | **Created** | 0 |
| `modules/backend/temporal/models.py` | **Created** | ~120 |
| `modules/backend/temporal/client.py` | **Created** | ~45 |
| `modules/backend/temporal/activities.py` | **Created** | ~180 |
| `modules/backend/temporal/workflow.py` | **Created** | ~230 |
| `modules/backend/temporal/worker.py` | **Created** | ~55 |
| `modules/backend/agents/coordinator/approval.py` | **Created** | ~60 |
| `modules/backend/agents/coordinator/escalation.py` | **Created** | ~100 |
| `modules/backend/api/v1/endpoints/plans.py` | Modified | +80 |
| `tests/unit/backend/temporal/__init__.py` | **Created** | 0 |
| `tests/unit/backend/temporal/test_workflow.py` | **Created** | ~60 |
| `tests/unit/backend/temporal/test_activities.py` | **Created** | ~40 |
| `tests/unit/backend/agents/coordinator/test_approval.py` | **Created** | ~70 |

**Total**: ~1,080 lines across 16 files (13 new, 3 modified)

---

## Anti-Patterns — Do NOT

| Anti-pattern | Why prohibited |
|-------------|---------------|
| Storing large data in Temporal event history | Temporal stores workflow position and return values. Large objects (conversation history, plan details, agent outputs) bloat replay. Pass IDs, fetch from PostgreSQL in Activities. |
| Database access in Workflow code | Workflows are deterministic. Database access is non-deterministic. All DB operations happen in Activities. |
| `datetime.now()` in Workflow code | Non-deterministic. Use `workflow.now()` for deterministic timestamps. |
| Random/UUID generation in Workflow code | Non-deterministic. Generate IDs in Activities and pass to Workflow. |
| Mixing Temporal state with PostgreSQL state | Temporal owns orchestration (position, retries, signals). PostgreSQL owns domain (plans, tasks, decisions). Never store domain state in Temporal or orchestration state in PostgreSQL. |
| In-memory timers for escalation | In-memory timers die with the process. Use Temporal's durable timers via `workflow.wait_condition(timeout=...)`. |
| Hard-coding responder types in approval | The unified responder pattern means any entity can approve. Don't build separate code paths for human vs. AI approval. |
| Calling request_approval() in Tier 4 | In Tier 4, approval is handled by the workflow via Signals. The workflow calls `wait_condition()`, not `request_approval()`. |

---
