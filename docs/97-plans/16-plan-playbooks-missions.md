# Implementation Plan: Playbooks & Missions (Multi-Agent Workflow Composition)

*Created: 2026-03-03*
*Status: Not Started*
*Phase: 7 of 7 (AI-First Platform Build)*
*Depends on: Phase 1-5 (Event Bus, Sessions, Coordinator, PM Agent, Plan Management)*
*Optionally uses: Phase 6 (Temporal — for scheduled triggers and crash recovery)*
*Blocked by: Phase 5*

---

## Summary

Build the multi-agent workflow composition layer. **Playbooks** are declarative YAML templates that compose agent capabilities into reusable, schedulable, multi-step workflows. **Missions** are runtime instances of playbooks — they create sessions, generate plans, resolve agent capabilities, pass context between steps, and track execution to completion.

This addresses the agent grouping problem: agents are not grouped into "teams" or "projects." They are **capabilities** composed into **playbooks**. The same agent participates in many playbooks. A playbook declares *what* needs to happen and *which capabilities* are required. The mission engine handles the rest.

Two modes of operation:
- **Playbook-driven (deterministic):** User or schedule triggers a known playbook. System loads YAML, resolves capabilities, generates a plan, executes. No LLM reasoning needed to assemble the workflow. This is P2 (Deterministic Over Non-Deterministic).
- **Ad-hoc (dynamic):** User gives a freeform goal. PM agent (Plan 13) reasons about what's needed, creates a plan, delegates. No playbook involved. This is the existing flow.

The coordinator can match incoming requests against known playbooks before falling back to PM agent reasoning — deterministic path first, LLM fallback second.

**Dev mode: breaking changes allowed.** This is a new subsystem — no backward-compatibility constraints.

## Context

- Reference architecture: `docs/99-reference-architecture/46-agentic-event-session-architecture.md` (Section 1: Session Model, Section 4: Plan Management)
- Agent organization: `docs/99-reference-architecture/47-agentic-module-organization.md` (agent registry, capability naming, access control, execution modes)
- Agentic architecture: `docs/99-reference-architecture/40-agentic-architecture.md` (Option B: Plan-Centric Assembled Teams, Option D: Hybrid approach)
- PydanticAI implementation: `docs/99-reference-architecture/41-agentic-pydanticai.md` (agent-as-tool delegation, UsageLimits)
- Project principles: `docs/03-principles/01-project-principles.md` — P1 (Infrastructure Before Agents), P2 (Deterministic Over Non-Deterministic), P4 (Scope Is Configuration Not Code), P5 (Streaming Is Default), P10 (Expansion Not Rewrite)
- Plan 14: `docs/97-plans/14-plan-plan-management.md` — mutable DAG of tasks, PlanService, ready-task query. Playbook steps generate Plan tasks.
- Plan 11: Session model. Missions auto-create sessions.
- Plan 10: Event bus. Mission lifecycle events flow through it.
- Capability naming convention: `{category}.{name}` maps to agent `{category}.{name}.agent` in the registry (doc 47)
- Execution mode (doc 47, Dimension 4): `local` (default) or `container` (future). Playbooks declare per-step environment; this plan prepares the data model but does not implement containerization.
- Anti-pattern: Do NOT make playbooks executable code. They are YAML configuration (P4).
- Anti-pattern: Do NOT bypass the Plan system. Playbook steps MUST generate Plans (Plan 14). Do not create a parallel execution engine.
- Anti-pattern: Do NOT hard-couple missions to specific agents. Use capability references, resolved at mission creation time.
- Anti-pattern: Do NOT store large payloads in the mission context. Store references (file paths, IDs) rather than full data. Keep context under 1MB.

## What to Build

- `config/settings/playbooks.yaml` — Playbook system configuration (defaults, limits)
- `modules/backend/core/config_schema.py` — `PlaybooksSchema` config schema
- `modules/backend/core/config.py` — Register playbooks config in `AppConfig`
- `modules/backend/schemas/playbook.py` — `PlaybookSchema`, `PlaybookStepSchema`, `PlaybookTriggerSchema`, `PlaybookBudgetSchema` Pydantic schemas for validating playbook YAML files
- `modules/backend/services/playbook.py` — `PlaybookService` (load, validate, list, resolve capabilities, generate plan tasks)
- `modules/backend/models/mission.py` — `MissionStatus` enum, `MissionTriggerType` enum, `Mission` SQLAlchemy model
- `modules/backend/schemas/mission.py` — `MissionCreate`, `MissionResponse`, `MissionDetailResponse`, `MissionStatusSummary` Pydantic schemas
- `modules/backend/repositories/mission.py` — `MissionRepository` with status queries, playbook lookups
- `modules/backend/services/mission.py` — `MissionService` (create from playbook, start, track, resolve step inputs, complete/fail)
- `modules/backend/events/types.py` — Add `MissionCreatedEvent`, `MissionStartedEvent`, `MissionStepCompletedEvent`, `MissionCompletedEvent`, `MissionFailedEvent`
- `modules/backend/api/v1/endpoints/playbooks.py` — REST endpoints: list playbooks, get playbook detail, create mission from playbook, get mission status, list missions
- `config/playbooks/` — Directory for playbook YAML files
- `config/playbooks/examples/ai-news-digest.yaml` — Example playbook demonstrating full feature set
- Alembic migration for `missions` table
- Update coordinator to check playbook matches before PM agent fallback
- Tests for playbook loading, validation, capability resolution, mission lifecycle, step input resolution, API endpoints

## Key Design Decisions

- **Playbooks are YAML, loaded from `config/playbooks/`** (P4). The PlaybookService scans for `*.yaml` files recursively, validates each against `PlaybookSchema`, and caches results. Playbook identity comes from the `playbook_name` field inside the YAML, not from the file path. This mirrors the agent registry pattern from doc 47.
- **Capability resolution is convention-based.** A playbook step declares `capability: content.summarizer`. This resolves to agent `content.summarizer.agent` by appending `.agent`. The resolver validates the agent exists and is enabled in the registry at mission creation time. If resolution fails, the mission fails at creation (P5: Fail Fast).
- **Playbook steps become Plan tasks.** When a mission starts, the PlaybookService converts each step into a `PlanTaskCreate` with `assigned_agent` set to the resolved agent name, `input_data` set to the step's input (with unresolved references left as marker strings), and dependencies mapped from `depends_on`. This reuses Plan 14's entire DAG infrastructure — no parallel execution engine.
- **Step outputs flow via mission context.** Each playbook step declares an `output` key. When the corresponding Plan task completes, the MissionService stores `task.output_data` in `mission.context[step.output]`. Downstream steps reference these via `@steps.<step_id>.output` syntax. Resolution happens just before task execution.
- **Reference resolution syntax.** Two patterns: `@context.<key>` resolves to `mission.context[key]` (includes both playbook-defined context and accumulated step outputs). `@steps.<step_id>.output` resolves to the output of a completed step (equivalent to `@context[step.output_key]`). Unresolvable references raise `ValidationError` at task start time — the plan task is failed, triggering Plan 14's retry/revise/escalate chain.
- **Missions auto-create sessions.** Every mission creates a Session (Plan 11) with `goal` set to the playbook description, `cost_budget_usd` set from the playbook budget, and `agent_id` set to `"playbook:{playbook_name}"`. The session tracks cost across all steps. This gives missions full session infrastructure (events, cost tracking, channel binding) for free.
- **Three trigger types, phased implementation.** `on_demand` (API call or PM agent) implemented in this plan. `schedule` (cron via Temporal timers) and `event` (event bus subscription) are declared in the playbook schema but implementation deferred to after Plan 15 (Temporal). The trigger schema is forward-looking — no schema changes needed later.
- **Execution environment is per-step metadata.** Each step can declare `environment: local | container | sandbox`. This plan stores the value in the Plan task's `input_data` under `_execution_environment`. The coordinator reads this field when executing the task. Actual container orchestration is future work — this plan only prepares the data path. All steps execute `local` for now.
- **Playbook matching in the coordinator.** The coordinator's routing logic gains a deterministic fast-path: before calling the PM agent for complex requests, check if the input matches a playbook's `trigger.match_patterns` (keyword patterns). If matched, instantiate the playbook directly. This is P2 (Deterministic Over Non-Deterministic).
- **String UUIDs** via `UUIDMixin` for consistency with existing codebase (SQLite test compatibility).
- **Missions are session-scoped.** A mission always has a `session_id`. A session can have at most one active mission (but can have historical completed/failed missions). No orphan missions.
- **Playbook versioning is declarative.** Playbooks have a `version` field. The mission records `playbook_version` at creation time. If the playbook is updated, existing running missions continue with their recorded version. New missions use the current version.
- **Example playbook included.** An AI news digest playbook is included as `config/playbooks/examples/ai-news-digest.yaml` to demonstrate the full feature set. It is `enabled: false` by default (its agent capabilities don't exist yet).

## Success Criteria

- [ ] Playbook YAML files load and validate from `config/playbooks/`
- [ ] Capability resolution maps `content.summarizer` to `content.summarizer.agent` and fails fast if agent missing
- [ ] Mission creation from playbook: auto-creates session, generates plan with correct task DAG
- [ ] Step dependencies in playbook correctly translate to Plan task dependencies
- [ ] Step input references (`@context.*`, `@steps.*.output`) resolve correctly at task start time
- [ ] Step outputs accumulate in mission context as tasks complete
- [ ] Mission status tracks overall progress (pending → running → completed/failed)
- [ ] Mission lifecycle events publish to the event bus
- [ ] API endpoints: list playbooks, create mission, get mission status
- [ ] Coordinator playbook matching triggers deterministic execution for known patterns
- [ ] Execution environment field preserved through plan task creation (metadata, not execution)
- [ ] Playbook trigger schema supports `on_demand`, `schedule`, `event` (only `on_demand` implemented)
- [ ] Config loads from `playbooks.yaml` with defaults
- [ ] Example playbook validates successfully
- [ ] All existing tests still pass (no breaking changes)
- [ ] New tests cover playbook loading, validation, capability resolution, mission lifecycle, step input resolution, API endpoints

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
#   enable_playbook_matching   - Enable coordinator playbook matching fast-path (boolean)
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

Pydantic models for validating playbook YAML files. These are NOT API response schemas — they validate the YAML structure at load time.

```python
"""
Playbook YAML validation schemas.

Validates playbook structure, step definitions, trigger configuration,
budget limits, and context declarations. Used by PlaybookService at
load time to reject invalid playbooks early (P5: Fail Fast).
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlaybookStepSchema(BaseModel):
    """A single step in a playbook workflow."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Step identifier, used in depends_on and @steps references",
    )
    description: str | None = Field(
        None,
        max_length=500,
        description="Human-readable description of what this step does",
    )
    capability: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$",
        description="Agent capability to resolve (e.g. 'content.summarizer')",
    )
    environment: str = Field(
        default="local",
        pattern=r"^(local|container|sandbox)$",
        description="Execution environment for this step",
    )
    input: dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters. Values starting with @ are resolved at runtime",
    )
    output: str | None = Field(
        None,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Key name for storing step result in mission context",
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
        description="Keywords for coordinator playbook matching (P2 deterministic fast-path)",
    )


class PlaybookBudgetSchema(BaseModel):
    """Cost constraints for mission execution."""

    model_config = ConfigDict(extra="forbid")

    max_cost_usd: float = Field(
        default=10.00,
        ge=0.01,
        description="Maximum cost for a single mission run",
    )
    max_tokens: int | None = Field(
        None,
        ge=1000,
        description="Maximum total tokens across all steps (optional)",
    )


class PlaybookSchema(BaseModel):
    """Root schema for a playbook YAML file.

    Validates the complete playbook definition including steps, triggers,
    budget, and context. All validation happens at load time — a playbook
    that passes validation is guaranteed to be structurally correct.
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
        description="Human-readable description, used as session goal",
    )
    version: int = Field(
        default=1,
        ge=1,
        description="Playbook version, recorded in mission for traceability",
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
        description="Cost constraints",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Initial context available to all steps via @context references",
    )
    steps: list[PlaybookStepSchema] = Field(
        ...,
        min_length=1,
        description="Ordered list of workflow steps",
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

        # Check output keys are unique (where declared)
        output_keys = [s.output for s in steps if s.output is not None]
        if len(output_keys) != len(set(output_keys)):
            raise ValueError("Duplicate output keys in playbook steps")

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
- Step ID pattern (`^[a-z][a-z0-9_-]*$`) enforces clean identifiers for `@steps.*` references
- Capability pattern enforces dot-notation matching agent naming convention
- Cycle detection in `validate_steps` prevents invalid DAGs at load time, before a mission is created
- Output key uniqueness prevents ambiguous `@context.*` references
- `PlaybookListResponse` and `PlaybookDetailResponse` are API response schemas (not YAML validation schemas)

---

### Step 3: Playbook Service

**File**: `modules/backend/services/playbook.py` (NEW)

Service that loads, validates, caches, and resolves playbooks. Does NOT extend `BaseService` — it reads from the filesystem and agent registry, not from the database.

```python
"""
Playbook Service.

Loads playbook YAML files from config/playbooks/, validates against
PlaybookSchema, resolves capability references to agent names, and
generates Plan task definitions from playbook steps.

This service is stateless — it reads from the filesystem and agent
registry. It does not touch the database.
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
            agent_registry: Dict mapping agent_name → agent config dict.
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
            Dict mapping playbook_name → PlaybookSchema
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

    def generate_plan_tasks(
        self, playbook: PlaybookSchema
    ) -> list[dict[str, Any]]:
        """Convert playbook steps into Plan task definitions.

        Each step becomes a PlanTaskCreate-compatible dict with:
        - name: step.id
        - description: step.description
        - assigned_agent: resolved agent name
        - input_data: step.input (with @references preserved for runtime resolution)
        - sort_order: step index
        - dependencies: mapped from depends_on

        The _playbook_step_id and _execution_environment fields are
        stored in input_data as metadata for the MissionService.

        Returns:
            List of task dicts compatible with PlanService.create_plan().
        """
        # Build step index map for dependency resolution
        step_index_map: dict[str, int] = {}
        for i, step in enumerate(playbook.steps):
            step_index_map[step.id] = i

        tasks: list[dict[str, Any]] = []
        app_config = get_app_config()

        for i, step in enumerate(playbook.steps):
            # Resolve capability to agent name
            agent_name = self.resolve_capability(step.capability)

            # Build input data with metadata
            input_data = dict(step.input)
            input_data["_playbook_step_id"] = step.id
            input_data["_execution_environment"] = step.environment
            if step.output:
                input_data["_output_key"] = step.output
            input_data["_timeout_seconds"] = (
                step.timeout_seconds
                or app_config.playbooks.default_step_timeout_seconds
            )

            # Build dependencies
            dependencies = []
            for dep_id in step.depends_on:
                dep_index = step_index_map.get(dep_id)
                if dep_index is not None:
                    dependencies.append({
                        "depends_on_index": dep_index,
                        "type": "completion",
                    })

            tasks.append({
                "name": step.id,
                "description": step.description or f"Execute step: {step.id}",
                "assigned_agent": agent_name,
                "input_data": input_data,
                "sort_order": i,
                "dependencies": dependencies,
            })

        return tasks

    def match_playbook(self, user_input: str) -> PlaybookSchema | None:
        """Match user input against playbook trigger patterns.

        Used by the coordinator for deterministic fast-path routing (P2).
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
```

**Key implementation notes**:
- `load_playbooks()` is called lazily and can be re-called for hot-reload
- Invalid playbooks are logged and skipped, not fatal — a broken playbook shouldn't prevent the system from starting
- `generate_plan_tasks()` preserves `@` references in `input_data` — resolution happens later in the MissionService at task start time
- Metadata fields (`_playbook_step_id`, `_execution_environment`, `_output_key`, `_timeout_seconds`) are prefixed with `_` to distinguish them from user-defined input
- `match_playbook()` is intentionally simple (keyword containment). Complex matching belongs in the PM agent (LLM), not here (P2)
- The service does NOT extend `BaseService` — it has no database dependency

---

### Step 4: Mission Model

**File**: `modules/backend/models/mission.py` (NEW)

```python
"""
Mission Model.

A mission is a runtime instance of a playbook. It tracks execution
of a multi-agent workflow: which playbook was used, current status,
accumulated context (step outputs), cost, and timing.

Missions auto-create sessions (Plan 11) and generate plans (Plan 14).
"""

import enum

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class MissionStatus(str, enum.Enum):
    """Mission lifecycle status.

    Transitions:
        pending → running (execution started)
        running → completed (all steps done)
        running → failed (unrecoverable error)
        running → cancelled (user cancelled)
        pending → cancelled (cancelled before start)
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid transitions for mission status state machine
VALID_MISSION_TRANSITIONS: dict[MissionStatus, set[MissionStatus]] = {
    MissionStatus.PENDING: {MissionStatus.RUNNING, MissionStatus.CANCELLED},
    MissionStatus.RUNNING: {
        MissionStatus.COMPLETED,
        MissionStatus.FAILED,
        MissionStatus.CANCELLED,
    },
    MissionStatus.COMPLETED: set(),  # terminal
    MissionStatus.FAILED: set(),  # terminal
    MissionStatus.CANCELLED: set(),  # terminal
}


class MissionTriggerType(str, enum.Enum):
    """How the mission was triggered."""

    ON_DEMAND = "on_demand"
    SCHEDULE = "schedule"
    EVENT = "event"


class Mission(UUIDMixin, TimestampMixin, Base):
    """A runtime instance of a playbook."""

    __tablename__ = "missions"

    # Playbook reference
    playbook_id: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        comment="Playbook name (e.g. 'research.ai-news-digest')",
    )
    playbook_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Playbook version at mission creation time",
    )

    # Status
    status: Mapped[str] = mapped_column(
        Enum(MissionStatus, native_enum=False),
        default=MissionStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Session and plan references
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id"),
        nullable=False,
        index=True,
        comment="Auto-created session for this mission",
    )
    plan_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("plans.id"),
        nullable=True,
        index=True,
        comment="Generated plan from playbook steps (set after plan creation)",
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
        comment="Who/what triggered: 'user:<id>', 'schedule', 'event:<type>'",
    )

    # Context: playbook context + accumulated step outputs
    context: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Playbook context merged with step outputs as they complete",
    )

    # Cost tracking (aggregated from session)
    total_cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    budget_usd: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Cost limit from playbook budget",
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

    # Results summary (if completed)
    result_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable summary of mission results",
    )

    def __repr__(self) -> str:
        return (
            f"<Mission(id={self.id}, playbook={self.playbook_id!r}, "
            f"status={self.status})>"
        )
```

**File**: `modules/backend/models/__init__.py` — Add import:

```python
from modules.backend.models.mission import Mission
```

This registers the model with Alembic for autogenerate.

**Adapter notes**:
- Uses `JSON` (via `sqlalchemy.dialects.sqlite`) for `context` and `error_data` — works with both PostgreSQL (JSONB) and SQLite (text JSON) for test compatibility
- `started_at`, `completed_at` stored as ISO strings rather than DateTime — matches Plan 14 pattern
- `session_id` FK to `sessions` table (Plan 11). `plan_id` FK to `plans` table (Plan 14).
- `VALID_MISSION_TRANSITIONS` dict mirrors the session/task status pattern

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
    """Create a mission from a playbook."""

    playbook_name: str = Field(
        ...,
        description="Name of the playbook to instantiate",
    )
    triggered_by: str = Field(
        default="user:anonymous",
        description="Who triggered: 'user:<id>', 'api', 'schedule'",
    )
    context_overrides: dict | None = Field(
        None,
        description="Override playbook context values for this run",
    )


class MissionResponse(BaseModel):
    """API response for a mission."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    playbook_id: str
    playbook_version: int
    status: str
    session_id: str
    plan_id: str | None
    trigger_type: str
    triggered_by: str
    total_cost_usd: float
    budget_usd: float | None
    started_at: str | None
    completed_at: str | None
    created_at: str
    updated_at: str


class MissionDetailResponse(BaseModel):
    """Detailed mission response with context and results."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    playbook_id: str
    playbook_version: int
    status: str
    session_id: str
    plan_id: str | None
    trigger_type: str
    triggered_by: str
    context: dict
    total_cost_usd: float
    budget_usd: float | None
    started_at: str | None
    completed_at: str | None
    result_summary: str | None
    error_data: dict | None
    created_at: str
    updated_at: str


class MissionStatusSummary(BaseModel):
    """Mission progress summary combining mission and plan status."""

    mission_id: str
    playbook_id: str
    status: str
    total_steps: int
    completed_steps: int
    failed_steps: int
    in_progress_steps: int
    pending_steps: int
    progress_pct: float
    total_cost_usd: float
    budget_usd: float | None
    started_at: str | None
    elapsed_seconds: float | None
```

---

### Step 6: Mission Repository

**File**: `modules/backend/repositories/mission.py` (NEW)

```python
"""
Mission Repository.

Standard CRUD plus mission-specific queries: lookup by playbook,
active mission count, and status filtering.
"""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.models.mission import Mission, MissionStatus
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

    async def get_by_playbook(
        self,
        playbook_id: str,
        status: MissionStatus | None = None,
    ) -> list[Mission]:
        """Get missions for a specific playbook, optionally filtered by status."""
        conditions = [Mission.playbook_id == playbook_id]
        if status:
            conditions.append(Mission.status == status)

        stmt = (
            select(Mission)
            .where(and_(*conditions))
            .order_by(Mission.created_at.desc())
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
                    MissionStatus.PENDING,
                    MissionStatus.RUNNING,
                ])
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_active_for_playbook(self, playbook_id: str) -> Mission | None:
        """Get the currently active mission for a playbook (if any).

        Returns the most recent pending or running mission.
        """
        stmt = (
            select(Mission)
            .where(
                and_(
                    Mission.playbook_id == playbook_id,
                    Mission.status.in_([
                        MissionStatus.PENDING,
                        MissionStatus.RUNNING,
                    ]),
                )
            )
            .order_by(Mission.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_missions(
        self,
        status: MissionStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Mission], int]:
        """List missions with optional status filter and pagination.

        Returns:
            Tuple of (missions, total_count).
        """
        conditions = []
        if status:
            conditions.append(Mission.status == status)

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

**File**: `modules/backend/services/mission.py` (NEW)

This is the core of the system — it bridges playbooks, sessions, plans, and agents.

```python
"""
Mission Service.

Orchestrates mission lifecycle: creates missions from playbooks,
generates plans, resolves step inputs, tracks context accumulation,
and manages completion/failure.

This service bridges PlaybookService (YAML), SessionService (Plan 11),
PlanService (Plan 14), and the event bus (Plan 10).
"""

import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.config import get_app_config
from modules.backend.core.exceptions import NotFoundError, ValidationError
from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now
from modules.backend.models.mission import (
    Mission,
    MissionStatus,
    MissionTriggerType,
    VALID_MISSION_TRANSITIONS,
)
from modules.backend.repositories.mission import MissionRepository
from modules.backend.services.base import BaseService
from modules.backend.services.playbook import PlaybookService

logger = get_logger(__name__)

# Pattern for @context.<key> and @steps.<step_id>.output references
REFERENCE_PATTERN = re.compile(r"^@(context|steps)\.(.+)$")


class MissionService(BaseService):
    """Mission lifecycle management.

    Accepts service dependencies via constructor injection.
    PlanService and SessionService are optional to allow incremental
    adoption — if not provided, the corresponding features are skipped.
    """

    def __init__(
        self,
        session: AsyncSession,
        playbook_service: PlaybookService,
        plan_service: Any | None = None,
        session_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        super().__init__(session)
        self._mission_repo = MissionRepository(session)
        self._playbook_service = playbook_service
        self._plan_service = plan_service
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

    async def create_mission(
        self,
        playbook_name: str,
        triggered_by: str,
        trigger_type: str = "on_demand",
        context_overrides: dict | None = None,
    ) -> Mission:
        """Create a mission from a playbook.

        Steps:
        1. Load and validate the playbook
        2. Check concurrency limits
        3. Validate all capabilities resolve to agents
        4. Create a session (auto)
        5. Create a plan from playbook steps
        6. Create the mission row
        7. Publish MissionCreatedEvent

        Args:
            playbook_name: Name of the playbook to instantiate.
            triggered_by: Who/what triggered (e.g. 'user:123', 'schedule').
            trigger_type: 'on_demand', 'schedule', or 'event'.
            context_overrides: Override playbook context values for this run.

        Returns:
            Created Mission instance.

        Raises:
            NotFoundError: If playbook not found or disabled.
            ValidationError: If capabilities don't resolve or limits exceeded.
        """

        async def _create() -> Mission:
            # 1. Load playbook
            playbook = self._playbook_service.get_playbook(playbook_name)
            if not playbook:
                raise NotFoundError(
                    message=f"Playbook '{playbook_name}' not found or disabled",
                )
            if not playbook.enabled:
                raise ValidationError(
                    message=f"Playbook '{playbook_name}' is disabled",
                )

            # 2. Check concurrency limits
            app_config = get_app_config()
            active_count = await self._mission_repo.count_active()
            if active_count >= app_config.playbooks.max_concurrent_missions:
                raise ValidationError(
                    message=(
                        f"Maximum concurrent missions ({app_config.playbooks.max_concurrent_missions}) "
                        f"reached. {active_count} currently active."
                    ),
                )

            # 3. Validate capabilities
            errors = self._playbook_service.validate_playbook_capabilities(playbook)
            if errors:
                raise ValidationError(
                    message=f"Cannot resolve capabilities: {'; '.join(errors)}",
                )

            # 4. Build initial context (playbook context + overrides)
            context = dict(playbook.context)
            if context_overrides:
                context.update(context_overrides)

            # 5. Create session (auto)
            session_id = None
            if self._session_service:
                from modules.backend.schemas.session import SessionCreate

                session_data = SessionCreate(
                    goal=playbook.description,
                    agent_id=f"playbook:{playbook.playbook_name}",
                    cost_budget_usd=playbook.budget.max_cost_usd,
                    metadata={"playbook": playbook.playbook_name},
                )
                session_response = await self._session_service.create_session(
                    session_data
                )
                session_id = str(session_response.id)
            else:
                # Fallback: generate a placeholder session ID
                from uuid import uuid4

                session_id = str(uuid4())
                logger.warning(
                    "SessionService not available, using placeholder session_id",
                    extra={"session_id": session_id},
                )

            # 6. Generate plan from playbook steps
            plan_id = None
            if self._plan_service:
                plan_tasks = self._playbook_service.generate_plan_tasks(playbook)
                plan = await self._plan_service.create_plan(
                    session_id=session_id,
                    goal=f"Execute playbook: {playbook.playbook_name}",
                    tasks=plan_tasks,
                )
                plan_id = plan.id

            # 7. Create mission
            mission = Mission(
                playbook_id=playbook.playbook_name,
                playbook_version=playbook.version,
                status=MissionStatus.PENDING,
                session_id=session_id,
                plan_id=plan_id,
                trigger_type=MissionTriggerType(trigger_type),
                triggered_by=triggered_by,
                context=context,
                total_cost_usd=0.0,
                budget_usd=playbook.budget.max_cost_usd,
            )
            self._session.add(mission)
            await self._session.flush()
            await self._session.refresh(mission)

            logger.info(
                "Mission created",
                extra={
                    "mission_id": mission.id,
                    "playbook": playbook.playbook_name,
                    "session_id": session_id,
                    "plan_id": plan_id,
                    "trigger_type": trigger_type,
                    "triggered_by": triggered_by,
                },
            )

            return mission

        return await self._execute_db_operation("create_mission", _create)

    # ---- Mission lifecycle ----

    async def start_mission(self, mission_id: str) -> Mission:
        """Start executing a mission.

        Transitions status from PENDING to RUNNING.
        Promotes initial plan tasks to ready via PlanService.

        Returns:
            Updated Mission instance.
        """
        mission = await self._get_mission(mission_id)
        self._validate_transition(mission, MissionStatus.RUNNING)

        mission.status = MissionStatus.RUNNING
        mission.started_at = utc_now().isoformat()
        await self._session.flush()

        # Promote initial plan tasks
        if self._plan_service and mission.plan_id:
            await self._plan_service.promote_ready_tasks(mission.plan_id)

        logger.info(
            "Mission started",
            extra={"mission_id": mission_id, "playbook": mission.playbook_id},
        )

        return mission

    async def complete_mission(self, mission_id: str) -> Mission:
        """Mark mission as completed."""
        mission = await self._get_mission(mission_id)
        self._validate_transition(mission, MissionStatus.COMPLETED)

        mission.status = MissionStatus.COMPLETED
        mission.completed_at = utc_now().isoformat()
        await self._session.flush()

        logger.info(
            "Mission completed",
            extra={
                "mission_id": mission_id,
                "playbook": mission.playbook_id,
                "cost": mission.total_cost_usd,
            },
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
        self._validate_transition(mission, MissionStatus.FAILED)

        mission.status = MissionStatus.FAILED
        mission.completed_at = utc_now().isoformat()
        mission.error_data = error_data or {"message": error}
        await self._session.flush()

        logger.error(
            "Mission failed",
            extra={
                "mission_id": mission_id,
                "playbook": mission.playbook_id,
                "error": error,
            },
        )

        return mission

    async def cancel_mission(self, mission_id: str, reason: str) -> Mission:
        """Cancel a mission."""
        mission = await self._get_mission(mission_id)
        self._validate_transition(mission, MissionStatus.CANCELLED)

        mission.status = MissionStatus.CANCELLED
        mission.completed_at = utc_now().isoformat()
        mission.error_data = {"cancelled_reason": reason}
        await self._session.flush()

        logger.info(
            "Mission cancelled",
            extra={
                "mission_id": mission_id,
                "playbook": mission.playbook_id,
                "reason": reason,
            },
        )

        return mission

    # ---- Context and step output management ----

    async def on_task_completed(
        self,
        mission_id: str,
        task_id: str,
        output_data: dict | None = None,
        cost_usd: float = 0.0,
    ) -> None:
        """Handle task completion within a mission.

        1. Read the task's _output_key from input_data metadata
        2. Store output in mission context under that key
        3. Update mission cost
        4. Check context size limit
        5. Check if all plan tasks are complete → complete mission

        Called by the coordinator after PlanService.complete_task().
        """
        mission = await self._get_mission(mission_id)

        # Update cost
        mission.total_cost_usd += cost_usd

        # Store output in mission context if output key specified
        if output_data and self._plan_service:
            from modules.backend.models.plan import PlanTask

            task = await self._session.get(PlanTask, task_id)
            if task and task.input_data:
                output_key = task.input_data.get("_output_key")
                if output_key:
                    # Check context size limit
                    context = dict(mission.context)
                    context[output_key] = output_data

                    context_size = len(json.dumps(context).encode("utf-8"))
                    max_size = get_app_config().playbooks.max_context_size_bytes
                    if context_size > max_size:
                        logger.warning(
                            "Mission context exceeds size limit, storing reference only",
                            extra={
                                "mission_id": mission_id,
                                "context_size": context_size,
                                "max_size": max_size,
                                "output_key": output_key,
                            },
                        )
                        context[output_key] = {
                            "_truncated": True,
                            "_task_id": task_id,
                            "_message": "Output too large for context. Retrieve from task output_data.",
                        }

                    mission.context = context

        await self._session.flush()

        # Check if mission is complete (all plan tasks done)
        if self._plan_service and mission.plan_id:
            status = await self._plan_service.get_plan_status(mission.plan_id)
            if status["completed_tasks"] == status["total_tasks"]:
                await self.complete_mission(mission_id)
            elif status["failed_tasks"] > 0 and status["in_progress_tasks"] == 0 and status["ready_tasks"] == 0 and status["pending_tasks"] == 0:
                # All remaining tasks failed or blocked — mission failed
                await self.fail_mission(
                    mission_id,
                    error="All plan tasks completed or failed with unresolved failures",
                )

    async def resolve_step_inputs(
        self,
        mission_id: str,
        task_input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve @context.* and @steps.*.output references in task input.

        Called by the coordinator just before executing a plan task that
        belongs to a mission.

        Reference patterns:
        - @context.<key>         → mission.context[key]
        - @steps.<step_id>.output → mission.context[step_output_key]

        Unresolvable references are left as-is with a warning logged.
        The agent receives the unresolved reference string and can
        report it as an error.

        Args:
            mission_id: The mission ID.
            task_input_data: The task's input_data dict (may contain @ references).

        Returns:
            New dict with references resolved. Original dict is not modified.
        """
        mission = await self._get_mission(mission_id)
        resolved = {}

        for key, value in task_input_data.items():
            # Skip metadata keys
            if key.startswith("_"):
                resolved[key] = value
                continue

            resolved[key] = self._resolve_value(value, mission.context, mission_id)

        return resolved

    def _resolve_value(
        self,
        value: Any,
        context: dict[str, Any],
        mission_id: str,
    ) -> Any:
        """Recursively resolve @ references in a value.

        Handles strings, lists, and nested dicts.
        """
        if isinstance(value, str):
            match = REFERENCE_PATTERN.match(value)
            if match:
                ref_type = match.group(1)  # "context" or "steps"
                ref_path = match.group(2)  # key or "step_id.output"

                if ref_type == "context":
                    if ref_path in context:
                        return context[ref_path]
                    else:
                        logger.warning(
                            "Unresolved context reference",
                            extra={
                                "mission_id": mission_id,
                                "reference": value,
                                "available_keys": list(context.keys()),
                            },
                        )
                        return value  # Leave unresolved

                elif ref_type == "steps":
                    # Parse step_id.output
                    parts = ref_path.split(".", 1)
                    if len(parts) == 2 and parts[1] == "output":
                        step_id = parts[0]
                        # Find the output key for this step in context
                        # The step output was stored under the step's output key
                        # We need to find which context key came from this step
                        # Convention: the step's _output_key was used as the context key
                        # For now, check if step_id exists as a context key directly
                        if step_id in context:
                            return context[step_id]
                        else:
                            # Try to find by scanning context for the step's output
                            logger.warning(
                                "Unresolved step reference",
                                extra={
                                    "mission_id": mission_id,
                                    "reference": value,
                                    "step_id": step_id,
                                },
                            )
                            return value

            return value

        elif isinstance(value, list):
            return [
                self._resolve_value(item, context, mission_id) for item in value
            ]

        elif isinstance(value, dict):
            return {
                k: self._resolve_value(v, context, mission_id) for k, v in value.items()
            }

        return value

    # ---- Status and queries ----

    async def get_mission(self, mission_id: str) -> Mission:
        """Get a mission by ID."""
        return await self._get_mission(mission_id)

    async def get_mission_status(self, mission_id: str) -> dict[str, Any]:
        """Get combined mission + plan progress status."""
        mission = await self._get_mission(mission_id)

        result: dict[str, Any] = {
            "mission_id": mission.id,
            "playbook_id": mission.playbook_id,
            "status": mission.status,
            "total_cost_usd": mission.total_cost_usd,
            "budget_usd": mission.budget_usd,
            "started_at": mission.started_at,
            "total_steps": 0,
            "completed_steps": 0,
            "failed_steps": 0,
            "in_progress_steps": 0,
            "pending_steps": 0,
            "progress_pct": 0.0,
            "elapsed_seconds": None,
        }

        # Merge plan status if available
        if self._plan_service and mission.plan_id:
            try:
                plan_status = await self._plan_service.get_plan_status(
                    mission.plan_id
                )
                result.update({
                    "total_steps": plan_status["total_tasks"],
                    "completed_steps": plan_status["completed_tasks"],
                    "failed_steps": plan_status["failed_tasks"],
                    "in_progress_steps": plan_status["in_progress_tasks"],
                    "pending_steps": (
                        plan_status["pending_tasks"] + plan_status["ready_tasks"]
                    ),
                    "progress_pct": plan_status["progress_pct"],
                })
            except KeyError:
                pass

        # Calculate elapsed time
        if mission.started_at:
            started = utc_now()  # Would parse mission.started_at in real impl
            # For now, leave elapsed_seconds as None
            # TODO: Parse ISO string and compute delta

        return result

    async def list_missions(
        self,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Mission], int]:
        """List missions with optional status filter."""
        mission_status = MissionStatus(status) if status else None
        return await self._mission_repo.list_missions(
            status=mission_status, limit=limit, offset=offset
        )

    async def get_mission_for_plan(self, plan_id: str) -> Mission | None:
        """Find the mission that owns a specific plan (if any).

        Used by the coordinator to determine if a plan task belongs
        to a mission and needs context resolution.
        """
        stmt = (
            self._session.query(Mission)
            if hasattr(self._session, "query")
            else None
        )
        # Use repository pattern
        from sqlalchemy import select

        result = await self._session.execute(
            select(Mission).where(Mission.plan_id == plan_id).limit(1)
        )
        return result.scalar_one_or_none()

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
        self, mission: Mission, new_status: MissionStatus
    ) -> None:
        """Validate mission status transition."""
        current = MissionStatus(mission.status)
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
- `create_mission()` is the main entry point — validates playbook, creates session, generates plan, creates mission row. This is a single transactional operation.
- `resolve_step_inputs()` handles `@context.*` and `@steps.*.output` references recursively (supports nested dicts and lists).
- `on_task_completed()` is called by the coordinator after each plan task completion — it stores step output in mission context and checks if the mission is complete.
- Context size is checked after each step output — large outputs are truncated with a reference to the task's `output_data`.
- The service accepts `plan_service` and `session_service` as optional dependencies — this allows the mission system to be tested independently and adopted incrementally.

---

### Step 8: Mission Events

**File**: `modules/backend/events/types.py` — Add mission event types after the existing plan events:

```python
# --- Mission events ---

class MissionCreatedEvent(SessionEvent):
    event_type: str = "mission.created"
    mission_id: str
    playbook_id: str
    playbook_version: int
    trigger_type: str
    triggered_by: str


class MissionStartedEvent(SessionEvent):
    event_type: str = "mission.started"
    mission_id: str
    playbook_id: str
    step_count: int


class MissionStepCompletedEvent(SessionEvent):
    event_type: str = "mission.step.completed"
    mission_id: str
    step_id: str
    step_name: str
    output_key: str | None = None
    cost_usd: float = 0.0


class MissionCompletedEvent(SessionEvent):
    event_type: str = "mission.completed"
    mission_id: str
    playbook_id: str
    total_cost_usd: float
    step_count: int
    elapsed_seconds: float | None = None
    result_summary: str | None = None


class MissionFailedEvent(SessionEvent):
    event_type: str = "mission.failed"
    mission_id: str
    playbook_id: str
    error: str
    failed_step: str | None = None
    total_cost_usd: float = 0.0
```

**File**: `modules/backend/events/schemas.py` — Register new event types in the event type registry (follow the existing pattern for plan events):

```python
# Mission events
"mission.created": MissionCreatedEvent,
"mission.started": MissionStartedEvent,
"mission.step.completed": MissionStepCompletedEvent,
"mission.completed": MissionCompletedEvent,
"mission.failed": MissionFailedEvent,
```

---

### Step 9: API Endpoints

**File**: `modules/backend/api/v1/endpoints/playbooks.py` (NEW)

```python
"""
Playbook and Mission API endpoints.

Provides endpoints for listing playbooks, creating missions from playbooks,
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
    MissionStatusSummary,
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
    # PlanService and SessionService injected when available (Plan 11, 14)
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
    """Create and start a mission from a playbook."""
    service = _get_mission_service(db)

    mission = await service.create_mission(
        playbook_name=data.playbook_name,
        triggered_by=data.triggered_by,
        trigger_type="on_demand",
        context_overrides=data.context_overrides,
    )

    # Auto-start the mission
    mission = await service.start_mission(mission.id)

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
    limit: int = 20,
    offset: int = 0,
) -> ApiResponse:
    """List missions with optional status filter."""
    service = _get_mission_service(db)
    missions, total = await service.list_missions(
        status=status, limit=limit, offset=offset
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


@router.get("/missions/{mission_id}/status", response_model=ApiResponse)
async def get_mission_status(
    mission_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse:
    """Get mission progress summary with step-level breakdown."""
    service = _get_mission_service(db)
    status = await service.get_mission_status(mission_id)

    return ApiResponse(
        success=True,
        data=status,
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

### Step 10: Coordinator Integration (Playbook Matching Fast-Path)

**File**: `modules/backend/agents/coordinator/coordinator.py` — Add playbook matching

The coordinator gains a deterministic fast-path that checks incoming requests against playbook trigger patterns before falling back to the PM agent. This implements P2 (Deterministic Over Non-Deterministic).

Add to the coordinator's routing logic, before the LLM-based routing:

```python
# In the coordinator's handle() or route() method, add BEFORE the existing
# rule-based and LLM routing:

async def _try_playbook_match(self, user_input: str, session_id: str) -> dict | None:
    """Check if user input matches a known playbook (P2: deterministic fast-path).

    Returns a CoordinatorResponse dict if matched, None otherwise.
    """
    app_config = get_app_config()
    if not app_config.playbooks.enable_playbook_matching:
        return None

    playbook_service = PlaybookService(agent_registry=self._registry)
    matched = playbook_service.match_playbook(user_input)

    if not matched:
        return None

    logger.info(
        "Playbook matched, creating mission",
        extra={
            "playbook": matched.playbook_name,
            "user_input": user_input[:200],
        },
    )

    # Create and start mission
    # This requires MissionService — get it from the coordinator's dependencies
    # The actual injection pattern depends on Plan 11/14 implementation
    # For now, return a routing decision that the coordinator handles
    return {
        "route_type": "playbook",
        "playbook_name": matched.playbook_name,
        "playbook": matched,
    }
```

**Integration point**: The coordinator's main `handle()` method checks playbook match first:

```python
async def handle(self, user_input, session_id, ...):
    # 1. Deterministic: check playbook match (P2)
    playbook_match = await self._try_playbook_match(user_input, session_id)
    if playbook_match:
        return await self._execute_playbook_mission(playbook_match, session_id, ...)

    # 2. Deterministic: check keyword routing rules (existing)
    matched_agent = self._rule_based_route(user_input)
    if matched_agent:
        return await self._execute_agent(matched_agent, user_input, ...)

    # 3. Non-deterministic: LLM routing / PM agent (existing)
    return await self._llm_route(user_input, session_id, ...)
```

**Important**: The exact integration depends on the coordinator's structure from Plan 12. The implementing agent should read the current coordinator code and adapt this pattern to fit. The key principle is: **playbook match happens first, before any LLM call.**

---

### Step 11: Database Migration

Create an Alembic migration for the `missions` table.

**Command**: `cd modules/backend && alembic revision --autogenerate -m "add_missions_table"`

The migration should create the `missions` table with all columns from the Mission model (Step 4). Verify the migration includes:
- `id` (String(36), primary key)
- `playbook_id` (String(200), indexed)
- `playbook_version` (Integer)
- `status` (String/Enum, indexed)
- `session_id` (String(36), FK to sessions, indexed)
- `plan_id` (String(36), FK to plans, nullable, indexed)
- `trigger_type` (String/Enum)
- `triggered_by` (String(200))
- `context` (JSON)
- `total_cost_usd` (Float)
- `budget_usd` (Float, nullable)
- `started_at` (String(30), nullable)
- `completed_at` (String(30), nullable)
- `error_data` (JSON, nullable)
- `result_summary` (Text, nullable)
- `created_at` (String(30))
- `updated_at` (String(30))

**Note**: The `sessions` and `plans` tables must exist before this migration runs (Plan 11, Plan 14). If they don't exist yet, make the FKs nullable or remove them temporarily and add them in a later migration.

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
# This playbook demonstrates: multi-step workflow, step dependencies,
# context passing, execution environments, and delivery.
#
# NOTE: This playbook is disabled by default. The referenced agent
# capabilities (research.scraper, content.summarizer, etc.) do not
# exist yet. Enable once the agents are built.
# =============================================================================

playbook_name: research.ai-news-digest
description: "Curate, summarize, and deliver AI news from thought leaders"
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
  max_cost_usd: 2.00
  max_tokens: 200000

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
    environment: container
    input:
      sources: "@context.sources"
      max_articles: "@context.max_articles"
    output: raw_articles
    timeout_seconds: 600

  - id: summarize
    description: "Synthesize articles into key learnings and takeaways"
    capability: content.summarizer
    environment: local
    input:
      articles: "@steps.scrape.output"
      style: "@context.summary_style"
    output: summaries
    depends_on:
      - scrape

  - id: extract-actions
    description: "Identify actionable takeaways and recommendations"
    capability: content.analyst
    environment: local
    input:
      summaries: "@steps.summarize.output"
    output: actions
    depends_on:
      - summarize

  - id: format
    description: "Format digest for delivery channels"
    capability: content.formatter
    environment: local
    input:
      summaries: "@steps.summarize.output"
      actions: "@steps.extract-actions.output"
      channels: "@context.delivery_channels"
    output: formatted_digest
    depends_on:
      - summarize
      - extract-actions

  - id: deliver
    description: "Send formatted digest via configured channels"
    capability: comms.dispatcher
    environment: local
    input:
      content: "@steps.format.output"
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
```

---

### Step 13: Tests

Create tests following the existing test patterns. Tests use real PostgreSQL with transaction rollback (P12).

**File**: `tests/unit/backend/services/test_playbook_service.py` (NEW)

```python
"""
Tests for PlaybookService.

Tests playbook loading, validation, capability resolution,
plan task generation, and playbook matching.
"""

import pytest
import tempfile
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
                    "input": {"key": "value"},
                    "output": "result",
                },
            ],
        }

        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text(yaml.dump(playbook_yaml))

        # PlaybookService loads from configured dir
        # For testing, directly validate via schema
        playbook = PlaybookSchema(**playbook_yaml)
        assert playbook.playbook_name == "test.example"
        assert len(playbook.steps) == 1
        assert playbook.steps[0].id == "step-one"

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

    def test_reject_duplicate_output_keys(self) -> None:
        """Duplicate output keys across steps are rejected."""
        with pytest.raises(ValueError, match="Duplicate output keys"):
            PlaybookSchema(
                playbook_name="test.dupe-output",
                description="Dupe output",
                steps=[
                    {"id": "step-a", "capability": "test.agent", "output": "result"},
                    {"id": "step-b", "capability": "test.agent", "output": "result"},
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


class TestCapabilityResolution:
    """Test capability-to-agent resolution."""

    def test_resolve_with_registry(self) -> None:
        """Capability resolves to agent name via registry."""
        registry = {
            "content.summarizer.agent": {"agent_name": "content.summarizer.agent", "enabled": True},
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
            "test.disabled.agent": {"agent_name": "test.disabled.agent", "enabled": False},
        }
        service = PlaybookService(agent_registry=registry)
        with pytest.raises(ValueError, match="disabled"):
            service.resolve_capability("test.disabled")


class TestPlanTaskGeneration:
    """Test conversion of playbook steps to plan tasks."""

    def test_generate_tasks_from_steps(self) -> None:
        """Playbook steps convert to plan-compatible task dicts."""
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
                    "input": {"key": "value"},
                    "output": "result_one",
                },
                {
                    "id": "step-two",
                    "capability": "test.step-two",
                    "input": {"data": "@steps.step-one.output"},
                    "output": "result_two",
                    "depends_on": ["step-one"],
                },
            ],
        )

        tasks = service.generate_plan_tasks(playbook)

        assert len(tasks) == 2
        assert tasks[0]["name"] == "step-one"
        assert tasks[0]["assigned_agent"] == "test.step-one.agent"
        assert tasks[0]["sort_order"] == 0
        assert tasks[0]["dependencies"] == []

        assert tasks[1]["name"] == "step-two"
        assert tasks[1]["assigned_agent"] == "test.step-two.agent"
        assert tasks[1]["sort_order"] == 1
        assert len(tasks[1]["dependencies"]) == 1
        assert tasks[1]["dependencies"][0]["depends_on_index"] == 0
        assert tasks[1]["dependencies"][0]["type"] == "completion"

    def test_metadata_preserved_in_input(self) -> None:
        """Step metadata (_output_key, _execution_environment) is in input_data."""
        registry = {
            "test.agent.agent": {"agent_name": "test.agent.agent", "enabled": True},
        }
        service = PlaybookService(agent_registry=registry)

        playbook = PlaybookSchema(
            playbook_name="test.meta",
            description="Test metadata",
            steps=[
                {
                    "id": "step-one",
                    "capability": "test.agent",
                    "environment": "container",
                    "output": "my_result",
                },
            ],
        )

        tasks = service.generate_plan_tasks(playbook)
        input_data = tasks[0]["input_data"]
        assert input_data["_playbook_step_id"] == "step-one"
        assert input_data["_execution_environment"] == "container"
        assert input_data["_output_key"] == "my_result"


class TestPlaybookMatching:
    """Test deterministic playbook matching (P2)."""

    def test_match_by_pattern(self) -> None:
        """User input matching trigger patterns returns the playbook."""
        registry = {}
        service = PlaybookService(agent_registry=registry)

        # Manually inject a playbook for testing
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

1. **Mission creation from playbook** — verify session created, plan generated, mission row persisted
2. **Mission state machine** — verify valid transitions (pending→running→completed), reject invalid ones (completed→running)
3. **Step output accumulation** — verify `on_task_completed()` stores output in mission context under the correct key
4. **Step input resolution** — verify `@context.key` and `@steps.step_id.output` references resolve correctly
5. **Nested reference resolution** — verify references inside lists and nested dicts resolve
6. **Context size limit** — verify large outputs are truncated with a reference
7. **Concurrency limit** — verify creation fails when max concurrent missions reached
8. **Mission completion detection** — verify mission auto-completes when all plan tasks complete
9. **Mission failure detection** — verify mission auto-fails when all remaining tasks are blocked
10. **Cancel mission** — verify pending and running missions can be cancelled

Follow the existing test patterns from `tests/unit/backend/services/` and `tests/unit/backend/repositories/`. Use real PostgreSQL with transaction rollback (P12). Use `TestModel` for any agent interactions (P11).

**File**: `tests/unit/backend/api/test_playbooks_api.py` (NEW)

Tests for the playbook and mission API endpoints. Follow the existing pattern from `tests/unit/backend/api/test_health.py`. Test:

1. `GET /api/v1/playbooks` — returns list of enabled playbooks
2. `GET /api/v1/playbooks/{name}` — returns playbook detail
3. `GET /api/v1/playbooks/{name}` with missing name — returns 404
4. `POST /api/v1/playbooks/missions` — creates and starts a mission
5. `GET /api/v1/playbooks/missions` — lists missions
6. `GET /api/v1/playbooks/missions/{id}` — returns mission detail
7. `GET /api/v1/playbooks/missions/{id}/status` — returns progress summary
8. `POST /api/v1/playbooks/missions/{id}/cancel` — cancels mission

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
- Coordinator playbook matching is skipped
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

1. **Container execution** (`environment: container`) — The data model is prepared (execution environment stored in task input metadata). Actual container orchestration (Docker/K8s) is a separate plan.
2. **Scheduled triggers** (`trigger.type: schedule`) — The schema supports cron expressions. Implementation requires Temporal timers (Plan 15) or Taskiq scheduled tasks.
3. **Event triggers** (`trigger.type: event`) — The schema supports event type subscriptions. Implementation requires event bus subscription management.
4. **Playbook composition** (playbooks that reference other playbooks) — Future extension. Keep playbooks flat for now.
5. **Playbook versioning with history** — Currently, the playbook YAML is the single source. No version history or rollback. If needed, use git.
6. **Agent-specific playbook tools** — `playbook.list_playbooks()`, `playbook.run_playbook()` tools for horizontal agents. Implement when the PM agent needs to trigger playbooks programmatically.
7. **Playbook marketplace/sharing** — Importing playbooks from external sources.
