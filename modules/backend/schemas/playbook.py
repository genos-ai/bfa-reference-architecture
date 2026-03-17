"""
Playbook YAML validation schemas.

Validates playbook structure, step definitions, trigger configuration,
budget limits, output mapping, and context declarations. Used by
PlaybookService at load time to reject invalid playbooks early (P5: Fail Fast).

Each step becomes a Mission at runtime. The output_mapping on each step
defines the anti-corruption layer for inter-mission data flow.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlaybookOutputFieldMapping(BaseModel):
    """Maps a field from a MissionOutcome task result to a named context key."""

    model_config = ConfigDict(extra="forbid")

    source_task: str = Field(
        ...,
        description="Task ID within the MissionOutcome whose output to extract from",
    )
    source_field: str = Field(
        ...,
        description="Field name within the task's output_data to extract",
    )
    target_key: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Context key name for downstream missions",
    )


class PlaybookStepOutputMapping(BaseModel):
    """Output mapping for a playbook step.

    Defines which fields from the step's MissionOutcome are extracted
    and made available to downstream steps. This is the anti-corruption
    layer — downstream missions only see curated context, never raw
    MissionOutcome internals.
    """

    model_config = ConfigDict(extra="forbid")

    summary_key: str | None = Field(
        None,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Store MissionOutcome.result_summary under this context key",
    )
    field_mappings: list[PlaybookOutputFieldMapping] = Field(
        default_factory=list,
        description="Extract specific fields from MissionOutcome task results",
    )


class PlaybookStepSchema(BaseModel):
    """A single step in a playbook workflow.

    Each step becomes a Mission with its own Mission Control instance.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_-]*$",
    )
    description: str | None = Field(None, max_length=500)
    capability: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$",
    )
    roster: str = Field(
        default="default",
        pattern=r"^[a-z][a-z0-9_-]*$",
    )
    complexity_tier: str = Field(
        default="simple",
        pattern=r"^(simple|complex)$",
    )
    cost_ceiling_usd: float | None = Field(None, ge=0.01)
    environment: str = Field(
        default="local",
        pattern=r"^(local|container|sandbox)$",
    )
    input: dict[str, Any] = Field(default_factory=dict)
    output_mapping: PlaybookStepOutputMapping | None = None
    depends_on: list[str] = Field(default_factory=list)
    timeout_seconds: int | None = Field(None, ge=10, le=86400)


class PlaybookTriggerSchema(BaseModel):
    """How and when the playbook is triggered."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        default="on_demand",
        pattern=r"^(on_demand|schedule|event)$",
    )
    schedule: str | None = None
    event_type: str | None = None
    match_patterns: list[str] = Field(default_factory=list)


class PlaybookBudgetSchema(BaseModel):
    """Cost constraints for playbook execution."""

    model_config = ConfigDict(extra="forbid")

    max_cost_usd: float = Field(default=10.00, ge=0.01)
    max_tokens: int | None = Field(None, ge=1000)


class PlaybookObjectiveSchema(BaseModel):
    """Strategic business outcome for the playbook."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(..., min_length=1, max_length=1000)
    category: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_-]*$",
    )
    owner: str = Field(..., min_length=1, max_length=200)
    priority: str = Field(..., pattern=r"^(critical|high|normal|low)$")
    regulatory_reference: str | None = Field(None, max_length=500)


class PlaybookSchema(BaseModel):
    """Root schema for a playbook YAML file."""

    model_config = ConfigDict(extra="forbid")

    playbook_name: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)*\.playbook$",
        description="Unique playbook identifier. Convention: {domain}.{name}.playbook",
    )
    description: str = Field(..., min_length=1, max_length=1000)
    objective: PlaybookObjectiveSchema
    version: int = Field(default=1, ge=1)
    enabled: bool = True
    project_name: str | None = Field(
        None,
        description="Human-readable project name (display only, not used for resolution).",
    )
    trigger: PlaybookTriggerSchema = Field(default_factory=PlaybookTriggerSchema)
    budget: PlaybookBudgetSchema = Field(default_factory=PlaybookBudgetSchema)
    context: dict[str, Any] = Field(default_factory=dict)
    steps: list[PlaybookStepSchema] = Field(..., min_length=1)

    @field_validator("steps")
    @classmethod
    def validate_steps(
        cls, steps: list[PlaybookStepSchema],
    ) -> list[PlaybookStepSchema]:
        """Validate step IDs are unique, deps exist, no cycles."""
        step_ids = {step.id for step in steps}

        # Duplicate IDs
        if len(step_ids) != len(steps):
            seen: set[str] = set()
            dupes = []
            for step in steps:
                if step.id in seen:
                    dupes.append(step.id)
                seen.add(step.id)
            raise ValueError(f"Duplicate step IDs: {dupes}")

        # Dependencies reference existing steps
        for step in steps:
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    raise ValueError(
                        f"Step '{step.id}' depends on '{dep_id}' "
                        f"which does not exist"
                    )

        # Self-dependencies
        for step in steps:
            if step.id in step.depends_on:
                raise ValueError(f"Step '{step.id}' depends on itself")

        # Cycle detection (Kahn's algorithm)
        in_degree: dict[str, int] = {s.id: 0 for s in steps}
        graph: dict[str, list[str]] = {s.id: [] for s in steps}
        for step in steps:
            for dep_id in step.depends_on:
                graph[dep_id].append(step.id)
                in_degree[step.id] += 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        sorted_count = 0
        while queue:
            node = queue.pop(0)
            sorted_count += 1
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if sorted_count != len(steps):
            raise ValueError("Playbook steps contain a dependency cycle")

        # Output mapping target key uniqueness
        target_keys: list[str] = []
        for step in steps:
            if step.output_mapping:
                if step.output_mapping.summary_key:
                    target_keys.append(step.output_mapping.summary_key)
                for fm in step.output_mapping.field_mappings:
                    target_keys.append(fm.target_key)
        if len(target_keys) != len(set(target_keys)):
            raise ValueError(
                "Duplicate output mapping target keys in playbook steps"
            )

        return steps


# =============================================================================
# API Response Schemas
# =============================================================================


class PlaybookListResponse(BaseModel):
    """API response for listing available playbooks."""

    playbook_name: str
    description: str
    version: int
    enabled: bool
    trigger_type: str
    step_count: int
    budget_usd: float
    objective_category: str
    objective_priority: str
    objective_owner: str


class PlaybookDetailResponse(BaseModel):
    """API response for a single playbook with full details."""

    playbook_name: str
    description: str
    objective: PlaybookObjectiveSchema
    version: int
    enabled: bool
    trigger: PlaybookTriggerSchema
    budget: PlaybookBudgetSchema
    context_keys: list[str]
    steps: list[PlaybookStepSchema]
