# Implementation Plan: Playbooks & Missions (Multi-Agent Workflow Composition)

*Created: 2026-03-03*
*Updated: 2026-03-04*
*Status: Done*
*Phase: 8 of 8 (AI-First Platform Build)*
*Depends on: Phase 1-6 (Event Bus, Sessions, Streaming Mission Control, Mission Control Dispatch, Verification Pipeline, Plan Persistence)*
*Optionally uses: Phase 7 (Temporal — for scheduled triggers, crash recovery, durable human-in-the-loop)*
*Blocked by: Phase 6*

---

## Summary

Build the multi-agent workflow composition layer. **Playbooks** are declarative YAML templates that compose agent capabilities into reusable, schedulable, multi-step workflows. Each playbook step becomes a **Mission** — a discrete objective with bounded scope, its own Mission Control instance, and its own agent roster. Missions execute via the Mission Control dispatch loop (Plan 13), producing structured `MissionOutcome` results that flow between missions through the Playbook's anti-corruption layer.

This addresses the agent grouping problem: agents are not grouped into "teams" or "projects." They are **capabilities** composed into **playbooks**. The same agent participates in many playbooks. A playbook declares *what* needs to happen and *which capabilities* are required. The mission layer handles the rest.

**Updated execution hierarchy:**

```
Playbook → Mission(s) → Mission Control → Planning Agent → TaskPlan → Agent(s)
```

Two modes of operation:
- **Playbook-driven (deterministic):** User or schedule triggers a known playbook. System loads YAML, converts steps to Missions, each Mission instantiates Mission Control with the appropriate roster, Planning Agent decomposes into TaskPlan, agents execute. No LLM reasoning needed to assemble the workflow. This is P2 (Deterministic Over Non-Deterministic).
- **Ad-hoc (dynamic):** User gives a freeform goal. Mission Control (Plan 13) reasons about what's needed via the Planning Agent, creates a TaskPlan, delegates. No playbook involved. This is the existing flow.

Mission Control can match incoming requests against known playbooks before falling back to Planning Agent reasoning — deterministic path first, LLM fallback second.

**Multi-team execution:** Each Mission has its own Mission Control instance with its own roster. The Playbook manages inter-mission data flow (anti-corruption layer). Agents in Mission B never access Mission A's agents — they receive only the curated context that the Playbook extracts from Mission A's `MissionOutcome`.

**Dev mode: breaking changes allowed.** This is a new subsystem — no backward-compatibility constraints.

## Context

- Research architecture: `docs/98-research/11-bfa-workflow-architecture-specification.md` (Execution Hierarchy, Mission layer, Playbook layer, inter-mission data flow, multi-team execution)
- Reference architecture: `docs/99-reference-architecture/46-agentic-event-session-architecture.md` (Section 1: Session Model, Section 4: Plan Management)
- Agent organization: `docs/99-reference-architecture/47-agentic-module-organization.md` (agent registry, capability naming, access control, execution modes)
- Agentic architecture: `docs/99-reference-architecture/40-agentic-architecture.md` (Option B: Plan-Centric Assembled Teams, Option D: Hybrid approach)
- PydanticAI implementation: `docs/99-reference-architecture/41-agentic-pydanticai.md` (agent-as-tool delegation, UsageLimits)
- Project principles: `docs/03-principles/01-project-principles.md` — P1 (Infrastructure Before Agents), P2 (Deterministic Over Non-Deterministic), P4 (Scope Is Configuration Not Code), P5 (Streaming Is Default), P10 (Expansion Not Rewrite)
- Plan 13: `docs/97-plans/13-plan-mission-control-dispatch.md` — Mission Control dispatch loop, Planning Agent, TaskPlan, MissionOutcome, agent roster
- Plan 14: `docs/97-plans/14-plan-verification-pipeline.md` — 3-tier verification, check registry, Verification Agent
- Plan 15: `docs/97-plans/15-plan-plan-persistence.md` — mission persistence, task execution records
- Plan 11: Session model. Missions auto-create sessions.
- Plan 10: Event bus. Mission lifecycle events flow through it.
- Capability naming convention: `{category}.{name}` maps to agent `{category}.{name}.agent` in the registry (doc 47)
- Execution mode (doc 47, Dimension 4): `local` (default) or `container` (future). Playbooks declare per-step environment; this plan prepares the data model but does not implement containerization.
- Anti-pattern: Do NOT make playbooks executable code. They are YAML configuration (P4).
- Anti-pattern: Do NOT bypass the Mission Control dispatch loop. Playbook steps become Missions, which instantiate Mission Control, which calls the Planning Agent. Do not create a parallel execution engine.
- Anti-pattern: Do NOT hard-couple missions to specific agents. Use capability references, resolved at mission creation time.
- Anti-pattern: Do NOT store large payloads in the mission context. Store references (file paths, IDs) rather than full data. Keep context under 1MB.
- Anti-pattern: Do NOT allow agents in one Mission to access agents or outputs from another Mission directly. All inter-mission data flows through the Playbook's output mapping.

## What to Build

- `config/settings/playbooks.yaml` — Playbook system configuration (defaults, limits)
- `modules/backend/core/config_schema.py` — `PlaybooksSchema` config schema
- `modules/backend/core/config.py` — Register playbooks config in `AppConfig`
- `modules/backend/schemas/playbook.py` — `PlaybookSchema`, `PlaybookObjectiveSchema`, `PlaybookStepSchema`, `PlaybookTriggerSchema`, `PlaybookBudgetSchema`, `PlaybookStepOutputMapping` Pydantic schemas for validating playbook YAML files
- `modules/backend/services/playbook.py` — `PlaybookService` (load, validate, list, resolve capabilities, convert steps to Mission briefs, manage output mapping)
- `modules/backend/models/mission.py` — NEW: Mission lifecycle entity with `roster_ref`, `complexity_tier`, `upstream_context`, `playbook_run_id`, `playbook_step_id`, `objective`, `cost_ceiling_usd`, `mission_outcome` fields
- `modules/backend/schemas/mission.py` — `MissionCreate`, `MissionResponse`, `MissionDetailResponse`, `MissionStateSummary` Pydantic schemas
- `modules/backend/repositories/mission.py` — `MissionRepository` with status queries, playbook run lookups
- `modules/backend/services/mission.py` — NEW: `MissionService` (create from playbook step as Mission, instantiate Mission Control with roster, track inter-mission data flow, manage output mapping)
- `modules/backend/events/types.py` — Add `PlaybookRunStartedEvent`, `PlaybookRunCompletedEvent`, `PlaybookRunFailedEvent`, `PlaybookMissionCompletedEvent`
- `modules/backend/api/v1/endpoints/playbooks.py` — REST endpoints: list playbooks, get playbook detail, create mission, get mission status, list missions
- `config/playbooks/` — Directory for playbook YAML files
- `config/playbooks/examples/ai-news-digest.yaml` — Example playbook demonstrating full feature set
- Alembic migration for `playbook_runs` table and mission model updates
- Update Mission Control to check playbook matches before Planning Agent fallback
- Tests for playbook loading, validation, capability resolution, mission lifecycle, output mapping, API endpoints

## Key Design Decisions

- **Playbooks are YAML, loaded from `config/playbooks/`** (P4). The PlaybookService scans for `*.yaml` files recursively, validates each against `PlaybookSchema`, and caches results. Playbook identity comes from the `playbook_name` field inside the YAML, not from the file path. This mirrors the agent registry pattern from doc 47.
- **Each playbook step becomes a Mission, not a Plan task.** A playbook step declares an objective, a roster reference, and a complexity tier. The PlaybookService converts each step into a Mission brief. The Mission instantiates Mission Control with the referenced roster. Mission Control calls the Planning Agent to decompose the objective into a TaskPlan. The TaskPlan's tasks are what agents execute. This gives each step the full Mission Control pipeline: planning, execution, verification.
- **Capability resolution is convention-based.** A playbook step declares `capability: content.summarizer`. This resolves to agent `content.summarizer.agent` by appending `.agent`. The resolver validates the agent exists and is enabled in the registry at mission creation time. If resolution fails, the mission fails at creation (P5: Fail Fast).
- **Inter-mission data flows through output mapping (anti-corruption layer).** Each playbook step declares an `output_mapping` that specifies which fields from the step's `MissionOutcome.task_results` are extracted and made available to downstream steps. The Playbook passes curated context to the next Mission as `upstream_context`. Agents in Mission B receive only what their Mission Control provides — they never access Mission A's agents or raw outputs.
- **Each Mission has its own Mission Control instance with its own roster.** Different playbook steps can use different agent rosters. A research step might use `roster: research_team` while a content step uses `roster: content_team`. This enables multi-team workflows where different groups of agents handle different phases.
- **Per-step complexity tier controls Planning Agent thinking budget.** Each step declares `complexity_tier: simple | complex`. Simple missions get a lower thinking budget (faster, cheaper). Complex missions get the full thinking budget. This is passed to Mission Control which configures the Planning Agent accordingly.
- **Per-step cost ceiling enforced by Mission layer.** Each step declares `cost_ceiling_usd`. The Mission layer enforces this ceiling — if the Mission Control dispatch exceeds it, execution is halted. This provides per-step cost control in addition to the overall playbook budget.
- **Missions auto-create sessions.** Every playbook run creates a parent Session (Plan 11) with `goal` set to the playbook's `objective.statement`, `cost_budget_usd` set from the playbook budget, and `agent_id` set to `"playbook:{playbook_name}"`. Each Mission within the run inherits the session. The session tracks cost across all missions. This gives the playbook full session infrastructure (events, cost tracking, channel binding) for free.
- **Three trigger types, phased implementation.** `on_demand` (API call or Mission Control) implemented in this plan. `schedule` (cron via Temporal timers) and `event` (event bus subscription) are declared in the playbook schema but implementation deferred to after Plan 16 (Temporal). The trigger schema is forward-looking — no schema changes needed later.
- **Execution environment is per-step metadata.** Each step can declare `environment: local | container | sandbox`. This plan stores the value in the Mission brief. The Mission Control dispatch loop reads this field when executing tasks. Actual container orchestration is future work — this plan only prepares the data path. All steps execute `local` for now.
- **Playbook matching in Mission Control.** Mission Control's routing logic gains a deterministic fast-path: before calling the Planning Agent for complex requests, check if the input matches a playbook's `trigger.match_patterns` (keyword patterns). If matched, instantiate the playbook directly. This is P2 (Deterministic Over Non-Deterministic).
- **Every playbook requires an Objective.** The Objective is strategic metadata (`statement`, `category`, `owner`, `priority`, optional `regulatory_reference`) declaring the business outcome the playbook achieves. Validated at load time via `PlaybookObjectiveSchema`. The Objective is not an execution layer — it does not affect how missions run. It enables: filtering playbooks by category/priority/owner, audit trail enrichment (objective flows into `MissionRecord`), structured log context (`objective_category`, `objective_priority`, `objective_owner` on playbook/mission spans), and regulatory traceability via `regulatory_reference`. Session `goal` is set from `objective.statement` for human readability.
- **String UUIDs** via `UUIDMixin` for consistency with existing codebase (SQLite test compatibility).
- **Playbook versioning is declarative.** Playbooks have a `version` field. The playbook run records `playbook_version` at creation time. If the playbook is updated, existing running playbook runs continue with their recorded version. New runs use the current version.
- **Example playbook included.** An AI news digest playbook is included as `config/playbooks/examples/ai-news-digest.yaml` to demonstrate the full feature set. It is `enabled: false` by default (its agent capabilities don't exist yet).

## Success Criteria

- [ ] Playbook YAML files load and validate from `config/playbooks/`
- [ ] Playbook schema supports `roster`, `complexity_tier`, `cost_ceiling_usd`, and `output_mapping` per step
- [ ] Capability resolution maps `content.summarizer` to `content.summarizer.agent` and fails fast if agent missing
- [ ] Each playbook step converts to a Mission brief (not a Plan task directly)
- [ ] Mission instantiates Mission Control with the step's referenced roster
- [ ] Mission Control calls Planning Agent to decompose Mission objective into TaskPlan
- [ ] Mission receives MissionOutcome and reports to Playbook
- [ ] Inter-mission data flows through output mapping: Playbook extracts fields from MissionOutcome, passes as upstream_context to next Mission
- [ ] Agents in Mission B never access Mission A's agents or raw outputs
- [ ] Per-step cost ceiling enforced by Mission layer
- [ ] Complexity tier passed to Mission Control, affects Planning Agent thinking budget
- [ ] Playbook run status tracks overall progress across all missions
- [ ] Playbook lifecycle events publish to the event bus
- [ ] API endpoints: list playbooks, create mission, get mission status
- [ ] Mission Control playbook matching triggers deterministic execution for known patterns
- [ ] Execution environment field preserved through mission creation (metadata, not execution)
- [ ] Playbook trigger schema supports `on_demand`, `schedule`, `event` (only `on_demand` implemented)
- [ ] Config loads from `playbooks.yaml` with defaults
- [ ] Example playbook validates successfully
- [ ] Playbook schema requires `objective` with `statement`, `category`, `owner`, `priority` fields
- [ ] Playbook schema validates `priority` against `critical | high | normal | low`
- [ ] `regulatory_reference` is optional (nullable)
- [ ] Example playbook includes a valid `objective` block
- [ ] Session `goal` is set from `objective.statement` (not playbook description)
- [ ] Objective metadata available in `PlaybookListResponse` and `PlaybookDetailResponse`
- [ ] All existing tests still pass (no breaking changes)
- [ ] New tests cover playbook loading, validation, capability resolution, mission lifecycle, output mapping, API endpoints

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Commit any uncommitted work | `git status`, then commit if needed |
| 0.2 | Create feature branch | `git checkout -b feature/playbooks-missions` |

---

### Step 1: Playbook Configuration

**File**: `config/settings/playbooks.yaml` (NEW)

```yaml
# =============================================================================
# Playbook & Mission Configuration
# =============================================================================
# Available options:
#   playbooks_dir              - Directory to scan for playbook YAML files (string)
#   max_steps_per_playbook     - Maximum steps in a single playbook (integer)
#   max_context_size_bytes     - Maximum mission context size in bytes (integer)
#   default_step_timeout_seconds - Default timeout per step if not specified (integer)
#   default_budget_usd         - Default mission budget if not specified in playbook (float)
#   max_budget_usd             - Hard cap on mission budget (float)
#   max_concurrent_missions    - Maximum missions running simultaneously (integer)
#   enable_playbook_matching   - Enable Mission Control playbook matching fast-path (boolean)
# =============================================================================

playbooks_dir: "config/playbooks"
max_steps_per_playbook: 20
max_context_size_bytes: 1048576
default_step_timeout_seconds: 600
default_budget_usd: 10.00
max_budget_usd: 100.00
max_concurrent_missions: 10
enable_playbook_matching: true
```

**File**: `modules/backend/core/config_schema.py` — Add `PlaybooksSchema`:

```python
class PlaybooksSchema(_StrictBase):
    """Playbook and mission system configuration."""

    playbooks_dir: str = "config/playbooks"
    max_steps_per_playbook: int = 20
    max_context_size_bytes: int = 1_048_576  # 1MB
    default_step_timeout_seconds: int = 600
    default_budget_usd: float = 10.00
    max_budget_usd: float = 100.00
    max_concurrent_missions: int = 10
    enable_playbook_matching: bool = True
```

**File**: `modules/backend/core/config.py` — Register in `AppConfig`:

Add `playbooks: PlaybooksSchema` field and load from `config/settings/playbooks.yaml` using the existing `_load_validated_optional()` pattern. Follow the exact pattern used for `sessions` in Plan 11.

```python
self._playbooks = _load_validated_optional(PlaybooksSchema, "playbooks.yaml")
```

Add property:

```python
@property
def playbooks(self) -> PlaybooksSchema:
    """Playbook and mission settings."""
    return self._playbooks
```

**Verification**: `python -c "from modules.backend.core.config import get_app_config; print(get_app_config().playbooks.playbooks_dir)"` — should print `config/playbooks`.

---

### Step 2: Playbook Schema (Pydantic Validation for Playbook YAML)

**File**: `modules/backend/schemas/playbook.py` (NEW)

Pydantic models for validating playbook YAML files. These are NOT API response schemas — they validate the YAML structure at load time. Includes `roster`, `complexity_tier`, `cost_ceiling_usd`, and `output_mapping` fields for the Mission layer.

```python
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
        description="Context key name for downstream missions to reference via @context.<key>",
    )


class PlaybookStepOutputMapping(BaseModel):
    """Output mapping for a playbook step.

    Defines which fields from the step's MissionOutcome are extracted
    and made available to downstream steps. This is the anti-corruption
    layer — downstream missions only see curated context, never raw
    MissionOutcome internals.
    """

    model_config = ConfigDict(extra="forbid")

    # Simple mode: extract the entire MissionOutcome.result_summary as a single key
    summary_key: str | None = Field(
        None,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Store MissionOutcome.result_summary under this context key",
    )

    # Detailed mode: extract specific fields from task results
    field_mappings: list[PlaybookOutputFieldMapping] = Field(
        default_factory=list,
        description="Extract specific fields from MissionOutcome task results",
    )


class PlaybookStepSchema(BaseModel):
    """A single step in a playbook workflow.

    Each step becomes a Mission with its own Mission Control instance.
    The roster determines which agents are available. The complexity_tier
    controls the Planning Agent's thinking budget.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Step identifier, used in depends_on references",
    )
    description: str | None = Field(
        None,
        max_length=500,
        description="Human-readable description of what this step does (becomes Mission objective)",
    )
    capability: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$",
        description="Agent capability to resolve (e.g. 'content.summarizer')",
    )
    roster: str = Field(
        default="default",
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Agent roster reference for this Mission (from config/mission_control/rosters/)",
    )
    complexity_tier: str = Field(
        default="simple",
        pattern=r"^(simple|complex)$",
        description="Mission complexity tier — affects Planning Agent thinking budget",
    )
    cost_ceiling_usd: float | None = Field(
        None,
        ge=0.01,
        description="Per-step cost ceiling enforced by Mission layer (overrides playbook default)",
    )
    environment: str = Field(
        default="local",
        pattern=r"^(local|container|sandbox)$",
        description="Execution environment for this step",
    )
    input: dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters. Values starting with @context. are resolved at runtime",
    )
    output_mapping: PlaybookStepOutputMapping | None = Field(
        None,
        description="How to extract outputs from this step's MissionOutcome for downstream steps",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="List of step IDs that must complete before this step",
    )
    timeout_seconds: int | None = Field(
        None,
        ge=10,
        le=86400,
        description="Step timeout override (default from config)",
    )


class PlaybookTriggerSchema(BaseModel):
    """How and when the playbook is triggered."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        default="on_demand",
        pattern=r"^(on_demand|schedule|event)$",
        description="Trigger type",
    )
    schedule: str | None = Field(
        None,
        description="Cron expression (required when type=schedule)",
    )
    event_type: str | None = Field(
        None,
        description="Event type to trigger on (required when type=event)",
    )
    match_patterns: list[str] = Field(
        default_factory=list,
        description="Keywords for Mission Control playbook matching (P2 deterministic fast-path)",
    )


class PlaybookBudgetSchema(BaseModel):
    """Cost constraints for playbook execution."""

    model_config = ConfigDict(extra="forbid")

    max_cost_usd: float = Field(
        default=10.00,
        ge=0.01,
        description="Maximum total cost for a single playbook run (sum of all missions)",
    )
    max_tokens: int | None = Field(
        None,
        ge=1000,
        description="Maximum total tokens across all missions (optional)",
    )


class PlaybookObjectiveSchema(BaseModel):
    """Strategic business outcome for the playbook.

    The Objective declares why this playbook exists — what business outcome
    it achieves, who is accountable, and how it maps to regulatory
    requirements. This is metadata, not an execution layer.
    """

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Human-readable business outcome this playbook achieves",
    )
    category: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Classification for grouping/filtering (e.g. 'compliance', 'security_remediation', 'incident_response')",
    )
    owner: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Accountable person or role (e.g. 'group-ciso', 'iam-programme-lead')",
    )
    priority: str = Field(
        ...,
        pattern=r"^(critical|high|normal|low)$",
        description="Objective priority: critical, high, normal, or low",
    )
    regulatory_reference: str | None = Field(
        None,
        max_length=500,
        description="Optional link to regulatory framework (e.g. 'Basel III Pillar 2, BCBS 239')",
    )


class PlaybookSchema(BaseModel):
    """Root schema for a playbook YAML file.

    Validates the complete playbook definition including steps, triggers,
    budget, output mapping, and context. All validation happens at load
    time — a playbook that passes validation is guaranteed to be
    structurally correct.

    Each step becomes a Mission at runtime. The Playbook manages
    inter-mission data flow via output_mapping on each step.
    """

    model_config = ConfigDict(extra="forbid")

    playbook_name: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)+$",
        description="Unique playbook identifier (dot-notation, e.g. 'research.ai-news-digest')",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Human-readable description of what this playbook does",
    )
    objective: PlaybookObjectiveSchema = Field(
        ...,
        description="Strategic business outcome — required metadata declaring why this playbook exists",
    )
    version: int = Field(
        default=1,
        ge=1,
        description="Playbook version, recorded in playbook run for traceability",
    )
    enabled: bool = Field(
        default=True,
        description="Disabled playbooks are not listed or matchable",
    )
    trigger: PlaybookTriggerSchema = Field(
        default_factory=PlaybookTriggerSchema,
        description="Trigger configuration",
    )
    budget: PlaybookBudgetSchema = Field(
        default_factory=PlaybookBudgetSchema,
        description="Cost constraints (total across all missions)",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Initial context available to all steps via @context references",
    )
    steps: list[PlaybookStepSchema] = Field(
        ...,
        min_length=1,
        description="Ordered list of workflow steps (each becomes a Mission)",
    )

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps: list[PlaybookStepSchema]) -> list[PlaybookStepSchema]:
        """Validate step IDs are unique and dependencies reference existing steps."""
        step_ids = {step.id for step in steps}

        # Check for duplicate IDs
        if len(step_ids) != len(steps):
            seen = set()
            dupes = []
            for step in steps:
                if step.id in seen:
                    dupes.append(step.id)
                seen.add(step.id)
            raise ValueError(f"Duplicate step IDs: {dupes}")

        # Check dependencies reference existing steps
        for step in steps:
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    raise ValueError(
                        f"Step '{step.id}' depends on '{dep_id}' which does not exist"
                    )

        # Check for self-dependencies
        for step in steps:
            if step.id in step.depends_on:
                raise ValueError(f"Step '{step.id}' depends on itself")

        # Check for cycles using topological sort (Kahn's algorithm)
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

        # Check output mapping target keys are unique across steps
        target_keys: list[str] = []
        for step in steps:
            if step.output_mapping:
                if step.output_mapping.summary_key:
                    target_keys.append(step.output_mapping.summary_key)
                for fm in step.output_mapping.field_mappings:
                    target_keys.append(fm.target_key)
        if len(target_keys) != len(set(target_keys)):
            raise ValueError("Duplicate output mapping target keys in playbook steps")

        return steps


class PlaybookListResponse(BaseModel):
    """API response for listing available playbooks."""

    playbook_name: str
    description: str
    version: int
    enabled: bool
    trigger_type: str
    step_count: int
    budget_usd: float


class PlaybookDetailResponse(BaseModel):
    """API response for a single playbook with full details."""

    playbook_name: str
    description: str
    version: int
    enabled: bool
    trigger: PlaybookTriggerSchema
    budget: PlaybookBudgetSchema
    context_keys: list[str]
    steps: list[PlaybookStepSchema]
```

**Key notes**:
- `extra="forbid"` on all schemas catches typos in YAML (P5: Fail Fast)
- Step ID pattern (`^[a-z][a-z0-9_-]*$`) enforces clean identifiers
- Capability pattern enforces dot-notation matching agent naming convention
- Cycle detection in `validate_steps` prevents invalid DAGs at load time, before missions are created
- Output mapping target key uniqueness prevents ambiguous `@context.*` references downstream
- `PlaybookListResponse` and `PlaybookDetailResponse` are API response schemas (not YAML validation schemas)
- `PlaybookStepOutputMapping` replaces the old `output` key and `@steps.*.output` syntax — the Playbook now explicitly declares which MissionOutcome fields flow to downstream missions
- `roster` and `complexity_tier` per step enable multi-team workflows with varying Planning Agent budgets

---

### Step 3: Playbook Service

**File**: `modules/backend/services/playbook.py` (NEW)

Service that loads, validates, caches, and resolves playbooks. Does NOT extend `BaseService` — it reads from the filesystem and agent registry, not from the database. Updated to convert steps into Mission briefs rather than Plan tasks.

```python
"""
Playbook Service.

Loads playbook YAML files from config/playbooks/, validates against
PlaybookSchema, resolves capability references to agent names, and
generates Mission briefs from playbook steps.

This service is stateless — it reads from the filesystem and agent
registry. It does not touch the database.

Each playbook step becomes a Mission brief rather than a Plan task.
Mission Control handles the decomposition into TaskPlan tasks via
the Planning Agent.
"""

from pathlib import Path
from typing import Any

import yaml

from modules.backend.core.config import find_project_root, get_app_config
from modules.backend.core.logging import get_logger
from modules.backend.schemas.playbook import PlaybookSchema, PlaybookStepSchema

logger = get_logger(__name__)


class PlaybookService:
    """Load, validate, and resolve playbooks from config/playbooks/.

    Thread-safe. Playbooks are loaded fresh on each call (no stale cache).
    For hot-reload: call load_playbooks() again.
    """

    def __init__(self, agent_registry: dict[str, Any] | None = None) -> None:
        """Initialize with optional agent registry for capability resolution.

        Args:
            agent_registry: Dict mapping agent_name -> agent config dict.
                           If None, resolution scans config/agents/ directly.
        """
        self._project_root = find_project_root()
        self._agent_registry = agent_registry
        self._playbooks: dict[str, PlaybookSchema] = {}

    def load_playbooks(self) -> dict[str, PlaybookSchema]:
        """Load all playbook YAML files from the configured directory.

        Scans recursively for *.yaml files, validates each against
        PlaybookSchema, and returns a dict keyed by playbook_name.
        Invalid playbooks are logged and skipped (not fatal).

        Returns:
            Dict mapping playbook_name -> PlaybookSchema
        """
        app_config = get_app_config()
        playbooks_dir = self._project_root / app_config.playbooks.playbooks_dir

        if not playbooks_dir.exists():
            logger.warning(
                "Playbooks directory not found",
                extra={"path": str(playbooks_dir)},
            )
            return {}

        loaded: dict[str, PlaybookSchema] = {}

        for yaml_path in sorted(playbooks_dir.rglob("*.yaml")):
            try:
                raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if not raw or not isinstance(raw, dict):
                    continue

                playbook = PlaybookSchema(**raw)

                if playbook.playbook_name in loaded:
                    logger.warning(
                        "Duplicate playbook name, skipping",
                        extra={
                            "playbook_name": playbook.playbook_name,
                            "path": str(yaml_path),
                            "existing_path": "already loaded",
                        },
                    )
                    continue

                # Validate step count against config
                max_steps = app_config.playbooks.max_steps_per_playbook
                if len(playbook.steps) > max_steps:
                    logger.warning(
                        "Playbook exceeds max steps, skipping",
                        extra={
                            "playbook_name": playbook.playbook_name,
                            "step_count": len(playbook.steps),
                            "max_steps": max_steps,
                        },
                    )
                    continue

                # Validate budget against config cap
                max_budget = app_config.playbooks.max_budget_usd
                if playbook.budget.max_cost_usd > max_budget:
                    logger.warning(
                        "Playbook budget exceeds system cap, capping",
                        extra={
                            "playbook_name": playbook.playbook_name,
                            "requested": playbook.budget.max_cost_usd,
                            "capped_to": max_budget,
                        },
                    )
                    playbook.budget.max_cost_usd = max_budget

                loaded[playbook.playbook_name] = playbook

                logger.debug(
                    "Playbook loaded",
                    extra={
                        "playbook_name": playbook.playbook_name,
                        "version": playbook.version,
                        "steps": len(playbook.steps),
                        "enabled": playbook.enabled,
                    },
                )

            except Exception as e:
                logger.warning(
                    "Failed to load playbook",
                    extra={"path": str(yaml_path), "error": str(e)},
                )
                continue

        self._playbooks = loaded
        logger.info(
            "Playbooks loaded",
            extra={"count": len(loaded), "names": list(loaded.keys())},
        )
        return loaded

    def list_playbooks(self, enabled_only: bool = True) -> list[PlaybookSchema]:
        """List available playbooks.

        Args:
            enabled_only: If True, filter to enabled playbooks only.

        Returns:
            List of PlaybookSchema objects.
        """
        if not self._playbooks:
            self.load_playbooks()

        playbooks = list(self._playbooks.values())
        if enabled_only:
            playbooks = [p for p in playbooks if p.enabled]
        return playbooks

    def get_playbook(self, playbook_name: str) -> PlaybookSchema | None:
        """Get a specific playbook by name.

        Returns None if not found or disabled.
        """
        if not self._playbooks:
            self.load_playbooks()
        return self._playbooks.get(playbook_name)

    def resolve_capability(self, capability: str) -> str:
        """Resolve a capability string to an agent name.

        Convention: capability 'content.summarizer' resolves to
        agent 'content.summarizer.agent'.

        If agent_registry was provided, checks against it.
        Otherwise, scans config/agents/ for the agent YAML.

        Returns:
            The resolved agent_name string.

        Raises:
            ValueError: If no agent found for the capability.
        """
        agent_name = f"{capability}.agent"

        if self._agent_registry is not None:
            if agent_name not in self._agent_registry:
                raise ValueError(
                    f"No agent found for capability '{capability}' "
                    f"(expected agent '{agent_name}' in registry)"
                )
            agent_config = self._agent_registry[agent_name]
            if not agent_config.get("enabled", True):
                raise ValueError(
                    f"Agent '{agent_name}' for capability '{capability}' is disabled"
                )
            return agent_name

        # Fallback: scan config/agents/ for the agent YAML
        agents_dir = self._project_root / "config" / "agents"
        if not agents_dir.exists():
            raise ValueError(
                f"No agent found for capability '{capability}' "
                f"(agents directory not found)"
            )

        for yaml_path in agents_dir.rglob("agent.yaml"):
            try:
                raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if raw and raw.get("agent_name") == agent_name:
                    if not raw.get("enabled", True):
                        raise ValueError(
                            f"Agent '{agent_name}' for capability '{capability}' "
                            f"is disabled"
                        )
                    return agent_name
            except yaml.YAMLError:
                continue

        raise ValueError(
            f"No agent found for capability '{capability}' "
            f"(expected agent '{agent_name}')"
        )

    def validate_playbook_capabilities(
        self, playbook: PlaybookSchema
    ) -> list[str]:
        """Validate that all capabilities in a playbook resolve to agents.

        Returns:
            List of error messages. Empty list means all capabilities resolve.
        """
        errors: list[str] = []
        for step in playbook.steps:
            try:
                self.resolve_capability(step.capability)
            except ValueError as e:
                errors.append(f"Step '{step.id}': {e}")
        return errors

    def generate_mission_briefs(
        self, playbook: PlaybookSchema
    ) -> list[dict[str, Any]]:
        """Convert playbook steps into Mission brief definitions.

        Each step becomes a Mission brief with:
        - objective: step description (becomes mission brief for Planning Agent)
        - roster_ref: which agent roster to use for this Mission's Mission Control
        - complexity_tier: simple/complex (affects Planning Agent thinking budget)
        - cost_ceiling_usd: per-mission cost ceiling
        - capability: resolved agent capability (primary agent for this mission)
        - environment: execution environment
        - input_context: step input with @context references preserved
        - output_mapping: how to extract outputs for downstream missions
        - dependencies: which prior steps must complete first
        - timeout_seconds: mission timeout

        The Mission Control dispatch loop (Plan 13) handles the actual
        decomposition into TaskPlan tasks via the Planning Agent.

        Returns:
            List of mission brief dicts for the MissionService.
        """
        # Build step index map for dependency resolution
        step_index_map: dict[str, int] = {}
        for i, step in enumerate(playbook.steps):
            step_index_map[step.id] = i

        briefs: list[dict[str, Any]] = []
        app_config = get_app_config()

        for i, step in enumerate(playbook.steps):
            # Resolve capability to agent name
            agent_name = self.resolve_capability(step.capability)

            # Build mission brief
            brief: dict[str, Any] = {
                "step_id": step.id,
                "objective": step.description or f"Execute: {step.id}",
                "primary_capability": step.capability,
                "resolved_agent": agent_name,
                "roster_ref": step.roster,
                "complexity_tier": step.complexity_tier,
                "cost_ceiling_usd": (
                    step.cost_ceiling_usd
                    or app_config.playbooks.default_budget_usd
                ),
                "environment": step.environment,
                "input_context": dict(step.input),
                "output_mapping": (
                    step.output_mapping.model_dump()
                    if step.output_mapping
                    else None
                ),
                "timeout_seconds": (
                    step.timeout_seconds
                    or app_config.playbooks.default_step_timeout_seconds
                ),
                "dependencies": [
                    {
                        "depends_on_step": dep_id,
                        "depends_on_index": step_index_map.get(dep_id),
                    }
                    for dep_id in step.depends_on
                ],
                "sort_order": i,
            }

            briefs.append(brief)

        return briefs

    def match_playbook(self, user_input: str) -> PlaybookSchema | None:
        """Match user input against playbook trigger patterns.

        Used by Mission Control for deterministic fast-path routing (P2).
        Returns the first matching enabled playbook, or None.

        Matching is case-insensitive keyword containment.
        """
        if not self._playbooks:
            self.load_playbooks()

        input_lower = user_input.lower()

        for playbook in self._playbooks.values():
            if not playbook.enabled:
                continue
            if not playbook.trigger.match_patterns:
                continue

            for pattern in playbook.trigger.match_patterns:
                if pattern.lower() in input_lower:
                    logger.info(
                        "Playbook matched by pattern",
                        extra={
                            "playbook_name": playbook.playbook_name,
                            "pattern": pattern,
                        },
                    )
                    return playbook

        return None

    def resolve_upstream_context(
        self,
        step: PlaybookStepSchema,
        completed_outcomes: dict[str, dict],
        playbook_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build upstream_context for a Mission from completed prior missions.

        The Playbook is the anti-corruption layer: it extracts specific
        fields from prior MissionOutcomes via output_mapping and merges
        them with the playbook's initial context. The resulting dict
        becomes the Mission's upstream_context, which Mission Control
        passes to the Planning Agent.

        Args:
            step: The playbook step about to execute.
            completed_outcomes: Dict mapping step_id -> extracted outputs dict
                               for all completed prior steps (already resolved
                               via output_mapping by the MissionService).
            playbook_context: The playbook's initial context dict.

        Returns:
            Merged upstream_context dict for this Mission.
        """
        upstream: dict[str, Any] = dict(playbook_context)

        # Merge extracted outputs from completed dependencies
        for dep_id in step.depends_on:
            if dep_id in completed_outcomes:
                upstream.update(completed_outcomes[dep_id])

        # Resolve @context.* references in step input
        resolved_input: dict[str, Any] = {}
        for key, value in step.input.items():
            if isinstance(value, str) and value.startswith("@context."):
                context_key = value[len("@context."):]
                if context_key in upstream:
                    resolved_input[key] = upstream[context_key]
                else:
                    logger.warning(
                        "Unresolved @context reference in step input",
                        extra={
                            "step_id": step.id,
                            "reference": value,
                            "available_keys": list(upstream.keys()),
                        },
                    )
                    resolved_input[key] = value  # Leave unresolved
            else:
                resolved_input[key] = value

        # Add resolved input to upstream context
        upstream["_step_input"] = resolved_input

        return upstream
```

**Key implementation notes**:
- `load_playbooks()` is called lazily and can be re-called for hot-reload
- Invalid playbooks are logged and skipped, not fatal — a broken playbook shouldn't prevent the system from starting
- `generate_mission_briefs()` replaces the old `generate_plan_tasks()` — each step becomes a Mission brief, not a Plan task. The Mission Control dispatch loop (Plan 13) handles TaskPlan decomposition via the Planning Agent.
- `resolve_upstream_context()` implements the anti-corruption layer — it merges prior mission outputs (already extracted via output_mapping) with the playbook context and resolves `@context.*` references in step input
- `match_playbook()` is intentionally simple (keyword containment). Complex matching belongs in the Planning Agent (LLM), not here (P2)
- The service does NOT extend `BaseService` — it has no database dependency

---

### Step 4: Mission Model Updates

**File**: `modules/backend/models/mission.py` — NEW

Create the Mission lifecycle entity. This is distinct from `MissionRecord` (Plan 15) which stores execution artifacts. The Mission model tracks the lifecycle state of a playbook-initiated mission: pending, running, completed, failed, cancelled. Fields: `playbook_run_id`, `playbook_step_id`, `objective`, `roster_ref`, `complexity_tier`, `upstream_context`, `cost_ceiling_usd`, `mission_outcome`.

```python
"""
Mission Model (Updated for Playbook Integration).

A mission is a discrete objective with bounded scope. When created by a
Playbook, each mission has its own roster, complexity tier, and upstream
context. The Mission instantiates Mission Control with these parameters.

Missions created by Playbooks have a playbook_run_id linking them to
their parent PlaybookRun. Ad-hoc missions (from direct API calls) have
no playbook_run_id.
"""

import enum

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class MissionState(str, enum.Enum):
    """Mission lifecycle status.

    Transitions:
        pending -> running (execution started)
        running -> completed (all tasks done)
        running -> failed (unrecoverable error)
        running -> cancelled (user cancelled)
        pending -> cancelled (cancelled before start)
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid transitions for mission status state machine
VALID_MISSION_TRANSITIONS: dict[MissionState, set[MissionState]] = {
    MissionState.PENDING: {MissionState.RUNNING, MissionState.CANCELLED},
    MissionState.RUNNING: {
        MissionState.COMPLETED,
        MissionState.FAILED,
        MissionState.CANCELLED,
    },
    MissionState.COMPLETED: set(),  # terminal
    MissionState.FAILED: set(),  # terminal
    MissionState.CANCELLED: set(),  # terminal
}


class MissionTriggerType(str, enum.Enum):
    """How the mission was triggered."""

    ON_DEMAND = "on_demand"
    SCHEDULE = "schedule"
    EVENT = "event"
    PLAYBOOK = "playbook"


class Mission(UUIDMixin, TimestampMixin, Base):
    """A runtime mission — a discrete objective with bounded scope.

    When created by a Playbook, the mission has a roster_ref, complexity_tier,
    and upstream_context that configure its Mission Control instance.
    """

    __tablename__ = "missions"

    # Playbook run reference (null for ad-hoc missions)
    playbook_run_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
        comment="Parent PlaybookRun ID (null for ad-hoc missions)",
    )
    playbook_step_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Which playbook step this mission corresponds to",
    )

    # Mission brief
    objective: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Mission objective (from playbook step description or ad-hoc goal)",
    )

    # Roster and complexity (set by Playbook, default for ad-hoc)
    roster_ref: Mapped[str] = mapped_column(
        String(100),
        default="default",
        nullable=False,
        comment="Agent roster reference (from config/mission_control/rosters/)",
    )
    complexity_tier: Mapped[str] = mapped_column(
        String(20),
        default="simple",
        nullable=False,
        comment="Mission complexity tier: simple or complex",
    )

    # Status
    status: Mapped[str] = mapped_column(
        Enum(MissionState, native_enum=False),
        default=MissionState.PENDING,
        nullable=False,
        index=True,
    )

    # Session reference
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
        comment="Session for this mission",
    )

    # Trigger info
    trigger_type: Mapped[str] = mapped_column(
        Enum(MissionTriggerType, native_enum=False),
        default=MissionTriggerType.ON_DEMAND,
        nullable=False,
    )
    triggered_by: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Who/what triggered: 'user:<id>', 'schedule', 'playbook:<name>'",
    )

    # Context: upstream context from Playbook + accumulated during execution
    upstream_context: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Curated context from Playbook (prior mission outputs via output_mapping)",
    )
    context: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Runtime context accumulated during execution",
    )

    # Cost tracking
    total_cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    cost_ceiling_usd: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Per-mission cost ceiling (from playbook step or default)",
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

    # Error info (if failed)
    error_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Error details if mission failed",
    )

    # Mission outcome (serialized MissionOutcome from Mission Control dispatch)
    mission_outcome: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Serialized MissionOutcome from Mission Control dispatch loop",
    )

    # Results summary (if completed)
    result_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable summary of mission results",
    )

    def __repr__(self) -> str:
        return (
            f"<Mission(id={self.id}, objective={self.objective[:50]!r}, "
            f"status={self.status}, roster={self.roster_ref})>"
        )
```

**File**: `modules/backend/models/__init__.py` — Add import:

```python
from modules.backend.models.mission import Mission
```

This registers the model with Alembic for autogenerate.

**Adapter notes**:
- Uses `JSON` (via `sqlalchemy.dialects.sqlite`) for `context`, `upstream_context`, `error_data`, and `mission_outcome` — works with both PostgreSQL (JSONB) and SQLite (text JSON) for test compatibility
- `started_at`, `completed_at` stored as ISO strings rather than DateTime — matches Plan 15 pattern
- `session_id` FK to `sessions` table (Plan 11)
- `playbook_run_id` links to the `playbook_runs` table (new in this plan)
- `VALID_MISSION_TRANSITIONS` dict mirrors the session/task status pattern
- `MissionTriggerType` gains a `PLAYBOOK` value for missions created by playbook runs
- `roster_ref` and `complexity_tier` are passed to Mission Control at instantiation time
- `upstream_context` holds the curated context from the Playbook's output mapping — this is what Mission Control passes to the Planning Agent as upstream context
- `mission_outcome` stores the serialized MissionOutcome from the dispatch loop, used by the Playbook to extract outputs via output_mapping

---

### Step 5: Mission Schemas

**File**: `modules/backend/schemas/mission.py` (NEW)

```python
"""
Mission API schemas.

Request/response models for mission CRUD, status reporting,
and playbook-to-mission conversion.
"""

from pydantic import BaseModel, ConfigDict, Field


class MissionCreate(BaseModel):
    """Create an ad-hoc mission (not from a playbook)."""

    objective: str = Field(
        ...,
        description="Mission objective",
    )
    roster_ref: str = Field(
        default="default",
        description="Agent roster reference",
    )
    complexity_tier: str = Field(
        default="simple",
        description="Mission complexity tier: simple or complex",
    )
    triggered_by: str = Field(
        default="user:anonymous",
        description="Who triggered: 'user:<id>', 'api'",
    )
    cost_ceiling_usd: float | None = Field(
        None,
        description="Per-mission cost ceiling",
    )
    upstream_context: dict | None = Field(
        None,
        description="Upstream context for the Planning Agent",
    )


class MissionResponse(BaseModel):
    """API response for a mission."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    playbook_run_id: str | None
    playbook_step_id: str | None
    objective: str
    roster_ref: str
    complexity_tier: str
    status: str
    session_id: str
    trigger_type: str
    triggered_by: str
    total_cost_usd: float
    cost_ceiling_usd: float | None
    started_at: str | None
    completed_at: str | None
    created_at: str
    updated_at: str


class MissionDetailResponse(BaseModel):
    """Detailed mission response with context and results."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    playbook_run_id: str | None
    playbook_step_id: str | None
    objective: str
    roster_ref: str
    complexity_tier: str
    status: str
    session_id: str
    trigger_type: str
    triggered_by: str
    upstream_context: dict
    context: dict
    total_cost_usd: float
    cost_ceiling_usd: float | None
    started_at: str | None
    completed_at: str | None
    result_summary: str | None
    error_data: dict | None
    created_at: str
    updated_at: str


class MissionStateSummary(BaseModel):
    """Mission progress summary."""

    mission_id: str
    objective: str
    status: str
    roster_ref: str
    total_cost_usd: float
    cost_ceiling_usd: float | None
    started_at: str | None
    elapsed_seconds: float | None
```

---

### Step 6: Mission Repository

**File**: `modules/backend/repositories/mission.py` (NEW)

```python
"""
Mission Repository.

Standard CRUD plus mission-specific queries: lookup by playbook run,
active mission count, and status filtering.
"""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.models.mission import Mission, MissionState
from modules.backend.repositories.base import BaseRepository

logger = get_logger(__name__)


class MissionRepository(BaseRepository[Mission]):
    """Mission repository with workflow-specific queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Mission, session)

    async def get_by_session(self, session_id: str) -> list[Mission]:
        """Get all missions for a session."""
        stmt = (
            select(Mission)
            .where(Mission.session_id == session_id)
            .order_by(Mission.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_playbook_run(
        self,
        playbook_run_id: str,
    ) -> list[Mission]:
        """Get all missions for a specific playbook run."""
        stmt = (
            select(Mission)
            .where(Mission.playbook_run_id == playbook_run_id)
            .order_by(Mission.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_active(self) -> int:
        """Count currently running missions (for concurrency limits)."""
        stmt = (
            select(func.count())
            .select_from(Mission)
            .where(
                Mission.status.in_([
                    MissionState.PENDING,
                    MissionState.RUNNING,
                ])
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_missions(
        self,
        status: MissionState | None = None,
        playbook_run_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Mission], int]:
        """List missions with optional filters and pagination.

        Returns:
            Tuple of (missions, total_count).
        """
        conditions = []
        if status:
            conditions.append(Mission.status == status)
        if playbook_run_id:
            conditions.append(Mission.playbook_run_id == playbook_run_id)

        # Count query
        count_stmt = select(func.count()).select_from(Mission)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.session.execute(count_stmt)).scalar_one()

        # Data query
        data_stmt = (
            select(Mission)
            .order_by(Mission.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if conditions:
            data_stmt = data_stmt.where(and_(*conditions))

        result = await self.session.execute(data_stmt)
        return list(result.scalars().all()), total
```

---

### Step 7: Mission Service

**File**: `modules/backend/services/mission.py` — NEW

This is the core of the system — it bridges playbooks, Mission Control, sessions, and agents. Creates and manages Mission lifecycle, instantiates Mission Control with the appropriate roster and complexity tier, and manages inter-mission data flow via the Playbook's output mapping.

```python
"""
Mission Service.

Orchestrates mission lifecycle: creates missions from playbook steps,
instantiates Mission Control with the appropriate roster, tracks
MissionOutcome results, and manages inter-mission data flow.

This service bridges PlaybookService (YAML), Mission Control (Plan 13),
SessionService (Plan 11), and the event bus (Plan 10).

Key flow:
  Playbook step -> Mission brief -> MissionService.create_mission()
  -> Mission Control instantiated with roster_ref + complexity_tier
  -> Planning Agent decomposes objective into TaskPlan
  -> Agents execute tasks
  -> MissionOutcome returned to MissionService
  -> Playbook extracts outputs via output_mapping
  -> Downstream Mission receives curated upstream_context
"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.config import get_app_config
from modules.backend.core.exceptions import NotFoundError, ValidationError
from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now
from modules.backend.models.mission import (
    Mission,
    MissionState,
    MissionTriggerType,
    VALID_MISSION_TRANSITIONS,
)
from modules.backend.repositories.mission import MissionRepository
from modules.backend.services.base import BaseService
from modules.backend.services.playbook import PlaybookService

logger = get_logger(__name__)


class MissionService(BaseService):
    """Mission lifecycle management.

    Accepts service dependencies via constructor injection.
    Mission Control dispatch and SessionService are optional to allow
    incremental adoption — if not provided, the corresponding features
    are skipped.
    """

    def __init__(
        self,
        session: AsyncSession,
        playbook_service: PlaybookService,
        mission_control_dispatch: Any | None = None,
        session_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        super().__init__(session)
        self._mission_repo = MissionRepository(session)
        self._playbook_service = playbook_service
        self._mission_control_dispatch = mission_control_dispatch
        self._session_service = session_service
        self._event_bus = event_bus

    async def _publish_event(self, event: Any) -> None:
        """Publish event to session event bus (best-effort)."""
        if self._event_bus is None:
            return
        try:
            await self._event_bus.publish(event)
        except Exception:
            logger.warning(
                "Failed to publish mission event",
                extra={"event_type": getattr(event, "event_type", "unknown")},
            )

    # ---- Mission creation ----

    async def create_mission_from_step(
        self,
        playbook_run_id: str,
        step_id: str,
        objective: str,
        roster_ref: str,
        complexity_tier: str,
        cost_ceiling_usd: float,
        upstream_context: dict,
        session_id: str,
        environment: str = "local",
    ) -> Mission:
        """Create a mission from a playbook step.

        This is called by the PlaybookRunService for each step
        in the playbook. The mission is created with the step's
        roster, complexity tier, cost ceiling, and upstream context.

        Args:
            playbook_run_id: Parent PlaybookRun ID.
            step_id: Playbook step ID this mission corresponds to.
            objective: Mission objective (from step description).
            roster_ref: Agent roster reference for Mission Control.
            complexity_tier: simple or complex.
            cost_ceiling_usd: Per-mission cost ceiling.
            upstream_context: Curated context from prior missions.
            session_id: Session ID for this mission.
            environment: Execution environment.

        Returns:
            Created Mission instance.
        """

        async def _create() -> Mission:
            # Check concurrency limits
            app_config = get_app_config()
            active_count = await self._mission_repo.count_active()
            if active_count >= app_config.playbooks.max_concurrent_missions:
                raise ValidationError(
                    message=(
                        f"Maximum concurrent missions "
                        f"({app_config.playbooks.max_concurrent_missions}) "
                        f"reached. {active_count} currently active."
                    ),
                )

            # Create mission
            mission = Mission(
                playbook_run_id=playbook_run_id,
                playbook_step_id=step_id,
                objective=objective,
                roster_ref=roster_ref,
                complexity_tier=complexity_tier,
                status=MissionState.PENDING,
                session_id=session_id,
                trigger_type=MissionTriggerType.PLAYBOOK,
                triggered_by=f"playbook_run:{playbook_run_id}",
                upstream_context=upstream_context,
                context={},
                total_cost_usd=0.0,
                cost_ceiling_usd=cost_ceiling_usd,
            )
            self._session.add(mission)
            await self._session.flush()
            await self._session.refresh(mission)

            logger.info(
                "Mission created from playbook step",
                extra={
                    "mission_id": mission.id,
                    "playbook_run_id": playbook_run_id,
                    "step_id": step_id,
                    "roster_ref": roster_ref,
                    "complexity_tier": complexity_tier,
                    "cost_ceiling_usd": cost_ceiling_usd,
                },
            )

            return mission

        return await self._execute_db_operation("create_mission_from_step", _create)

    async def create_adhoc_mission(
        self,
        objective: str,
        triggered_by: str,
        roster_ref: str = "default",
        complexity_tier: str = "simple",
        cost_ceiling_usd: float | None = None,
        upstream_context: dict | None = None,
    ) -> Mission:
        """Create an ad-hoc mission (not from a playbook).

        Args:
            objective: Mission objective.
            triggered_by: Who/what triggered (e.g. 'user:123').
            roster_ref: Agent roster reference.
            complexity_tier: simple or complex.
            cost_ceiling_usd: Per-mission cost ceiling.
            upstream_context: Optional upstream context.

        Returns:
            Created Mission instance.
        """

        async def _create() -> Mission:
            app_config = get_app_config()

            # Check concurrency limits
            active_count = await self._mission_repo.count_active()
            if active_count >= app_config.playbooks.max_concurrent_missions:
                raise ValidationError(
                    message=(
                        f"Maximum concurrent missions "
                        f"({app_config.playbooks.max_concurrent_missions}) "
                        f"reached. {active_count} currently active."
                    ),
                )

            # Create session (auto)
            session_id = None
            if self._session_service:
                from modules.backend.schemas.session import SessionCreate

                session_data = SessionCreate(
                    goal=objective,
                    agent_id="mission:adhoc",
                    cost_budget_usd=cost_ceiling_usd or app_config.playbooks.default_budget_usd,
                    metadata={"mission_type": "adhoc"},
                )
                session_response = await self._session_service.create_session(
                    session_data
                )
                session_id = str(session_response.id)
            else:
                from uuid import uuid4

                session_id = str(uuid4())
                logger.warning(
                    "SessionService not available, using placeholder session_id",
                    extra={"session_id": session_id},
                )

            mission = Mission(
                objective=objective,
                roster_ref=roster_ref,
                complexity_tier=complexity_tier,
                status=MissionState.PENDING,
                session_id=session_id,
                trigger_type=MissionTriggerType.ON_DEMAND,
                triggered_by=triggered_by,
                upstream_context=upstream_context or {},
                context={},
                total_cost_usd=0.0,
                cost_ceiling_usd=cost_ceiling_usd or app_config.playbooks.default_budget_usd,
            )
            self._session.add(mission)
            await self._session.flush()
            await self._session.refresh(mission)

            logger.info(
                "Ad-hoc mission created",
                extra={
                    "mission_id": mission.id,
                    "session_id": session_id,
                    "roster_ref": roster_ref,
                },
            )

            return mission

        return await self._execute_db_operation("create_adhoc_mission", _create)

    # ---- Mission execution ----

    async def execute_mission(self, mission_id: str) -> Mission:
        """Execute a mission by instantiating Mission Control with the
        appropriate roster and dispatching.

        Steps:
        1. Transition to RUNNING
        2. Instantiate Mission Control with roster_ref and complexity_tier
        3. Pass objective + upstream_context to Mission Control dispatch
        4. Receive MissionOutcome
        5. Store outcome, transition to COMPLETED or FAILED

        Returns:
            Updated Mission instance with outcome.
        """
        mission = await self._get_mission(mission_id)
        self._validate_transition(mission, MissionState.RUNNING)

        mission.status = MissionState.RUNNING
        mission.started_at = utc_now().isoformat()
        await self._session.flush()

        if self._mission_control_dispatch is None:
            logger.warning(
                "Mission Control dispatch not available, mission stays in RUNNING",
                extra={"mission_id": mission_id},
            )
            return mission

        try:
            # Instantiate Mission Control with this mission's roster and complexity
            outcome = await self._mission_control_dispatch.execute(
                mission_brief=mission.objective,
                roster_ref=mission.roster_ref,
                complexity_tier=mission.complexity_tier,
                upstream_context=mission.upstream_context,
                cost_ceiling_usd=mission.cost_ceiling_usd,
                session_id=mission.session_id,
            )

            # Store outcome
            mission.mission_outcome = (
                outcome if isinstance(outcome, dict) else outcome.model_dump()
            )
            mission.total_cost_usd = (
                outcome.get("total_cost_usd", 0.0)
                if isinstance(outcome, dict)
                else getattr(outcome, "total_cost_usd", 0.0)
            )
            mission.result_summary = (
                outcome.get("summary", None)
                if isinstance(outcome, dict)
                else getattr(outcome, "summary", None)
            )

            # Check cost ceiling
            if (
                mission.cost_ceiling_usd
                and mission.total_cost_usd > mission.cost_ceiling_usd
            ):
                logger.warning(
                    "Mission exceeded cost ceiling",
                    extra={
                        "mission_id": mission_id,
                        "cost": mission.total_cost_usd,
                        "ceiling": mission.cost_ceiling_usd,
                    },
                )

            # Determine success
            success = (
                outcome.get("success", False)
                if isinstance(outcome, dict)
                else getattr(outcome, "success", False)
            )
            if success:
                mission.status = MissionState.COMPLETED
            else:
                mission.status = MissionState.FAILED
                mission.error_data = {
                    "message": "Mission Control dispatch returned failure",
                    "outcome_summary": mission.result_summary,
                }

            mission.completed_at = utc_now().isoformat()
            await self._session.flush()

        except Exception as e:
            mission.status = MissionState.FAILED
            mission.completed_at = utc_now().isoformat()
            mission.error_data = {"message": str(e), "type": type(e).__name__}
            await self._session.flush()

            logger.error(
                "Mission execution failed",
                extra={"mission_id": mission_id, "error": str(e)},
            )

        return mission

    # ---- Mission lifecycle ----

    async def complete_mission(self, mission_id: str) -> Mission:
        """Mark mission as completed."""
        mission = await self._get_mission(mission_id)
        self._validate_transition(mission, MissionState.COMPLETED)

        mission.status = MissionState.COMPLETED
        mission.completed_at = utc_now().isoformat()
        await self._session.flush()

        logger.info(
            "Mission completed",
            extra={"mission_id": mission_id, "cost": mission.total_cost_usd},
        )

        return mission

    async def fail_mission(
        self,
        mission_id: str,
        error: str,
        error_data: dict | None = None,
    ) -> Mission:
        """Mark mission as failed."""
        mission = await self._get_mission(mission_id)
        self._validate_transition(mission, MissionState.FAILED)

        mission.status = MissionState.FAILED
        mission.completed_at = utc_now().isoformat()
        mission.error_data = error_data or {"message": error}
        await self._session.flush()

        logger.error(
            "Mission failed",
            extra={"mission_id": mission_id, "error": error},
        )

        return mission

    async def cancel_mission(self, mission_id: str, reason: str) -> Mission:
        """Cancel a mission."""
        mission = await self._get_mission(mission_id)
        self._validate_transition(mission, MissionState.CANCELLED)

        mission.status = MissionState.CANCELLED
        mission.completed_at = utc_now().isoformat()
        mission.error_data = {"cancelled_reason": reason}
        await self._session.flush()

        logger.info(
            "Mission cancelled",
            extra={"mission_id": mission_id, "reason": reason},
        )

        return mission

    # ---- Output extraction (anti-corruption layer) ----

    def extract_outputs(
        self,
        mission: Mission,
        output_mapping: dict | None,
    ) -> dict[str, Any]:
        """Extract outputs from a completed mission's MissionOutcome
        according to the playbook step's output_mapping.

        This implements the anti-corruption layer: downstream missions
        only see the specific fields the Playbook declares, not the
        full MissionOutcome.

        Args:
            mission: Completed mission with mission_outcome populated.
            output_mapping: The playbook step's output_mapping dict
                          (from PlaybookStepOutputMapping.model_dump()).

        Returns:
            Dict of extracted outputs keyed by target_key.
        """
        if not output_mapping or not mission.mission_outcome:
            return {}

        extracted: dict[str, Any] = {}
        outcome = mission.mission_outcome

        # Extract summary if requested
        summary_key = output_mapping.get("summary_key")
        if summary_key:
            extracted[summary_key] = (
                outcome.get("summary") or mission.result_summary
            )

        # Extract specific fields from task results
        field_mappings = output_mapping.get("field_mappings", [])
        task_results = outcome.get("task_results", {})

        for mapping in field_mappings:
            source_task = mapping["source_task"]
            source_field = mapping["source_field"]
            target_key = mapping["target_key"]

            if source_task in task_results:
                task_output = task_results[source_task]
                if isinstance(task_output, dict) and source_field in task_output:
                    extracted[target_key] = task_output[source_field]
                else:
                    logger.warning(
                        "Output mapping source field not found in task result",
                        extra={
                            "mission_id": mission.id,
                            "source_task": source_task,
                            "source_field": source_field,
                        },
                    )
            else:
                logger.warning(
                    "Output mapping source task not found in MissionOutcome",
                    extra={
                        "mission_id": mission.id,
                        "source_task": source_task,
                    },
                )

        return extracted

    # ---- Status and queries ----

    async def get_mission(self, mission_id: str) -> Mission:
        """Get a mission by ID."""
        return await self._get_mission(mission_id)

    async def list_missions(
        self,
        status: str | None = None,
        playbook_run_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Mission], int]:
        """List missions with optional filters."""
        mission_status = MissionState(status) if status else None
        return await self._mission_repo.list_missions(
            status=mission_status,
            playbook_run_id=playbook_run_id,
            limit=limit,
            offset=offset,
        )

    # ---- Internal helpers ----

    async def _get_mission(self, mission_id: str) -> Mission:
        """Get mission or raise NotFoundError."""
        mission = await self._mission_repo.get(mission_id)
        if not mission:
            raise NotFoundError(
                message=f"Mission '{mission_id}' not found",
            )
        return mission

    def _validate_transition(
        self, mission: Mission, new_status: MissionState
    ) -> None:
        """Validate mission status transition."""
        current = MissionState(mission.status)
        allowed = VALID_MISSION_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise ValidationError(
                message=(
                    f"Cannot transition mission from '{current.value}' "
                    f"to '{new_status.value}'. "
                    f"Allowed: {[s.value for s in allowed]}"
                ),
            )
```

**Key implementation notes**:
- `create_mission_from_step()` creates a mission with playbook-specific parameters (roster, complexity tier, cost ceiling, upstream context). Called by the playbook execution flow for each step.
- `create_adhoc_mission()` creates a standalone mission not tied to a playbook. Used for direct API calls or Mission Control dispatch.
- `execute_mission()` is the main execution flow: it transitions the mission to RUNNING, instantiates Mission Control with the mission's roster and complexity tier, passes the objective and upstream context, and stores the MissionOutcome.
- `extract_outputs()` implements the anti-corruption layer: it reads the step's output_mapping and extracts specific fields from the MissionOutcome for downstream missions.
- The service accepts `mission_control_dispatch` as an optional dependency — this allows the mission system to be tested independently and adopted incrementally.

---

### Step 8: Playbook Events

**File**: `modules/backend/events/types.py` — Add playbook event types after the existing events:

```python
# --- Playbook events ---

class PlaybookRunStartedEvent(SessionEvent):
    event_type: str = "playbook.run.started"
    playbook_run_id: str
    playbook_name: str
    playbook_version: int
    step_count: int
    trigger_type: str
    triggered_by: str


class PlaybookMissionStartedEvent(SessionEvent):
    event_type: str = "playbook.mission.started"
    playbook_run_id: str
    mission_id: str
    step_id: str
    roster_ref: str
    complexity_tier: str


class PlaybookMissionCompletedEvent(SessionEvent):
    event_type: str = "playbook.mission.completed"
    playbook_run_id: str
    mission_id: str
    step_id: str
    success: bool
    cost_usd: float = 0.0


class PlaybookRunCompletedEvent(SessionEvent):
    event_type: str = "playbook.run.completed"
    playbook_run_id: str
    playbook_name: str
    total_cost_usd: float
    mission_count: int
    elapsed_seconds: float | None = None
    result_summary: str | None = None


class PlaybookRunFailedEvent(SessionEvent):
    event_type: str = "playbook.run.failed"
    playbook_run_id: str
    playbook_name: str
    error: str
    failed_step: str | None = None
    total_cost_usd: float = 0.0
```

**File**: `modules/backend/events/schemas.py` — Register new event types in the event type registry (follow the existing pattern):

```python
# Playbook events
"playbook.run.started": PlaybookRunStartedEvent,
"playbook.mission.started": PlaybookMissionStartedEvent,
"playbook.mission.completed": PlaybookMissionCompletedEvent,
"playbook.run.completed": PlaybookRunCompletedEvent,
"playbook.run.failed": PlaybookRunFailedEvent,
```

---

### Step 9: API Endpoints

**File**: `modules/backend/api/v1/endpoints/playbooks.py` (NEW)

```python
"""
Playbook and Mission API endpoints.

Provides endpoints for listing playbooks, creating missions,
and monitoring mission status. All endpoints follow the standard API
response envelope from doc 09.
"""

from fastapi import APIRouter, Depends

from modules.backend.core.dependencies import DbSession, RequestId
from modules.backend.core.exceptions import NotFoundError
from modules.backend.schemas.base import ApiResponse
from modules.backend.schemas.mission import (
    MissionCreate,
    MissionDetailResponse,
    MissionResponse,
    MissionStateSummary,
)
from modules.backend.schemas.playbook import PlaybookDetailResponse, PlaybookListResponse
from modules.backend.services.mission import MissionService
from modules.backend.services.playbook import PlaybookService

router = APIRouter()


def _get_playbook_service() -> PlaybookService:
    """Get PlaybookService instance."""
    return PlaybookService()


def _get_mission_service(db: DbSession) -> MissionService:
    """Get MissionService instance with dependencies."""
    playbook_service = PlaybookService()
    return MissionService(
        session=db,
        playbook_service=playbook_service,
    )


# ---- Playbook endpoints ----


@router.get("", response_model=ApiResponse)
async def list_playbooks(
    request_id: RequestId,
    enabled_only: bool = True,
) -> ApiResponse:
    """List available playbooks."""
    service = _get_playbook_service()
    playbooks = service.list_playbooks(enabled_only=enabled_only)

    items = [
        PlaybookListResponse(
            playbook_name=p.playbook_name,
            description=p.description,
            version=p.version,
            enabled=p.enabled,
            trigger_type=p.trigger.type,
            step_count=len(p.steps),
            budget_usd=p.budget.max_cost_usd,
        )
        for p in playbooks
    ]

    return ApiResponse(
        success=True,
        data={"playbooks": [item.model_dump() for item in items]},
        metadata={"request_id": request_id, "count": len(items)},
    )


@router.get("/{playbook_name}", response_model=ApiResponse)
async def get_playbook(
    playbook_name: str,
    request_id: RequestId,
) -> ApiResponse:
    """Get a specific playbook with full details."""
    service = _get_playbook_service()
    playbook = service.get_playbook(playbook_name)

    if not playbook:
        raise NotFoundError(
            message=f"Playbook '{playbook_name}' not found",
        )

    detail = PlaybookDetailResponse(
        playbook_name=playbook.playbook_name,
        description=playbook.description,
        version=playbook.version,
        enabled=playbook.enabled,
        trigger=playbook.trigger,
        budget=playbook.budget,
        context_keys=list(playbook.context.keys()),
        steps=playbook.steps,
    )

    return ApiResponse(
        success=True,
        data=detail.model_dump(),
        metadata={"request_id": request_id},
    )


# ---- Mission endpoints ----


@router.post("/missions", response_model=ApiResponse)
async def create_mission(
    data: MissionCreate,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Create and start an ad-hoc mission."""
    service = _get_mission_service(db)

    mission = await service.create_adhoc_mission(
        objective=data.objective,
        triggered_by=data.triggered_by,
        roster_ref=data.roster_ref,
        complexity_tier=data.complexity_tier,
        cost_ceiling_usd=data.cost_ceiling_usd,
        upstream_context=data.upstream_context,
    )

    response = MissionResponse.model_validate(mission)
    return ApiResponse(
        success=True,
        data=response.model_dump(),
        metadata={"request_id": request_id},
    )


@router.get("/missions", response_model=ApiResponse)
async def list_missions(
    db: DbSession,
    request_id: RequestId,
    status: str | None = None,
    playbook_run_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ApiResponse:
    """List missions with optional filters."""
    service = _get_mission_service(db)
    missions, total = await service.list_missions(
        status=status,
        playbook_run_id=playbook_run_id,
        limit=limit,
        offset=offset,
    )

    items = [MissionResponse.model_validate(m).model_dump() for m in missions]

    return ApiResponse(
        success=True,
        data={"missions": items, "total": total},
        metadata={"request_id": request_id},
    )


@router.get("/missions/{mission_id}", response_model=ApiResponse)
async def get_mission(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Get detailed mission info including context and results."""
    service = _get_mission_service(db)
    mission = await service.get_mission(mission_id)

    response = MissionDetailResponse.model_validate(mission)
    return ApiResponse(
        success=True,
        data=response.model_dump(),
        metadata={"request_id": request_id},
    )


@router.post("/missions/{mission_id}/cancel", response_model=ApiResponse)
async def cancel_mission(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
    reason: str = "User cancelled",
) -> ApiResponse:
    """Cancel a running or pending mission."""
    service = _get_mission_service(db)
    mission = await service.cancel_mission(mission_id, reason=reason)

    response = MissionResponse.model_validate(mission)
    return ApiResponse(
        success=True,
        data=response.model_dump(),
        metadata={"request_id": request_id},
    )
```

**File**: `modules/backend/api/v1/__init__.py` — Register the router:

Add the playbooks router to the v1 API router following the existing pattern for notes and agents endpoints:

```python
from modules.backend.api.v1.endpoints import playbooks

# Playbook and mission endpoints
router.include_router(playbooks.router, prefix="/playbooks", tags=["playbooks"])
```

---

### Step 10: Mission Control Integration (Playbook Matching Fast-Path)

**File**: `modules/backend/agents/mission_control/mission_control.py` — Add playbook matching

Mission Control gains a deterministic fast-path that checks incoming requests against playbook trigger patterns before falling back to the Planning Agent. This implements P2 (Deterministic Over Non-Deterministic).

Add to Mission Control's routing logic, before the LLM-based routing:

```python
# In Mission Control's handle() or route() method, add BEFORE the existing
# rule-based and LLM routing:

async def _try_playbook_match(self, user_input: str, session_id: str) -> dict | None:
    """Check if user input matches a known playbook (P2: deterministic fast-path).

    Returns a routing decision dict if matched, None otherwise.
    """
    app_config = get_app_config()
    if not app_config.playbooks.enable_playbook_matching:
        return None

    playbook_service = PlaybookService(agent_registry=self._registry)
    matched = playbook_service.match_playbook(user_input)

    if not matched:
        return None

    logger.info(
        "Playbook matched, creating playbook run",
        extra={
            "playbook": matched.playbook_name,
            "user_input": user_input[:200],
        },
    )

    # Return a routing decision that Mission Control handles
    return {
        "route_type": "playbook",
        "playbook_name": matched.playbook_name,
        "playbook": matched,
    }
```

**Integration point**: Mission Control's main `handle()` method checks playbook match first:

```python
async def handle(self, user_input, session_id, ...):
    # 1. Deterministic: check playbook match (P2)
    playbook_match = await self._try_playbook_match(user_input, session_id)
    if playbook_match:
        return await self._execute_playbook_run(playbook_match, session_id, ...)

    # 2. Deterministic: check keyword routing rules (existing)
    matched_agent = self._rule_based_route(user_input)
    if matched_agent:
        return await self._execute_agent(matched_agent, user_input, ...)

    # 3. Non-deterministic: Planning Agent routing (existing)
    return await self._planning_agent_route(user_input, session_id, ...)
```

**Important**: The exact integration depends on Mission Control's structure from Plan 12/13. The implementing agent should read the current Mission Control code and adapt this pattern to fit. The key principle is: **playbook match happens first, before any LLM call.**

---

### Step 11: Database Migration

Create an Alembic migration for the updated `missions` table (adding playbook-specific fields) and the new `playbook_runs` table.

**Command**: `cd modules/backend && alembic revision --autogenerate -m "add_playbook_runs_and_update_missions"`

The migration should:

1. Add `playbook_runs` table:
   - `id` (String(36), primary key)
   - `playbook_name` (String(200), indexed)
   - `playbook_version` (Integer)
   - `status` (String/Enum, indexed)
   - `session_id` (String(36), FK to sessions, indexed)
   - `trigger_type` (String/Enum)
   - `triggered_by` (String(200))
   - `context` (JSON) — initial playbook context
   - `total_cost_usd` (Float)
   - `budget_usd` (Float, nullable)
   - `started_at` (String(30), nullable)
   - `completed_at` (String(30), nullable)
   - `error_data` (JSON, nullable)
   - `result_summary` (Text, nullable)
   - `created_at` (String(30))
   - `updated_at` (String(30))

2. Update `missions` table with new columns:
   - `playbook_run_id` (String(36), FK to playbook_runs, nullable, indexed)
   - `playbook_step_id` (String(100), nullable)
   - `objective` (Text, not null)
   - `roster_ref` (String(100), default "default")
   - `complexity_tier` (String(20), default "simple")
   - `upstream_context` (JSON)
   - `cost_ceiling_usd` (Float, nullable)
   - `mission_outcome` (JSON, nullable)

**Note**: The `sessions` table must exist before this migration runs (Plan 11). If it doesn't exist yet, make the FKs nullable or remove them temporarily and add them in a later migration.

**Verification**: `alembic upgrade head` completes without errors.

---

### Step 12: Example Playbook

**Directory**: Create `config/playbooks/` and `config/playbooks/examples/`

**File**: `config/playbooks/examples/ai-news-digest.yaml` (NEW)

```yaml
# =============================================================================
# Example Playbook: AI News Digest
# =============================================================================
# Curates, summarizes, and delivers AI news from thought leaders.
# This playbook demonstrates: multi-mission workflow, per-step rosters,
# complexity tiers, output mapping, and inter-mission data flow.
#
# NOTE: This playbook is disabled by default. The referenced agent
# capabilities (research.scraper, content.summarizer, etc.) do not
# exist yet. Enable once the agents are built.
#
# Execution hierarchy:
#   Playbook (this file)
#     -> Mission 1: scrape (roster: research_team, simple)
#       -> Mission Control -> Planning Agent -> TaskPlan -> research.scraper.agent
#     -> Mission 2: summarize (roster: content_team, complex)
#       -> Mission Control -> Planning Agent -> TaskPlan -> content.summarizer.agent
#     -> Mission 3: extract-actions (roster: content_team, simple)
#     -> Mission 4: format (roster: content_team, simple)
#     -> Mission 5: deliver (roster: delivery_team, simple)
# =============================================================================

playbook_name: research.ai-news-digest
description: "Curate, summarize, and deliver AI news from thought leaders"
objective:
  statement: "Keep engineering team informed of AI developments that may affect platform architecture decisions"
  category: research
  owner: engineering-lead
  priority: normal
  regulatory_reference: null
version: 1
enabled: false

trigger:
  type: on_demand
  # Future: type: schedule, schedule: "0 8 * * *"
  match_patterns:
    - "ai news"
    - "ai digest"
    - "news digest"
    - "ai updates"

budget:
  max_cost_usd: 5.00
  max_tokens: 500000

context:
  sources:
    - name: "Simon Willison"
      url: "https://simonwillison.net/atom/everything/"
      type: rss
    - name: "Andrej Karpathy"
      url: "https://karpathy.ai/"
      type: blog
  delivery_channels:
    - telegram
  max_articles: 20
  summary_style: "concise, actionable, technical"

steps:
  - id: scrape
    description: "Fetch content from curated source list"
    capability: research.scraper
    roster: research_team
    complexity_tier: simple
    cost_ceiling_usd: 0.50
    environment: container
    input:
      sources: "@context.sources"
      max_articles: "@context.max_articles"
    output_mapping:
      field_mappings:
        - source_task: scrape_articles
          source_field: articles
          target_key: raw_articles
    timeout_seconds: 600

  - id: summarize
    description: "Synthesize articles into key learnings and takeaways"
    capability: content.summarizer
    roster: content_team
    complexity_tier: complex
    cost_ceiling_usd: 2.00
    environment: local
    input:
      articles: "@context.raw_articles"
      style: "@context.summary_style"
    output_mapping:
      summary_key: summaries_summary
      field_mappings:
        - source_task: summarize_articles
          source_field: summaries
          target_key: summaries
    depends_on:
      - scrape

  - id: extract-actions
    description: "Identify actionable takeaways and recommendations"
    capability: content.analyst
    roster: content_team
    complexity_tier: simple
    cost_ceiling_usd: 0.50
    environment: local
    input:
      summaries: "@context.summaries"
    output_mapping:
      field_mappings:
        - source_task: analyze_content
          source_field: actions
          target_key: actions
    depends_on:
      - summarize

  - id: format
    description: "Format digest for delivery channels"
    capability: content.formatter
    roster: content_team
    complexity_tier: simple
    cost_ceiling_usd: 0.50
    environment: local
    input:
      summaries: "@context.summaries"
      actions: "@context.actions"
      channels: "@context.delivery_channels"
    output_mapping:
      field_mappings:
        - source_task: format_digest
          source_field: formatted_content
          target_key: formatted_digest
    depends_on:
      - summarize
      - extract-actions

  - id: deliver
    description: "Send formatted digest via configured channels"
    capability: comms.dispatcher
    roster: delivery_team
    complexity_tier: simple
    cost_ceiling_usd: 0.10
    environment: local
    input:
      content: "@context.formatted_digest"
      channels: "@context.delivery_channels"
    depends_on:
      - format
```

**Verification**: The example playbook should load and validate successfully via PlaybookService (even though it's disabled and its agents don't exist):

```python
service = PlaybookService()
playbooks = service.load_playbooks()
assert "research.ai-news-digest" in playbooks
playbook = playbooks["research.ai-news-digest"]
assert playbook.enabled is False
assert len(playbook.steps) == 5
assert playbook.steps[0].roster == "research_team"
assert playbook.steps[1].complexity_tier == "complex"
assert playbook.steps[0].output_mapping is not None
```

---

### Step 13: Tests

Create tests following the existing test patterns. Tests use real PostgreSQL with transaction rollback (P12).

**File**: `tests/unit/backend/services/test_playbook_service.py` (NEW)

```python
"""
Tests for PlaybookService.

Tests playbook loading, validation, capability resolution,
mission brief generation, output mapping, and playbook matching.
"""

import pytest
from pathlib import Path

import yaml

from modules.backend.schemas.playbook import PlaybookSchema
from modules.backend.services.playbook import PlaybookService


class TestPlaybookLoading:
    """Test playbook YAML loading and validation."""

    def test_load_valid_playbook(self, tmp_path: Path) -> None:
        """Valid playbook YAML loads and validates."""
        playbook_yaml = {
            "playbook_name": "test.example",
            "description": "Test playbook",
            "version": 1,
            "enabled": True,
            "steps": [
                {
                    "id": "step-one",
                    "capability": "test.agent",
                    "roster": "default",
                    "complexity_tier": "simple",
                    "input": {"key": "value"},
                    "output_mapping": {
                        "summary_key": "result",
                    },
                },
            ],
        }

        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text(yaml.dump(playbook_yaml))

        playbook = PlaybookSchema(**playbook_yaml)
        assert playbook.playbook_name == "test.example"
        assert len(playbook.steps) == 1
        assert playbook.steps[0].id == "step-one"
        assert playbook.steps[0].roster == "default"
        assert playbook.steps[0].complexity_tier == "simple"

    def test_reject_duplicate_step_ids(self) -> None:
        """Playbooks with duplicate step IDs are rejected."""
        with pytest.raises(ValueError, match="Duplicate step IDs"):
            PlaybookSchema(
                playbook_name="test.dupes",
                description="Has dupes",
                steps=[
                    {"id": "step-a", "capability": "test.agent"},
                    {"id": "step-a", "capability": "test.other"},
                ],
            )

    def test_reject_cycle_in_dependencies(self) -> None:
        """Playbooks with dependency cycles are rejected."""
        with pytest.raises(ValueError, match="dependency cycle"):
            PlaybookSchema(
                playbook_name="test.cycle",
                description="Has cycle",
                steps=[
                    {"id": "step-a", "capability": "test.agent", "depends_on": ["step-b"]},
                    {"id": "step-b", "capability": "test.agent", "depends_on": ["step-a"]},
                ],
            )

    def test_reject_missing_dependency(self) -> None:
        """Dependencies referencing non-existent steps are rejected."""
        with pytest.raises(ValueError, match="does not exist"):
            PlaybookSchema(
                playbook_name="test.missing-dep",
                description="Missing dep",
                steps=[
                    {"id": "step-a", "capability": "test.agent", "depends_on": ["step-z"]},
                ],
            )

    def test_reject_self_dependency(self) -> None:
        """Steps depending on themselves are rejected."""
        with pytest.raises(ValueError, match="depends on itself"):
            PlaybookSchema(
                playbook_name="test.self-dep",
                description="Self dep",
                steps=[
                    {"id": "step-a", "capability": "test.agent", "depends_on": ["step-a"]},
                ],
            )

    def test_reject_duplicate_output_mapping_keys(self) -> None:
        """Duplicate output mapping target keys across steps are rejected."""
        with pytest.raises(ValueError, match="Duplicate output mapping target keys"):
            PlaybookSchema(
                playbook_name="test.dupe-output",
                description="Dupe output mapping",
                steps=[
                    {
                        "id": "step-a",
                        "capability": "test.agent",
                        "output_mapping": {"summary_key": "result"},
                    },
                    {
                        "id": "step-b",
                        "capability": "test.agent",
                        "output_mapping": {"summary_key": "result"},
                    },
                ],
            )

    def test_extra_fields_rejected(self) -> None:
        """Typos in YAML keys are caught by extra=forbid."""
        with pytest.raises(ValueError):
            PlaybookSchema(
                playbook_name="test.typo",
                description="Has typo",
                unknown_field="oops",
                steps=[
                    {"id": "step-a", "capability": "test.agent"},
                ],
            )

    def test_roster_and_complexity_defaults(self) -> None:
        """Steps default to roster='default' and complexity_tier='simple'."""
        playbook = PlaybookSchema(
            playbook_name="test.defaults",
            description="Test defaults",
            steps=[
                {"id": "step-a", "capability": "test.agent"},
            ],
        )
        assert playbook.steps[0].roster == "default"
        assert playbook.steps[0].complexity_tier == "simple"
        assert playbook.steps[0].cost_ceiling_usd is None

    def test_invalid_complexity_tier_rejected(self) -> None:
        """Invalid complexity_tier values are rejected."""
        with pytest.raises(ValueError):
            PlaybookSchema(
                playbook_name="test.bad-tier",
                description="Bad tier",
                steps=[
                    {
                        "id": "step-a",
                        "capability": "test.agent",
                        "complexity_tier": "medium",
                    },
                ],
            )


class TestCapabilityResolution:
    """Test capability-to-agent resolution."""

    def test_resolve_with_registry(self) -> None:
        """Capability resolves to agent name via registry."""
        registry = {
            "content.summarizer.agent": {
                "agent_name": "content.summarizer.agent",
                "enabled": True,
            },
        }
        service = PlaybookService(agent_registry=registry)
        result = service.resolve_capability("content.summarizer")
        assert result == "content.summarizer.agent"

    def test_resolve_missing_raises(self) -> None:
        """Missing capability raises ValueError."""
        registry = {}
        service = PlaybookService(agent_registry=registry)
        with pytest.raises(ValueError, match="No agent found"):
            service.resolve_capability("nonexistent.agent")

    def test_resolve_disabled_raises(self) -> None:
        """Disabled agent raises ValueError."""
        registry = {
            "test.disabled.agent": {
                "agent_name": "test.disabled.agent",
                "enabled": False,
            },
        }
        service = PlaybookService(agent_registry=registry)
        with pytest.raises(ValueError, match="disabled"):
            service.resolve_capability("test.disabled")


class TestMissionBriefGeneration:
    """Test conversion of playbook steps to mission briefs."""

    def test_generate_briefs_from_steps(self) -> None:
        """Playbook steps convert to mission brief dicts."""
        registry = {
            "test.step-one.agent": {"agent_name": "test.step-one.agent", "enabled": True},
            "test.step-two.agent": {"agent_name": "test.step-two.agent", "enabled": True},
        }
        service = PlaybookService(agent_registry=registry)

        playbook = PlaybookSchema(
            playbook_name="test.pipeline",
            description="Test pipeline",
            steps=[
                {
                    "id": "step-one",
                    "capability": "test.step-one",
                    "roster": "research_team",
                    "complexity_tier": "complex",
                    "cost_ceiling_usd": 5.0,
                    "input": {"key": "value"},
                    "output_mapping": {"summary_key": "result_one"},
                },
                {
                    "id": "step-two",
                    "capability": "test.step-two",
                    "roster": "content_team",
                    "input": {"data": "@context.result_one"},
                    "depends_on": ["step-one"],
                },
            ],
        )

        briefs = service.generate_mission_briefs(playbook)

        assert len(briefs) == 2
        assert briefs[0]["step_id"] == "step-one"
        assert briefs[0]["roster_ref"] == "research_team"
        assert briefs[0]["complexity_tier"] == "complex"
        assert briefs[0]["cost_ceiling_usd"] == 5.0
        assert briefs[0]["resolved_agent"] == "test.step-one.agent"
        assert briefs[0]["dependencies"] == []

        assert briefs[1]["step_id"] == "step-two"
        assert briefs[1]["roster_ref"] == "content_team"
        assert briefs[1]["complexity_tier"] == "simple"  # default
        assert len(briefs[1]["dependencies"]) == 1
        assert briefs[1]["dependencies"][0]["depends_on_step"] == "step-one"


class TestPlaybookMatching:
    """Test deterministic playbook matching (P2)."""

    def test_match_by_pattern(self) -> None:
        """User input matching trigger patterns returns the playbook."""
        registry = {}
        service = PlaybookService(agent_registry=registry)

        playbook = PlaybookSchema(
            playbook_name="test.digest",
            description="Test digest",
            trigger={"type": "on_demand", "match_patterns": ["ai news", "ai digest"]},
            steps=[{"id": "step-one", "capability": "test.agent"}],
        )
        service._playbooks = {"test.digest": playbook}

        result = service.match_playbook("Show me the latest ai news")
        assert result is not None
        assert result.playbook_name == "test.digest"

    def test_no_match(self) -> None:
        """User input not matching any pattern returns None."""
        service = PlaybookService()
        service._playbooks = {}

        result = service.match_playbook("Tell me about the weather")
        assert result is None

    def test_disabled_playbook_not_matched(self) -> None:
        """Disabled playbooks are not matched."""
        service = PlaybookService()
        playbook = PlaybookSchema(
            playbook_name="test.disabled",
            description="Disabled",
            enabled=False,
            trigger={"type": "on_demand", "match_patterns": ["test"]},
            steps=[{"id": "step-one", "capability": "test.agent"}],
        )
        service._playbooks = {"test.disabled": playbook}

        result = service.match_playbook("test something")
        assert result is None
```

**File**: `tests/unit/backend/services/test_mission_service.py` (NEW)

Tests for MissionService with real database. The implementing agent should write tests covering:

1. **Mission creation from playbook step** — verify mission created with roster_ref, complexity_tier, cost_ceiling_usd, upstream_context
2. **Ad-hoc mission creation** — verify session created, mission row persisted with defaults
3. **Mission state machine** — verify valid transitions (pending->running->completed), reject invalid ones (completed->running)
4. **Mission execution** — verify Mission Control dispatch called with correct roster and complexity tier
5. **Output extraction** — verify `extract_outputs()` extracts correct fields from MissionOutcome via output_mapping
6. **Cost ceiling enforcement** — verify warning logged when mission exceeds cost ceiling
7. **Concurrency limit** — verify creation fails when max concurrent missions reached
8. **Cancel mission** — verify pending and running missions can be cancelled
9. **Inter-mission data flow** — verify upstream_context correctly curated from prior mission outputs

Follow the existing test patterns from `tests/unit/backend/services/` and `tests/unit/backend/repositories/`. Use real PostgreSQL with transaction rollback (P12). Use `TestModel` for any agent interactions (P11).

**File**: `tests/unit/backend/api/test_playbooks_api.py` (NEW)

Tests for the playbook and mission API endpoints. Follow the existing pattern from `tests/unit/backend/api/test_health.py`. Test:

1. `GET /api/v1/playbooks` — returns list of enabled playbooks
2. `GET /api/v1/playbooks/{name}` — returns playbook detail
3. `GET /api/v1/playbooks/{name}` with missing name — returns 404
4. `POST /api/v1/playbooks/missions` — creates an ad-hoc mission
5. `GET /api/v1/playbooks/missions` — lists missions
6. `GET /api/v1/playbooks/missions/{id}` — returns mission detail
7. `POST /api/v1/playbooks/missions/{id}/cancel` — cancels mission

---

### Step 14: Feature Flag

**File**: `modules/backend/core/config_schema.py` — Add to `FeaturesSchema`:

```python
playbooks_enabled: bool = False
```

**File**: `config/settings/features.yaml` — Add:

```yaml
playbooks_enabled: false
```

The playbook system is behind a feature flag. When disabled:
- `GET /api/v1/playbooks` returns empty list
- `POST /api/v1/playbooks/missions` returns 403
- Mission Control playbook matching is skipped
- No playbook YAML files are loaded

This follows the existing feature flag pattern (events, sessions, etc.) and allows the playbook system to be deployed without activating it.

---

### Step 15: Verification

Run the full test suite to verify no regressions:

```bash
# Run all existing tests
python cli.py --service test --test-type all

# Run only playbook/mission tests
pytest tests/unit/backend/services/test_playbook_service.py -v
pytest tests/unit/backend/services/test_mission_service.py -v
pytest tests/unit/backend/api/test_playbooks_api.py -v

# Verify config loads
python -c "
from modules.backend.core.config import get_app_config
config = get_app_config()
print('playbooks_dir:', config.playbooks.playbooks_dir)
print('playbooks_enabled:', config.features.playbooks_enabled)
"

# Verify playbook loads
python -c "
from modules.backend.services.playbook import PlaybookService
service = PlaybookService()
playbooks = service.load_playbooks()
print(f'Loaded {len(playbooks)} playbooks')
for name, pb in playbooks.items():
    print(f'  {name} (v{pb.version}, {len(pb.steps)} steps, enabled={pb.enabled})')
    for step in pb.steps:
        print(f'    step: {step.id} roster={step.roster} tier={step.complexity_tier}')
"

# Verify migration
cd modules/backend && alembic upgrade head

# Verify API starts
python cli.py --service server --reload
# Then: curl http://localhost:8000/api/v1/playbooks
```

---

## Future Work (Not In Scope)

These are explicitly **not** part of this plan. They are noted here for context and to prevent scope creep.

1. **Container execution** (`environment: container`) — The data model is prepared (execution environment stored in mission brief). Actual container orchestration (Docker/K8s) is a separate plan.
2. **Scheduled triggers** (`trigger.type: schedule`) — The schema supports cron expressions. Implementation requires Temporal timers (Plan 16) or Taskiq scheduled tasks.
3. **Event triggers** (`trigger.type: event`) — The schema supports event type subscriptions. Implementation requires event bus subscription management.
4. **Playbook composition** (playbooks that reference other playbooks) — Future extension. Keep playbooks flat for now.
5. **Playbook versioning with history** — Currently, the playbook YAML is the single source. No version history or rollback. If needed, use git.
6. **Agent-specific playbook tools** — `playbook.list_playbooks()`, `playbook.run_playbook()` tools for horizontal agents. Implement when Mission Control needs to trigger playbooks programmatically.
7. **Playbook marketplace/sharing** — Importing playbooks from external sources.
8. **Dynamic roster selection** — Currently, roster is declared statically per step. Future: allow the Planning Agent to recommend roster changes (explicitly excluded per research doc — no AI control over team composition in regulated environments).
9. **Cross-mission agent communication** — Agents in Mission A communicating directly with agents in Mission B. Explicitly prohibited by the anti-corruption layer design. All inter-mission data flows through the Playbook's output mapping.
