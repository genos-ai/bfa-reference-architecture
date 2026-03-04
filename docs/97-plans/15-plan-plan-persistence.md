# Implementation Plan: Plan Persistence & Audit Trail

*Created: 2026-03-04*
*Status: Not Started*
*Phase: 6 of 8 (AI-First Platform Build)*
*Depends on: Phase 1-5 (Event Bus, Sessions, Streaming Mission Control, Mission Control Dispatch Loop, Verification & Quality Gates)*
*Blocked by: Phase 5*

---

## Summary

Build the persistence and audit layer for Mission Control's runtime artifacts. When Mission Control executes a mission (Plan 13) with verification (Plan 14), the results need durable storage for compliance, audit, cost analytics, and historical queries. This plan stores TaskPlans, task execution results, verification outcomes, decision trails, and cost breakdowns in PostgreSQL.

This is NOT a mutable DAG. Mission Control owns runtime execution (Plan 13). This plan owns what gets persisted afterward and how it's queried. The Planning Agent produces a TaskPlan (a frozen JSON structure). Mission Control executes it. This plan records the full execution history: what was planned, what happened, why decisions were made, and how much it cost.

**Dev mode: breaking changes allowed.** This is a new subsystem — no backward-compatibility constraints.

## Context

- Research doc: `docs/98-research/11-bfa-workflow-architecture-specification.md` — Mission Control execution model, TaskPlan, MissionOutcome, verification tiers
- Plan 13: `docs/97-plans/13-plan-mission-control-dispatch.md` — Mission Control dispatch loop, Planning Agent, TaskPlan dataclass, MissionOutcome dataclass
- Plan 14: Verification & Quality Gates — verification outcome structure, failure tiers, retry/re-plan/fail decisions
- Plan 12: `docs/97-plans/12-plan-streaming-mission-control.md` — Streaming Mission Control, agent contracts, cost tracking
- Plan 11: Session model — sessions table, session_messages, cost tracking
- Plan 10: `docs/97-plans/10-plan-event-bus.done.md` — Event bus, session events
- Project principles: `docs/03-principles/01-project-principles.md` — P1 (Infrastructure Before Agents), P6 (Mission Control Is Infrastructure), P12 (Test Against Real Infrastructure)
- Old Plan 14 (Plan Management / Mutable DAG) is superseded. This plan replaces it with a persistence-only focus.

## What Changed from Old Plan 14

The old Plan 14 ("Plan Management — Mutable DAG") combined plan creation, mutable DAG management, task execution flow, and persistence into one plan. The architecture has since evolved:

- **Mission Control dispatch loop (Plan 13)** now owns task execution, retry logic, and the Planning Agent
- **Verification & Quality Gates (Plan 14)** now owns output validation and failure tier classification
- **TaskPlan** is a frozen JSON structure produced by the Planning Agent — not a mutable DAG in PostgreSQL
- **Dependencies** live inside the TaskPlan JSON, not in a separate `task_dependencies` table

What remains for this plan:
- **Persist** the TaskPlan JSON and MissionOutcome after execution
- **Record** each task execution with its verification outcome, tokens, cost, and duration
- **Log** every decision Mission Control made (retry, fail, pass, re-plan) with reasoning
- **Track** individual task attempts for debugging and audit
- **Query** mission history for compliance, cost analytics, and debugging

## What to Build

- `modules/backend/models/mission_record.py` — `MissionRecord`, `TaskExecution`, `TaskAttempt`, `MissionDecision` SQLAlchemy models
- `modules/backend/schemas/mission_record.py` — `MissionRecordResponse`, `TaskExecutionResponse`, `MissionDecisionResponse`, `MissionListResponse` Pydantic schemas
- `modules/backend/repositories/mission_record.py` — `MissionRecordRepository` with cost aggregation queries, status filtering, session lookups
- `modules/backend/services/mission_persistence.py` — `MissionPersistenceService`: `save_mission()`, `save_task_execution()`, `save_attempt()`, `save_decision()`, `get_mission()`, `list_missions()`, `get_mission_cost_breakdown()`
- `modules/backend/api/v1/endpoints/missions.py` — REST: `GET /missions`, `GET /missions/{id}`, `GET /missions/{id}/decisions`, `GET /missions/{id}/cost`
- `config/settings/missions.yaml` — Mission persistence configuration
- `modules/backend/core/config_schema.py` — `MissionsSchema` config schema
- Alembic migration for `mission_records`, `task_executions`, `task_attempts`, `mission_decisions` tables
- Integration hook: `dispatch.py` calls `MissionPersistenceService.save_mission()` after mission completes
- Tests

## Key Design Decisions

- **Four tables, not five.** The old Plan 14 had `plans`, `plan_tasks`, `task_dependencies`, `task_attempts`, `plan_decisions`. The new design has `mission_records`, `task_executions`, `task_attempts`, `mission_decisions`. Dependencies are not a separate table — they live inside the `task_plan_json` JSONB column. This is simpler and avoids the impedance mismatch between the Planning Agent's JSON output and relational normalization.
- **TaskPlan JSON is stored verbatim.** The Planning Agent produces a `TaskPlan` dataclass (Plan 13). We store its JSON representation in `mission_records.task_plan_json`. This preserves the exact plan the agent produced, including dependency graph, agent assignments, and input specifications. No translation to relational tables needed.
- **MissionOutcome JSON is stored verbatim.** The dispatch loop produces a `MissionOutcome` (Plan 13). We store it in `mission_records.mission_outcome_json`. This preserves the complete execution result including all task results, verification outcomes, and cost data.
- **Planning Agent thinking trace.** The Planning Agent's chain-of-thought reasoning is stored as text in `mission_records.planning_thinking_trace`. This is the audit trail for why the plan was shaped the way it was. Optional — only populated when the Planning Agent provides a reasoning trace.
- **Verification outcomes on task executions.** Each `task_executions` row has a `verification_outcome` JSONB column that stores the Tier 1/2 verification result from Plan 14. This answers "did the output pass validation?" per task.
- **Task attempts track retries.** When Mission Control retries a task (failure tier allows it), each attempt is a separate row in `task_attempts`. This shows the full retry history: what failed, what feedback was provided, how many tokens were used per attempt.
- **Decision audit trail.** Every decision Mission Control makes — retry, fail, pass, re-plan — is logged in `mission_decisions` with the decision type, reasoning, and context. This is the compliance layer: you can reconstruct exactly why Mission Control took every action.
- **Cost breakdown per task and per mission.** `task_executions` has `cost_usd` and `token_usage` (JSONB with input/output tokens per model). `mission_records` has `total_cost_usd` aggregated. The `GET /missions/{id}/cost` endpoint returns a full cost breakdown.
- **No PM agent plan tools.** The old Plan 14 had `create_plan()`, `revise_plan()`, `get_plan_status()` tools for the PM agent. These are removed. Mission Control's dispatch loop (Plan 13) drives execution. The Planning Agent produces TaskPlans via its own interface. No tool-based plan mutation.
- **No mutable DAG.** The old design mutated plan tasks in PostgreSQL during execution. The new design treats the TaskPlan as immutable. Mission Control tracks execution state in memory during the dispatch loop. After completion, the full result is persisted. If a re-plan happens, a new TaskPlan is generated and stored as a new mission record (or linked via `parent_mission_id`).
- **String UUIDs** via `UUIDMixin` for consistency with existing codebase.
- **Mission records belong to sessions.** Every mission record has a `session_id` linking it to the session that triggered the mission. A session can have multiple mission records (e.g., re-plans, sequential missions).

## Success Criteria

- [ ] `mission_records` table stores TaskPlan JSON, MissionOutcome JSON, planning thinking trace, total cost, and timing
- [ ] `task_executions` table stores per-task results with verification outcomes, token usage, and cost
- [ ] `task_attempts` table stores per-attempt details for retried tasks
- [ ] `mission_decisions` table stores every Mission Control decision with type and reasoning
- [ ] `MissionPersistenceService.save_mission()` persists a complete mission record from a MissionOutcome
- [ ] `MissionPersistenceService.save_task_execution()` persists individual task results during execution
- [ ] `MissionPersistenceService.save_decision()` logs Mission Control decisions in real time
- [ ] `GET /missions` returns paginated mission list with status filtering
- [ ] `GET /missions/{id}` returns full mission record with TaskPlan and MissionOutcome
- [ ] `GET /missions/{id}/decisions` returns the decision audit trail
- [ ] `GET /missions/{id}/cost` returns cost breakdown by task and model
- [ ] Dispatch loop integration: persistence is called after mission completion
- [ ] Config loads from `missions.yaml` with defaults
- [ ] Alembic migration creates all four tables
- [ ] `mission_records` table includes `objective_statement` and `objective_category` columns
- [ ] `objective_category` is indexed for query filtering
- [ ] `MissionPersistenceService.save_mission()` populates objective fields from Playbook Objective when available
- [ ] `GET /missions` supports filtering by `objective_category`
- [ ] All existing tests still pass
- [ ] New tests cover persistence, queries, cost aggregation, and API endpoints

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Commit any uncommitted work | `git status`, then commit if needed |
| 0.2 | Create feature branch | `git checkout -b feature/plan-persistence` |

---

### Step 1: Mission Persistence Configuration

**File**: `config/settings/missions.yaml` (NEW)

```yaml
# =============================================================================
# Mission Persistence Configuration
# =============================================================================
#   Controls how mission execution records are stored and queried.
#   This is the audit and analytics layer, not the execution engine.
#
# Available options:
#   max_thinking_trace_length    - Max characters for planning thinking trace (integer)
#   max_task_output_size_bytes   - Max size for task output_data JSONB (integer)
#   retention_days               - Days to retain mission records (integer, 0=forever)
#   default_page_size            - Default pagination size for list queries (integer)
#   max_page_size                - Maximum pagination size (integer)
#   persist_thinking_trace       - Whether to store planning agent thinking trace (boolean)
#   persist_verification_details - Whether to store full verification outcome JSON (boolean)
# =============================================================================

max_thinking_trace_length: 50000
max_task_output_size_bytes: 1048576
retention_days: 0
default_page_size: 20
max_page_size: 100
persist_thinking_trace: true
persist_verification_details: true
```

**File**: `modules/backend/core/config_schema.py` — Add `MissionsSchema`:

```python
class MissionsSchema(_StrictBase):
    """Mission persistence and audit trail configuration."""

    max_thinking_trace_length: int = 50000
    max_task_output_size_bytes: int = 1_048_576  # 1MB
    retention_days: int = 0  # 0 = keep forever
    default_page_size: int = 20
    max_page_size: int = 100
    persist_thinking_trace: bool = True
    persist_verification_details: bool = True
```

**File**: `modules/backend/core/config.py` — Register in `AppConfig`:

Add `missions: MissionsSchema` field and load from `config/settings/missions.yaml` using the existing `_load_validated_optional()` pattern:

```python
self._missions = _load_validated_optional(MissionsSchema, "missions.yaml")
```

Add property:

```python
@property
def missions(self) -> MissionsSchema:
    """Mission persistence settings."""
    return self._missions
```

**Verification**: `python -c "from modules.backend.core.config import get_app_config; print(get_app_config().missions.retention_days)"` — should print `0`.

---

### Step 2: Mission Record Models

**File**: `modules/backend/models/mission_record.py` (NEW)

```python
"""
Mission Record Models.

Persistence layer for Mission Control execution artifacts.
Stores TaskPlans, execution results, verification outcomes,
decision trails, and cost breakdowns.

These are audit/history tables. Mission Control's dispatch loop
(Plan 13) drives execution in memory. After completion, results
are persisted here.
"""

import enum

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class MissionRecordStatus(str, enum.Enum):
    """Terminal status of a completed mission record."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TaskExecutionStatus(str, enum.Enum):
    """Terminal status of a task execution."""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskAttemptStatus(str, enum.Enum):
    """Status of a single task attempt."""

    PASSED = "passed"
    FAILED = "failed"


class DecisionType(str, enum.Enum):
    """Types of decisions Mission Control makes."""

    RETRY = "retry"
    FAIL = "fail"
    PASS = "pass"
    RE_PLAN = "re_plan"
    SKIP = "skip"
    ESCALATE = "escalate"


class FailureTier(str, enum.Enum):
    """Failure classification from Plan 14 verification."""

    TIER_1_STRUCTURAL = "tier_1_structural"
    TIER_2_QUALITY = "tier_2_quality"
    TIER_3_INTEGRATION = "tier_3_integration"
    AGENT_ERROR = "agent_error"
    TIMEOUT = "timeout"


class MissionRecord(UUIDMixin, TimestampMixin, Base):
    """A persisted record of a Mission Control execution.

    Stores the complete execution history: what was planned (TaskPlan JSON),
    what happened (MissionOutcome JSON), why the plan was shaped that way
    (thinking trace), and how much it cost.
    """

    __tablename__ = "mission_records"

    # Session reference
    session_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="Session that triggered this mission",
    )

    # Roster used for this mission
    roster_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
        comment="Agent roster used (e.g. 'code_review', 'research')",
    )

    # Objective traceability (from Playbook Objective metadata)
    objective_statement: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Business outcome from Playbook Objective (null for ad-hoc missions)",
    )
    objective_category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Objective category from Playbook (enables filtering by business domain)",
    )

    # Terminal status
    status: Mapped[str] = mapped_column(
        Enum(MissionRecordStatus, native_enum=False),
        nullable=False,
        index=True,
    )

    # The frozen TaskPlan produced by the Planning Agent
    task_plan_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="TaskPlan dataclass serialized to JSON. Immutable after creation.",
    )

    # The MissionOutcome produced by the dispatch loop
    mission_outcome_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="MissionOutcome dataclass serialized to JSON. Full execution result.",
    )

    # Planning Agent's reasoning trace
    planning_thinking_trace: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Planning Agent chain-of-thought for audit/debugging",
    )

    # Cost aggregation
    total_cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Total cost across all task executions",
    )

    # Timing
    started_at: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    completed_at: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    # Re-plan lineage
    parent_mission_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_records.id"),
        nullable=True,
        index=True,
        comment="If this mission was a re-plan, link to the original",
    )

    # Relationships
    task_executions: Mapped[list["TaskExecution"]] = relationship(
        "TaskExecution",
        back_populates="mission_record",
        cascade="all, delete-orphan",
    )
    decisions: Mapped[list["MissionDecision"]] = relationship(
        "MissionDecision",
        back_populates="mission_record",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<MissionRecord(id={self.id}, roster={self.roster_name!r}, "
            f"status={self.status}, cost=${self.total_cost_usd:.4f})>"
        )


class TaskExecution(UUIDMixin, TimestampMixin, Base):
    """A single task execution within a mission.

    Records the agent assignment, output, verification outcome,
    token usage, cost, and duration. One row per task in the TaskPlan.
    """

    __tablename__ = "task_executions"

    # Mission reference
    mission_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mission_records.id"),
        nullable=False,
        index=True,
    )

    # Task identity (from TaskPlan)
    task_id: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Task ID from the TaskPlan JSON",
    )
    agent_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Agent that executed this task",
    )

    # Terminal status
    status: Mapped[str] = mapped_column(
        Enum(TaskExecutionStatus, native_enum=False),
        nullable=False,
        index=True,
    )

    # Output
    output_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Structured output from the agent",
    )

    # Token usage breakdown
    token_usage: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment='{"input_tokens": int, "output_tokens": int, "model": str}',
    )

    # Cost
    cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    # Duration
    duration_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Verification outcome from Plan 14
    verification_outcome: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Tier 1/2 verification result: {passed, tier, details, feedback}",
    )

    # Timing
    started_at: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    completed_at: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    # Relationships
    mission_record: Mapped["MissionRecord"] = relationship(
        "MissionRecord",
        back_populates="task_executions",
    )
    attempts: Mapped[list["TaskAttempt"]] = relationship(
        "TaskAttempt",
        back_populates="task_execution",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<TaskExecution(id={self.id}, task={self.task_id!r}, "
            f"agent={self.agent_name!r}, status={self.status})>"
        )


class TaskAttempt(UUIDMixin, TimestampMixin, Base):
    """A single attempt to execute a task.

    When Mission Control retries a task (failure tier allows it),
    each attempt is recorded separately. This shows the full retry
    history: what failed, what feedback was provided, how many tokens
    were consumed per attempt.
    """

    __tablename__ = "task_attempts"

    # Task execution reference
    task_execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("task_executions.id"),
        nullable=False,
        index=True,
    )

    # Attempt number (1-based)
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Status of this attempt
    status: Mapped[str] = mapped_column(
        Enum(TaskAttemptStatus, native_enum=False),
        nullable=False,
    )

    # Failure details (if failed)
    failure_tier: Mapped[str | None] = mapped_column(
        Enum(FailureTier, native_enum=False),
        nullable=True,
        comment="Failure classification from verification",
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Why this attempt failed",
    )

    # Feedback provided to the agent for retry
    feedback_provided: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Feedback injected into agent prompt for next attempt",
    )

    # Token usage for this attempt
    input_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Cost for this attempt
    cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    # Relationship
    task_execution: Mapped["TaskExecution"] = relationship(
        "TaskExecution",
        back_populates="attempts",
    )

    def __repr__(self) -> str:
        return (
            f"<TaskAttempt(id={self.id}, attempt={self.attempt_number}, "
            f"status={self.status})>"
        )


class MissionDecision(UUIDMixin, TimestampMixin, Base):
    """A decision made by Mission Control during execution.

    Every decision — retry, fail, pass, re-plan, skip, escalate —
    is logged with the decision type, reasoning, and context.
    This is the compliance and audit layer.
    """

    __tablename__ = "mission_decisions"

    # Mission reference
    mission_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mission_records.id"),
        nullable=False,
        index=True,
    )

    # Decision details
    decision_type: Mapped[str] = mapped_column(
        Enum(DecisionType, native_enum=False),
        nullable=False,
        index=True,
        comment="retry, fail, pass, re_plan, skip, escalate",
    )

    # Which task this decision applies to (if task-specific)
    task_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Task ID from TaskPlan, if decision is task-specific",
    )

    # Reasoning
    reasoning: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Why Mission Control made this decision",
    )

    def __repr__(self) -> str:
        return (
            f"<MissionDecision(id={self.id}, type={self.decision_type!r}, "
            f"task={self.task_id!r})>"
        )
```

**File**: `modules/backend/models/__init__.py` — Add import:

```python
from modules.backend.models.mission_record import (
    MissionRecord,
    TaskExecution,
    TaskAttempt,
    MissionDecision,
)
```

This registers the models with Alembic for autogenerate.

**Design notes**:
- Uses `JSON` (via `sqlalchemy.dialects.sqlite`) for JSONB columns — works with both PostgreSQL (JSONB) and SQLite (text JSON) for test compatibility
- `started_at`, `completed_at` stored as ISO strings rather than DateTime — matches existing codebase pattern
- `parent_mission_id` self-referential FK enables re-plan lineage tracking
- `FailureTier` enum mirrors the verification failure tiers from Plan 14
- `DecisionType` enum covers all decisions Mission Control can make

---

### Step 3: Mission Record Schemas

**File**: `modules/backend/schemas/mission_record.py` (NEW)

```python
"""
Mission Record API schemas.

Request/response models for querying mission execution history,
task results, decisions, and cost breakdowns.
"""

from pydantic import BaseModel, ConfigDict, Field


class TaskAttemptResponse(BaseModel):
    """API response for a single task attempt."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    attempt_number: int
    status: str
    failure_tier: str | None
    failure_reason: str | None
    feedback_provided: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: str


class TaskExecutionResponse(BaseModel):
    """API response for a single task execution."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    agent_name: str
    status: str
    output_data: dict | None
    token_usage: dict | None
    cost_usd: float
    duration_seconds: float | None
    verification_outcome: dict | None
    started_at: str | None
    completed_at: str | None
    created_at: str


class TaskExecutionDetailResponse(TaskExecutionResponse):
    """Task execution with attempt history."""

    attempts: list[TaskAttemptResponse] = Field(default_factory=list)


class MissionDecisionResponse(BaseModel):
    """API response for a Mission Control decision."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    decision_type: str
    task_id: str | None
    reasoning: str
    created_at: str


class MissionRecordResponse(BaseModel):
    """API response for a mission record (list view)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    roster_name: str | None
    status: str
    total_cost_usd: float
    started_at: str | None
    completed_at: str | None
    parent_mission_id: str | None
    created_at: str
    updated_at: str


class MissionRecordDetailResponse(MissionRecordResponse):
    """Detailed mission record with full execution data."""

    task_plan_json: dict | None
    mission_outcome_json: dict | None
    planning_thinking_trace: str | None
    task_executions: list[TaskExecutionResponse] = Field(default_factory=list)
    decisions: list[MissionDecisionResponse] = Field(default_factory=list)


class MissionCostBreakdown(BaseModel):
    """Cost breakdown for a mission."""

    mission_id: str
    total_cost_usd: float
    task_costs: list[dict] = Field(
        default_factory=list,
        description="Per-task cost: [{task_id, agent_name, cost_usd, tokens}]",
    )
    model_costs: dict[str, float] = Field(
        default_factory=dict,
        description="Cost aggregated by model name",
    )
    attempt_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class MissionListResponse(BaseModel):
    """Paginated mission list."""

    missions: list[MissionRecordResponse]
    total: int
    page_size: int
    offset: int
```

---

### Step 4: Mission Record Repository

**File**: `modules/backend/repositories/mission_record.py` (NEW)

```python
"""
Mission Record Repository.

Standard CRUD plus mission-specific queries: cost aggregation,
status filtering, session lookups, re-plan lineage.
"""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.backend.core.logging import get_logger
from modules.backend.models.mission_record import (
    MissionDecision,
    MissionRecord,
    MissionRecordStatus,
    TaskAttempt,
    TaskExecution,
)
from modules.backend.repositories.base import BaseRepository

logger = get_logger(__name__)


class MissionRecordRepository(BaseRepository[MissionRecord]):
    """Mission record repository with audit-specific queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(MissionRecord, session)

    async def get_with_details(self, mission_id: str) -> MissionRecord | None:
        """Get mission record with task executions and decisions eagerly loaded."""
        stmt = (
            select(MissionRecord)
            .where(MissionRecord.id == mission_id)
            .options(
                selectinload(MissionRecord.task_executions)
                .selectinload(TaskExecution.attempts),
                selectinload(MissionRecord.decisions),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_session(self, session_id: str) -> list[MissionRecord]:
        """Get all mission records for a session, newest first."""
        stmt = (
            select(MissionRecord)
            .where(MissionRecord.session_id == session_id)
            .order_by(MissionRecord.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_missions(
        self,
        status: MissionRecordStatus | None = None,
        roster_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[MissionRecord], int]:
        """List mission records with optional filters and pagination.

        Returns:
            Tuple of (missions, total_count).
        """
        conditions = []
        if status:
            conditions.append(MissionRecord.status == status)
        if roster_name:
            conditions.append(MissionRecord.roster_name == roster_name)

        # Count query
        count_stmt = select(func.count()).select_from(MissionRecord)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(MissionRecord)
            .order_by(MissionRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if conditions:
            data_stmt = data_stmt.where(and_(*conditions))

        result = await self.session.execute(data_stmt)
        return list(result.scalars().all()), total

    async def get_decisions(self, mission_id: str) -> list[MissionDecision]:
        """Get all decisions for a mission, ordered chronologically."""
        stmt = (
            select(MissionDecision)
            .where(MissionDecision.mission_record_id == mission_id)
            .order_by(MissionDecision.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_task_executions(
        self, mission_id: str
    ) -> list[TaskExecution]:
        """Get all task executions for a mission with attempts loaded."""
        stmt = (
            select(TaskExecution)
            .where(TaskExecution.mission_record_id == mission_id)
            .options(selectinload(TaskExecution.attempts))
            .order_by(TaskExecution.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_cost_by_model(self, mission_id: str) -> dict[str, float]:
        """Aggregate cost by model for a mission."""
        executions = await self.get_task_executions(mission_id)
        model_costs: dict[str, float] = {}
        for execution in executions:
            if execution.token_usage and "model" in execution.token_usage:
                model = execution.token_usage["model"]
                model_costs[model] = model_costs.get(model, 0.0) + execution.cost_usd
        return model_costs

    async def get_replan_chain(self, mission_id: str) -> list[MissionRecord]:
        """Get the full re-plan lineage for a mission.

        Follows parent_mission_id links to build the chain.
        Returns oldest-first.
        """
        chain: list[MissionRecord] = []
        current_id: str | None = mission_id

        while current_id:
            mission = await self.get(current_id)
            if not mission:
                break
            chain.append(mission)
            current_id = mission.parent_mission_id

        chain.reverse()  # oldest first
        return chain
```

---

### Step 5: Mission Persistence Service

**File**: `modules/backend/services/mission_persistence.py` (NEW)

```python
"""
Mission Persistence Service.

Saves Mission Control execution artifacts to PostgreSQL for audit,
compliance, cost analytics, and historical queries.

Called by the dispatch loop (Plan 13) during and after mission execution.
This service is write-heavy during execution and read-heavy afterward.
"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now
from modules.backend.models.mission_record import (
    DecisionType,
    FailureTier,
    MissionDecision,
    MissionRecord,
    MissionRecordStatus,
    TaskAttempt,
    TaskAttemptStatus,
    TaskExecution,
    TaskExecutionStatus,
)
from modules.backend.repositories.mission_record import MissionRecordRepository
from modules.backend.schemas.mission_record import MissionCostBreakdown
from modules.backend.services.base import BaseService

logger = get_logger(__name__)


class MissionPersistenceService(BaseService):
    """Persist and query mission execution records.

    Write methods are called during/after dispatch loop execution.
    Read methods serve the REST API and analytics.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = MissionRecordRepository(session)

    # ---- Write operations (called by dispatch loop) ----

    async def save_mission(
        self,
        session_id: str,
        status: str,
        *,
        roster_name: str | None = None,
        task_plan_json: dict | None = None,
        mission_outcome_json: dict | None = None,
        planning_thinking_trace: str | None = None,
        total_cost_usd: float = 0.0,
        started_at: str | None = None,
        completed_at: str | None = None,
        parent_mission_id: str | None = None,
    ) -> MissionRecord:
        """Persist a complete mission record.

        Called after the dispatch loop completes (or fails/times out).
        Stores the TaskPlan, MissionOutcome, thinking trace, and cost.

        Args:
            session_id: Session that triggered this mission.
            status: Terminal status (completed, failed, cancelled, timed_out).
            roster_name: Agent roster used.
            task_plan_json: Serialized TaskPlan from Planning Agent.
            mission_outcome_json: Serialized MissionOutcome from dispatch loop.
            planning_thinking_trace: Planning Agent reasoning trace.
            total_cost_usd: Aggregated cost.
            started_at: ISO timestamp when execution began.
            completed_at: ISO timestamp when execution ended.
            parent_mission_id: Link to original mission if this was a re-plan.

        Returns:
            Created MissionRecord.
        """
        config = get_app_config().missions

        # Truncate thinking trace if needed
        if planning_thinking_trace and config.persist_thinking_trace:
            if len(planning_thinking_trace) > config.max_thinking_trace_length:
                planning_thinking_trace = (
                    planning_thinking_trace[: config.max_thinking_trace_length]
                    + "\n\n[TRUNCATED]"
                )
        elif not config.persist_thinking_trace:
            planning_thinking_trace = None

        record = MissionRecord(
            session_id=session_id,
            roster_name=roster_name,
            status=MissionRecordStatus(status),
            task_plan_json=task_plan_json,
            mission_outcome_json=mission_outcome_json,
            planning_thinking_trace=planning_thinking_trace,
            total_cost_usd=total_cost_usd,
            started_at=started_at or utc_now().isoformat(),
            completed_at=completed_at or utc_now().isoformat(),
            parent_mission_id=parent_mission_id,
        )

        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)

        logger.info(
            "Mission record saved",
            extra={
                "mission_id": record.id,
                "session_id": session_id,
                "roster": roster_name,
                "status": status,
                "cost": total_cost_usd,
            },
        )

        return record

    async def save_task_execution(
        self,
        mission_record_id: str,
        task_id: str,
        agent_name: str,
        status: str,
        *,
        output_data: dict | None = None,
        token_usage: dict | None = None,
        cost_usd: float = 0.0,
        duration_seconds: float | None = None,
        verification_outcome: dict | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> TaskExecution:
        """Persist a single task execution result.

        Called after each task completes (or fails) within the dispatch loop.

        Args:
            mission_record_id: Parent mission record ID.
            task_id: Task ID from the TaskPlan.
            agent_name: Agent that executed the task.
            status: Terminal status (completed, failed, skipped).
            output_data: Structured output from the agent.
            token_usage: Token counts and model info.
            cost_usd: Cost for this task execution.
            duration_seconds: Wall-clock duration.
            verification_outcome: Tier 1/2 verification result.
            started_at: ISO timestamp.
            completed_at: ISO timestamp.

        Returns:
            Created TaskExecution.
        """
        config = get_app_config().missions

        # Truncate output if needed
        if output_data:
            output_size = len(json.dumps(output_data).encode("utf-8"))
            if output_size > config.max_task_output_size_bytes:
                output_data = {
                    "_truncated": True,
                    "_original_size_bytes": output_size,
                    "_message": "Output truncated. Exceeded max_task_output_size_bytes.",
                }

        # Strip verification details if config says not to persist them
        if verification_outcome and not config.persist_verification_details:
            verification_outcome = {
                "passed": verification_outcome.get("passed"),
                "tier": verification_outcome.get("tier"),
            }

        execution = TaskExecution(
            mission_record_id=mission_record_id,
            task_id=task_id,
            agent_name=agent_name,
            status=TaskExecutionStatus(status),
            output_data=output_data,
            token_usage=token_usage,
            cost_usd=cost_usd,
            duration_seconds=duration_seconds,
            verification_outcome=verification_outcome,
            started_at=started_at,
            completed_at=completed_at,
        )

        self._session.add(execution)
        await self._session.flush()
        await self._session.refresh(execution)

        logger.debug(
            "Task execution saved",
            extra={
                "execution_id": execution.id,
                "mission_id": mission_record_id,
                "task_id": task_id,
                "agent": agent_name,
                "status": status,
                "cost": cost_usd,
            },
        )

        return execution

    async def save_attempt(
        self,
        task_execution_id: str,
        attempt_number: int,
        status: str,
        *,
        failure_tier: str | None = None,
        failure_reason: str | None = None,
        feedback_provided: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> TaskAttempt:
        """Persist a single task attempt within a task execution.

        Called after each attempt (including retries).

        Args:
            task_execution_id: Parent task execution ID.
            attempt_number: 1-based attempt number.
            status: passed or failed.
            failure_tier: Failure classification (if failed).
            failure_reason: Why the attempt failed.
            feedback_provided: Feedback injected for the next attempt.
            input_tokens: Input tokens consumed.
            output_tokens: Output tokens consumed.
            cost_usd: Cost for this attempt.

        Returns:
            Created TaskAttempt.
        """
        attempt = TaskAttempt(
            task_execution_id=task_execution_id,
            attempt_number=attempt_number,
            status=TaskAttemptStatus(status),
            failure_tier=FailureTier(failure_tier) if failure_tier else None,
            failure_reason=failure_reason,
            feedback_provided=feedback_provided,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

        self._session.add(attempt)
        await self._session.flush()
        await self._session.refresh(attempt)

        return attempt

    async def save_decision(
        self,
        mission_record_id: str,
        decision_type: str,
        reasoning: str,
        *,
        task_id: str | None = None,
    ) -> MissionDecision:
        """Log a Mission Control decision.

        Called in real time as decisions are made during the dispatch loop.

        Args:
            mission_record_id: Parent mission record ID.
            decision_type: retry, fail, pass, re_plan, skip, escalate.
            reasoning: Why this decision was made.
            task_id: Task ID if the decision is task-specific.

        Returns:
            Created MissionDecision.
        """
        decision = MissionDecision(
            mission_record_id=mission_record_id,
            decision_type=DecisionType(decision_type),
            task_id=task_id,
            reasoning=reasoning,
        )

        self._session.add(decision)
        await self._session.flush()
        await self._session.refresh(decision)

        logger.debug(
            "Decision logged",
            extra={
                "decision_id": decision.id,
                "mission_id": mission_record_id,
                "type": decision_type,
                "task_id": task_id,
            },
        )

        return decision

    # ---- Read operations (serve REST API) ----

    async def get_mission(self, mission_id: str) -> MissionRecord | None:
        """Get a mission record with all details loaded."""
        return await self._repo.get_with_details(mission_id)

    async def list_missions(
        self,
        status: str | None = None,
        roster_name: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[MissionRecord], int]:
        """List mission records with optional filters.

        Returns:
            Tuple of (missions, total_count).
        """
        config = get_app_config().missions
        if limit is None:
            limit = config.default_page_size
        limit = min(limit, config.max_page_size)

        mission_status = MissionRecordStatus(status) if status else None
        return await self._repo.list_missions(
            status=mission_status,
            roster_name=roster_name,
            limit=limit,
            offset=offset,
        )

    async def get_decisions(self, mission_id: str) -> list[MissionDecision]:
        """Get the decision audit trail for a mission."""
        return await self._repo.get_decisions(mission_id)

    async def get_cost_breakdown(self, mission_id: str) -> MissionCostBreakdown:
        """Get detailed cost breakdown for a mission.

        Aggregates cost by task and by model.
        """
        mission = await self._repo.get(mission_id)
        if not mission:
            from modules.backend.core.exceptions import NotFoundError
            raise NotFoundError(message=f"Mission '{mission_id}' not found")

        executions = await self._repo.get_task_executions(mission_id)
        model_costs = await self._repo.get_cost_by_model(mission_id)

        task_costs = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_attempts = 0

        for execution in executions:
            task_cost: dict[str, Any] = {
                "task_id": execution.task_id,
                "agent_name": execution.agent_name,
                "cost_usd": execution.cost_usd,
                "status": execution.status,
                "duration_seconds": execution.duration_seconds,
            }
            if execution.token_usage:
                task_cost["input_tokens"] = execution.token_usage.get(
                    "input_tokens", 0
                )
                task_cost["output_tokens"] = execution.token_usage.get(
                    "output_tokens", 0
                )
                total_input_tokens += task_cost.get("input_tokens", 0)
                total_output_tokens += task_cost.get("output_tokens", 0)

            total_attempts += len(execution.attempts)
            task_costs.append(task_cost)

        return MissionCostBreakdown(
            mission_id=mission_id,
            total_cost_usd=mission.total_cost_usd,
            task_costs=task_costs,
            model_costs=model_costs,
            attempt_count=total_attempts,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )

    async def get_missions_by_session(
        self, session_id: str
    ) -> list[MissionRecord]:
        """Get all mission records for a session."""
        return await self._repo.get_by_session(session_id)

    async def get_replan_chain(self, mission_id: str) -> list[MissionRecord]:
        """Get the full re-plan lineage for a mission."""
        return await self._repo.get_replan_chain(mission_id)
```

---

### Step 6: REST API Endpoints

**File**: `modules/backend/api/v1/endpoints/missions.py` (NEW)

```python
"""
Mission Record API endpoints.

Read-only endpoints for querying mission execution history,
decisions, and cost breakdowns. Write operations happen via
the MissionPersistenceService called from the dispatch loop.
"""

from fastapi import APIRouter

from modules.backend.core.dependencies import DbSession, RequestId
from modules.backend.core.exceptions import NotFoundError
from modules.backend.schemas.base import ApiResponse
from modules.backend.schemas.mission_record import (
    MissionCostBreakdown,
    MissionDecisionResponse,
    MissionListResponse,
    MissionRecordDetailResponse,
    MissionRecordResponse,
    TaskExecutionDetailResponse,
)
from modules.backend.services.mission_persistence import MissionPersistenceService

router = APIRouter()


@router.get("", response_model=ApiResponse, summary="List mission records")
async def list_missions(
    db: DbSession,
    request_id: RequestId,
    status: str | None = None,
    roster_name: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ApiResponse:
    """List mission execution records with optional filters."""
    service = MissionPersistenceService(db)
    missions, total = await service.list_missions(
        status=status,
        roster_name=roster_name,
        limit=limit,
        offset=offset,
    )

    items = [
        MissionRecordResponse.model_validate(m).model_dump() for m in missions
    ]

    return ApiResponse(
        success=True,
        data=MissionListResponse(
            missions=[MissionRecordResponse.model_validate(m) for m in missions],
            total=total,
            page_size=limit,
            offset=offset,
        ).model_dump(),
        metadata={"request_id": request_id},
    )


@router.get(
    "/{mission_id}",
    response_model=ApiResponse,
    summary="Get mission record detail",
)
async def get_mission(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Get a mission record with full execution details."""
    service = MissionPersistenceService(db)
    mission = await service.get_mission(mission_id)

    if not mission:
        raise NotFoundError(message=f"Mission '{mission_id}' not found")

    response = MissionRecordDetailResponse.model_validate(mission)
    return ApiResponse(
        success=True,
        data=response.model_dump(),
        metadata={"request_id": request_id},
    )


@router.get(
    "/{mission_id}/decisions",
    response_model=ApiResponse,
    summary="Get mission decision audit trail",
)
async def get_mission_decisions(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Get the decision audit trail for a mission.

    Returns every decision Mission Control made during execution:
    retry, fail, pass, re-plan, skip, escalate — with reasoning.
    """
    service = MissionPersistenceService(db)

    # Verify mission exists
    mission = await service.get_mission(mission_id)
    if not mission:
        raise NotFoundError(message=f"Mission '{mission_id}' not found")

    decisions = await service.get_decisions(mission_id)
    items = [
        MissionDecisionResponse.model_validate(d).model_dump()
        for d in decisions
    ]

    return ApiResponse(
        success=True,
        data={"decisions": items, "count": len(items)},
        metadata={"request_id": request_id},
    )


@router.get(
    "/{mission_id}/cost",
    response_model=ApiResponse,
    summary="Get mission cost breakdown",
)
async def get_mission_cost(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Get detailed cost breakdown for a mission.

    Returns cost by task, by model, and token totals.
    """
    service = MissionPersistenceService(db)
    breakdown = await service.get_cost_breakdown(mission_id)

    return ApiResponse(
        success=True,
        data=breakdown.model_dump(),
        metadata={"request_id": request_id},
    )
```

**File**: `modules/backend/api/v1/__init__.py` — Register the router:

Add the missions router to the v1 API router following the existing pattern:

```python
from modules.backend.api.v1.endpoints import missions

# Mission record endpoints (audit, history, cost)
router.include_router(missions.router, prefix="/missions", tags=["missions"])
```

---

### Step 7: Database Migration

Create an Alembic migration for all four tables.

**Command**: `cd modules/backend && alembic revision --autogenerate -m "add_mission_record_tables"`

The migration should create:

1. **`mission_records`** — id, session_id (indexed), roster_name (indexed), status (indexed), task_plan_json (JSON), mission_outcome_json (JSON), planning_thinking_trace (Text), total_cost_usd (Float), started_at, completed_at, parent_mission_id (FK to self, indexed), created_at, updated_at
2. **`task_executions`** — id, mission_record_id (FK, indexed), task_id, agent_name, status (indexed), output_data (JSON), token_usage (JSON), cost_usd, duration_seconds, verification_outcome (JSON), started_at, completed_at, created_at, updated_at
3. **`task_attempts`** — id, task_execution_id (FK, indexed), attempt_number, status, failure_tier, failure_reason, feedback_provided, input_tokens, output_tokens, cost_usd, created_at, updated_at
4. **`mission_decisions`** — id, mission_record_id (FK, indexed), decision_type (indexed), task_id, reasoning, created_at, updated_at

**Note**: The `sessions` table must exist before this migration runs (Plan 11). If it does not exist yet, drop the FK constraint on `session_id` and add it in a later migration.

**Verification**: `alembic upgrade head` completes without errors.

---

### Step 8: Dispatch Loop Integration

**File**: `modules/backend/agents/mission_control/dispatch.py` (MODIFY)

After the dispatch loop completes a mission, it calls the persistence service to save the results. This is a non-critical operation — persistence failure should be logged but should not crash the mission.

**Integration point** (pseudocode — adapt to actual dispatch.py structure from Plan 13):

```python
async def _persist_mission_results(
    session_id: str,
    roster_name: str | None,
    task_plan: dict,
    mission_outcome: dict,
    thinking_trace: str | None,
    decisions: list[dict],
    task_results: list[dict],
    db_session: AsyncSession,
) -> None:
    """Persist mission execution results. Best-effort — does not raise."""
    try:
        service = MissionPersistenceService(db_session)

        # 1. Save the mission record
        record = await service.save_mission(
            session_id=session_id,
            status=mission_outcome.get("status", "completed"),
            roster_name=roster_name,
            task_plan_json=task_plan,
            mission_outcome_json=mission_outcome,
            planning_thinking_trace=thinking_trace,
            total_cost_usd=mission_outcome.get("total_cost_usd", 0.0),
            started_at=mission_outcome.get("started_at"),
            completed_at=mission_outcome.get("completed_at"),
        )

        # 2. Save each task execution
        for task_result in task_results:
            execution = await service.save_task_execution(
                mission_record_id=record.id,
                task_id=task_result["task_id"],
                agent_name=task_result["agent_name"],
                status=task_result["status"],
                output_data=task_result.get("output_data"),
                token_usage=task_result.get("token_usage"),
                cost_usd=task_result.get("cost_usd", 0.0),
                duration_seconds=task_result.get("duration_seconds"),
                verification_outcome=task_result.get("verification_outcome"),
                started_at=task_result.get("started_at"),
                completed_at=task_result.get("completed_at"),
            )

            # 3. Save attempt history for this task
            for attempt in task_result.get("attempts", []):
                await service.save_attempt(
                    task_execution_id=execution.id,
                    attempt_number=attempt["attempt_number"],
                    status=attempt["status"],
                    failure_tier=attempt.get("failure_tier"),
                    failure_reason=attempt.get("failure_reason"),
                    feedback_provided=attempt.get("feedback_provided"),
                    input_tokens=attempt.get("input_tokens", 0),
                    output_tokens=attempt.get("output_tokens", 0),
                    cost_usd=attempt.get("cost_usd", 0.0),
                )

        # 4. Save decisions
        for decision in decisions:
            await service.save_decision(
                mission_record_id=record.id,
                decision_type=decision["type"],
                reasoning=decision["reasoning"],
                task_id=decision.get("task_id"),
            )

        await db_session.commit()

        logger.info(
            "Mission results persisted",
            extra={
                "mission_id": record.id,
                "task_count": len(task_results),
                "decision_count": len(decisions),
            },
        )

    except Exception as e:
        logger.error(
            "Failed to persist mission results",
            extra={"session_id": session_id, "error": str(e)},
        )
```

**Key patterns**:
- Persistence is best-effort — wrapped in try/except
- The dispatch loop calls this after `MissionOutcome` is assembled
- All task results and decisions are saved in a single transaction
- The function is `async` — it runs within the existing async context

---

### Step 9: Tests

**File**: `tests/unit/backend/models/test_mission_record.py` (NEW, ~80 lines)

```python
"""
Tests for mission record models.
"""

import pytest

from modules.backend.models.mission_record import (
    DecisionType,
    FailureTier,
    MissionDecision,
    MissionRecord,
    MissionRecordStatus,
    TaskAttempt,
    TaskAttemptStatus,
    TaskExecution,
    TaskExecutionStatus,
)


class TestMissionRecordModel:
    """Tests for MissionRecord SQLAlchemy model."""

    def test_create_mission_record(self):
        record = MissionRecord(
            session_id="test-session",
            status=MissionRecordStatus.COMPLETED,
            roster_name="code_review",
            total_cost_usd=0.0123,
        )
        assert record.status == MissionRecordStatus.COMPLETED
        assert record.roster_name == "code_review"

    def test_mission_record_repr(self):
        record = MissionRecord(
            id="abc-123",
            session_id="test-session",
            status=MissionRecordStatus.FAILED,
            roster_name="research",
            total_cost_usd=1.50,
        )
        assert "research" in repr(record)
        assert "FAILED" in repr(record) or "failed" in repr(record)


class TestTaskExecutionModel:
    """Tests for TaskExecution SQLAlchemy model."""

    def test_create_task_execution(self):
        execution = TaskExecution(
            mission_record_id="mission-123",
            task_id="analyze_code",
            agent_name="code.qa.agent",
            status=TaskExecutionStatus.COMPLETED,
            cost_usd=0.005,
        )
        assert execution.agent_name == "code.qa.agent"

    def test_task_execution_with_verification(self):
        execution = TaskExecution(
            mission_record_id="mission-123",
            task_id="summarize",
            agent_name="content.summarizer.agent",
            status=TaskExecutionStatus.COMPLETED,
            verification_outcome={
                "passed": True,
                "tier": "tier_1_structural",
                "details": "Output matches expected schema",
            },
        )
        assert execution.verification_outcome["passed"] is True


class TestEnums:
    """Tests for model enums."""

    def test_decision_types(self):
        assert DecisionType.RETRY.value == "retry"
        assert DecisionType.RE_PLAN.value == "re_plan"
        assert DecisionType.ESCALATE.value == "escalate"

    def test_failure_tiers(self):
        assert FailureTier.TIER_1_STRUCTURAL.value == "tier_1_structural"
        assert FailureTier.AGENT_ERROR.value == "agent_error"

    def test_mission_record_status(self):
        assert MissionRecordStatus.COMPLETED.value == "completed"
        assert MissionRecordStatus.TIMED_OUT.value == "timed_out"
```

**File**: `tests/unit/backend/services/test_mission_persistence.py` (NEW, ~200 lines)

Tests for MissionPersistenceService with real database (P12):

1. **Save and retrieve mission** — `save_mission()` persists record, `get_mission()` retrieves it with all fields
2. **Save task execution** — `save_task_execution()` persists task result with verification outcome
3. **Save attempt** — `save_attempt()` persists retry attempt with failure details
4. **Save decision** — `save_decision()` persists Mission Control decision with reasoning
5. **List missions with filters** — status filter, roster filter, pagination
6. **Cost breakdown** — `get_cost_breakdown()` aggregates by task and model correctly
7. **Re-plan chain** — `get_replan_chain()` follows parent links
8. **Thinking trace truncation** — traces exceeding max length are truncated
9. **Output truncation** — task outputs exceeding max size are replaced with reference
10. **Session lookup** — `get_missions_by_session()` returns correct records

Testing strategy (P12):
- Use real PostgreSQL via `db_session` fixture with transaction rollback
- No mocks — all service and repository operations hit real database
- Use `TestModel` only if LLM calls are needed (none in this plan)

**File**: `tests/unit/backend/api/test_missions_api.py` (NEW, ~100 lines)

Tests for the mission API endpoints:

1. `GET /api/v1/missions` — returns paginated list
2. `GET /api/v1/missions/{id}` — returns detail with TaskPlan and MissionOutcome
3. `GET /api/v1/missions/{id}` with missing ID — returns 404
4. `GET /api/v1/missions/{id}/decisions` — returns decision audit trail
5. `GET /api/v1/missions/{id}/cost` — returns cost breakdown
6. Pagination — limit and offset work correctly
7. Status filter — only matching records returned

**File**: `tests/unit/backend/events/test_config_missions.py` (NEW, ~30 lines)

```python
"""Tests for MissionsSchema config loading."""

import pytest

from modules.backend.core.config_schema import MissionsSchema


class TestMissionsConfig:
    def test_defaults(self):
        config = MissionsSchema()
        assert config.retention_days == 0
        assert config.default_page_size == 20
        assert config.persist_thinking_trace is True

    def test_strict_rejects_unknown(self):
        with pytest.raises(ValueError):
            MissionsSchema(unknown_field="oops")
```

---

### Step 10: Cleanup and Review

- Verify all four tables are created by the Alembic migration
- Verify `MissionPersistenceService` is called from the dispatch loop (Plan 13 integration)
- Verify no hardcoded values — all limits from `missions.yaml`
- Verify all logging uses `get_logger(__name__)`
- Verify all datetimes use `utc_now()` from `modules.backend.core.utils`
- Verify `__init__.py` files have correct exports
- Verify no file exceeds 500 lines
- Verify old Plan 14 tables (`plans`, `plan_tasks`, `task_dependencies`) are NOT created by this plan
- Verify old PM agent tools (`create_plan`, `revise_plan`, `get_plan_status`) are NOT created by this plan

---

## Files Summary

| Category | File | Action | Est. Lines |
|----------|------|--------|-----------|
| Config YAML | `config/settings/missions.yaml` | New | ~20 |
| Config schema | `modules/backend/core/config_schema.py` | Modify | +12 |
| Config loader | `modules/backend/core/config.py` | Modify | +5 |
| Models | `modules/backend/models/mission_record.py` | New | ~350 |
| Models init | `modules/backend/models/__init__.py` | Modify | +5 |
| Schemas | `modules/backend/schemas/mission_record.py` | New | ~130 |
| Repository | `modules/backend/repositories/mission_record.py` | New | ~150 |
| Service | `modules/backend/services/mission_persistence.py` | New | ~350 |
| API | `modules/backend/api/v1/endpoints/missions.py` | New | ~130 |
| API router | `modules/backend/api/v1/__init__.py` | Modify | +3 |
| Dispatch integration | `modules/backend/agents/mission_control/dispatch.py` | Modify | +80 |
| Migration | `alembic/versions/xxx_add_mission_record_tables.py` | New | ~80 |
| Tests - models | `tests/unit/backend/models/test_mission_record.py` | New | ~80 |
| Tests - service | `tests/unit/backend/services/test_mission_persistence.py` | New | ~200 |
| Tests - API | `tests/unit/backend/api/test_missions_api.py` | New | ~100 |
| Tests - config | `tests/unit/backend/events/test_config_missions.py` | New | ~30 |
| **Total** | **16 files** | **10 new, 6 modified** | **~1,725** |

---

## Anti-Patterns (Do NOT)

- Do not put execution logic in this plan. Mission Control's dispatch loop (Plan 13) handles execution. This plan only persists results.
- Do not create a mutable DAG. The TaskPlan is an immutable JSON blob produced by the Planning Agent. No `task_dependencies` table. No mutation of plan state in PostgreSQL during execution.
- Do not create PM agent plan tools (`create_plan`, `revise_plan`, `get_plan_status`). Those belong to the old architecture. Mission Control drives execution directly.
- Do not make persistence critical-path. The dispatch loop should work even if persistence fails. Wrap persistence calls in try/except.
- Do not store raw LLM conversation history in mission records. That lives in `session_messages` (Plan 11). Mission records store the structured TaskPlan and MissionOutcome.
- Do not import `logging` directly. Use `from modules.backend.core.logging import get_logger`.
- Do not use `datetime.utcnow()`. Use `from modules.backend.core.utils import utc_now`.
- Do not hardcode limits, page sizes, or retention periods. All from `missions.yaml`.
- Do not store unbounded data in JSONB columns. Truncate thinking traces and task outputs per config limits.

---
