"""TaskPlan schema — the contract between Planning Agent and Mission Control.

The Planning Agent produces this structure as JSON within XML tags.
Mission Control parses, validates (plan_validator.py), and executes it.
This is the handoff point between AI reasoning and deterministic execution.
"""

from pydantic import BaseModel, ConfigDict, Field


class FromUpstreamRef(BaseModel):
    """Reference to a field in a completed upstream task's output."""

    model_config = ConfigDict(extra="forbid")

    source_task: str = Field(
        ...,
        description="task_id of the upstream task",
    )
    source_field: str = Field(
        ...,
        description="Field name in the upstream task's output",
    )


class TaskInputs(BaseModel):
    """Static and upstream-derived inputs for a task."""

    model_config = ConfigDict(extra="forbid")

    static: dict = Field(
        default_factory=dict,
        description="Fixed input values defined by the Planning Agent",
    )
    from_upstream: dict[str, FromUpstreamRef] = Field(
        default_factory=dict,
        description="References to outputs from completed upstream tasks",
    )


class Tier1Verification(BaseModel):
    """Tier 1: Structural verification — code, zero tokens, milliseconds."""

    model_config = ConfigDict(extra="forbid")

    schema_validation: bool = True
    required_output_fields: list[str] = Field(default_factory=list)


class DeterministicCheck(BaseModel):
    """A single deterministic check in Tier 2 verification."""

    model_config = ConfigDict(extra="forbid")

    check: str = Field(
        ...,
        description="Registered check function name",
    )
    params: dict = Field(
        default_factory=dict,
        description="Check-specific configuration",
    )


class Tier2Verification(BaseModel):
    """Tier 2: Deterministic functional verification — code, zero tokens."""

    model_config = ConfigDict(extra="forbid")

    deterministic_checks: list[DeterministicCheck] = Field(default_factory=list)


class Tier3Verification(BaseModel):
    """Tier 3: AI-based quality evaluation — only when judgment is required."""

    model_config = ConfigDict(extra="forbid")

    requires_ai_evaluation: bool = False
    evaluation_criteria: list[str] = Field(default_factory=list)
    evaluator_agent: str | None = None
    min_evaluation_score: float | None = None


class TaskVerification(BaseModel):
    """Per-task verification specification across all three tiers."""

    model_config = ConfigDict(extra="forbid")

    tier_1: Tier1Verification = Field(default_factory=Tier1Verification)
    tier_2: Tier2Verification = Field(default_factory=Tier2Verification)
    tier_3: Tier3Verification = Field(default_factory=Tier3Verification)


class TaskConstraints(BaseModel):
    """Per-task execution constraints."""

    model_config = ConfigDict(extra="forbid")

    timeout_override_seconds: int | None = None
    priority: str = "normal"


class TaskDefinition(BaseModel):
    """A single task in the TaskPlan DAG."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    agent: str
    agent_version: str
    description: str
    instructions: str
    inputs: TaskInputs = Field(default_factory=TaskInputs)
    dependencies: list[str] = Field(default_factory=list)
    verification: TaskVerification = Field(default_factory=TaskVerification)
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)


class ExecutionHints(BaseModel):
    """Plan-level execution hints for partial failure handling."""

    model_config = ConfigDict(extra="forbid")

    min_success_threshold: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of tasks that must succeed for partial success",
    )
    critical_path: list[str] = Field(
        default_factory=list,
        description="Task IDs that must succeed regardless of threshold",
    )


class TaskPlan(BaseModel):
    """Complete task plan produced by the Planning Agent.

    This is a directed acyclic graph (DAG) expressed as JSON.
    Each task is a node. Each dependency is a directed edge.
    Mission Control validates and executes this deterministically.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = "1.0.0"
    mission_id: str
    summary: str
    estimated_cost_usd: float = Field(ge=0.0)
    estimated_duration_seconds: int = Field(ge=0)
    tasks: list[TaskDefinition]
    execution_hints: ExecutionHints = Field(default_factory=ExecutionHints)

    @property
    def task_ids(self) -> list[str]:
        """All task IDs in the plan."""
        return [t.task_id for t in self.tasks]

    def get_task(self, task_id: str) -> TaskDefinition | None:
        """Look up task by ID."""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None
