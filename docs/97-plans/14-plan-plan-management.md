# Implementation Plan: Plan Management (Mutable DAG)

*Created: 2026-03-02*
*Status: Not Started*
*Phase: 5 of 6 (AI-First Platform Build)*
*Depends on: Phase 1-4 (Event Bus, Sessions, Coordinator, PM Agent)*
*Blocked by: Phase 4*

---

## Summary

Build the plan management system — a mutable DAG of tasks stored in PostgreSQL. Plans decompose goals into tasks with dependencies. When a task fails, the coordinator revises remaining tasks rather than regenerating the entire plan. Every decision is logged in a `plan_decisions` audit trail.

Plans are living documents, not static blueprints. They are versioned, revisable, and auditable. This is the foundation that Temporal workflows will wrap in Phase 6.

**Dev mode: breaking changes allowed.** This is a new subsystem — no backward-compatibility constraints.

## Context

- Reference architecture: `docs/99-reference-architecture/46-event-session-architecture.md` (Section 4: Plan Management)
- Research: `docs/98-research/09-Building autonomous AI agents that run for weeks.md` — DAG-based plan management, LLMCompiler pattern, plan revision over replanning, no-progress detection
- Task state machine: `pending → ready → in_progress → completed | failed | waiting_for_input | waiting_for_approval`
- Plans belong to sessions — a session can have multiple plans (sequential goals), but a plan always belongs to exactly one session
- The PM agent (Phase 4) delegates task execution; the PlanService manages task lifecycle
- Ready-task query: SQL with NOT EXISTS subquery — find tasks where all dependencies are completed
- Anti-pattern: Do NOT replan from scratch on failure. Modify remaining tasks. Completed work is preserved.
- Anti-pattern: Do NOT store plan data in Temporal's event history. Temporal owns orchestration state. PostgreSQL owns domain state.

## What to Build

- `modules/backend/models/plan.py` — `PlanStatus` enum, `TaskStatus` enum, `DependencyType` enum, `DecisionType` enum, `Plan`, `PlanTask`, `TaskDependency`, `TaskAttempt`, `PlanDecision` SQLAlchemy models
- `modules/backend/schemas/plan.py` — `PlanCreate`, `PlanResponse`, `PlanTaskCreate`, `PlanTaskResponse`, `TaskDependencyCreate`, `PlanRevisionRequest`, `PlanDecisionResponse` Pydantic schemas
- `modules/backend/repositories/plan.py` — `PlanRepository` with ready-task query, DAG validation, task lookup by plan
- `modules/backend/services/plan.py` — `PlanService` with plan lifecycle, task execution flow, failure handling (retry → revise → escalate), plan revision, decision logging
- `modules/backend/api/v1/endpoints/plans.py` — REST endpoints for plan CRUD, task status updates, ready-task queries, plan decisions
- `modules/backend/agents/tools/plan.py` — `create_plan()`, `get_plan_status()`, `revise_plan()` shared tool implementations for the PM agent
- `config/settings/plans.yaml` — plan config: max retries, no-progress thresholds, escalation timeouts
- `modules/backend/core/config_schema.py` — `PlansSchema` config schema
- `modules/backend/core/config.py` — Register plans config in `AppConfig`
- Alembic migration for `plans`, `plan_tasks`, `task_dependencies`, `task_attempts`, `plan_decisions` tables
- Update PM agent to use plan tools (add tool wrappers, update YAML config)
- Plan events: `plan.created`, `plan.task.started`, `plan.task.completed`, `plan.task.failed`, `plan.revised`
- Tests for DAG traversal, ready-task query, plan revision, failure handling, decision logging

## Key Design Decisions

- **Five tables**: `plans` (goals with versioning), `plan_tasks` (DAG nodes), `task_dependencies` (DAG edges), `task_attempts` (audit trail per execution), `plan_decisions` (every coordinator decision with reasoning)
- **Task status state machine**: `pending → ready → in_progress → completed | failed | waiting_for_input | waiting_for_approval`. Tasks start as `pending`. When all dependencies are completed, the service promotes them to `ready`. The executor picks up `ready` tasks and moves them to `in_progress`. Terminal states: `completed`, `failed` (after max retries + revision + escalation).
- **Ready-task query**: `SELECT tasks WHERE status='pending' AND NOT EXISTS (dep WHERE dep.status NOT IN ('completed'))` — efficiently finds executable tasks.
- **Plan revision over replanning**: on failure, modify remaining tasks. Completed work is preserved. The PM agent is called with the failure context and remaining tasks to produce a revision.
- **Decision audit trail**: Every meaningful coordinator decision is logged in `plan_decisions` with `decision_type`, `description`, `decided_by`, and `reasoning`. This creates a complete audit trail for debugging, analysis, and compliance.
- **`dependency_type`**: Two types — `completion` (predecessor must complete successfully) and `data` (needs output data but can handle predecessor failure). This allows partial-failure tolerance in the DAG.
- **No-progress detection**: Track repeated tool calls via `task_attempts`. If the same task fails with the same error 3 times, escalate to a smarter model or human rather than retrying with the same approach.
- **Plan version bumps on revision**: Every revision increments `plan.version`. The `plan_decisions` table records `plan_version_before` and `plan_version_after` for each change. This creates a versioned history of the plan's evolution.
- **String UUIDs** via `UUIDMixin` for consistency with existing codebase.
- **Plans are session-scoped**: A plan always has a `session_id`. No orphan plans.

## Success Criteria

- [ ] Plans decompose into task DAGs with dependencies stored in PostgreSQL
- [ ] Ready-task query correctly identifies executable tasks (all deps satisfied)
- [ ] Tasks follow the state machine: pending → ready → in_progress → completed/failed
- [ ] Failed tasks trigger retry (up to `max_retries`), then plan revision, then escalation
- [ ] Every decision is logged in `plan_decisions` with reasoning
- [ ] Plan events publish to the event bus
- [ ] Plan revision modifies remaining tasks without re-executing completed work
- [ ] DAG validation rejects cycles at creation time
- [ ] PM agent (Phase 4) can create and manage plans through the plan tools
- [ ] Config loads from `plans.yaml` with defaults
- [ ] All tests pass

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Commit any uncommitted work | `git status`, then commit if needed |
| 0.2 | Create feature branch | `git checkout -b feature/plan-management` |

---

### Step 1: Plan Configuration

**File**: `config/settings/plans.yaml` (NEW)

```yaml
# =============================================================================
# Plan Management Configuration
# =============================================================================
# Available options:
#   default_max_retries      - Default max retries per task (integer)
#   no_progress_threshold    - Consecutive identical failures before escalation (integer)
#   task_timeout_seconds     - Default task execution timeout (integer)
#   max_tasks_per_plan       - Maximum tasks in a single plan (integer)
#   max_parallel_tasks       - Maximum tasks executing concurrently (integer)
#   escalation_timeout_seconds - Time before escalating unresolved failures (integer)
# =============================================================================

default_max_retries: 3
no_progress_threshold: 3
task_timeout_seconds: 300
max_tasks_per_plan: 50
max_parallel_tasks: 5
escalation_timeout_seconds: 14400
```

**File**: `modules/backend/core/config_schema.py` — Add `PlansSchema`:

```python
class PlansSchema(_StrictBase):
    """Plan management configuration."""

    default_max_retries: int = 3
    no_progress_threshold: int = 3
    task_timeout_seconds: int = 300
    max_tasks_per_plan: int = 50
    max_parallel_tasks: int = 5
    escalation_timeout_seconds: int = 14400
```

**File**: `modules/backend/core/config.py` — Register in `AppConfig`:

Add `plans: PlansSchema` field and load from `config/settings/plans.yaml` using the existing `_load_validated()` pattern.

**Verification**: `python -c "from modules.backend.core.config import get_app_config; print(get_app_config().plans.default_max_retries)"` — should print `3`.

---

### Step 2: Plan Models

**File**: `modules/backend/models/plan.py` (NEW)

Create five SQLAlchemy 2.0 models matching the reference architecture's database schema, adapted to the codebase's patterns (string UUIDs via `UUIDMixin`, `TimestampMixin`, `Mapped` type hints):

```python
"""
Plan Management Models.

Mutable DAG of tasks stored in PostgreSQL. Plans decompose goals into
tasks with dependencies. Every decision is logged in plan_decisions.
"""

import enum

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class PlanStatus(str, enum.Enum):
    """Plan lifecycle status."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(str, enum.Enum):
    """Task state machine.

    Transitions:
        pending → ready (all deps completed)
        ready → in_progress (executor picks up)
        in_progress → completed | failed | waiting_for_input | waiting_for_approval
        waiting_for_input → in_progress (input received)
        waiting_for_approval → in_progress (approved) | failed (rejected)
        failed → ready (retry after plan revision)
    """

    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    REPLACED = "replaced"
    WAITING_FOR_INPUT = "waiting_for_input"
    WAITING_FOR_APPROVAL = "waiting_for_approval"


# Valid transitions for task status state machine
VALID_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.READY},
    TaskStatus.READY: {TaskStatus.IN_PROGRESS},
    TaskStatus.IN_PROGRESS: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.WAITING_FOR_INPUT,
        TaskStatus.WAITING_FOR_APPROVAL,
    },
    TaskStatus.COMPLETED: set(),  # terminal
    TaskStatus.FAILED: {TaskStatus.READY},  # retry
    TaskStatus.SKIPPED: set(),  # terminal
    TaskStatus.REPLACED: set(),  # terminal
    TaskStatus.WAITING_FOR_INPUT: {TaskStatus.IN_PROGRESS},
    TaskStatus.WAITING_FOR_APPROVAL: {TaskStatus.IN_PROGRESS, TaskStatus.FAILED},
}


class DependencyType(str, enum.Enum):
    """Task dependency types."""

    COMPLETION = "completion"  # predecessor must complete successfully
    DATA = "data"  # needs output data, can handle predecessor failure


class DecisionType(str, enum.Enum):
    """Plan decision types for audit trail."""

    PLAN_CREATED = "plan_created"
    TASK_ADDED = "task_added"
    TASK_REMOVED = "task_removed"
    TASK_REORDERED = "task_reordered"
    TASK_RETRIED = "task_retried"
    PLAN_REVISED = "plan_revised"
    TASK_ESCALATED = "task_escalated"
    HUMAN_OVERRIDE = "human_override"
    AUTO_APPROVED = "auto_approved"


class Plan(UUIDMixin, TimestampMixin, Base):
    """Top-level plan — a goal decomposed into a DAG of tasks."""

    __tablename__ = "plans"

    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(PlanStatus, native_enum=False),
        default=PlanStatus.ACTIVE,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    tasks: Mapped[list["PlanTask"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan",
    )
    decisions: Mapped[list["PlanDecision"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Plan(id={self.id}, goal={self.goal[:50]!r}, status={self.status})>"


class PlanTask(UUIDMixin, TimestampMixin, Base):
    """A single task in a plan DAG."""

    __tablename__ = "plan_tasks"

    plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("plans.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(TaskStatus, native_enum=False),
        default=TaskStatus.PENDING,
        nullable=False,
    )
    assigned_agent: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )
    assigned_model: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )
    input_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Relationships
    plan: Mapped["Plan"] = relationship(back_populates="tasks")
    attempts: Mapped[list["TaskAttempt"]] = relationship(
        back_populates="task", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<PlanTask(id={self.id}, name={self.name!r}, status={self.status})>"


class TaskDependency(UUIDMixin, Base):
    """DAG edge: task_id depends on depends_on_task_id."""

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dep"),
    )

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("plan_tasks.id"),
        nullable=False,
        index=True,
    )
    depends_on_task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("plan_tasks.id"),
        nullable=False,
    )
    dependency_type: Mapped[str] = mapped_column(
        Enum(DependencyType, native_enum=False),
        default=DependencyType.COMPLETION,
        nullable=False,
    )


class TaskAttempt(UUIDMixin, Base):
    """Audit trail of every task execution attempt."""

    __tablename__ = "task_attempts"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt_number", name="uq_task_attempt"),
    )

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("plan_tasks.id"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[str] = mapped_column(String(30), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    task: Mapped["PlanTask"] = relationship(back_populates="attempts")


class PlanDecision(UUIDMixin, Base):
    """Audit log of every coordinator decision about a plan."""

    __tablename__ = "plan_decisions"

    plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("plans.id"),
        nullable=False,
        index=True,
    )
    decision_type: Mapped[str] = mapped_column(
        Enum(DecisionType, native_enum=False),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_version_before: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(30), nullable=False)

    # Relationships
    plan: Mapped["Plan"] = relationship(back_populates="decisions")
```

**Adapter notes**:
- Uses `JSON` (via `sqlalchemy.dialects.sqlite`) for `input_data`, `output_data`, `error_data` — works with both PostgreSQL (JSONB) and SQLite (text JSON) for test compatibility
- `started_at`, `completed_at` stored as ISO strings rather than DateTime — simpler for JSON serialization
- `VALID_TASK_TRANSITIONS` dict mirrors the session status pattern from Plan 11
- Table named `plan_tasks` (not `tasks`) to avoid ambiguity with generic concept of "tasks"

**File**: `modules/backend/models/__init__.py` — Add import:

```python
from modules.backend.models.plan import Plan, PlanTask, TaskDependency, TaskAttempt, PlanDecision
```

This registers the models with Alembic for autogenerate.

---

### Step 3: Plan Schemas

**File**: `modules/backend/schemas/plan.py` (NEW)

Pydantic schemas for API serialization and validation:

```python
"""
Plan management API schemas.

Request/response models for plan CRUD, task management, and plan revision.
"""

from pydantic import BaseModel, ConfigDict, Field

from modules.backend.models.plan import (
    DependencyType,
    PlanStatus,
    TaskStatus,
)


# ---- Task dependency schemas ----

class TaskDependencyCreate(BaseModel):
    """Create a dependency between two tasks."""

    depends_on_task_id: str
    dependency_type: DependencyType = DependencyType.COMPLETION


class TaskDependencyResponse(BaseModel):
    """API response for a task dependency."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    depends_on_task_id: str
    dependency_type: str


# ---- Task schemas ----

class PlanTaskCreate(BaseModel):
    """Create a new task in a plan."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    assigned_agent: str | None = None
    assigned_model: str | None = None
    input_data: dict | None = None
    max_retries: int = Field(default=3, ge=0, le=10)
    sort_order: int = 0
    dependencies: list[TaskDependencyCreate] = Field(default_factory=list)


class PlanTaskResponse(BaseModel):
    """API response for a task."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    plan_id: str
    name: str
    description: str | None
    status: str
    assigned_agent: str | None
    assigned_model: str | None
    input_data: dict | None
    output_data: dict | None
    error_data: dict | None
    retry_count: int
    max_retries: int
    sort_order: int
    started_at: str | None
    completed_at: str | None
    created_at: str
    updated_at: str


class PlanTaskUpdate(BaseModel):
    """Update task status and data."""

    status: TaskStatus | None = None
    output_data: dict | None = None
    error_data: dict | None = None


# ---- Plan schemas ----

class PlanCreate(BaseModel):
    """Create a new plan."""

    goal: str = Field(..., min_length=1)
    tasks: list[PlanTaskCreate] = Field(default_factory=list)


class PlanResponse(BaseModel):
    """API response for a plan."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    goal: str
    status: str
    version: int
    created_at: str
    updated_at: str


class PlanDetailResponse(BaseModel):
    """Detailed plan response with tasks."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    goal: str
    status: str
    version: int
    tasks: list[PlanTaskResponse]
    created_at: str
    updated_at: str


class PlanStatusSummary(BaseModel):
    """Summary of plan progress."""

    plan_id: str
    goal: str
    status: str
    version: int
    total_tasks: int
    pending_tasks: int
    ready_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    failed_tasks: int
    waiting_tasks: int
    progress_pct: float


# ---- Plan revision schemas ----

class TaskAddition(BaseModel):
    """A new task to add during plan revision."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    assigned_agent: str | None = None
    input_data: dict | None = None
    depends_on: list[str] = Field(default_factory=list)


class PlanRevisionResponse(BaseModel):
    """Result of a plan revision."""

    plan_id: str
    new_version: int
    tasks_added: list[str]
    tasks_removed: list[str]
    reasoning: str


# ---- Decision schemas ----

class PlanDecisionResponse(BaseModel):
    """API response for a plan decision."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    plan_id: str
    decision_type: str
    description: str
    decided_by: str
    reasoning: str | None
    plan_version_before: int
    plan_version_after: int
    created_at: str
```

---

### Step 4: Plan Repository

**File**: `modules/backend/repositories/plan.py` (NEW)

Repository with standard CRUD plus the critical ready-task query and DAG validation:

```python
"""
Plan Repository.

Provides standard CRUD plus plan-specific queries: ready-task discovery,
DAG validation, task lookup by plan, and incomplete task listing.
"""

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.backend.core.logging import get_logger
from modules.backend.models.plan import (
    Plan,
    PlanDecision,
    PlanTask,
    TaskAttempt,
    TaskDependency,
    TaskStatus,
)
from modules.backend.repositories.base import BaseRepository

logger = get_logger(__name__)


class PlanRepository(BaseRepository[Plan]):
    """Plan repository with DAG-specific queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Plan, session)

    async def get_with_tasks(self, plan_id: str) -> Plan | None:
        """Get a plan with all tasks eagerly loaded."""
        stmt = (
            select(Plan)
            .options(selectinload(Plan.tasks))
            .where(Plan.id == plan_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_session(self, session_id: str) -> list[Plan]:
        """Get all plans for a session."""
        stmt = (
            select(Plan)
            .where(Plan.session_id == session_id)
            .order_by(Plan.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class PlanTaskRepository(BaseRepository[PlanTask]):
    """Task repository with ready-task query."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PlanTask, session)

    async def get_ready_tasks(self, plan_id: str) -> list[PlanTask]:
        """Find tasks ready to execute: all dependencies satisfied.

        A task is ready when:
        1. Its status is 'pending'
        2. All its 'completion' dependencies have status 'completed'
        3. All its 'data' dependencies have status in ('completed', 'failed')

        This is the critical DAG traversal query from doc 46.
        """
        # Subquery: find tasks that have unsatisfied completion dependencies
        unsatisfied_completion = (
            select(TaskDependency.task_id)
            .join(
                PlanTask,
                PlanTask.id == TaskDependency.depends_on_task_id,
            )
            .where(
                and_(
                    TaskDependency.dependency_type == "completion",
                    PlanTask.status != TaskStatus.COMPLETED,
                ),
            )
        )

        # Subquery: find tasks that have unsatisfied data dependencies
        unsatisfied_data = (
            select(TaskDependency.task_id)
            .join(
                PlanTask,
                PlanTask.id == TaskDependency.depends_on_task_id,
            )
            .where(
                and_(
                    TaskDependency.dependency_type == "data",
                    PlanTask.status.not_in([
                        TaskStatus.COMPLETED,
                        TaskStatus.FAILED,
                    ]),
                ),
            )
        )

        stmt = (
            select(PlanTask)
            .where(
                and_(
                    PlanTask.plan_id == plan_id,
                    PlanTask.status == TaskStatus.PENDING,
                    PlanTask.id.not_in(unsatisfied_completion),
                    PlanTask.id.not_in(unsatisfied_data),
                ),
            )
            .order_by(PlanTask.sort_order)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_plan(self, plan_id: str) -> list[PlanTask]:
        """Get all tasks for a plan, ordered by sort_order."""
        stmt = (
            select(PlanTask)
            .where(PlanTask.plan_id == plan_id)
            .order_by(PlanTask.sort_order)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_incomplete_tasks(self, plan_id: str) -> list[PlanTask]:
        """Get tasks that are not yet completed or skipped."""
        stmt = (
            select(PlanTask)
            .where(
                and_(
                    PlanTask.plan_id == plan_id,
                    PlanTask.status.not_in([
                        TaskStatus.COMPLETED,
                        TaskStatus.SKIPPED,
                        TaskStatus.REPLACED,
                    ]),
                ),
            )
            .order_by(PlanTask.sort_order)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, plan_id: str) -> dict[str, int]:
        """Count tasks grouped by status for progress reporting."""
        stmt = (
            select(PlanTask.status, func.count())
            .where(PlanTask.plan_id == plan_id)
            .group_by(PlanTask.status)
        )
        result = await self.session.execute(stmt)
        return {status: count for status, count in result.all()}


class TaskDependencyRepository(BaseRepository[TaskDependency]):
    """Task dependency repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TaskDependency, session)

    async def get_dependencies(self, task_id: str) -> list[TaskDependency]:
        """Get all dependencies for a task."""
        stmt = (
            select(TaskDependency)
            .where(TaskDependency.task_id == task_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def validate_no_cycles(self, plan_id: str) -> bool:
        """Validate that the task DAG has no cycles.

        Uses Kahn's algorithm (topological sort) — if we can sort all
        tasks, there are no cycles.
        Returns True if DAG is valid (no cycles), False otherwise.
        """
        # Get all tasks and dependencies for this plan
        tasks = await self.session.execute(
            select(PlanTask.id).where(PlanTask.plan_id == plan_id)
        )
        task_ids = {row[0] for row in tasks.all()}

        if not task_ids:
            return True

        deps = await self.session.execute(
            select(TaskDependency.task_id, TaskDependency.depends_on_task_id)
            .join(PlanTask, PlanTask.id == TaskDependency.task_id)
            .where(PlanTask.plan_id == plan_id)
        )

        # Build adjacency list
        graph: dict[str, set[str]] = {tid: set() for tid in task_ids}
        in_degree: dict[str, int] = {tid: 0 for tid in task_ids}

        for task_id, dep_id in deps.all():
            graph.setdefault(dep_id, set()).add(task_id)
            in_degree[task_id] = in_degree.get(task_id, 0) + 1

        # Kahn's algorithm for topological sort
        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        sorted_count = 0

        while queue:
            node = queue.pop(0)
            sorted_count += 1
            for neighbor in graph.get(node, set()):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return sorted_count == len(task_ids)


class TaskAttemptRepository(BaseRepository[TaskAttempt]):
    """Task attempt repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TaskAttempt, session)

    async def get_by_task(self, task_id: str) -> list[TaskAttempt]:
        """Get all attempts for a task, ordered by attempt number."""
        stmt = (
            select(TaskAttempt)
            .where(TaskAttempt.task_id == task_id)
            .order_by(TaskAttempt.attempt_number)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_attempt(self, task_id: str) -> TaskAttempt | None:
        """Get the most recent attempt for a task."""
        stmt = (
            select(TaskAttempt)
            .where(TaskAttempt.task_id == task_id)
            .order_by(TaskAttempt.attempt_number.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class PlanDecisionRepository(BaseRepository[PlanDecision]):
    """Plan decision repository."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(PlanDecision, session)

    async def get_by_plan(self, plan_id: str) -> list[PlanDecision]:
        """Get all decisions for a plan, ordered by creation time."""
        stmt = (
            select(PlanDecision)
            .where(PlanDecision.plan_id == plan_id)
            .order_by(PlanDecision.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
```

**Key implementation**: The `get_ready_tasks` query is the heart of the DAG execution engine. It uses NOT IN subqueries to find pending tasks with all dependencies satisfied. The two dependency types (`completion` and `data`) are handled separately — `data` dependencies are satisfied by either `completed` or `failed` status.

---

### Step 5: Plan Service

**File**: `modules/backend/services/plan.py` (NEW)

Service with plan lifecycle, task execution flow, failure handling, and decision logging:

```python
"""
Plan Service.

Business logic for plan lifecycle: creation with DAG validation,
task promotion (pending → ready), failure handling (retry → revise → escalate),
plan revision, and decision audit logging.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now
from modules.backend.models.plan import (
    DecisionType,
    Plan,
    PlanDecision,
    PlanStatus,
    PlanTask,
    TaskAttempt,
    TaskDependency,
    TaskStatus,
    VALID_TASK_TRANSITIONS,
)
from modules.backend.repositories.plan import (
    PlanDecisionRepository,
    PlanRepository,
    PlanTaskRepository,
    TaskAttemptRepository,
    TaskDependencyRepository,
)
from modules.backend.services.base import BaseService

logger = get_logger(__name__)


class PlanService(BaseService):
    """Plan lifecycle management with DAG traversal and failure handling.

    Accepts an optional event_bus for publishing plan lifecycle events (P5).
    Event publishing is non-critical: failures are logged and swallowed.
    """

    def __init__(
        self,
        session: AsyncSession,
        event_bus: Any | None = None,
    ) -> None:
        super().__init__(session)
        self._plan_repo = PlanRepository(session)
        self._task_repo = PlanTaskRepository(session)
        self._dep_repo = TaskDependencyRepository(session)
        self._attempt_repo = TaskAttemptRepository(session)
        self._decision_repo = PlanDecisionRepository(session)
        self._event_bus = event_bus

    async def _publish_event(self, event: Any) -> None:
        """Publish an event to the session event bus (best-effort).

        Event publishing is non-critical — log and continue on failure.
        """
        if self._event_bus is None:
            return
        try:
            await self._event_bus.publish(event)
        except Exception:
            logger.warning(
                "Failed to publish plan event",
                extra={"event_type": getattr(event, "event_type", "unknown")},
            )

    # ---- Plan lifecycle ----

    async def create_plan(
        self,
        session_id: str,
        goal: str,
        tasks: list[dict[str, Any]] | None = None,
    ) -> Plan:
        """Create a new plan with optional initial tasks.

        If tasks are provided, validates the DAG has no cycles.
        Logs a plan_created decision.
        """
        async def _create() -> Plan:
            plan = Plan(session_id=session_id, goal=goal)
            self._session.add(plan)
            await self._session.flush()
            await self._session.refresh(plan)

            if tasks:
                task_id_map: dict[int, str] = {}

                # Create tasks first
                for i, task_data in enumerate(tasks):
                    task = PlanTask(
                        plan_id=plan.id,
                        name=task_data["name"],
                        description=task_data.get("description"),
                        assigned_agent=task_data.get("assigned_agent"),
                        assigned_model=task_data.get("assigned_model"),
                        input_data=task_data.get("input_data"),
                        max_retries=task_data.get("max_retries", 3),
                        sort_order=task_data.get("sort_order", i),
                    )
                    self._session.add(task)
                    await self._session.flush()
                    await self._session.refresh(task)
                    task_id_map[i] = task.id

                # Create dependencies (referenced by task index)
                for i, task_data in enumerate(tasks):
                    for dep in task_data.get("dependencies", []):
                        dep_index = dep.get("depends_on_index")
                        if dep_index is not None and dep_index in task_id_map:
                            dependency = TaskDependency(
                                task_id=task_id_map[i],
                                depends_on_task_id=task_id_map[dep_index],
                                dependency_type=dep.get("type", "completion"),
                            )
                            self._session.add(dependency)

                await self._session.flush()

                # Validate DAG has no cycles
                is_valid = await self._dep_repo.validate_no_cycles(plan.id)
                if not is_valid:
                    raise ValueError(
                        "Plan tasks contain a cycle — DAG validation failed"
                    )

            # Log decision
            await self._log_decision(
                plan_id=plan.id,
                decision_type=DecisionType.PLAN_CREATED,
                description=f"Plan created with goal: {goal[:200]}",
                decided_by="coordinator",
                version_before=0,
                version_after=1,
            )

            # Publish event (P5)
            await self._publish_event(PlanCreatedEvent(
                plan_id=plan.id,
                goal=goal,
                task_count=len(tasks) if tasks else 0,
            ))

            return plan

        return await self._execute_db_operation("create_plan", _create)

    async def get_plan(self, plan_id: str) -> Plan | None:
        """Get a plan by ID."""
        return await self._plan_repo.get(plan_id)

    async def get_plan_detail(self, plan_id: str) -> Plan | None:
        """Get a plan with tasks eagerly loaded."""
        return await self._plan_repo.get_with_tasks(plan_id)

    async def get_plans_for_session(self, session_id: str) -> list[Plan]:
        """Get all plans for a session."""
        return await self._plan_repo.get_by_session(session_id)

    async def get_plan_status(self, plan_id: str) -> dict[str, Any]:
        """Get plan progress summary."""
        plan = await self._plan_repo.get(plan_id)
        if not plan:
            raise KeyError(f"Plan '{plan_id}' not found")

        counts = await self._task_repo.count_by_status(plan_id)
        total = sum(counts.values())
        completed = counts.get(TaskStatus.COMPLETED, 0)

        return {
            "plan_id": plan.id,
            "goal": plan.goal,
            "status": plan.status,
            "version": plan.version,
            "total_tasks": total,
            "pending_tasks": counts.get(TaskStatus.PENDING, 0),
            "ready_tasks": counts.get(TaskStatus.READY, 0),
            "in_progress_tasks": counts.get(TaskStatus.IN_PROGRESS, 0),
            "completed_tasks": completed,
            "failed_tasks": counts.get(TaskStatus.FAILED, 0),
            "waiting_tasks": (
                counts.get(TaskStatus.WAITING_FOR_INPUT, 0)
                + counts.get(TaskStatus.WAITING_FOR_APPROVAL, 0)
            ),
            "progress_pct": round(
                (completed / total * 100) if total > 0 else 0, 1
            ),
        }

    # ---- Task lifecycle ----

    async def promote_ready_tasks(self, plan_id: str) -> list[PlanTask]:
        """Find pending tasks with all deps satisfied and promote to 'ready'.

        Called after each task completion to advance the DAG.
        Returns the list of newly ready tasks.
        """
        ready = await self._task_repo.get_ready_tasks(plan_id)
        for task in ready:
            task.status = TaskStatus.READY
        await self._session.flush()

        if ready:
            logger.info(
                "Tasks promoted to ready",
                extra={
                    "plan_id": plan_id,
                    "task_count": len(ready),
                    "tasks": [t.name for t in ready],
                },
            )

        return ready

    async def start_task(self, task_id: str) -> PlanTask:
        """Mark a task as in_progress. Creates a new attempt record."""
        task = await self._task_repo.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")

        self._validate_transition(task, TaskStatus.IN_PROGRESS)
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = utc_now().isoformat()

        # Create attempt record
        attempt = TaskAttempt(
            task_id=task.id,
            attempt_number=task.retry_count + 1,
            status="started",
            started_at=utc_now().isoformat(),
        )
        self._session.add(attempt)
        await self._session.flush()

        # Publish event (P5)
        await self._publish_event(PlanTaskStartedEvent(
            plan_id=task.plan_id,
            task_id=task.id,
            task_name=task.name,
            assigned_agent=task.assigned_agent,
        ))

        return task

    async def complete_task(
        self,
        task_id: str,
        output_data: dict | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        model: str | None = None,
    ) -> PlanTask:
        """Mark a task as completed with result data."""
        task = await self._task_repo.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")

        self._validate_transition(task, TaskStatus.COMPLETED)
        task.status = TaskStatus.COMPLETED
        task.output_data = output_data
        task.completed_at = utc_now().isoformat()

        # Update latest attempt
        attempt = await self._attempt_repo.get_latest_attempt(task_id)
        if attempt:
            attempt.status = "completed"
            attempt.completed_at = utc_now().isoformat()
            attempt.input_tokens = input_tokens
            attempt.output_tokens = output_tokens
            attempt.cost_usd = cost_usd
            attempt.model = model

        await self._session.flush()

        # Publish event (P5)
        await self._publish_event(PlanTaskCompletedEvent(
            plan_id=task.plan_id,
            task_id=task.id,
            task_name=task.name,
        ))

        # Check if plan is complete
        await self._check_plan_completion(task.plan_id)

        return task

    async def fail_task(
        self,
        task_id: str,
        error: str,
        error_data: dict | None = None,
    ) -> PlanTask:
        """Mark a task as failed."""
        task = await self._task_repo.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")

        self._validate_transition(task, TaskStatus.FAILED)
        task.status = TaskStatus.FAILED
        task.error_data = error_data or {"message": error}

        # Update latest attempt
        attempt = await self._attempt_repo.get_latest_attempt(task_id)
        if attempt:
            attempt.status = "failed"
            attempt.completed_at = utc_now().isoformat()
            attempt.error_message = error

        await self._session.flush()

        # Publish event (P5)
        await self._publish_event(PlanTaskFailedEvent(
            plan_id=task.plan_id,
            task_id=task.id,
            task_name=task.name,
            error=error,
        ))

        return task

    # ---- Failure handling ----

    async def handle_task_failure(
        self,
        plan_id: str,
        task_id: str,
        error: str,
    ) -> str:
        """Handle a failed task: retry, then report for revision.

        Returns the action taken: 'retried', 'needs_revision',
        'needs_escalation'.
        """
        task = await self._task_repo.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")

        if task.retry_count < task.max_retries:
            # Retry with same parameters
            task.retry_count += 1
            task.status = TaskStatus.READY
            task.error_data = None

            await self._log_decision(
                plan_id=plan_id,
                decision_type=DecisionType.TASK_RETRIED,
                description=(
                    f"Retrying task '{task.name}' "
                    f"(attempt {task.retry_count}/{task.max_retries})"
                ),
                decided_by="coordinator",
                reasoning=f"Task failed with: {error[:500]}",
            )

            await self._session.flush()
            return "retried"

        # Max retries exhausted — check for no-progress pattern
        attempts = await self._attempt_repo.get_by_task(task_id)
        errors = [a.error_message for a in attempts if a.error_message]

        if len(errors) >= 3 and len(set(errors[-3:])) == 1:
            # Same error 3 times — no progress, needs escalation
            await self._log_decision(
                plan_id=plan_id,
                decision_type=DecisionType.TASK_ESCALATED,
                description=(
                    f"Task '{task.name}' failed {len(errors)} times "
                    f"with same error — escalating"
                ),
                decided_by="coordinator",
                reasoning=f"No-progress detected. Error: {errors[-1][:500]}",
            )
            await self._session.flush()
            return "needs_escalation"

        # Needs plan revision — PM agent should be called to revise
        return "needs_revision"

    # ---- Plan revision ----

    async def revise_plan(
        self,
        plan_id: str,
        tasks_to_add: list[dict[str, Any]] | None = None,
        tasks_to_remove: list[str] | None = None,
        reasoning: str = "",
    ) -> Plan:
        """Revise a plan: add/remove tasks, bump version.

        Preserves completed work. Only modifies pending/ready/failed tasks.
        """
        plan = await self._plan_repo.get(plan_id)
        if not plan:
            raise KeyError(f"Plan '{plan_id}' not found")

        version_before = plan.version
        plan.version += 1

        # Remove tasks (only non-completed)
        removed_names = []
        for task_id in (tasks_to_remove or []):
            task = await self._task_repo.get(task_id)
            if task and task.status not in (
                TaskStatus.COMPLETED,
                TaskStatus.IN_PROGRESS,
            ):
                task.status = TaskStatus.SKIPPED
                removed_names.append(task.name)

        # Add new tasks
        added_names = []
        for task_data in (tasks_to_add or []):
            task = PlanTask(
                plan_id=plan.id,
                name=task_data["name"],
                description=task_data.get("description"),
                assigned_agent=task_data.get("assigned_agent"),
                input_data=task_data.get("input_data"),
                sort_order=task_data.get("sort_order", 0),
            )
            self._session.add(task)
            added_names.append(task.name)

        await self._log_decision(
            plan_id=plan_id,
            decision_type=DecisionType.PLAN_REVISED,
            description=(
                f"Plan revised: added {len(added_names)} tasks, "
                f"removed {len(removed_names)} tasks"
            ),
            decided_by="coordinator",
            reasoning=reasoning,
            version_before=version_before,
            version_after=plan.version,
        )

        await self._session.flush()

        # Publish event (P5)
        await self._publish_event(PlanRevisedEvent(
            plan_id=plan.id,
            new_version=plan.version,
            tasks_added=len(added_names),
            tasks_removed=len(removed_names),
            reasoning=reasoning,
        ))

        return plan

    # ---- Internal helpers ----

    def _validate_transition(
        self, task: PlanTask, new_status: TaskStatus
    ) -> None:
        """Validate a task status transition."""
        current = TaskStatus(task.status)
        valid = VALID_TASK_TRANSITIONS.get(current, set())
        if new_status not in valid:
            raise ValueError(
                f"Invalid task transition: {current.value} → "
                f"{new_status.value}. Valid: "
                f"{', '.join(s.value for s in valid) or 'none (terminal)'}"
            )

    async def _check_plan_completion(self, plan_id: str) -> None:
        """Check if all tasks are completed and mark plan as completed."""
        incomplete = await self._task_repo.get_incomplete_tasks(plan_id)
        if not incomplete:
            plan = await self._plan_repo.get(plan_id)
            if plan:
                plan.status = PlanStatus.COMPLETED
                await self._session.flush()
                logger.info("Plan completed", extra={"plan_id": plan_id})

    async def _log_decision(
        self,
        plan_id: str,
        decision_type: DecisionType,
        description: str,
        decided_by: str,
        reasoning: str | None = None,
        version_before: int | None = None,
        version_after: int | None = None,
    ) -> None:
        """Log a plan decision to the audit trail."""
        plan = await self._plan_repo.get(plan_id)
        current_version = plan.version if plan else 1

        decision = PlanDecision(
            plan_id=plan_id,
            decision_type=decision_type,
            description=description,
            decided_by=decided_by,
            reasoning=reasoning,
            plan_version_before=version_before or current_version,
            plan_version_after=version_after or current_version,
            created_at=utc_now().isoformat(),
        )
        self._session.add(decision)
        await self._session.flush()
```

---

### Step 6: Plan API Endpoints

**File**: `modules/backend/api/v1/endpoints/plans.py` (NEW)

REST endpoints for plan management:

```python
"""
Plan Management Endpoints.

REST API for plan CRUD, task status, ready-task queries, and decisions.
Plans are session-scoped — all plan operations require a valid session.
"""

from fastapi import APIRouter

from modules.backend.core.dependencies import DbSession, RequestId
from modules.backend.core.logging import get_logger
from modules.backend.schemas.base import ApiResponse
from modules.backend.schemas.plan import (
    PlanCreate,
    PlanDetailResponse,
    PlanResponse,
    PlanStatusSummary,
    PlanTaskResponse,
    PlanDecisionResponse,
)

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/",
    response_model=ApiResponse[PlanResponse],
    summary="Create a plan",
    description="Create a new plan with optional initial tasks.",
)
async def create_plan(
    session_id: str,
    data: PlanCreate,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[PlanResponse]:
    """Create a plan within a session."""
    from modules.backend.services.plan import PlanService

    service = PlanService(db)
    plan = await service.create_plan(
        session_id=session_id,
        goal=data.goal,
        tasks=[t.model_dump() for t in data.tasks] if data.tasks else None,
    )
    return ApiResponse(data=PlanResponse.model_validate(plan))


@router.get(
    "/{plan_id}",
    response_model=ApiResponse[PlanDetailResponse],
    summary="Get plan details",
)
async def get_plan(
    plan_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[PlanDetailResponse]:
    """Get plan details with tasks."""
    from modules.backend.services.plan import PlanService

    service = PlanService(db)
    plan = await service.get_plan_detail(plan_id)
    if not plan:
        from modules.backend.core.exceptions import NotFoundError
        raise NotFoundError(f"Plan '{plan_id}' not found")
    return ApiResponse(data=PlanDetailResponse.model_validate(plan))


@router.get(
    "/{plan_id}/status",
    response_model=ApiResponse[PlanStatusSummary],
    summary="Get plan progress",
)
async def get_plan_status(
    plan_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[PlanStatusSummary]:
    """Get plan progress summary with task counts."""
    from modules.backend.services.plan import PlanService

    service = PlanService(db)
    status = await service.get_plan_status(plan_id)
    return ApiResponse(data=PlanStatusSummary(**status))


@router.get(
    "/{plan_id}/tasks/ready",
    response_model=ApiResponse[list[PlanTaskResponse]],
    summary="Get ready tasks",
)
async def get_ready_tasks(
    plan_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[list[PlanTaskResponse]]:
    """Get tasks ready for execution (all dependencies satisfied)."""
    from modules.backend.repositories.plan import PlanTaskRepository

    repo = PlanTaskRepository(db)
    tasks = await repo.get_ready_tasks(plan_id)
    return ApiResponse(data=[PlanTaskResponse.model_validate(t) for t in tasks])


@router.get(
    "/{plan_id}/decisions",
    response_model=ApiResponse[list[PlanDecisionResponse]],
    summary="Get plan decisions",
)
async def get_plan_decisions(
    plan_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[list[PlanDecisionResponse]]:
    """Get decision audit trail for a plan."""
    from modules.backend.repositories.plan import PlanDecisionRepository

    repo = PlanDecisionRepository(db)
    decisions = await repo.get_by_plan(plan_id)
    return ApiResponse(
        data=[PlanDecisionResponse.model_validate(d) for d in decisions]
    )
```

**File**: `modules/backend/api/v1/__init__.py` — Register the plans router:

```python
from modules.backend.api.v1.endpoints import plans
api_v1_router.include_router(plans.router, prefix="/plans", tags=["plans"])
```

---

### Step 7: Plan Tools for PM Agent

**File**: `modules/backend/agents/tools/plan.py` (NEW)

Shared tool implementations — pure functions for the PM agent to create and manage plans:

```python
"""
Shared plan tool implementations.

Pure functions with no PydanticAI dependency. Used by horizontal agents
to create, query, and revise plans. The PlanService is injected by the
calling agent — these functions never create service instances directly.
"""

from typing import Any

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


async def create_plan(
    session_id: str,
    goal: str,
    tasks: list[dict[str, Any]],
    plan_service: Any,
) -> dict[str, Any]:
    """Create a new plan with tasks.

    Args:
        session_id: Session this plan belongs to.
        goal: The goal this plan achieves.
        tasks: List of task dicts with 'name', 'description',
               'assigned_agent', 'dependencies'.
        plan_service: PlanService instance (injected).

    Returns:
        Dict with plan_id, goal, task_count.
    """
    plan = await plan_service.create_plan(
        session_id=session_id,
        goal=goal,
        tasks=tasks,
    )

    logger.info(
        "Plan created via tool",
        extra={
            "plan_id": plan.id,
            "goal": goal[:200],
            "task_count": len(tasks),
        },
    )

    return {
        "plan_id": plan.id,
        "goal": plan.goal,
        "task_count": len(tasks),
        "version": plan.version,
    }


async def get_plan_status(
    plan_id: str,
    plan_service: Any,
) -> dict[str, Any]:
    """Get plan progress summary.

    Args:
        plan_id: Plan to check.
        plan_service: PlanService instance (injected).

    Returns:
        Dict with progress summary.
    """
    return await plan_service.get_plan_status(plan_id)


async def revise_plan(
    plan_id: str,
    tasks_to_add: list[dict[str, Any]] | None,
    tasks_to_remove: list[str] | None,
    reasoning: str,
    plan_service: Any,
) -> dict[str, Any]:
    """Revise a plan: add/remove tasks.

    Args:
        plan_id: Plan to revise.
        tasks_to_add: New tasks to add.
        tasks_to_remove: Task IDs to remove.
        reasoning: Why the revision is needed.
        plan_service: PlanService instance (injected).

    Returns:
        Dict with new version and changes.
    """
    plan = await plan_service.revise_plan(
        plan_id=plan_id,
        tasks_to_add=tasks_to_add,
        tasks_to_remove=tasks_to_remove,
        reasoning=reasoning,
    )

    return {
        "plan_id": plan.id,
        "new_version": plan.version,
        "reasoning": reasoning,
    }
```

---

### Step 8: Update PM Agent with Plan Tools

**File**: `modules/backend/agents/horizontal/pm/agent.py`

Add plan tool wrappers to the PM agent's `create_agent()` function. Add after the delegation and filesystem tool wrappers:

```python
    # ---- Plan tools (thin wrappers) ----

    @agent.tool
    async def create_plan_tool(
        ctx: RunContext[HorizontalAgentDeps],
        goal: str,
        tasks: list[dict],
    ) -> dict:
        """Create a plan with tasks and dependencies."""
        from modules.backend.agents.tools import plan as plan_tools
        return await plan_tools.create_plan(
            session_id=ctx.deps.session_id,
            goal=goal,
            tasks=tasks,
            plan_service=ctx.deps.plan_service,
        )

    @agent.tool
    async def get_plan_status_tool(
        ctx: RunContext[HorizontalAgentDeps],
        plan_id: str,
    ) -> dict:
        """Check plan progress: task counts, completion percentage."""
        from modules.backend.agents.tools import plan as plan_tools
        return await plan_tools.get_plan_status(
            plan_id=plan_id,
            plan_service=ctx.deps.plan_service,
        )

    @agent.tool
    async def revise_plan_tool(
        ctx: RunContext[HorizontalAgentDeps],
        plan_id: str,
        tasks_to_add: list[dict] | None,
        tasks_to_remove: list[str] | None,
        reasoning: str,
    ) -> dict:
        """Revise a plan after a failure: add/remove tasks."""
        from modules.backend.agents.tools import plan as plan_tools
        return await plan_tools.revise_plan(
            plan_id=plan_id,
            tasks_to_add=tasks_to_add,
            tasks_to_remove=tasks_to_remove,
            reasoning=reasoning,
            plan_service=ctx.deps.plan_service,
        )
```

**File**: `modules/backend/agents/deps/base.py` — Add `plan_service` to `HorizontalAgentDeps`:

```python
@dataclass
class HorizontalAgentDeps(BaseAgentDeps):
    """Horizontal (supervisory) agent deps — adds delegation and plan authority."""

    allowed_agents: set[str] = field(default_factory=set)
    max_delegation_depth: int = 0
    delegation_depth: int = 0
    coordinator: Any = None
    plan_service: Any = None
```

**Note**: `session_id` should already be on `BaseAgentDeps` from Plan 11. Only `plan_service` is added here.

**File**: `config/agents/horizontal/pm/agent.yaml` — Update tools list to include plan tools:

```yaml
tools:
  - delegation.invoke_agent
  - delegation.list_agents
  - plan.create_plan
  - plan.get_status
  - plan.revise_plan
  - filesystem.read_file
  - filesystem.list_files
```

---

### Step 9: Alembic Migration

Generate and review the migration:

```bash
alembic revision --autogenerate -m "add plan management tables"
```

The migration should create five tables:
1. `plans` — with `session_id` FK to `sessions`
2. `plan_tasks` — with `plan_id` FK to `plans`
3. `task_dependencies` — with FKs to `plan_tasks`, unique constraint
4. `task_attempts` — with FK to `plan_tasks`, unique constraint
5. `plan_decisions` — with FK to `plans`

Plus indexes on all foreign key columns.

**Verification**: `alembic upgrade head` then `alembic check` — no pending changes.

---

### Step 10: Plan Event Types

Extend the event types from Phase 1 with plan-specific events:

```python
class PlanCreatedEvent(SessionEvent):
    """Emitted when a new plan is created."""
    event_type: str = "plan.created"
    plan_id: str
    goal: str
    task_count: int


class PlanTaskStartedEvent(SessionEvent):
    """Emitted when a task begins execution."""
    event_type: str = "plan.task.started"
    plan_id: str
    task_id: str
    task_name: str
    assigned_agent: str | None


class PlanTaskCompletedEvent(SessionEvent):
    """Emitted when a task completes successfully."""
    event_type: str = "plan.task.completed"
    plan_id: str
    task_id: str
    task_name: str


class PlanTaskFailedEvent(SessionEvent):
    """Emitted when a task fails."""
    event_type: str = "plan.task.failed"
    plan_id: str
    task_id: str
    task_name: str
    error: str


class PlanRevisedEvent(SessionEvent):
    """Emitted when a plan is revised."""
    event_type: str = "plan.revised"
    plan_id: str
    new_version: int
    tasks_added: int
    tasks_removed: int
    reasoning: str
```

Add these to the event type registry from Phase 1. These events are already wired into the `PlanService` methods above via `_publish_event()` (try/except, log, continue — event publishing is non-critical). The `PlanService.__init__` accepts an optional `event_bus` parameter; callers that don't provide one get silent no-ops.

---

### Step 11: Tests

**File**: `tests/unit/backend/services/test_plan.py` (NEW)

```python
"""
Plan service tests.

Tests plan lifecycle, DAG traversal, ready-task discovery,
failure handling, and decision audit logging.
"""

import pytest

from modules.backend.models.plan import (
    PlanStatus,
    TaskStatus,
    VALID_TASK_TRANSITIONS,
)


class TestPlanCreation:
    """Tests for plan creation and DAG validation."""

    @pytest.mark.asyncio
    async def test_create_empty_plan(self, db_session):
        from modules.backend.services.plan import PlanService

        service = PlanService(db_session)
        plan = await service.create_plan(
            session_id="test-session-id",
            goal="Test goal",
        )

        assert plan.goal == "Test goal"
        assert plan.status == PlanStatus.ACTIVE
        assert plan.version == 1

    @pytest.mark.asyncio
    async def test_create_plan_with_tasks(self, db_session):
        from modules.backend.services.plan import PlanService

        service = PlanService(db_session)
        plan = await service.create_plan(
            session_id="test-session-id",
            goal="Refactor auth",
            tasks=[
                {"name": "Review code", "assigned_agent": "code.qa.agent"},
                {
                    "name": "Implement changes",
                    "assigned_agent": "code.coder.agent",
                    "dependencies": [
                        {"depends_on_index": 0, "type": "completion"},
                    ],
                },
            ],
        )

        assert plan.goal == "Refactor auth"

    @pytest.mark.asyncio
    async def test_reject_cyclic_dag(self, db_session):
        from modules.backend.services.plan import PlanService

        service = PlanService(db_session)
        with pytest.raises(ValueError, match="cycle"):
            await service.create_plan(
                session_id="test-session-id",
                goal="Cyclic plan",
                tasks=[
                    {
                        "name": "Task A",
                        "dependencies": [
                            {"depends_on_index": 1, "type": "completion"},
                        ],
                    },
                    {
                        "name": "Task B",
                        "dependencies": [
                            {"depends_on_index": 0, "type": "completion"},
                        ],
                    },
                ],
            )


class TestReadyTaskQuery:
    """Tests for the ready-task DAG traversal query."""

    @pytest.mark.asyncio
    async def test_root_tasks_are_ready(self, db_session):
        """Tasks with no dependencies should be promotable to ready."""
        from modules.backend.services.plan import PlanService

        service = PlanService(db_session)
        plan = await service.create_plan(
            session_id="test-session-id",
            goal="Test",
            tasks=[
                {"name": "Root task 1"},
                {"name": "Root task 2"},
            ],
        )

        ready = await service.promote_ready_tasks(plan.id)
        assert len(ready) == 2

    @pytest.mark.asyncio
    async def test_dependent_task_not_ready_until_dep_completes(
        self, db_session
    ):
        """A task with unmet dependencies should not be ready."""
        from modules.backend.services.plan import PlanService

        service = PlanService(db_session)
        plan = await service.create_plan(
            session_id="test-session-id",
            goal="Sequential",
            tasks=[
                {"name": "Step 1"},
                {
                    "name": "Step 2",
                    "dependencies": [
                        {"depends_on_index": 0, "type": "completion"},
                    ],
                },
            ],
        )

        # Only step 1 should be ready initially
        ready = await service.promote_ready_tasks(plan.id)
        assert len(ready) == 1
        assert ready[0].name == "Step 1"


class TestTaskStateMachine:
    """Tests for task status transitions."""

    def test_valid_transitions(self):
        assert TaskStatus.READY in VALID_TASK_TRANSITIONS[TaskStatus.PENDING]
        assert TaskStatus.IN_PROGRESS in VALID_TASK_TRANSITIONS[TaskStatus.READY]
        assert TaskStatus.COMPLETED in VALID_TASK_TRANSITIONS[TaskStatus.IN_PROGRESS]
        assert TaskStatus.FAILED in VALID_TASK_TRANSITIONS[TaskStatus.IN_PROGRESS]

    def test_terminal_states_have_no_transitions(self):
        assert VALID_TASK_TRANSITIONS[TaskStatus.COMPLETED] == set()
        assert VALID_TASK_TRANSITIONS[TaskStatus.SKIPPED] == set()
        assert VALID_TASK_TRANSITIONS[TaskStatus.REPLACED] == set()


class TestFailureHandling:
    """Tests for retry and escalation logic."""

    @pytest.mark.asyncio
    async def test_retry_on_first_failure(self, db_session):
        from modules.backend.services.plan import PlanService

        service = PlanService(db_session)
        plan = await service.create_plan(
            session_id="test-session-id",
            goal="Test retry",
            tasks=[{"name": "Flaky task", "max_retries": 3}],
        )

        # Promote and start task
        await service.promote_ready_tasks(plan.id)
        tasks = await service._task_repo.get_by_plan(plan.id)
        task = tasks[0]
        await service.start_task(task.id)
        await service.fail_task(task.id, "transient error")

        # Handle failure — should retry
        action = await service.handle_task_failure(
            plan.id, task.id, "transient error"
        )
        assert action == "retried"


class TestPlanDecisions:
    """Tests for decision audit trail."""

    @pytest.mark.asyncio
    async def test_plan_creation_logged(self, db_session):
        from modules.backend.services.plan import PlanService
        from modules.backend.repositories.plan import PlanDecisionRepository

        service = PlanService(db_session)
        plan = await service.create_plan(
            session_id="test-session-id",
            goal="Audit trail test",
        )

        repo = PlanDecisionRepository(db_session)
        decisions = await repo.get_by_plan(plan.id)
        assert len(decisions) == 1
        assert decisions[0].decision_type == "plan_created"
```

**File**: `tests/unit/backend/repositories/test_plan.py` (NEW)

```python
"""
Plan repository tests.

Tests ready-task SQL query, DAG cycle validation, and status counting.
"""

import pytest

from modules.backend.models.plan import TaskStatus
from modules.backend.repositories.plan import (
    PlanTaskRepository,
    TaskDependencyRepository,
)


class TestCycleDetection:
    """Tests for DAG cycle validation."""

    @pytest.mark.asyncio
    async def test_linear_dag_valid(self, db_session, sample_linear_plan):
        """A → B → C should be valid (no cycles)."""
        repo = TaskDependencyRepository(db_session)
        is_valid = await repo.validate_no_cycles(sample_linear_plan.id)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_empty_plan_valid(self, db_session, sample_empty_plan):
        """A plan with no tasks should be valid."""
        repo = TaskDependencyRepository(db_session)
        is_valid = await repo.validate_no_cycles(sample_empty_plan.id)
        assert is_valid is True


class TestStatusCounting:
    """Tests for task status aggregation."""

    @pytest.mark.asyncio
    async def test_count_by_status(
        self, db_session, sample_plan_with_mixed_statuses
    ):
        repo = PlanTaskRepository(db_session)
        counts = await repo.count_by_status(
            sample_plan_with_mixed_statuses.id
        )
        assert isinstance(counts, dict)
        assert sum(counts.values()) > 0
```

**Note**: Test fixtures (`sample_linear_plan`, `sample_empty_plan`, `sample_plan_with_mixed_statuses`) should be defined in a `conftest.py` that creates plans with tasks in the test database. These fixtures will need the Session model from Plan 11 to exist (FK constraint).

---

### Step 12: Verify and Commit

| # | Task | Command/Notes |
|---|------|---------------|
| 12.1 | Run all existing tests | `python -m pytest tests/ -x -q` — ensure nothing broken |
| 12.2 | Run plan service tests | `python -m pytest tests/unit/backend/services/test_plan.py -v` |
| 12.3 | Run plan repo tests | `python -m pytest tests/unit/backend/repositories/test_plan.py -v` |
| 12.4 | Run full test suite | `python -m pytest tests/ -q` — all green |
| 12.5 | Verify config loading | `python -c "from modules.backend.core.config import get_app_config; print(get_app_config().plans)"` |
| 12.6 | Verify migration | `alembic upgrade head && alembic check` |
| 12.7 | Commit | `git commit -m "Add plan management: mutable DAG with task lifecycle and decision audit"` |

---

## Files Created/Modified Summary

| File | Action | Lines (est.) |
|------|--------|-------------|
| `modules/backend/models/plan.py` | **Created** | ~220 |
| `modules/backend/models/__init__.py` | Modified | +2 |
| `modules/backend/schemas/plan.py` | **Created** | ~160 |
| `modules/backend/repositories/plan.py` | **Created** | ~230 |
| `modules/backend/services/plan.py` | **Created** | ~310 |
| `modules/backend/api/v1/endpoints/plans.py` | **Created** | ~110 |
| `modules/backend/api/v1/__init__.py` | Modified | +2 |
| `modules/backend/agents/tools/plan.py` | **Created** | ~90 |
| `modules/backend/agents/horizontal/pm/agent.py` | Modified | +40 |
| `modules/backend/agents/deps/base.py` | Modified | +2 |
| `config/agents/horizontal/pm/agent.yaml` | Modified | +3 |
| `config/settings/plans.yaml` | **Created** | ~15 |
| `modules/backend/core/config_schema.py` | Modified | +10 |
| `modules/backend/core/config.py` | Modified | +5 |
| `modules/backend/migrations/versions/xxx_plan_tables.py` | **Created** | ~80 |
| Event type definitions (Phase 1 extension) | Modified | +30 |
| `tests/unit/backend/services/test_plan.py` | **Created** | ~120 |
| `tests/unit/backend/repositories/test_plan.py` | **Created** | ~50 |

**Total**: ~1,479 lines across 18 files (9 new, 9 modified)

---

## Anti-Patterns — Do NOT

| Anti-pattern | Why prohibited |
|-------------|---------------|
| Storing plan data in Temporal event history | Temporal owns orchestration state. PostgreSQL owns domain state (plans, tasks, decisions). Temporal Activities read/write PostgreSQL. |
| Replanning from scratch on every failure | Modify remaining tasks. Full replanning loses completed work and context. |
| Agents spinning without progress | Track tool invocations and errors. If the same call repeats 3 times without state change, escalate to a smarter model or human. |
| Plan tools importing coordinator directly | Plan tools are pure functions. The PlanService is injected via deps. |
| Skipping decision logging | Every plan modification must be logged in `plan_decisions`. This is the audit trail. No exceptions. |
| Orphan plans without sessions | Plans always have a `session_id`. No orphan plans. Cost rolls up to the session. |
| Modifying completed tasks during revision | Completed work is preserved. Revision only affects pending/ready/failed tasks. |

---
