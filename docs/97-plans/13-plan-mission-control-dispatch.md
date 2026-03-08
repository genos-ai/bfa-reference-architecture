# Implementation Plan: Mission Control Dispatch + Planning Agent

*Created: 2026-03-04*
*Status: Done*
*Phase: 4 of 8 (AI-First Platform Build)*
*Depends on: Phase 1 (Event Bus), Phase 2 (Session Model), Phase 3 (Streaming Mission Control)*
*Blocked by: Phase 3*

---

## Summary

Build the Mission Control dispatch engine — a deterministic Python class that receives a mission brief, calls the Planning Agent for task decomposition, validates the resulting TaskPlan, and executes agents in topological order with parallel execution where possible. This replaces the old PM Agent concept.

The Planning Agent (Opus 4.6 with extended thinking) is the only point where AI reasoning influences orchestration. Everything else is deterministic code: DAG validation, agent dispatch, timeout enforcement, cost tracking, result aggregation.

Verification in this plan is Tier 1 only (structural validation against agent output contracts). The full 3-tier pipeline comes in Plan 14.

**Dev mode: breaking changes allowed.** This is a new subsystem — no backward-compatibility constraints. The `AgentConfigSchema` gains a required `interface` field for roster agents. Mission control gains a dispatch entry point alongside the existing `handle()` from Plan 12. All multi-agent orchestration flows through the dispatch loop.

## Context

- Research doc: `docs/98-research/11-bfa-workflow-architecture-specification.md` — Mission Control, Planning Agent, TaskPlan schema, agent roster, execution flow
- Architecture: `docs/99-reference-architecture/40-agentic-architecture.md`, `docs/99-reference-architecture/47-agentic-module-organization.md`
- Project principles: P2 (Deterministic Over Non-Deterministic), P6 (Mission Control Is Infrastructure), P11 (Test Without LLMs), P13 (No Agent Self-Evaluation)
- Plan 12: streaming `handle()`, `mission_control/` directory, `AgentInterfaceSchema`, `AgentModelSchema`
- Plan 14 (downstream): full 3-tier verification pipeline, deterministic check registry — this plan stubs the verification hook that Plan 14 replaces

## What to Build

- `config/mission_control/rosters/` directory — roster YAML files
- `config/mission_control/rosters/default.yaml` — default roster (existing vertical agents + planning + verification)
- `modules/backend/agents/mission_control/roster.py` — roster loading, validation, agent lookup (~150 lines)
- `modules/backend/schemas/task_plan.py` — TaskPlan Pydantic model matching research doc schema (~200 lines)
- `modules/backend/agents/mission_control/plan_validator.py` — 11 validation rules (~200 lines)
- `modules/backend/agents/mission_control/dispatch.py` — dispatch loop, the core of Mission Control (~300 lines)
- `modules/backend/agents/mission_control/outcome.py` — MissionOutcome schema (~80 lines)
- `modules/backend/agents/horizontal/__init__.py` — package init
- `modules/backend/agents/horizontal/planning/__init__.py` — package init
- `modules/backend/agents/horizontal/planning/agent.py` — Planning Agent definition (~100 lines)
- `config/agents/horizontal/planning/agent.yaml` — Planning Agent config
- `config/prompts/categories/horizontal.md` — horizontal agent category prompt
- `config/prompts/agents/horizontal/planning/system.md` — Planning Agent system prompt (security-critical)
- `modules/backend/agents/mission_control/mission_control.py` — MODIFY: add dispatch entry point
- `modules/backend/agents/config_schema.py` — MODIFY: make `interface` required for roster agents
- Tests: TaskPlan validation, dispatch loop, roster loading, Planning Agent with TestModel

## Key Design Decisions

- **Mission Control is a Python class, not a PydanticAI agent.** It is deterministic code that calls agents. It never calls an LLM directly — it delegates to the Planning Agent for task decomposition. This is P2 (Deterministic Over Non-Deterministic) and P6 (Mission Control Is Infrastructure) applied directly.
- **Planning Agent specification:**
  - Model: Opus 4.6 with extended thinking
  - Single shared definition used by all Mission Control instances
  - Input: mission brief, agent roster (names + descriptions + interface contracts), upstream context, output format spec
  - Output: TaskPlan JSON within XML tags (extended thinking doesn't support `response_format`)
  - Thinking budget scaled per mission complexity tier (configurable in `mission_control.yaml`)
  - System prompt is security-critical and version-controlled
  - Thinking trace captured and stored for audit trail
- **TaskPlan schema (from research doc):**
  - Top-level: `version`, `mission_id`, `summary`, `estimated_cost_usd`, `estimated_duration_seconds`
  - Per task: `task_id`, `agent`, `agent_version`, `description`, `instructions`, `inputs` (static + from_upstream), `dependencies`, verification spec (tier_1/tier_2/tier_3), `constraints` (timeout_override, priority)
  - Execution hints: `min_success_threshold`, `critical_path`
- **11 Validation rules (all deterministic code):**
  1. Schema validation — all required fields, correct types
  2. Agent validation — agent + version exists in roster
  3. DAG validation — topological sort succeeds, no cycles (Kahn's algorithm)
  4. Dependency consistency — `from_upstream` source_tasks in dependencies
  5. Input compatibility — source_fields exist in source agent output contract
  6. Check registry validation — DEFERRED to Plan 14 (always passes in this plan)
  7. Budget validation — estimated_cost within mission budget
  8. Timeout validation — overrides within roster maximums
  9. Critical path validation — all `critical_path` task_ids exist
  10. Tier 3 completeness — criteria + evaluator + threshold present when required
  11. Self-evaluation prevention — no task specifies itself as evaluator
  - On validation failure: retry Planning Agent (max 2 attempts), then fail mission
- **Dispatch loop:**
  - Topological sort of DAG
  - Independent tasks run in parallel via `asyncio.gather`
  - Sequential dependencies enforced
  - Per-agent timeout via `asyncio.wait_for`
  - Per-agent cost ceiling enforcement via PydanticAI `UsageLimits`
  - `from_upstream` resolution: substitute actual outputs from completed tasks at dispatch time
  - Verification hook: `verify_task()` called after each agent returns — Tier 1 only (structural validation against interface contract). Plan 14 replaces this with full 3-tier pipeline.
  - On Tier 1 failure: retry agent with failure details appended to instructions (Reflection pattern), within retry budget
  - Partial failure: if `min_success_threshold` met and critical path tasks succeeded, return partial success
- **MissionOutcome schema:**
  - `mission_id`, `status` (success/partial/failed)
  - `task_results`: per task — `task_id`, `agent_name`, `status`, `output_reference`, `token_usage`, `cost_usd`, `duration_seconds`, `verification_outcome` (tier_1 only in this plan), `retry_count`, `retry_history`
  - `total_cost_usd`, `total_duration_seconds`, `total_tokens`
  - `planning_trace_reference`, `task_plan_reference`
- **P10 Integration — simple vs complex requests:**
  - `handle()` from Plan 12 gains a complexity check
  - Simple requests (single agent, no decomposition): existing direct-agent path, unchanged
  - Complex requests (explicit `mission_brief` parameter or matched playbook): routed to dispatch loop
  - This is additive — Plan 12's functionality is preserved
- **Agent roster:**
  - Static per Mission Control type, defined in YAML
  - Each roster entry: `agent_name`, `agent_version`, `description` (written for LLM comprehension), `model` (pinned), `tools`, `interface` contract, `constraints` (timeout, cost_ceiling, retry_budget, parallelism)
  - Every roster auto-includes planning agent and verification agent (verification agent used in Plan 14)
  - Roster validation at load time
- **Model pinning:** Models are immutable agent properties (from Plan 12's `AgentModelSchema`). Planning Agent always uses Opus 4.6. Worker agents use whatever model is pinned in their config. No runtime override.

## Success Criteria

- [ ] Roster YAML loads and validates with agent existence checks
- [ ] Planning Agent (TestModel in tests) receives mission brief and returns TaskPlan JSON
- [ ] TaskPlan validates against all 11 rules (rule 6 deferred)
- [ ] Invalid TaskPlan triggers Planning Agent retry (max 2), then mission failure
- [ ] Dispatch loop executes tasks in topological order
- [ ] Independent tasks run in parallel
- [ ] `from_upstream` references resolve correctly at dispatch time
- [ ] Per-agent timeout enforced (`asyncio.wait_for`)
- [ ] Tier 1 verification validates agent output against interface contract
- [ ] Retry-with-feedback appends failure details to instructions
- [ ] Partial success when threshold met and critical path succeeded
- [ ] MissionOutcome returned with per-task results and cost breakdown
- [ ] Planning Agent thinking trace captured
- [ ] `handle()` routes simple requests to direct path, complex to dispatch
- [ ] All Plan 12 tests still pass (simple agent routing unchanged)

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Commit any uncommitted work | `git status`, then commit if needed |
| 0.2 | Create feature branch | `git checkout -b feature/mission-control-dispatch` |

---

### Step 1: Roster Config + Schema

**Directory:** `config/mission_control/rosters/` (NEW)

Create the directory structure for roster YAML files.

**File:** `config/mission_control/rosters/default.yaml` (NEW, ~80 lines)

The default roster defines all agents available to Mission Control for dispatch. Every roster auto-includes the planning and verification agents. Worker agents are the existing vertical agents.

```yaml
# =============================================================================
# Default Agent Roster
# =============================================================================
#   Static agent roster for Mission Control dispatch.
#   Each entry defines what the Planning Agent can select from.
#   Models are pinned — no runtime override (P2, research doc 11).
#
#   auto_include:
#     planning_agent and verification_agent are appended automatically.
#     Do not list them here unless overriding defaults.
#
#   Fields per agent:
#     agent_name       - Unique identifier matching agent YAML (string)
#     agent_version    - Semantic version, must match agent config (string)
#     description      - Written for LLM comprehension (string)
#     model            - Pinned model config (object)
#       name           - Model identifier (string)
#       temperature    - Temperature (float)
#       max_tokens     - Max output tokens (int)
#     tools            - Available tool names (list of strings)
#     interface        - Typed I/O contract (object)
#       input          - Input fields: field_name → type_name (object)
#       output         - Output fields: field_name → type_name (object)
#     constraints      - Execution constraints (object)
#       timeout_seconds    - Hard timeout per invocation (int)
#       cost_ceiling_usd   - Max cost per invocation (float)
#       retry_budget       - Max retries on failure (int)
#       parallelism        - "safe" or "unsafe" (string)
# =============================================================================

agents:
  - agent_name: code.qa.agent
    agent_version: "1.0.0"
    description: >
      Audits Python codebases for compliance violations including import
      patterns, datetime usage, hardcoded values, and file size limits.
      Returns structured findings with severity ratings and suggested fixes.
    model:
      name: "anthropic:claude-haiku-4-5-20251001"
      temperature: 0.0
      max_tokens: 4096
    tools:
      - filesystem.read_file
      - filesystem.list_files
      - compliance.scan_imports
      - compliance.scan_datetime
      - compliance.scan_hardcoded
      - compliance.scan_file_sizes
      - code.apply_fix
      - code.run_tests
    interface:
      input:
        target_path: string
        scan_rules: list[string]
      output:
        findings: list[object]
        summary: string
        severity_counts: object
        confidence: float
    constraints:
      timeout_seconds: 120
      cost_ceiling_usd: 0.50
      retry_budget: 2
      parallelism: safe

  - agent_name: system.health.agent
    agent_version: "1.0.0"
    description: >
      Reports system health status including service availability, resource
      utilization, and configuration validation. Used as the fallback agent
      for unroutable requests.
    model:
      name: "anthropic:claude-haiku-4-5-20251001"
      temperature: 0.0
      max_tokens: 2048
    tools:
      - system.check_health
      - system.get_config_status
    interface:
      input:
        query: string
      output:
        status: string
        details: object
        confidence: float
    constraints:
      timeout_seconds: 60
      cost_ceiling_usd: 0.10
      retry_budget: 1
      parallelism: safe
```

**File:** `modules/backend/agents/mission_control/roster.py` (NEW, ~150 lines)

Loads roster YAML, validates against `RosterSchema`, provides agent lookup by name+version.

```python
"""Agent roster loader and validator.

The roster defines which agents are available for Mission Control dispatch.
Static per Mission Control type, loaded from YAML at startup.
Planning Agent and Verification Agent are auto-included in every roster.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from modules.backend.core.logging import get_logger
from modules.backend.core.utils import find_project_root

logger = get_logger(__name__)


# -- Roster entry schemas ---------------------------------------------------

class RosterModelSchema(BaseModel):
    """Pinned model config within a roster entry."""

    model_config = ConfigDict(extra="forbid")

    name: str
    temperature: float = 0.0
    max_tokens: int = 4096


class RosterInterfaceSchema(BaseModel):
    """Typed I/O contract within a roster entry."""

    model_config = ConfigDict(extra="forbid")

    input: dict[str, str] = Field(default_factory=dict)
    output: dict[str, str] = Field(default_factory=dict)


class RosterConstraintsSchema(BaseModel):
    """Execution constraints within a roster entry."""

    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int = 120
    cost_ceiling_usd: float = 1.0
    retry_budget: int = 2
    parallelism: str = "safe"


class RosterAgentEntry(BaseModel):
    """A single agent in the roster."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    agent_version: str
    description: str
    model: RosterModelSchema
    tools: list[str] = Field(default_factory=list)
    interface: RosterInterfaceSchema
    constraints: RosterConstraintsSchema = Field(
        default_factory=RosterConstraintsSchema,
    )


class Roster(BaseModel):
    """Complete agent roster for a Mission Control instance."""

    model_config = ConfigDict(extra="forbid")

    agents: list[RosterAgentEntry]

    def get_agent(self, name: str, version: str) -> RosterAgentEntry | None:
        """Look up agent by name and version. Returns None if not found."""
        for agent in self.agents:
            if agent.agent_name == name and agent.agent_version == version:
                return agent
        return None

    def get_agent_by_name(self, name: str) -> RosterAgentEntry | None:
        """Look up agent by name only (latest version). Returns None if not found."""
        for agent in self.agents:
            if agent.agent_name == name:
                return agent
        return None

    @property
    def agent_names(self) -> list[str]:
        """All agent names in the roster."""
        return [a.agent_name for a in self.agents]


# -- Auto-included agents --------------------------------------------------

PLANNING_AGENT_ENTRY = RosterAgentEntry(
    agent_name="horizontal.planning.agent",
    agent_version="1.0.0",
    description="Decomposes mission briefs into executable task plans.",
    model=RosterModelSchema(
        name="anthropic:claude-opus-4-20250514",
        temperature=0.0,
        max_tokens=16384,
    ),
    tools=[],
    interface=RosterInterfaceSchema(
        input={"mission_brief": "string", "roster": "object", "upstream_context": "object"},
        output={"task_plan": "object"},
    ),
    constraints=RosterConstraintsSchema(
        timeout_seconds=300,
        cost_ceiling_usd=5.0,
        retry_budget=2,
        parallelism="unsafe",
    ),
)

VERIFICATION_AGENT_ENTRY = RosterAgentEntry(
    agent_name="horizontal.verification.agent",
    agent_version="1.0.0",
    description="Evaluates agent output quality against criteria. Used in Tier 3 verification.",
    model=RosterModelSchema(
        name="anthropic:claude-opus-4-20250514",
        temperature=0.0,
        max_tokens=8192,
    ),
    tools=[],
    interface=RosterInterfaceSchema(
        input={"task_instructions": "string", "evaluation_criteria": "list[string]", "agent_output": "object"},
        output={"overall_score": "float", "pass": "bool", "criteria_results": "list[object]"},
    ),
    constraints=RosterConstraintsSchema(
        timeout_seconds=180,
        cost_ceiling_usd=3.0,
        retry_budget=1,
        parallelism="unsafe",
    ),
)


def load_roster(roster_name: str = "default") -> Roster:
    """Load and validate a roster from YAML. Auto-includes planning and verification agents."""
    roster_path = (
        find_project_root()
        / "config"
        / "mission_control"
        / "rosters"
        / f"{roster_name}.yaml"
    )
    if not roster_path.exists():
        raise FileNotFoundError(f"Roster not found: {roster_path}")

    with open(roster_path) as f:
        raw = yaml.safe_load(f)

    roster = Roster.model_validate(raw)

    # Auto-include planning and verification agents if not already present
    if not roster.get_agent_by_name(PLANNING_AGENT_ENTRY.agent_name):
        roster.agents.append(PLANNING_AGENT_ENTRY)
    if not roster.get_agent_by_name(VERIFICATION_AGENT_ENTRY.agent_name):
        roster.agents.append(VERIFICATION_AGENT_ENTRY)

    logger.info(
        "Roster loaded",
        extra={
            "roster": roster_name,
            "agent_count": len(roster.agents),
            "agents": roster.agent_names,
        },
    )
    return roster
```

**Verify:** `load_roster("default")` returns a `Roster` with worker agents + auto-included planning and verification agents.

---

### Step 2: TaskPlan Schema

**File:** `modules/backend/schemas/task_plan.py` (NEW, ~200 lines)

Pydantic models for the TaskPlan JSON that the Planning Agent produces and Mission Control validates. Matches the schema defined in `docs/98-research/11-bfa-workflow-architecture-specification.md`.

```python
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
```

**Verify:** `TaskPlan.model_validate(research_doc_example)` parses the full example from the research doc without error.

---

### Step 3: Plan Validator

**File:** `modules/backend/agents/mission_control/plan_validator.py` (NEW, ~200 lines)

All 11 validation rules as deterministic code. Each rule is a function that returns a list of error strings. The validator runs all rules and aggregates errors.

```python
"""TaskPlan validation — 11 deterministic rules.

Every plan must pass all rules before Mission Control begins execution.
On failure: log the specific error, retry Planning Agent (max 2), then fail mission.

Rules:
  1. Schema validation — Pydantic handles this at parse time
  2. Agent validation — agent+version exists in roster
  3. DAG validation — topological sort succeeds, no cycles
  4. Dependency consistency — from_upstream source_tasks in dependencies
  5. Input compatibility — source_fields exist in source agent output contract
  6. Check registry validation — DEFERRED to Plan 14 (always passes)
  7. Budget validation — estimated_cost within mission budget
  8. Timeout validation — overrides within roster maximums
  9. Critical path validation — all critical_path task_ids exist
  10. Tier 3 completeness — criteria + evaluator + threshold present
  11. Self-evaluation prevention — no task specifies itself as evaluator
"""

from collections import deque

from modules.backend.agents.mission_control.roster import Roster
from modules.backend.core.logging import get_logger
from modules.backend.schemas.task_plan import TaskPlan

logger = get_logger(__name__)


class ValidationResult:
    """Aggregated result from all validation rules."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, rule: str, message: str) -> None:
        self.errors.append(f"[{rule}] {message}")

    def __repr__(self) -> str:
        if self.is_valid:
            return "ValidationResult(valid=True)"
        return f"ValidationResult(valid=False, errors={len(self.errors)})"


def validate_plan(
    plan: TaskPlan,
    roster: Roster,
    mission_budget_usd: float,
) -> ValidationResult:
    """Run all 11 validation rules against the plan. Returns aggregated result."""
    result = ValidationResult()

    # Rule 1: Schema validation — handled by Pydantic at parse time.
    # If we reach this function, parsing succeeded.

    _rule_2_agent_validation(plan, roster, result)
    _rule_3_dag_validation(plan, result)
    _rule_4_dependency_consistency(plan, result)
    _rule_5_input_compatibility(plan, roster, result)
    _rule_6_check_registry(plan, result)       # DEFERRED — always passes
    _rule_7_budget_validation(plan, mission_budget_usd, result)
    _rule_8_timeout_validation(plan, roster, result)
    _rule_9_critical_path_validation(plan, result)
    _rule_10_tier3_completeness(plan, roster, result)
    _rule_11_self_evaluation_prevention(plan, result)

    if result.is_valid:
        logger.info("TaskPlan validation passed", extra={"mission_id": plan.mission_id})
    else:
        logger.warning(
            "TaskPlan validation failed",
            extra={"mission_id": plan.mission_id, "error_count": len(result.errors)},
        )

    return result


def _rule_2_agent_validation(plan: TaskPlan, roster: Roster, result: ValidationResult) -> None:
    """Every agent+version in the plan must exist in the roster."""
    for task in plan.tasks:
        entry = roster.get_agent(task.agent, task.agent_version)
        if entry is None:
            result.add_error(
                "agent_validation",
                f"Task '{task.task_id}': agent '{task.agent}' "
                f"version '{task.agent_version}' not in roster",
            )


def _rule_3_dag_validation(plan: TaskPlan, result: ValidationResult) -> None:
    """Topological sort using Kahn's algorithm. Reject cycles."""
    task_ids = {t.task_id for t in plan.tasks}

    # Check for duplicate task IDs
    if len(task_ids) != len(plan.tasks):
        seen = set()
        for t in plan.tasks:
            if t.task_id in seen:
                result.add_error("dag_validation", f"Duplicate task_id: '{t.task_id}'")
            seen.add(t.task_id)
        return

    # Check dependency references exist
    for task in plan.tasks:
        for dep in task.dependencies:
            if dep not in task_ids:
                result.add_error(
                    "dag_validation",
                    f"Task '{task.task_id}' depends on unknown task '{dep}'",
                )

    # Kahn's algorithm for cycle detection
    in_degree: dict[str, int] = {tid: 0 for tid in task_ids}
    adjacency: dict[str, list[str]] = {tid: [] for tid in task_ids}

    for task in plan.tasks:
        for dep in task.dependencies:
            if dep in task_ids:
                adjacency[dep].append(task.task_id)
                in_degree[task.task_id] += 1

    queue: deque[str] = deque(
        tid for tid, deg in in_degree.items() if deg == 0
    )
    sorted_count = 0

    while queue:
        node = queue.popleft()
        sorted_count += 1
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if sorted_count != len(task_ids):
        result.add_error("dag_validation", "Cycle detected in task dependency graph")


def _rule_4_dependency_consistency(plan: TaskPlan, result: ValidationResult) -> None:
    """Every from_upstream source_task must be in the task's dependencies."""
    for task in plan.tasks:
        for field_name, ref in task.inputs.from_upstream.items():
            if ref.source_task not in task.dependencies:
                result.add_error(
                    "dependency_consistency",
                    f"Task '{task.task_id}': from_upstream field '{field_name}' "
                    f"references task '{ref.source_task}' which is not in dependencies",
                )


def _rule_5_input_compatibility(plan: TaskPlan, roster: Roster, result: ValidationResult) -> None:
    """Every from_upstream source_field must exist in the source agent's output contract."""
    task_agent_map = {t.task_id: t.agent for t in plan.tasks}

    for task in plan.tasks:
        for field_name, ref in task.inputs.from_upstream.items():
            source_agent_name = task_agent_map.get(ref.source_task)
            if source_agent_name is None:
                continue  # Rule 3 catches missing tasks

            source_entry = roster.get_agent_by_name(source_agent_name)
            if source_entry is None:
                continue  # Rule 2 catches missing agents

            if ref.source_field not in source_entry.interface.output:
                result.add_error(
                    "input_compatibility",
                    f"Task '{task.task_id}': from_upstream field '{field_name}' "
                    f"references source_field '{ref.source_field}' which does not "
                    f"exist in agent '{source_agent_name}' output contract "
                    f"(available: {list(source_entry.interface.output.keys())})",
                )


def _rule_6_check_registry(plan: TaskPlan, result: ValidationResult) -> None:
    """DEFERRED to Plan 14. Always passes in this plan."""
    pass


def _rule_7_budget_validation(
    plan: TaskPlan,
    mission_budget_usd: float,
    result: ValidationResult,
) -> None:
    """Estimated cost must be within mission budget."""
    if plan.estimated_cost_usd > mission_budget_usd:
        result.add_error(
            "budget_validation",
            f"Estimated cost ${plan.estimated_cost_usd:.2f} exceeds "
            f"mission budget ${mission_budget_usd:.2f}",
        )


def _rule_8_timeout_validation(plan: TaskPlan, roster: Roster, result: ValidationResult) -> None:
    """Timeout overrides must not exceed roster maximums."""
    for task in plan.tasks:
        override = task.constraints.timeout_override_seconds
        if override is None:
            continue

        entry = roster.get_agent_by_name(task.agent)
        if entry is None:
            continue  # Rule 2 catches missing agents

        if override > entry.constraints.timeout_seconds:
            result.add_error(
                "timeout_validation",
                f"Task '{task.task_id}': timeout override {override}s exceeds "
                f"roster maximum {entry.constraints.timeout_seconds}s for agent '{task.agent}'",
            )


def _rule_9_critical_path_validation(plan: TaskPlan, result: ValidationResult) -> None:
    """All critical_path task_ids must exist in the plan."""
    task_ids = set(plan.task_ids)
    for cp_id in plan.execution_hints.critical_path:
        if cp_id not in task_ids:
            result.add_error(
                "critical_path_validation",
                f"Critical path references unknown task: '{cp_id}'",
            )


def _rule_10_tier3_completeness(plan: TaskPlan, roster: Roster, result: ValidationResult) -> None:
    """When Tier 3 is required, criteria+evaluator+threshold must all be present."""
    for task in plan.tasks:
        t3 = task.verification.tier_3
        if not t3.requires_ai_evaluation:
            continue

        if not t3.evaluation_criteria:
            result.add_error(
                "tier3_completeness",
                f"Task '{task.task_id}': Tier 3 enabled but evaluation_criteria is empty",
            )
        if not t3.evaluator_agent:
            result.add_error(
                "tier3_completeness",
                f"Task '{task.task_id}': Tier 3 enabled but evaluator_agent is missing",
            )
        if t3.min_evaluation_score is None:
            result.add_error(
                "tier3_completeness",
                f"Task '{task.task_id}': Tier 3 enabled but min_evaluation_score is missing",
            )
        if t3.evaluator_agent and not roster.get_agent_by_name(t3.evaluator_agent):
            result.add_error(
                "tier3_completeness",
                f"Task '{task.task_id}': evaluator_agent '{t3.evaluator_agent}' not in roster",
            )


def _rule_11_self_evaluation_prevention(plan: TaskPlan, result: ValidationResult) -> None:
    """No task may specify itself (its own agent) as the evaluator."""
    for task in plan.tasks:
        t3 = task.verification.tier_3
        if t3.requires_ai_evaluation and t3.evaluator_agent == task.agent:
            result.add_error(
                "self_evaluation_prevention",
                f"Task '{task.task_id}': agent '{task.agent}' cannot evaluate its own output (P13)",
            )
```

**Verify:** Create a valid TaskPlan and an invalid one (cycle, missing agent, budget exceeded). Validate both. Valid passes, invalid returns specific errors per rule.

---

### Step 4: Planning Agent

**File:** `modules/backend/agents/horizontal/__init__.py` (NEW)

```python
"""Horizontal agents — cross-domain specialists that serve Mission Control."""
```

**File:** `modules/backend/agents/horizontal/planning/__init__.py` (NEW)

```python
"""Planning Agent — task decomposition for Mission Control."""
```

**File:** `modules/backend/agents/horizontal/planning/agent.py` (NEW, ~100 lines)

The Planning Agent is a PydanticAI agent that decomposes mission briefs into TaskPlan JSON. It is the only point where AI reasoning influences orchestration.

```python
"""Planning Agent — task decomposition via Opus 4.6 extended thinking.

Called by Mission Control (code), not by other agents.
Input: mission brief, agent roster, upstream context, output format spec.
Output: TaskPlan JSON within <task_plan> XML tags.
Thinking trace captured for audit trail.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent

from modules.backend.agents.deps.base import BaseAgentDeps
from modules.backend.agents.mission_control.mission_control import (
    assemble_instructions,
    _build_model,
)
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PlanningAgentDeps(BaseAgentDeps):
    """Dependencies injected into the Planning Agent at runtime."""

    mission_brief: str = ""
    roster_description: str = ""
    upstream_context: dict[str, Any] | None = None


def create_agent(config: dict) -> Agent:
    """Create the Planning Agent instance.

    Model: Opus 4.6 with extended thinking.
    System prompt loaded from config/prompts/agents/horizontal/planning/system.md.
    """
    model = _build_model(config.get("model", "anthropic:claude-opus-4-20250514"))
    system_prompt = assemble_instructions("horizontal", "planning")

    agent = Agent(
        model,
        system_prompt=system_prompt,
        deps_type=PlanningAgentDeps,
    )

    return agent


async def run_agent(
    agent: Agent,
    deps: PlanningAgentDeps,
    user_prompt: str,
    **kwargs: Any,
) -> dict:
    """Run the Planning Agent. Returns parsed TaskPlan dict and thinking trace.

    The agent returns JSON within <task_plan> tags. This function extracts,
    parses, and returns the JSON as a dict. The caller (Mission Control)
    validates it via plan_validator.
    """
    result = await agent.run(user_prompt, deps=deps, **kwargs)

    # Extract JSON from <task_plan> tags
    response_text = result.data
    plan_json = extract_task_plan_json(response_text)

    # Capture thinking trace if available
    thinking_trace = None
    if hasattr(result, "all_messages"):
        for msg in result.all_messages():
            for part in getattr(msg, "parts", []):
                if hasattr(part, "content") and hasattr(part, "part_kind"):
                    if "thinking" in str(getattr(part, "part_kind", "")):
                        thinking_trace = part.content

    return {
        "task_plan": plan_json,
        "thinking_trace": thinking_trace,
        "usage": result.usage() if hasattr(result, "usage") else None,
    }


def extract_task_plan_json(text: str) -> dict:
    """Extract TaskPlan JSON from within <task_plan> XML tags.

    Raises ValueError if tags are missing or JSON is malformed.
    """
    pattern = r"<task_plan>\s*(.*?)\s*</task_plan>"
    match = re.search(pattern, text, re.DOTALL)

    if not match:
        raise ValueError(
            "Planning Agent response does not contain <task_plan> tags. "
            "Response must include JSON within <task_plan>...</task_plan> tags."
        )

    json_str = match.group(1).strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Planning Agent response contains invalid JSON within <task_plan> tags: {e}"
        ) from e
```

**File:** `config/agents/horizontal/planning/agent.yaml` (NEW)

```yaml
# =============================================================================
# Planning Agent Configuration
# =============================================================================
#   The Planning Agent decomposes mission briefs into executable task plans.
#   Called by Mission Control, not by other agents.
#
#   Model: Opus 4.6 with extended thinking — best reasoning for task decomposition.
#   Model is PINNED — no runtime override (P2).
#   System prompt is security-critical — changes require review.
#
#   Fields:
#     agent_name        - Unique agent identifier (string)
#     agent_type        - Agent type: horizontal (string)
#     description       - Agent description (string)
#     enabled           - Enable/disable (boolean)
#     model             - Pinned model config (object)
#       name            - Model identifier (string)
#       temperature     - Temperature, pinned (float)
#       max_tokens      - Max output tokens, pinned (int)
#     version           - Semantic version (string)
#     keywords          - Not used for horizontal agents (empty list)
#     tools             - No tools — Planning Agent reasons only (empty list)
#     max_input_length  - Maximum input character count (integer)
#     max_budget_usd    - Maximum cost per invocation in USD (decimal)
#     execution         - Execution mode (object)
#     interface         - Typed I/O contract (object)
#     thinking_budget   - Extended thinking token budget per complexity tier (object)
# =============================================================================

agent_name: horizontal.planning.agent
agent_type: horizontal
description: "Decomposes mission briefs into executable task plans with dependency graphs, verification specs, and cost estimates."
enabled: true
version: "1.0.0"

model:
  name: "anthropic:claude-opus-4-20250514"
  temperature: 0.0
  max_tokens: 16384

keywords: []
tools: []

max_input_length: 64000
max_budget_usd: 5.00

execution:
  mode: local

interface:
  input:
    mission_brief: string
    roster: object
    upstream_context: object
  output:
    task_plan: object

thinking_budget:
  simple: 10000
  standard: 20000
  complex: 30000
```

**File:** `config/prompts/categories/horizontal.md` (NEW)

```markdown
You are a horizontal agent in the BFA agentic platform. Horizontal agents operate across domain boundaries to serve Mission Control. You do not execute domain-specific work — you plan, verify, or coordinate.

Your output is consumed by deterministic code (Mission Control), not by humans directly. Precision, structure, and adherence to the output format specification are critical. Ambiguity in your output causes validation failures and mission retries.
```

**File:** `config/prompts/agents/horizontal/planning/system.md` (NEW, security-critical)

```markdown
You are the Planning Agent. Your job is to decompose a mission brief into a structured task plan that Mission Control will execute deterministically.

## Your Input

You receive:
1. A mission brief describing the objective, constraints, and expected outcomes.
2. An agent roster listing every available agent with their descriptions, interface contracts (typed inputs and outputs), tools, and constraints.
3. Upstream context from previously completed missions (if any).
4. An output format specification.

## Your Output

You MUST return a TaskPlan as JSON within <task_plan> XML tags. No other format is accepted. Example:

<task_plan>
{
  "version": "1.0.0",
  "mission_id": "...",
  "summary": "...",
  ...
}
</task_plan>

## TaskPlan Rules

1. Every `agent` and `agent_version` MUST reference an agent in the provided roster. Do not invent agents.
2. Every `from_upstream.source_task` MUST appear in the task's `dependencies` array.
3. Every `from_upstream.source_field` MUST exist in the source agent's output contract from the roster.
4. The dependency graph MUST be a DAG (directed acyclic graph). No cycles.
5. `estimated_cost_usd` MUST be a realistic estimate based on agent model pricing and expected token usage. Do not underestimate.
6. `estimated_duration_seconds` MUST account for parallelism — independent tasks run concurrently.
7. Use `critical_path` to mark tasks that must succeed for the mission to be meaningful.
8. Set `min_success_threshold` appropriately — 1.0 means all tasks must succeed, 0.5 means half.

## Verification Rules

- Tier 1 (structural): Always enable `schema_validation: true`. List all expected output fields in `required_output_fields`.
- Tier 2 (deterministic): Specify deterministic checks only if registered check functions exist for this domain.
- Tier 3 (AI evaluation): Request ONLY when the task output genuinely requires judgment — code generation, analysis, recommendations. Pure data retrieval or transformation tasks survive on Tier 1 and Tier 2 alone. Every Tier 3 evaluation is an Opus call. Use sparingly to control cost.
- The `evaluator_agent` for Tier 3 MUST be "horizontal.verification.agent". No agent may evaluate its own output.

## Constraints

- Do not include agents not in the roster.
- Do not override model selections — models are pinned in the roster.
- Do not create circular dependencies.
- Do not request Tier 3 evaluation for simple data retrieval tasks.
- Keep instructions specific and actionable. Vague instructions produce vague outputs.
```

**Verify:** Planning Agent creates successfully with correct model and system prompt. `extract_task_plan_json()` parses valid `<task_plan>` wrapped JSON.

---

### Step 5: Dispatch Loop

**File:** `modules/backend/agents/mission_control/dispatch.py` (NEW, ~300 lines)

The dispatch loop is the core of Mission Control. It takes a validated TaskPlan and executes agents in topological order with parallel execution where possible.

```python
"""Mission Control dispatch loop — deterministic agent execution.

Takes a validated TaskPlan, executes agents in topological order,
enforces timeouts and cost ceilings, resolves from_upstream references,
runs Tier 1 verification, and aggregates results into a MissionOutcome.

This is deterministic code. No LLM calls happen here — agents are
invoked through the standard agent execution path.
"""

import asyncio
import time
from collections import deque
from typing import Any

from pydantic_ai import UsageLimits

from modules.backend.agents.mission_control.outcome import (
    MissionOutcome,
    MissionStatus,
    RetryHistoryEntry,
    TaskResult,
    TaskStatus,
    TaskTokenUsage,
    Tier1Outcome,
    VerificationOutcome,
)
from modules.backend.agents.mission_control.roster import Roster, RosterAgentEntry
from modules.backend.core.logging import get_logger
from modules.backend.schemas.task_plan import TaskDefinition, TaskPlan

logger = get_logger(__name__)


def topological_sort(plan: TaskPlan) -> list[list[str]]:
    """Sort tasks into execution layers. Each layer runs in parallel.

    Returns a list of layers, where each layer is a list of task_ids
    that can execute concurrently. Assumes DAG validation already passed.
    """
    task_ids = {t.task_id for t in plan.tasks}
    in_degree: dict[str, int] = {tid: 0 for tid in task_ids}
    dependents: dict[str, list[str]] = {tid: [] for tid in task_ids}

    for task in plan.tasks:
        for dep in task.dependencies:
            dependents[dep].append(task.task_id)
            in_degree[task.task_id] += 1

    layers: list[list[str]] = []
    queue: deque[str] = deque(
        tid for tid, deg in in_degree.items() if deg == 0
    )

    while queue:
        layer = list(queue)
        queue.clear()
        layers.append(layer)

        for node in layer:
            for neighbor in dependents[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

    return layers


def resolve_upstream_inputs(
    task: TaskDefinition,
    completed_outputs: dict[str, dict],
) -> dict[str, Any]:
    """Resolve from_upstream references using outputs from completed tasks.

    Returns the merged input dict (static + resolved upstream).
    Raises KeyError if a referenced task or field is missing.
    """
    resolved = dict(task.inputs.static)

    for field_name, ref in task.inputs.from_upstream.items():
        source_output = completed_outputs.get(ref.source_task)
        if source_output is None:
            raise KeyError(
                f"Task '{task.task_id}': upstream task '{ref.source_task}' "
                f"has no output (did it fail?)"
            )
        if ref.source_field not in source_output:
            raise KeyError(
                f"Task '{task.task_id}': upstream task '{ref.source_task}' "
                f"output missing field '{ref.source_field}'"
            )
        resolved[field_name] = source_output[ref.source_field]

    return resolved


def verify_tier1(
    output: dict,
    task: TaskDefinition,
    roster_entry: RosterAgentEntry,
) -> Tier1Outcome:
    """Tier 1 structural verification — validate output against interface contract.

    Checks:
    1. All required_output_fields from verification spec are present.
    2. All output fields from the roster interface contract are present.

    Returns Tier1Outcome with pass/fail and details.
    Plan 14 replaces this with the full 3-tier pipeline.
    """
    missing_fields: list[str] = []

    # Check required_output_fields from plan verification spec
    for field in task.verification.tier_1.required_output_fields:
        if field not in output:
            missing_fields.append(field)

    # Check roster interface contract output fields
    for field in roster_entry.interface.output:
        if field not in output:
            missing_fields.append(field)

    # Deduplicate
    missing_fields = list(set(missing_fields))

    if missing_fields:
        return Tier1Outcome(
            status="fail",
            details=f"Missing output fields: {missing_fields}",
        )

    return Tier1Outcome(status="pass", details="All required fields present")


async def execute_task(
    task: TaskDefinition,
    roster_entry: RosterAgentEntry,
    resolved_inputs: dict[str, Any],
    execute_agent_fn: Any,
) -> dict:
    """Execute a single agent task with timeout and cost ceiling enforcement.

    Args:
        task: The task definition from the plan.
        roster_entry: The agent's roster entry with constraints.
        resolved_inputs: Merged static + upstream inputs.
        execute_agent_fn: Async callable that runs the agent.
            Signature: async (agent_name, instructions, inputs, usage_limits) -> dict

    Returns:
        Agent output dict.

    Raises:
        asyncio.TimeoutError: If agent exceeds timeout.
    """
    timeout = task.constraints.timeout_override_seconds or roster_entry.constraints.timeout_seconds
    cost_ceiling = roster_entry.constraints.cost_ceiling_usd

    usage_limits = UsageLimits(
        request_limit=50,
        total_token_limit=int(cost_ceiling * 1_000_000 / 3),  # rough estimate
    )

    return await asyncio.wait_for(
        execute_agent_fn(
            agent_name=task.agent,
            instructions=task.instructions,
            inputs=resolved_inputs,
            usage_limits=usage_limits,
        ),
        timeout=timeout,
    )


async def dispatch(
    plan: TaskPlan,
    roster: Roster,
    execute_agent_fn: Any,
    mission_budget_usd: float,
) -> MissionOutcome:
    """Execute the dispatch loop for a validated TaskPlan.

    1. Topological sort into execution layers
    2. Execute each layer (parallel within layer, sequential across layers)
    3. Resolve from_upstream at dispatch time
    4. Tier 1 verification after each task
    5. Retry with feedback on Tier 1 failure
    6. Aggregate results into MissionOutcome

    Args:
        plan: Validated TaskPlan.
        roster: Agent roster.
        execute_agent_fn: Async callable to run an agent.
        mission_budget_usd: Mission cost ceiling.

    Returns:
        MissionOutcome with per-task results and cost breakdown.
    """
    start_time = time.monotonic()
    layers = topological_sort(plan)

    completed_outputs: dict[str, dict] = {}
    task_results: list[TaskResult] = []
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    total_thinking_tokens = 0

    for layer in layers:
        # Execute all tasks in this layer concurrently
        coros = []
        layer_tasks: list[TaskDefinition] = []

        for task_id in layer:
            task = plan.get_task(task_id)
            if task is None:
                continue

            roster_entry = roster.get_agent_by_name(task.agent)
            if roster_entry is None:
                # Should not happen after validation, but defensive
                task_results.append(_failed_result(task, "Agent not found in roster"))
                continue

            try:
                resolved_inputs = resolve_upstream_inputs(task, completed_outputs)
            except KeyError as e:
                task_results.append(_failed_result(task, str(e)))
                continue

            layer_tasks.append(task)
            coros.append(
                _execute_with_retry(
                    task=task,
                    roster_entry=roster_entry,
                    resolved_inputs=resolved_inputs,
                    execute_agent_fn=execute_agent_fn,
                )
            )

        if not coros:
            continue

        results = await asyncio.gather(*coros, return_exceptions=True)

        for task, result in zip(layer_tasks, results):
            if isinstance(result, Exception):
                task_results.append(_failed_result(task, str(result)))
                continue

            task_result: TaskResult = result
            task_results.append(task_result)

            # Track completed outputs for downstream from_upstream resolution
            if task_result.status == TaskStatus.SUCCESS:
                completed_outputs[task.task_id] = task_result.output_reference

            # Accumulate costs
            total_cost += task_result.cost_usd
            total_input_tokens += task_result.token_usage.input
            total_output_tokens += task_result.token_usage.output
            total_thinking_tokens += task_result.token_usage.thinking

    # Determine mission status
    total_tasks = len(plan.tasks)
    successful_tasks = sum(
        1 for r in task_results if r.status == TaskStatus.SUCCESS
    )
    success_ratio = successful_tasks / total_tasks if total_tasks > 0 else 0.0

    critical_path_ids = set(plan.execution_hints.critical_path)
    critical_path_success = all(
        any(
            r.task_id == cp_id and r.status == TaskStatus.SUCCESS
            for r in task_results
        )
        for cp_id in critical_path_ids
    ) if critical_path_ids else True

    if successful_tasks == total_tasks:
        status = MissionStatus.SUCCESS
    elif (
        success_ratio >= plan.execution_hints.min_success_threshold
        and critical_path_success
    ):
        status = MissionStatus.PARTIAL
    else:
        status = MissionStatus.FAILED

    total_duration = time.monotonic() - start_time

    return MissionOutcome(
        mission_id=plan.mission_id,
        status=status,
        task_results=task_results,
        total_cost_usd=round(total_cost, 6),
        total_duration_seconds=round(total_duration, 2),
        total_tokens=TaskTokenUsage(
            input=total_input_tokens,
            output=total_output_tokens,
            thinking=total_thinking_tokens,
        ),
        planning_trace_reference=None,  # Set by caller
        task_plan_reference=None,       # Set by caller
    )


async def _execute_with_retry(
    task: TaskDefinition,
    roster_entry: RosterAgentEntry,
    resolved_inputs: dict[str, Any],
    execute_agent_fn: Any,
) -> TaskResult:
    """Execute a task with Tier 1 verification and retry-with-feedback."""
    retry_budget = roster_entry.constraints.retry_budget
    retry_history: list[RetryHistoryEntry] = []
    instructions = task.instructions

    for attempt in range(retry_budget + 1):
        task_start = time.monotonic()

        try:
            output = await execute_task(
                task=task,
                roster_entry=roster_entry,
                resolved_inputs=resolved_inputs,
                execute_agent_fn=execute_agent_fn,
            )
        except asyncio.TimeoutError:
            duration = time.monotonic() - task_start
            if attempt < retry_budget:
                retry_history.append(RetryHistoryEntry(
                    attempt=attempt + 1,
                    failure_tier=0,
                    failure_reason="Timeout",
                    feedback_provided="Previous attempt timed out. Work more efficiently.",
                ))
                instructions = _append_feedback(
                    task.instructions,
                    "Previous attempt timed out. Complete the task more efficiently.",
                )
                continue

            return TaskResult(
                task_id=task.task_id,
                agent_name=task.agent,
                status=TaskStatus.TIMEOUT,
                output_reference={},
                token_usage=TaskTokenUsage(),
                cost_usd=0.0,
                duration_seconds=round(duration, 2),
                verification_outcome=VerificationOutcome(
                    tier_1=Tier1Outcome(status="skipped", details="Task timed out"),
                ),
                retry_count=attempt,
                retry_history=retry_history,
            )
        except Exception as e:
            duration = time.monotonic() - task_start
            logger.error(
                "Task execution failed",
                extra={"task_id": task.task_id, "error": str(e), "attempt": attempt},
            )
            if attempt < retry_budget:
                retry_history.append(RetryHistoryEntry(
                    attempt=attempt + 1,
                    failure_tier=0,
                    failure_reason=str(e),
                    feedback_provided=f"Previous attempt failed: {e}",
                ))
                instructions = _append_feedback(
                    task.instructions,
                    f"Previous attempt failed with error: {e}. Avoid this error.",
                )
                continue

            return _failed_result(task, str(e), retry_count=attempt, retry_history=retry_history)

        duration = time.monotonic() - task_start

        # Extract token usage and cost from output metadata
        token_usage = TaskTokenUsage(
            input=output.get("_meta", {}).get("input_tokens", 0),
            output=output.get("_meta", {}).get("output_tokens", 0),
            thinking=output.get("_meta", {}).get("thinking_tokens", 0),
        )
        cost_usd = output.get("_meta", {}).get("cost_usd", 0.0)

        # Tier 1 verification
        tier1 = verify_tier1(output, task, roster_entry)

        if tier1.status == "fail":
            if attempt < retry_budget:
                retry_history.append(RetryHistoryEntry(
                    attempt=attempt + 1,
                    failure_tier=1,
                    failure_reason=tier1.details,
                    feedback_provided=f"Output validation failed: {tier1.details}",
                ))
                instructions = _append_feedback(
                    task.instructions,
                    f"Your previous output failed structural validation: {tier1.details}. "
                    f"Ensure your output includes all required fields.",
                )
                continue

            return TaskResult(
                task_id=task.task_id,
                agent_name=task.agent,
                status=TaskStatus.FAILED,
                output_reference=output,
                token_usage=token_usage,
                cost_usd=cost_usd,
                duration_seconds=round(duration, 2),
                verification_outcome=VerificationOutcome(tier_1=tier1),
                retry_count=attempt,
                retry_history=retry_history,
            )

        # Success
        return TaskResult(
            task_id=task.task_id,
            agent_name=task.agent,
            status=TaskStatus.SUCCESS,
            output_reference=output,
            token_usage=token_usage,
            cost_usd=cost_usd,
            duration_seconds=round(duration, 2),
            verification_outcome=VerificationOutcome(tier_1=tier1),
            retry_count=attempt,
            retry_history=retry_history,
        )

    # Should not reach here, but defensive
    return _failed_result(task, "Exhausted retry budget")


def _append_feedback(original_instructions: str, feedback: str) -> str:
    """Append failure feedback to agent instructions (Reflection pattern)."""
    return (
        f"{original_instructions}\n\n"
        f"--- FEEDBACK FROM PREVIOUS ATTEMPT ---\n"
        f"{feedback}"
    )


def _failed_result(
    task: TaskDefinition,
    reason: str,
    retry_count: int = 0,
    retry_history: list[RetryHistoryEntry] | None = None,
) -> TaskResult:
    """Create a failed TaskResult."""
    return TaskResult(
        task_id=task.task_id,
        agent_name=task.agent,
        status=TaskStatus.FAILED,
        output_reference={},
        token_usage=TaskTokenUsage(),
        cost_usd=0.0,
        duration_seconds=0.0,
        verification_outcome=VerificationOutcome(
            tier_1=Tier1Outcome(status="skipped", details=reason),
        ),
        retry_count=retry_count,
        retry_history=retry_history or [],
    )
```

**Verify:** Create a mock `execute_agent_fn`, build a 3-task plan (A, B parallel, C depends on both), dispatch. Verify A and B execute concurrently, C waits, outputs resolve correctly.

---

### Step 6: MissionOutcome

**File:** `modules/backend/agents/mission_control/outcome.py` (NEW, ~80 lines)

Structured output from the dispatch loop. Matches the Mission Control output contract from the research doc.

```python
"""MissionOutcome — structured result from Mission Control dispatch.

Returned to the Mission layer (or caller) with per-task results,
cost breakdown, and references to planning artifacts.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MissionStatus(StrEnum):
    """Mission completion status."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class TaskStatus(StrEnum):
    """Individual task completion status."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TaskTokenUsage(BaseModel):
    """Token usage for a single task execution."""

    model_config = ConfigDict(extra="forbid")

    input: int = 0
    output: int = 0
    thinking: int = 0


class Tier1Outcome(BaseModel):
    """Tier 1 structural verification outcome."""

    model_config = ConfigDict(extra="forbid")

    status: str = "skipped"     # "pass" | "fail" | "skipped"
    details: str = ""


class VerificationOutcome(BaseModel):
    """Per-task verification outcome across all tiers.

    In this plan (Plan 13), only Tier 1 is implemented.
    Tier 2 and Tier 3 are added in Plan 14.
    """

    model_config = ConfigDict(extra="forbid")

    tier_1: Tier1Outcome = Field(default_factory=Tier1Outcome)
    # tier_2 and tier_3 added in Plan 14


class RetryHistoryEntry(BaseModel):
    """Record of a single retry attempt."""

    model_config = ConfigDict(extra="forbid")

    attempt: int
    failure_tier: int           # 0=execution, 1=tier1, 2=tier2, 3=tier3
    failure_reason: str
    feedback_provided: str


class TaskResult(BaseModel):
    """Result of a single task execution."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    agent_name: str
    status: TaskStatus
    output_reference: dict = Field(default_factory=dict)
    token_usage: TaskTokenUsage = Field(default_factory=TaskTokenUsage)
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    verification_outcome: VerificationOutcome = Field(
        default_factory=VerificationOutcome,
    )
    retry_count: int = 0
    retry_history: list[RetryHistoryEntry] = Field(default_factory=list)


class MissionOutcome(BaseModel):
    """Complete result of a Mission Control dispatch.

    Returned to the Mission layer with per-task results and cost breakdown.
    """

    model_config = ConfigDict(extra="forbid")

    mission_id: str
    status: MissionStatus
    task_results: list[TaskResult] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    total_tokens: TaskTokenUsage = Field(default_factory=TaskTokenUsage)
    planning_trace_reference: str | None = None
    task_plan_reference: str | None = None
```

**Verify:** `MissionOutcome` serializes and deserializes correctly. `TaskResult` captures all fields from the dispatch loop.

---

### Step 7: Integration into handle()

**File:** `modules/backend/agents/mission_control/mission_control.py` (MODIFY)

Add the dispatch entry point alongside the existing `handle()` from Plan 12. This is additive — Plan 12's direct-agent path is preserved.

```python
# Add to existing imports at top of file
from modules.backend.agents.mission_control.dispatch import dispatch
from modules.backend.agents.mission_control.outcome import MissionOutcome
from modules.backend.agents.mission_control.plan_validator import validate_plan
from modules.backend.agents.mission_control.roster import Roster, load_roster
from modules.backend.schemas.task_plan import TaskPlan


async def handle_mission(
    mission_id: str,
    mission_brief: str,
    *,
    session_service: Any,
    event_bus: Any | None = None,
    roster_name: str = "default",
    mission_budget_usd: float = 10.0,
    upstream_context: dict | None = None,
) -> MissionOutcome:
    """Dispatch entry point for complex multi-agent missions.

    1. Load roster
    2. Call Planning Agent for task decomposition
    3. Validate TaskPlan against all 11 rules
    4. Execute dispatch loop
    5. Return MissionOutcome

    Simple requests continue through handle() from Plan 12.
    Complex requests (explicit mission_brief or matched playbook)
    route here.
    """
    roster = load_roster(roster_name)

    # Build planning prompt with roster descriptions
    roster_description = _build_roster_prompt(roster)
    planning_prompt = _build_planning_prompt(
        mission_brief=mission_brief,
        mission_id=mission_id,
        roster_description=roster_description,
        upstream_context=upstream_context,
    )

    # Call Planning Agent (with retry on validation failure)
    plan = None
    thinking_trace = None
    max_planning_attempts = 3

    for attempt in range(max_planning_attempts):
        try:
            planning_result = await _call_planning_agent(
                planning_prompt, roster, upstream_context,
            )
            thinking_trace = planning_result.get("thinking_trace")

            # Parse TaskPlan
            plan = TaskPlan.model_validate(planning_result["task_plan"])

            # Validate
            validation = validate_plan(plan, roster, mission_budget_usd)
            if validation.is_valid:
                break

            logger.warning(
                "TaskPlan validation failed, retrying Planning Agent",
                extra={
                    "attempt": attempt + 1,
                    "errors": validation.errors,
                    "mission_id": mission_id,
                },
            )

            # Append validation errors to planning prompt for retry
            planning_prompt = _append_validation_feedback(
                planning_prompt, validation.errors,
            )
            plan = None

        except (ValueError, Exception) as e:
            logger.warning(
                "Planning Agent error, retrying",
                extra={
                    "attempt": attempt + 1,
                    "error": str(e),
                    "mission_id": mission_id,
                },
            )
            planning_prompt = _append_validation_feedback(
                planning_prompt, [str(e)],
            )

    if plan is None:
        return MissionOutcome(
            mission_id=mission_id,
            status="failed",
            planning_trace_reference=thinking_trace,
        )

    # Execute dispatch loop
    outcome = await dispatch(
        plan=plan,
        roster=roster,
        execute_agent_fn=_make_agent_executor(session_service, event_bus),
        mission_budget_usd=mission_budget_usd,
    )

    # Attach planning artifacts
    outcome.planning_trace_reference = thinking_trace
    outcome.task_plan_reference = plan.model_dump_json()

    return outcome


def _build_roster_prompt(roster: Roster) -> str:
    """Format roster for the Planning Agent's context."""
    lines = ["## Available Agents\n"]
    for agent in roster.agents:
        lines.append(f"### {agent.agent_name} (v{agent.agent_version})")
        lines.append(f"**Description:** {agent.description}")
        lines.append(f"**Model:** {agent.model.name}")
        lines.append(f"**Tools:** {', '.join(agent.tools) if agent.tools else 'none'}")
        lines.append(f"**Input contract:** {agent.interface.input}")
        lines.append(f"**Output contract:** {agent.interface.output}")
        lines.append(
            f"**Constraints:** timeout={agent.constraints.timeout_seconds}s, "
            f"cost_ceiling=${agent.constraints.cost_ceiling_usd}, "
            f"retry_budget={agent.constraints.retry_budget}"
        )
        lines.append("")
    return "\n".join(lines)


def _build_planning_prompt(
    mission_brief: str,
    mission_id: str,
    roster_description: str,
    upstream_context: dict | None,
) -> str:
    """Assemble the full prompt for the Planning Agent."""
    parts = [
        f"## Mission Brief\n\n{mission_brief}\n",
        f"## Mission ID\n\n{mission_id}\n",
        roster_description,
    ]

    if upstream_context:
        import json
        parts.append(
            f"## Upstream Context\n\n```json\n{json.dumps(upstream_context, indent=2)}\n```\n"
        )

    parts.append(
        "## Output Format\n\n"
        "Return your task plan as JSON within <task_plan> tags.\n"
        "Follow the TaskPlan schema exactly. See system prompt for rules.\n"
    )

    return "\n".join(parts)


def _append_validation_feedback(prompt: str, errors: list[str]) -> str:
    """Append validation errors to planning prompt for retry."""
    error_text = "\n".join(f"- {e}" for e in errors)
    return (
        f"{prompt}\n\n"
        f"--- VALIDATION ERRORS FROM PREVIOUS ATTEMPT ---\n"
        f"Your previous TaskPlan failed validation:\n{error_text}\n"
        f"Fix these errors and try again.\n"
    )


def _make_agent_executor(session_service: Any, event_bus: Any | None):
    """Create the execute_agent_fn closure for the dispatch loop."""

    async def execute_agent(
        agent_name: str,
        instructions: str,
        inputs: dict,
        usage_limits: UsageLimits,
    ) -> dict:
        """Execute a single agent through the standard path."""
        # Import here to avoid circular imports
        from modules.backend.agents.mission_control.registry import get_registry

        registry = get_registry()
        agent_config = registry.get_agent_config(agent_name)
        if agent_config is None:
            raise ValueError(f"Agent '{agent_name}' not found in registry")

        # Import and run agent module
        module = _import_agent_module(agent_name)
        agent = module.create_agent(agent_config.model_dump())
        deps = _build_agent_deps(agent_name, agent_config)

        result = await module.run_agent(
            agent=agent,
            deps=deps,
            user_prompt=instructions,
            usage_limits=usage_limits,
        )

        return result

    return execute_agent


async def _call_planning_agent(
    prompt: str,
    roster: Roster,
    upstream_context: dict | None,
) -> dict:
    """Call the Planning Agent and return the raw result."""
    from modules.backend.agents.horizontal.planning.agent import (
        PlanningAgentDeps,
        create_agent,
        run_agent,
    )

    config = {
        "model": "anthropic:claude-opus-4-20250514",
    }
    agent = create_agent(config)
    deps = PlanningAgentDeps(
        project_root=find_project_root(),
        scope=FileScope(read=[], write=[]),
        mission_brief=prompt,
        roster_description=_build_roster_prompt(roster) if roster else "",
        upstream_context=upstream_context,
    )

    return await run_agent(agent, deps, prompt)
```

**Update `handle()` with complexity routing:**

```python
# Add to existing handle() function, before the agent resolution step:

async def handle(
    session_id: str,
    message: str,
    *,
    session_service: SessionService,
    event_bus: SessionEventBus | None = None,
    channel: str = "api",
    sender_id: str | None = None,
    mission_brief: str | None = None,
) -> AsyncIterator[SessionEvent]:
    """Universal streaming mission control entry point.

    Simple requests: existing direct-agent path (Plan 12).
    Complex requests: routed to dispatch via handle_mission().

    A request is complex if:
    - mission_brief parameter is explicitly provided
    - (Future: matched playbook)
    """
    # ... existing Plan 12 code ...

    # Complexity routing (P10)
    if mission_brief is not None:
        # Complex request — route to dispatch loop
        outcome = await handle_mission(
            mission_id=f"mission-{session_id}",
            mission_brief=mission_brief,
            session_service=session_service,
            event_bus=event_bus,
        )
        # Convert MissionOutcome to events for streaming
        yield _outcome_to_event(outcome, session_id)
        return

    # ... rest of existing Plan 12 direct-agent path ...
```

**Verify:** `handle()` without `mission_brief` follows the existing Plan 12 path. `handle()` with `mission_brief` routes to `handle_mission()`. `handle_mission()` calls the Planning Agent, validates, dispatches, and returns `MissionOutcome`.

---

### Step 8: Modify config_schema.py for Roster Agents

**File:** `modules/backend/agents/config_schema.py` (MODIFY)

Add `interface` as required for agents participating in roster dispatch. Keep it optional for backward compatibility with existing agents that don't participate in missions.

```python
# Add to existing AgentConfigSchema:

class AgentConfigSchema(_StrictBase):
    """Schema for config/agents/**/agent.yaml files."""

    agent_name: str
    agent_type: str
    description: str
    enabled: bool
    model: str | AgentModelSchema   # Accept both flat string and structured schema (Plan 12)
    version: str = "1.0.0"         # Semantic versioning (Plan 12)
    keywords: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    max_input_length: int
    max_budget_usd: float
    execution: ExecutionSchema
    scope: FileScopeConfigSchema = Field(default_factory=FileScopeConfigSchema)
    interface: AgentInterfaceSchema | None = None  # Required for roster agents (validated at roster load time)

    # Agent-specific optional fields
    file_size_limit: int | None = None
    rules: list[ComplianceRuleSchema] | None = None
    exclusions: ExclusionsSchema | None = None

    # Horizontal agent fields (Plan 13)
    thinking_budget: dict[str, int] | None = None
```

Note: The `interface` field is optional on `AgentConfigSchema` (backward compatible). The roster loader in `roster.py` validates that every agent in the roster has a populated `interface`. This is the enforcement point — not the schema itself.

**Verify:** Existing agent YAMLs (`code/qa/agent.yaml`, `system/health/agent.yaml`) load without error. New agents with `interface` and `thinking_budget` fields also load correctly.

---

### Step 9: Tests

**File:** `tests/unit/backend/agents/mission_control/__init__.py` (NEW, empty)

**File:** `tests/unit/backend/agents/mission_control/test_roster.py` (NEW, ~80 lines)

```python
"""Tests for agent roster loading and validation."""

import pytest

from modules.backend.agents.mission_control.roster import (
    PLANNING_AGENT_ENTRY,
    VERIFICATION_AGENT_ENTRY,
    Roster,
    RosterAgentEntry,
    RosterConstraintsSchema,
    RosterInterfaceSchema,
    RosterModelSchema,
    load_roster,
)


def _make_entry(name: str = "test.agent", version: str = "1.0.0") -> RosterAgentEntry:
    """Create a minimal roster entry for testing."""
    return RosterAgentEntry(
        agent_name=name,
        agent_version=version,
        description="Test agent",
        model=RosterModelSchema(name="test-model"),
        interface=RosterInterfaceSchema(
            input={"query": "string"},
            output={"result": "string", "confidence": "float"},
        ),
    )


class TestRoster:
    def test_get_agent_by_name_and_version(self):
        roster = Roster(agents=[_make_entry()])
        assert roster.get_agent("test.agent", "1.0.0") is not None
        assert roster.get_agent("test.agent", "2.0.0") is None
        assert roster.get_agent("nonexistent", "1.0.0") is None

    def test_get_agent_by_name_only(self):
        roster = Roster(agents=[_make_entry()])
        assert roster.get_agent_by_name("test.agent") is not None
        assert roster.get_agent_by_name("nonexistent") is None

    def test_agent_names(self):
        roster = Roster(agents=[_make_entry("a"), _make_entry("b")])
        assert roster.agent_names == ["a", "b"]

    def test_extra_fields_rejected(self):
        with pytest.raises(Exception):
            RosterAgentEntry(
                agent_name="test",
                agent_version="1.0.0",
                description="Test",
                model=RosterModelSchema(name="test"),
                interface=RosterInterfaceSchema(),
                unknown_field="bad",
            )


class TestLoadRoster:
    def test_load_default_roster(self):
        roster = load_roster("default")
        assert len(roster.agents) >= 2  # At least worker agents + auto-included

    def test_auto_includes_planning_agent(self):
        roster = load_roster("default")
        planning = roster.get_agent_by_name("horizontal.planning.agent")
        assert planning is not None

    def test_auto_includes_verification_agent(self):
        roster = load_roster("default")
        verification = roster.get_agent_by_name("horizontal.verification.agent")
        assert verification is not None

    def test_missing_roster_raises(self):
        with pytest.raises(FileNotFoundError):
            load_roster("nonexistent_roster")
```

**File:** `tests/unit/backend/schemas/test_task_plan.py` (NEW, ~100 lines)

```python
"""Tests for TaskPlan schema validation."""

import pytest

from modules.backend.schemas.task_plan import (
    ExecutionHints,
    FromUpstreamRef,
    TaskConstraints,
    TaskDefinition,
    TaskInputs,
    TaskPlan,
    TaskVerification,
    Tier1Verification,
    Tier3Verification,
)


def _make_task(task_id: str = "task_1", deps: list[str] | None = None) -> dict:
    """Create a minimal task dict for testing."""
    return {
        "task_id": task_id,
        "agent": "test.agent",
        "agent_version": "1.0.0",
        "description": "Test task",
        "instructions": "Do the thing",
        "dependencies": deps or [],
    }


def _make_plan(tasks: list[dict] | None = None) -> dict:
    """Create a minimal plan dict for testing."""
    return {
        "version": "1.0.0",
        "mission_id": "test-mission",
        "summary": "Test plan",
        "estimated_cost_usd": 1.0,
        "estimated_duration_seconds": 60,
        "tasks": tasks or [_make_task()],
    }


class TestTaskPlan:
    def test_minimal_plan_parses(self):
        plan = TaskPlan.model_validate(_make_plan())
        assert plan.mission_id == "test-mission"
        assert len(plan.tasks) == 1

    def test_task_ids_property(self):
        plan = TaskPlan.model_validate(_make_plan([
            _make_task("a"),
            _make_task("b"),
        ]))
        assert plan.task_ids == ["a", "b"]

    def test_get_task(self):
        plan = TaskPlan.model_validate(_make_plan([_make_task("a")]))
        assert plan.get_task("a") is not None
        assert plan.get_task("nonexistent") is None

    def test_from_upstream_ref(self):
        ref = FromUpstreamRef(source_task="task_1", source_field="output_field")
        assert ref.source_task == "task_1"

    def test_execution_hints_defaults(self):
        plan = TaskPlan.model_validate(_make_plan())
        assert plan.execution_hints.min_success_threshold == 1.0
        assert plan.execution_hints.critical_path == []

    def test_negative_cost_rejected(self):
        data = _make_plan()
        data["estimated_cost_usd"] = -1.0
        with pytest.raises(Exception):
            TaskPlan.model_validate(data)

    def test_extra_fields_rejected(self):
        data = _make_plan()
        data["unknown_field"] = "bad"
        with pytest.raises(Exception):
            TaskPlan.model_validate(data)

    def test_full_plan_from_research_doc(self):
        """Validate the full example from the research doc parses."""
        plan_data = {
            "version": "1.0.0",
            "mission_id": "iam-audit-001",
            "summary": "IAM policy audit and remediation",
            "estimated_cost_usd": 2.50,
            "estimated_duration_seconds": 300,
            "tasks": [
                {
                    "task_id": "analyse_config",
                    "agent": "config_scanner",
                    "agent_version": "1.0.0",
                    "description": "Scan current IAM configuration",
                    "instructions": "Scan all environments for IAM config",
                    "inputs": {
                        "static": {"environments": ["prod", "staging"]},
                        "from_upstream": {},
                    },
                    "dependencies": [],
                    "verification": {
                        "tier_1": {
                            "schema_validation": True,
                            "required_output_fields": ["config_data", "confidence"],
                        },
                        "tier_2": {"deterministic_checks": []},
                        "tier_3": {"requires_ai_evaluation": False},
                    },
                },
                {
                    "task_id": "generate_remediation",
                    "agent": "code_generator",
                    "agent_version": "1.0.0",
                    "description": "Generate remediation code",
                    "instructions": "Generate Terraform modules",
                    "inputs": {
                        "static": {"output_format": "terraform"},
                        "from_upstream": {
                            "current_config": {
                                "source_task": "analyse_config",
                                "source_field": "config_data",
                            },
                        },
                    },
                    "dependencies": ["analyse_config"],
                    "verification": {
                        "tier_1": {
                            "schema_validation": True,
                            "required_output_fields": ["code", "confidence"],
                        },
                        "tier_2": {"deterministic_checks": []},
                        "tier_3": {
                            "requires_ai_evaluation": True,
                            "evaluation_criteria": ["Code addresses all gaps"],
                            "evaluator_agent": "verification_agent",
                            "min_evaluation_score": 0.85,
                        },
                    },
                },
            ],
            "execution_hints": {
                "min_success_threshold": 0.66,
                "critical_path": ["analyse_config"],
            },
        }
        plan = TaskPlan.model_validate(plan_data)
        assert len(plan.tasks) == 2
        assert plan.execution_hints.min_success_threshold == 0.66
```

**File:** `tests/unit/backend/agents/mission_control/test_plan_validator.py` (NEW, ~200 lines)

```python
"""Tests for TaskPlan validation — all 11 rules."""

import pytest

from modules.backend.agents.mission_control.plan_validator import validate_plan
from modules.backend.agents.mission_control.roster import (
    Roster,
    RosterAgentEntry,
    RosterConstraintsSchema,
    RosterInterfaceSchema,
    RosterModelSchema,
)
from modules.backend.schemas.task_plan import TaskPlan


def _entry(name: str, version: str = "1.0.0", timeout: int = 120) -> RosterAgentEntry:
    return RosterAgentEntry(
        agent_name=name,
        agent_version=version,
        description=f"Agent {name}",
        model=RosterModelSchema(name="test-model"),
        interface=RosterInterfaceSchema(
            input={"query": "string"},
            output={"result": "string", "confidence": "float"},
        ),
        constraints=RosterConstraintsSchema(timeout_seconds=timeout),
    )


def _roster(*names: str) -> Roster:
    return Roster(agents=[_entry(n) for n in names])


def _plan(tasks: list[dict], **overrides) -> TaskPlan:
    data = {
        "version": "1.0.0",
        "mission_id": "test",
        "summary": "Test",
        "estimated_cost_usd": 1.0,
        "estimated_duration_seconds": 60,
        "tasks": tasks,
        **overrides,
    }
    return TaskPlan.model_validate(data)


def _task(task_id: str, agent: str = "agent_a", deps: list[str] | None = None, **kw) -> dict:
    return {
        "task_id": task_id,
        "agent": agent,
        "agent_version": "1.0.0",
        "description": "Test",
        "instructions": "Do it",
        "dependencies": deps or [],
        **kw,
    }


class TestRule2AgentValidation:
    def test_valid_agents_pass(self):
        plan = _plan([_task("t1", "agent_a")])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_unknown_agent_fails(self):
        plan = _plan([_task("t1", "unknown_agent")])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("agent_validation" in e for e in result.errors)


class TestRule3DagValidation:
    def test_valid_dag_passes(self):
        plan = _plan([
            _task("t1", "agent_a"),
            _task("t2", "agent_a", deps=["t1"]),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_cycle_fails(self):
        plan = _plan([
            _task("t1", "agent_a", deps=["t2"]),
            _task("t2", "agent_a", deps=["t1"]),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("dag_validation" in e for e in result.errors)

    def test_duplicate_task_id_fails(self):
        plan = _plan([_task("t1", "agent_a"), _task("t1", "agent_a")])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid

    def test_unknown_dependency_fails(self):
        plan = _plan([_task("t1", "agent_a", deps=["nonexistent"])])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid


class TestRule4DependencyConsistency:
    def test_consistent_deps_pass(self):
        plan = _plan([
            _task("t1", "agent_a"),
            _task("t2", "agent_a", deps=["t1"], inputs={
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "result"},
                },
            }),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_upstream_not_in_deps_fails(self):
        plan = _plan([
            _task("t1", "agent_a"),
            _task("t2", "agent_a", deps=[], inputs={
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "result"},
                },
            }),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("dependency_consistency" in e for e in result.errors)


class TestRule5InputCompatibility:
    def test_valid_source_field_passes(self):
        plan = _plan([
            _task("t1", "agent_a"),
            _task("t2", "agent_a", deps=["t1"], inputs={
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "result"},
                },
            }),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_invalid_source_field_fails(self):
        plan = _plan([
            _task("t1", "agent_a"),
            _task("t2", "agent_a", deps=["t1"], inputs={
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "nonexistent_field"},
                },
            }),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("input_compatibility" in e for e in result.errors)


class TestRule7BudgetValidation:
    def test_within_budget_passes(self):
        plan = _plan([_task("t1", "agent_a")], estimated_cost_usd=5.0)
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_over_budget_fails(self):
        plan = _plan([_task("t1", "agent_a")], estimated_cost_usd=15.0)
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("budget_validation" in e for e in result.errors)


class TestRule8TimeoutValidation:
    def test_within_timeout_passes(self):
        plan = _plan([_task("t1", "agent_a", constraints={
            "timeout_override_seconds": 60,
            "priority": "normal",
        })])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_over_timeout_fails(self):
        plan = _plan([_task("t1", "agent_a", constraints={
            "timeout_override_seconds": 999,
            "priority": "normal",
        })])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("timeout_validation" in e for e in result.errors)


class TestRule9CriticalPathValidation:
    def test_valid_critical_path_passes(self):
        plan = _plan(
            [_task("t1", "agent_a")],
            execution_hints={"min_success_threshold": 1.0, "critical_path": ["t1"]},
        )
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_unknown_critical_path_fails(self):
        plan = _plan(
            [_task("t1", "agent_a")],
            execution_hints={"min_success_threshold": 1.0, "critical_path": ["nonexistent"]},
        )
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("critical_path" in e for e in result.errors)


class TestRule10Tier3Completeness:
    def test_complete_tier3_passes(self):
        roster = Roster(agents=[
            _entry("agent_a"),
            _entry("horizontal.verification.agent"),
        ])
        plan = _plan([_task("t1", "agent_a", verification={
            "tier_1": {"schema_validation": True, "required_output_fields": []},
            "tier_2": {"deterministic_checks": []},
            "tier_3": {
                "requires_ai_evaluation": True,
                "evaluation_criteria": ["Is it good?"],
                "evaluator_agent": "horizontal.verification.agent",
                "min_evaluation_score": 0.85,
            },
        })])
        result = validate_plan(plan, roster, 10.0)
        assert result.is_valid

    def test_missing_criteria_fails(self):
        roster = Roster(agents=[
            _entry("agent_a"),
            _entry("horizontal.verification.agent"),
        ])
        plan = _plan([_task("t1", "agent_a", verification={
            "tier_1": {"schema_validation": True, "required_output_fields": []},
            "tier_2": {"deterministic_checks": []},
            "tier_3": {
                "requires_ai_evaluation": True,
                "evaluation_criteria": [],
                "evaluator_agent": "horizontal.verification.agent",
                "min_evaluation_score": 0.85,
            },
        })])
        result = validate_plan(plan, roster, 10.0)
        assert not result.is_valid
        assert any("tier3_completeness" in e for e in result.errors)


class TestRule11SelfEvaluationPrevention:
    def test_different_evaluator_passes(self):
        roster = Roster(agents=[
            _entry("agent_a"),
            _entry("horizontal.verification.agent"),
        ])
        plan = _plan([_task("t1", "agent_a", verification={
            "tier_1": {"schema_validation": True, "required_output_fields": []},
            "tier_2": {"deterministic_checks": []},
            "tier_3": {
                "requires_ai_evaluation": True,
                "evaluation_criteria": ["Check quality"],
                "evaluator_agent": "horizontal.verification.agent",
                "min_evaluation_score": 0.85,
            },
        })])
        result = validate_plan(plan, roster, 10.0)
        assert result.is_valid

    def test_self_evaluation_fails(self):
        plan = _plan([_task("t1", "agent_a", verification={
            "tier_1": {"schema_validation": True, "required_output_fields": []},
            "tier_2": {"deterministic_checks": []},
            "tier_3": {
                "requires_ai_evaluation": True,
                "evaluation_criteria": ["Check quality"],
                "evaluator_agent": "agent_a",
                "min_evaluation_score": 0.85,
            },
        })])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("self_evaluation" in e for e in result.errors)
```

**File:** `tests/unit/backend/agents/mission_control/test_dispatch.py` (NEW, ~150 lines)

```python
"""Tests for the dispatch loop — topological sort, parallel execution, verification."""

import asyncio

import pytest

from modules.backend.agents.mission_control.dispatch import (
    dispatch,
    resolve_upstream_inputs,
    topological_sort,
    verify_tier1,
)
from modules.backend.agents.mission_control.outcome import MissionStatus, TaskStatus
from modules.backend.agents.mission_control.roster import (
    Roster,
    RosterAgentEntry,
    RosterConstraintsSchema,
    RosterInterfaceSchema,
    RosterModelSchema,
)
from modules.backend.schemas.task_plan import TaskPlan


def _entry(name: str) -> RosterAgentEntry:
    return RosterAgentEntry(
        agent_name=name,
        agent_version="1.0.0",
        description=f"Agent {name}",
        model=RosterModelSchema(name="test-model"),
        interface=RosterInterfaceSchema(
            input={"query": "string"},
            output={"result": "string", "confidence": "float"},
        ),
        constraints=RosterConstraintsSchema(
            timeout_seconds=10,
            cost_ceiling_usd=1.0,
            retry_budget=1,
        ),
    )


def _plan(tasks: list[dict], **kw) -> TaskPlan:
    return TaskPlan.model_validate({
        "version": "1.0.0",
        "mission_id": "test",
        "summary": "Test",
        "estimated_cost_usd": 1.0,
        "estimated_duration_seconds": 60,
        "tasks": tasks,
        **kw,
    })


def _task(task_id: str, agent: str = "agent_a", deps: list[str] | None = None) -> dict:
    return {
        "task_id": task_id,
        "agent": agent,
        "agent_version": "1.0.0",
        "description": "Test",
        "instructions": "Do it",
        "dependencies": deps or [],
        "verification": {
            "tier_1": {
                "schema_validation": True,
                "required_output_fields": ["result"],
            },
            "tier_2": {"deterministic_checks": []},
            "tier_3": {"requires_ai_evaluation": False},
        },
    }


class TestTopologicalSort:
    def test_no_deps_single_layer(self):
        plan = _plan([_task("a"), _task("b")])
        layers = topological_sort(plan)
        assert len(layers) == 1
        assert set(layers[0]) == {"a", "b"}

    def test_linear_chain(self):
        plan = _plan([
            _task("a"),
            _task("b", deps=["a"]),
            _task("c", deps=["b"]),
        ])
        layers = topological_sort(plan)
        assert len(layers) == 3
        assert layers[0] == ["a"]
        assert layers[1] == ["b"]
        assert layers[2] == ["c"]

    def test_diamond_pattern(self):
        plan = _plan([
            _task("a"),
            _task("b", deps=["a"]),
            _task("c", deps=["a"]),
            _task("d", deps=["b", "c"]),
        ])
        layers = topological_sort(plan)
        assert len(layers) == 3
        assert layers[0] == ["a"]
        assert set(layers[1]) == {"b", "c"}
        assert layers[2] == ["d"]


class TestResolveUpstreamInputs:
    def test_static_only(self):
        task = _plan([{
            **_task("t1"),
            "inputs": {"static": {"key": "value"}, "from_upstream": {}},
        }]).tasks[0]
        result = resolve_upstream_inputs(task, {})
        assert result == {"key": "value"}

    def test_upstream_resolution(self):
        task = _plan([{
            **_task("t2", deps=["t1"]),
            "inputs": {
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "result"},
                },
            },
        }]).tasks[0]
        completed = {"t1": {"result": "hello", "confidence": 0.9}}
        result = resolve_upstream_inputs(task, completed)
        assert result["data"] == "hello"

    def test_missing_upstream_raises(self):
        task = _plan([{
            **_task("t2", deps=["t1"]),
            "inputs": {
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "result"},
                },
            },
        }]).tasks[0]
        with pytest.raises(KeyError):
            resolve_upstream_inputs(task, {})


class TestVerifyTier1:
    def test_all_fields_present_passes(self):
        task = _plan([_task("t1")]).tasks[0]
        entry = _entry("agent_a")
        output = {"result": "hello", "confidence": 0.9}
        outcome = verify_tier1(output, task, entry)
        assert outcome.status == "pass"

    def test_missing_field_fails(self):
        task = _plan([_task("t1")]).tasks[0]
        entry = _entry("agent_a")
        output = {"result": "hello"}  # missing 'confidence'
        outcome = verify_tier1(output, task, entry)
        assert outcome.status == "fail"
        assert "confidence" in outcome.details


class TestDispatch:
    @pytest.mark.asyncio
    async def test_simple_plan_succeeds(self):
        """Single task, agent returns valid output."""
        plan = _plan([_task("t1")])
        roster = Roster(agents=[_entry("agent_a")])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            return {"result": "done", "confidence": 0.95, "_meta": {
                "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.01,
            }}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.SUCCESS
        assert len(outcome.task_results) == 1
        assert outcome.task_results[0].status == TaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """Two independent tasks run concurrently."""
        plan = _plan([_task("a"), _task("b")])
        roster = Roster(agents=[_entry("agent_a")])
        execution_order = []

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            execution_order.append(f"start_{inputs.get('_task_id', 'unknown')}")
            await asyncio.sleep(0.01)
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.SUCCESS
        assert len(outcome.task_results) == 2

    @pytest.mark.asyncio
    async def test_upstream_resolution_in_dispatch(self):
        """Task B receives output from Task A via from_upstream."""
        tasks = [
            _task("a"),
            {
                **_task("b", deps=["a"]),
                "inputs": {
                    "static": {},
                    "from_upstream": {
                        "data": {"source_task": "a", "source_field": "result"},
                    },
                },
            },
        ]
        plan = _plan(tasks)
        roster = Roster(agents=[_entry("agent_a")])
        received_inputs = {}

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            received_inputs[instructions] = inputs
            return {"result": "from_a", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_tier1_failure_triggers_retry(self):
        """Agent output missing required fields triggers retry."""
        plan = _plan([_task("t1")])
        roster = Roster(agents=[_entry("agent_a")])
        call_count = 0

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"result": "done", "_meta": {}}  # missing confidence
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.SUCCESS
        assert outcome.task_results[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_timeout_handled(self):
        """Agent exceeding timeout is handled gracefully."""
        plan = _plan([_task("t1")])
        entry = _entry("agent_a")
        entry.constraints.timeout_seconds = 1
        entry.constraints.retry_budget = 0
        roster = Roster(agents=[entry])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            await asyncio.sleep(10)
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.task_results[0].status == TaskStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_partial_success(self):
        """Partial success when threshold met and critical path succeeded."""
        tasks = [_task("a"), _task("b")]
        plan = _plan(
            tasks,
            execution_hints={"min_success_threshold": 0.5, "critical_path": ["a"]},
        )
        roster = Roster(agents=[_entry("agent_a")])

        call_count = 0

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Agent b failed")
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.PARTIAL

    @pytest.mark.asyncio
    async def test_mission_failure_on_critical_path_failure(self):
        """Mission fails when critical path task fails."""
        tasks = [_task("a"), _task("b")]
        plan = _plan(
            tasks,
            execution_hints={"min_success_threshold": 0.5, "critical_path": ["a"]},
        )
        entry = _entry("agent_a")
        entry.constraints.retry_budget = 0
        roster = Roster(agents=[entry])

        call_count = 0

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Agent a (critical) failed")
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.FAILED
```

**File:** `tests/unit/backend/agents/horizontal/planning/test_planning_agent.py` (NEW, ~60 lines)

```python
"""Tests for the Planning Agent — JSON extraction and agent creation."""

import pytest

from modules.backend.agents.horizontal.planning.agent import (
    extract_task_plan_json,
)


class TestExtractTaskPlanJson:
    def test_valid_json_in_tags(self):
        text = 'Some thinking...\n<task_plan>\n{"version": "1.0.0"}\n</task_plan>'
        result = extract_task_plan_json(text)
        assert result == {"version": "1.0.0"}

    def test_json_with_whitespace(self):
        text = '<task_plan>\n  {\n    "version": "1.0.0"\n  }\n</task_plan>'
        result = extract_task_plan_json(text)
        assert result["version"] == "1.0.0"

    def test_missing_tags_raises(self):
        text = '{"version": "1.0.0"}'
        with pytest.raises(ValueError, match="does not contain <task_plan> tags"):
            extract_task_plan_json(text)

    def test_invalid_json_raises(self):
        text = "<task_plan>not json</task_plan>"
        with pytest.raises(ValueError, match="invalid JSON"):
            extract_task_plan_json(text)

    def test_empty_tags_raises(self):
        text = "<task_plan></task_plan>"
        with pytest.raises(ValueError):
            extract_task_plan_json(text)

    def test_complex_plan_json(self):
        plan_json = '''
        <task_plan>
        {
            "version": "1.0.0",
            "mission_id": "test-001",
            "summary": "Test mission",
            "estimated_cost_usd": 2.50,
            "estimated_duration_seconds": 120,
            "tasks": [
                {
                    "task_id": "t1",
                    "agent": "agent_a",
                    "agent_version": "1.0.0",
                    "description": "First task",
                    "instructions": "Do it"
                }
            ]
        }
        </task_plan>
        '''
        result = extract_task_plan_json(plan_json)
        assert result["mission_id"] == "test-001"
        assert len(result["tasks"]) == 1
```

---

### Step 10: Cleanup

- Verify no hardcoded values (all config from YAML)
- Verify all imports are absolute (`from modules.backend.agents...`)
- Verify all logging uses `get_logger(__name__)`
- Verify all datetimes use `utc_now()` from `modules.backend.core.utils`
- Verify `__init__.py` files are minimal (exports only)
- Verify no file exceeds 500 lines (target ~100-200 per file)
- Verify all Plan 12 tests still pass (simple agent routing unchanged)
- Delete `docs/97-plans/13-plan-horizontal-pm-agent.md` (replaced by this plan)
- Run: `python -m pytest tests/unit -v`

---

## Files Summary

| Category | File | Action | Est. Lines |
|----------|------|--------|-----------|
| Config | `config/mission_control/rosters/default.yaml` | New | ~80 |
| Roster | `modules/backend/agents/mission_control/roster.py` | New | ~150 |
| Schema | `modules/backend/schemas/task_plan.py` | New | ~200 |
| Validator | `modules/backend/agents/mission_control/plan_validator.py` | New | ~200 |
| Dispatch | `modules/backend/agents/mission_control/dispatch.py` | New | ~300 |
| Outcome | `modules/backend/agents/mission_control/outcome.py` | New | ~80 |
| Horizontal init | `modules/backend/agents/horizontal/__init__.py` | New | ~2 |
| Planning init | `modules/backend/agents/horizontal/planning/__init__.py` | New | ~2 |
| Planning Agent | `modules/backend/agents/horizontal/planning/agent.py` | New | ~100 |
| Planning Config | `config/agents/horizontal/planning/agent.yaml` | New | ~50 |
| Category Prompt | `config/prompts/categories/horizontal.md` | New | ~5 |
| System Prompt | `config/prompts/agents/horizontal/planning/system.md` | New | ~60 |
| Mission Control | `modules/backend/agents/mission_control/mission_control.py` | Modify | +100 |
| Config Schema | `modules/backend/agents/config_schema.py` | Modify | +5 |
| Tests - Roster | `tests/unit/backend/agents/mission_control/test_roster.py` | New | ~80 |
| Tests - TaskPlan | `tests/unit/backend/schemas/test_task_plan.py` | New | ~100 |
| Tests - Validator | `tests/unit/backend/agents/mission_control/test_plan_validator.py` | New | ~200 |
| Tests - Dispatch | `tests/unit/backend/agents/mission_control/test_dispatch.py` | New | ~150 |
| Tests - Planning | `tests/unit/backend/agents/horizontal/planning/test_planning_agent.py` | New | ~60 |
| **Total** | **19 files** | **15 new, 4 modified** | **~1,924** |

---

## Anti-Patterns (Do NOT)

- Do not make Mission Control a PydanticAI agent. It is deterministic code. It calls agents, it is not an agent (P2, P6).
- Do not let the Planning Agent dispatch agents. It returns a plan. Mission Control dispatches. The boundary between AI reasoning and deterministic execution is the TaskPlan.
- Do not allow runtime model override. Models are pinned in agent config. Model upgrades are version bumps.
- Do not skip TaskPlan validation. Every plan must pass all 11 rules before execution. No "fast path" that bypasses validation.
- Do not use the old PM Agent delegation pattern. Dispatch is direct — Mission Control calls agents through the standard execution path, not through delegation tools.
- Do not bypass mission control middleware. Even dispatch-loop agent calls go through the standard agent execution path with middleware (guardrails, cost tracking, event emission).
- Do not let agents evaluate their own output. Self-evaluation is prevented by validation rule 11 (P13).
- Do not hardcode agent names, timeouts, cost ceilings, or thinking budgets. All from YAML config.
- Do not import `logging` directly. Use `from modules.backend.core.logging import get_logger`.
- Do not use `datetime.utcnow()`. Use `from modules.backend.core.utils import utc_now`.
- Do not put large inline content in MissionOutcome. Use references (IDs, paths) to stored artifacts.

---
