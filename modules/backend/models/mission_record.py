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

    session_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="Session that triggered this mission",
    )

    roster_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
        comment="Agent roster used (e.g. 'code_review', 'research')",
    )

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

    status: Mapped[str] = mapped_column(
        Enum(MissionRecordStatus, native_enum=False),
        nullable=False,
        index=True,
    )

    task_plan_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="TaskPlan dataclass serialized to JSON. Immutable after creation.",
    )

    mission_outcome_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="MissionOutcome dataclass serialized to JSON. Full execution result.",
    )

    planning_thinking_trace: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Planning Agent chain-of-thought for audit/debugging",
    )

    total_cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Total cost across all task executions",
    )

    started_at: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    completed_at: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    parent_mission_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_records.id"),
        nullable=True,
        index=True,
        comment="If this mission was a re-plan, link to the original",
    )

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

    mission_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mission_records.id"),
        nullable=False,
        index=True,
    )

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

    status: Mapped[str] = mapped_column(
        Enum(TaskExecutionStatus, native_enum=False),
        nullable=False,
        index=True,
    )

    output_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Structured output from the agent",
    )

    token_usage: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment='{"input_tokens": int, "output_tokens": int, "model": str}',
    )

    cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    duration_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    verification_outcome: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Tier 1/2/3 verification result from Plan 14",
    )

    started_at: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    completed_at: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

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

    task_execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("task_executions.id"),
        nullable=False,
        index=True,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        Enum(TaskAttemptStatus, native_enum=False),
        nullable=False,
    )

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

    feedback_provided: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Feedback injected into agent prompt for next attempt",
    )

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

    cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

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

    Every decision -- retry, fail, pass, re-plan, skip, escalate --
    is logged with the decision type, reasoning, and context.
    This is the compliance and audit layer.
    """

    __tablename__ = "mission_decisions"

    mission_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("mission_records.id"),
        nullable=False,
        index=True,
    )

    decision_type: Mapped[str] = mapped_column(
        Enum(DecisionType, native_enum=False),
        nullable=False,
        index=True,
        comment="retry, fail, pass, re_plan, skip, escalate",
    )

    task_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Task ID from TaskPlan, if decision is task-specific",
    )

    reasoning: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Why Mission Control made this decision",
    )

    mission_record: Mapped["MissionRecord"] = relationship(
        "MissionRecord",
        back_populates="decisions",
    )

    def __repr__(self) -> str:
        return (
            f"<MissionDecision(id={self.id}, type={self.decision_type!r}, "
            f"task={self.task_id!r})>"
        )
