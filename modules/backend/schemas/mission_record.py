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

    objective_statement: str | None = None
    objective_category: str | None = None
    task_plan_json: dict | None = None
    mission_outcome_json: dict | None = None
    planning_thinking_trace: str | None = None
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
