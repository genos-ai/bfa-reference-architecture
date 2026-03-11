# Implementation Plan: Project Context Layer (Persistent Cross-Mission Memory)

*Created: 2026-03-10*
*Updated: 2026-03-11 — Added Pre-Phase 0 (seam bug fixes, execution_id, identity model)*
*Status: Pending*
*Phase: 9 of 9 (AI-First Platform Build)*
*Depends on: Phase 4 (Mission Control Dispatch), Phase 6 (Plan Persistence), Phase 8 (Playbooks & Missions)*
*Blocked by: Phase 8*
*Pre-requisite: Pre-Phase 0 (dispatch seam fixes + execution_id) must be completed before Sub-Phase 1*

---

## Summary

Build the persistent project context layer — the system that allows ephemeral agents to operate on long-running projects spanning days, weeks, months, or years with full situational awareness. This introduces the **Project** entity as the top-level organizational boundary, the **Project Context Document (PCD)** as a living, agent-maintained knowledge brief, and the **Agent Contract** that requires every agent to contribute context updates after each task.

The architecture uses three layers of memory: Layer 0 (PCD — always loaded, ~15KB, actively curated), Layer 1 (mission context — existing TaskPlan + upstream_context, unchanged), and Layer 2 (project history — structured queries over past decisions, outcomes, and failures). Context is assembled per-task within a token budget by a new `ContextAssembler` service. Over time, a `SummarizationService` compresses old history at decreasing granularity (task → mission → milestone → PCD) so context scales with project lifetime, not linearly with history size.

A **Pre-Phase 0** addresses six dispatch seam bugs and introduces `execution_id` — a globally unique correlation ID assigned at dispatch time that threads through TaskResult, TaskExecution, logs, and events. This fixes the foundation before the context layer builds on it.

This plan is implemented in five sub-phases (plus Pre-Phase 0), each independently valuable and deployable. No existing tables are removed. No existing services are replaced. The context layer is additive.

### Identity Model (5 Layers)

The complete identity hierarchy from user boundary to task execution:

| Layer | ID | Type | Assigned By | Scope | Purpose |
|-------|------|------|-------------|-------|---------|
| 1 | `project_id` | UUID | User (via CLI/API) | Cross-session | Organizational boundary for all work |
| 2 | `step.id` | string | YAML author | Within playbook | DAG node label, dependency references |
| 3 | `mission.id` | UUID | Database | Per execution | DB record, lifecycle tracking |
| 4 | `task_id` | string | Planning Agent (LLM) | Within TaskPlan | DAG node label, upstream references |
| 5 | `execution_id` | UUID | Dispatch loop (code) | Global | Cross-cutting correlation for logs, events, tracing |

**Key design decision:** `task_id` (layer 4) is NOT a stable identity — the Planning Agent assigns fresh IDs each run (e.g., `task-001`, `task-002`). The `execution_id` (layer 5) is the globally unique, code-assigned UUID that enables cross-project tracking, monitoring dashboards, and end-to-end tracing. `task_id` is already persisted where needed (in `MissionRecord.task_plan_json` as JSONB and `TaskExecution.task_id` as a string column) and does not need its own DB table.

**Dev mode: breaking changes allowed to new code only.** Existing mission and playbook functionality is preserved. New `project_id` columns are added to existing tables but are nullable during migration to avoid breaking existing data.

## Context

- Architecture document: `docs/02-architecture/001-project-context-layer.md` — project-specific design (PCD schema, data model, agent contract, fractal summarization)
- Reference architecture: `docs/99-reference-architecture/48-agentic-project-context.md` — prescriptive standard (three-layer memory, required tables, service architecture, implementation sequence)
- Agentic architecture: `docs/99-reference-architecture/40-agentic-architecture.md` — orchestration patterns, agent lifecycle
- PydanticAI implementation: `docs/99-reference-architecture/41-agentic-pydanticai.md` — RunContext, output_type patterns
- Agent module organization: `docs/99-reference-architecture/47-agentic-module-organization.md` — horizontal agent layout, naming conventions
- Mission Control dispatch: `docs/97-plans/13-plan-mission-control-dispatch.md` — dispatch loop, Planning Agent, TaskPlan, MissionOutcome
- Playbooks & Missions: `docs/97-plans/17-plan-playbooks-missions.md` — playbook YAML, mission lifecycle, output mapping, upstream_context flow
- Plan persistence: `docs/97-plans/15-plan-plan-persistence.md` — MissionRecord, TaskExecution, TaskAttempt tables
- Existing models: `modules/backend/models/base.py` (UUIDMixin, TimestampMixin, Base), `modules/backend/models/mission.py` (Mission, PlaybookRun), `modules/backend/models/mission_record.py` (MissionRecord, TaskExecution, TaskAttempt, MissionDecision)
- Existing services: `modules/backend/services/mission.py` (MissionService), `modules/backend/services/playbook_run.py` (PlaybookRunService)
- Existing dispatch: `modules/backend/agents/mission_control/dispatch.py` (topological sort, resolve_upstream_inputs, execute_task, dispatch loop)
- Existing outcome: `modules/backend/agents/mission_control/outcome.py` (TaskResult, MissionOutcome)
- Existing persistence: `modules/backend/agents/mission_control/persistence_bridge.py` (persist_mission_results)
- Project principles: P1 (Infrastructure Before Agents), P2 (Deterministic Over Non-Deterministic), P10 (Expansion Not Rewrite)
- Anti-pattern: Do NOT use vector embeddings or semantic search for agent coordination. Agents need precise, deterministic data — structured queries only.
- Anti-pattern: Do NOT store PCD as multiple relational rows. Use a single JSONB column — flexible schema, single read, no joins.
- Anti-pattern: Do NOT allow the PCD to grow unbounded. Enforce hard size cap (20KB). Prune actively.
- Anti-pattern: Do NOT skip context_updates in the agent contract. Every agent must return them (even if empty).
- Anti-pattern: Do NOT delete raw history data during summarization. Mark as summarized, exclude from default queries.

## What to Build

### Pre-Phase 0: Dispatch Seam Fixes & Execution ID
- `modules/backend/agents/mission_control/dispatch.py` — MODIFY: enforce `mission_budget_usd`, deliver retry feedback to agents, assign `execution_id` per task at dispatch time
- `modules/backend/agents/mission_control/outcome.py` — MODIFY: add `execution_id` field to `TaskResult`
- `modules/backend/models/mission_record.py` — MODIFY: add `execution_id` to `TaskExecution`
- `modules/backend/agents/mission_control/persistence_bridge.py` — MODIFY: persist `execution_id` from TaskResult to TaskExecution
- `modules/backend/services/playbook.py` — MODIFY: fail loudly on unresolved `@context.*` references (raise `ValueError` instead of silent passthrough)
- `modules/backend/services/mission.py` — MODIFY: fix `extract_outputs` silent empty returns (log warning), fix `by_agent` dict overwrite on duplicate agents
- `modules/backend/agents/mission_control/mission_control.py` — MODIFY: either route on `complexity_tier` or remove it from the chain

### Sub-Phase 1: Project Entity
- `modules/backend/models/project.py` — NEW: `Project`, `ProjectMember`, `ProjectStatus` models
- `modules/backend/schemas/project.py` — NEW: `ProjectCreate`, `ProjectUpdate`, `ProjectResponse`, `ProjectMemberResponse` Pydantic schemas
- `modules/backend/repositories/project.py` — NEW: `ProjectRepository`, `ProjectMemberRepository`
- `modules/backend/services/project.py` — NEW: `ProjectService` (CRUD, membership, scoping)
- `modules/backend/cli/project.py` — NEW: CLI handler for project commands
- `cli.py` — MODIFY: add `project` command group with `create`, `list`, `detail`, `archive` subcommands
- `modules/backend/models/mission.py` — MODIFY: add `project_id` to `Mission` and `PlaybookRun`
- `modules/backend/models/mission_record.py` — MODIFY: add `project_id` to `MissionRecord`
- `config/settings/projects.yaml` — NEW: project system configuration

### Sub-Phase 2: Project Context Document
- `modules/backend/models/project_context.py` — NEW: `ProjectContext`, `ContextChange`, `ChangeType` models
- `modules/backend/schemas/project_context.py` — NEW: `PCDSchema`, `ContextUpdateOp`, `ContextUpdateRequest`, `ContextChangeResponse` Pydantic schemas
- `modules/backend/repositories/project_context.py` — NEW: `ProjectContextRepository`, `ContextChangeRepository`
- `modules/backend/services/project_context.py` — NEW: `ProjectContextManager` (read, write, version, cache, size tracking)
- `modules/backend/cli/project.py` — MODIFY: add `context show`, `context update`, `context history` subcommands

### Sub-Phase 3: Agent Contract
- `modules/backend/services/context_curator.py` — NEW: `ContextCurator` (validate + apply context_updates, enforce size caps, trigger pruning)
- `modules/backend/agents/mission_control/dispatch.py` — MODIFY: add pre-task context assembly hook and post-task context_updates extraction
- `modules/backend/agents/mission_control/outcome.py` — MODIFY: add `context_updates` field to `TaskResult`
- `modules/backend/agents/mission_control/helpers.py` — MODIFY: add PCD to agent prompt construction

### Sub-Phase 4: Context Assembly
- `modules/backend/services/context_assembler.py` — NEW: `ContextAssembler` (build context packets, token budgeting, layer priority)
- `modules/backend/services/history_query.py` — NEW: `HistoryQueryService` (structured queries by domain, component, failure, time range)
- `modules/backend/schemas/task_plan.py` — MODIFY: add `domain_tags` to `TaskDefinition`
- `modules/backend/models/mission_record.py` — MODIFY: add `domain_tags` to `TaskExecution`

### Sub-Phase 5: Fractal Summarization
- `modules/backend/models/project_history.py` — NEW: `ProjectDecision`, `MilestoneSummary`, `DecisionStatus` models
- `modules/backend/repositories/project_history.py` — NEW: `ProjectDecisionRepository`, `MilestoneSummaryRepository`
- `modules/backend/services/summarization.py` — NEW: `SummarizationService` (task→mission compression, mission→milestone compression, PCD pruning)
- `modules/backend/agents/horizontal/summarization/agent.py` — NEW: Summarization Agent (Haiku-class, compression tasks)
- `config/agents/horizontal/summarization/agent.yaml` — NEW: agent config
- `config/prompts/agents/horizontal/summarization/system.md` — NEW: system prompt

## Key Design Decisions

1. **Project is a thin grouping entity.** It stores identity, ownership, and configuration. The PCD carries the knowledge. Complexity grows into the Project over time, not upfront.
2. **PCD is a single JSONB column, not relational rows.** One read loads the entire context. Schema is flexible — project-specific sections can be added without migrations. Versioned via integer for optimistic concurrency.
3. **String UUIDs** via `UUIDMixin` for consistency with all existing models (SQLite test compatibility).
4. **project_id is nullable during migration.** Existing missions and playbook runs have no project. New ones require it. A data migration backfills existing records into a "default" project if needed.
5. **Context updates use JSON Patch-like operations** (`add`, `replace`, `remove`) with mandatory `reason` fields. This is deterministic, auditable, and simple to validate.
6. **Guardrails are append-only for agents.** Only human project owners can remove guardrails. This prevents agents from relaxing constraints.
7. **PCD size cap is 20KB (hard), target 10-15KB.** Measured as UTF-8 encoded JSON. Pruning triggers at 80%, alert at 90%, rejection at 100%.
8. **Context assembly priority: PCD first, task definition second, upstream third, history last.** History is always the first to be trimmed when token budget is constrained.
9. **Summarization never deletes raw data.** It marks records as "summarized" and excludes them from default history queries. Full detail always available for audit.
10. **No RAG, no vector embeddings, no semantic search.** All history retrieval uses structured queries by domain tag, component key, time range, or failure status. Agents need precise data, not fuzzy matches.
11. **The dispatch loop is the single integration point.** Context assembly happens before task execution, context_updates extraction happens after. No parallel systems, no separate event loops.
12. **Each sub-phase is independently deployable.** Sub-phase 1 (Project entity) works without any context layer. Sub-phase 2 (PCD) works without agent automation. Each phase adds value.
13. **execution_id is assigned by deterministic code, not the LLM.** The dispatch loop assigns a UUID per task execution. This separates global correlation (execution_id, code-assigned) from DAG identity (task_id, LLM-assigned). execution_id threads through TaskResult → TaskExecution → ContextChange → logs for end-to-end tracing.
14. **Pre-Phase 0 fixes dispatch seam bugs before building on top.** Six bugs at layer boundaries (budget enforcement, retry feedback, @context.* resolution, complexity_tier usage, extract_outputs reliability, execution_id) must be fixed before the context layer can safely integrate with dispatch.

## Success Criteria

- [ ] `mission_budget_usd` enforced in dispatch — tasks cancelled when budget exceeded
- [ ] Retry feedback delivered to agents (not dead code)
- [ ] Unresolved `@context.*` references raise `ValueError` (not silent passthrough)
- [ ] `complexity_tier` used in routing or removed from chain
- [ ] `extract_outputs` handles duplicate agents and logs warnings on missing data
- [ ] `execution_id` (UUID) assigned per task at dispatch time, persisted to `TaskExecution`
- [ ] All Pre-Phase 0 tests pass
- [ ] Projects can be created, listed, detailed, and archived via CLI
- [ ] Missions and playbook runs are scoped to projects via `project_id`
- [ ] PCD can be viewed and manually updated via CLI
- [ ] PCD version increments on every update, with full audit trail in `context_changes`
- [ ] PCD size stays within 20KB cap (updates rejected if they would exceed)
- [ ] Agents receive PCD as part of context assembly before task execution
- [ ] Agents return `context_updates` after task completion
- [ ] `ContextCurator` validates and applies context_updates (invalid patches logged and skipped)
- [ ] Optimistic concurrency on PCD version prevents lost updates
- [ ] `ContextAssembler` builds context packets within token budget (PCD never trimmed)
- [ ] `HistoryQueryService` retrieves decisions, task executions, and failures by domain tag
- [ ] `domain_tags` on `TaskExecution` enable structured history queries
- [ ] `SummarizationService` compresses task executions older than 30 days into mission summaries
- [ ] `SummarizationService` compresses completed workstreams into milestone summaries
- [ ] PCD pruning archives old decisions and removes stale entries
- [ ] Raw history data is never deleted — only excluded from default queries
- [ ] All existing tests still pass (no breaking changes to existing functionality)

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Commit any uncommitted work | `git status`, then commit if needed |
| 0.2 | Create feature branch | `git checkout -b feature/project-context-layer` |

---

## Pre-Phase 0: Dispatch Seam Fixes & Execution ID

These fixes address six bugs discovered at layer boundaries in the Playbook → Mission → Mission Control → Agents chain. They must be completed before the context layer can reliably build on top of dispatch.

### Step P0.1: Enforce mission_budget_usd in Dispatch

**File**: `modules/backend/agents/mission_control/dispatch.py` — MODIFY

**Bug:** `mission_budget_usd: float` parameter is accepted by `dispatch()` (line 165) but never referenced in the function body. Cost ceiling is not enforced during execution.

**Fix:** Add running cost tracking in the dispatch loop. After each task completes, accumulate `cost_usd` from `_meta`. If cumulative cost exceeds `mission_budget_usd`, cancel remaining tasks and return `MissionStatus.FAILED` with a budget-exceeded error.

```python
# In the dispatch loop, after task completion:
cumulative_cost += task_result.cost_usd
if mission_budget_usd and cumulative_cost > mission_budget_usd:
    logger.warning(
        "Mission budget exceeded, cancelling remaining tasks",
        extra={
            "cumulative_cost": cumulative_cost,
            "budget": mission_budget_usd,
        },
    )
    # Cancel remaining tasks, set outcome status to FAILED
    break
```

**Tests:** Add test `test_budget_enforcement_cancels_remaining_tasks` — two tasks, budget of $0.05, each task costs $0.04. Second task should not execute.

---

### Step P0.2: Deliver Retry Feedback to Agents

**File**: `modules/backend/agents/mission_control/dispatch.py` — MODIFY

**Bug:** In `_execute_with_retry()` (lines 279-413), a local `instructions` variable is built with feedback from prior failures, but `execute_task()` reads `task.instructions` (a frozen Pydantic field). The retry feedback is dead code — it's constructed but never delivered to the agent.

**Fix:** Pass the enriched `instructions` (with feedback) to `execute_agent_fn` instead of `task.instructions`. The `execute_agent_fn` callable's `instructions` parameter should receive the feedback-enriched version on retries.

```python
# In _execute_with_retry, pass enriched instructions:
result = await execute_agent_fn(
    agent_name=entry.agent_name,
    instructions=instructions,  # NOT task.instructions — includes retry feedback
    inputs=resolved_inputs,
    usage_limits=usage_limits,
)
```

**Tests:** Update `test_retry_records_feedback_in_history` to also verify that the agent received enriched instructions on retry (capture `instructions` arg in mock).

---

### Step P0.3: Fail Loudly on Unresolved @context.* References

**File**: `modules/backend/services/playbook.py` — MODIFY

**Bug:** In `resolve_upstream_context()` (lines 296-314), when a `@context.*` reference can't be resolved, the literal string (e.g., `"@context.missing_key"`) is silently passed through as the value. Downstream agents receive a string instead of actual data.

**Fix:** Raise `ValueError` when a `@context.*` reference cannot be resolved. The playbook orchestrator should catch this and fail the step with a clear error, not silently pass garbage to agents.

```python
# Replace the warning + passthrough with a hard failure:
if isinstance(value, str) and value.startswith("@context."):
    context_key = value[len("@context."):]
    if context_key in upstream:
        resolved_input[key] = upstream[context_key]
    else:
        raise ValueError(
            f"Step '{step.id}' has unresolvable @context reference: "
            f"'{value}' (available: {list(upstream.keys())})"
        )
```

**Tests:** Add test `test_unresolved_context_reference_raises` — step references `@context.missing`, verify `ValueError` is raised with helpful message.

---

### Step P0.4: Resolve complexity_tier Usage

**File**: `modules/backend/agents/mission_control/mission_control.py` — MODIFY

**Bug:** `complexity_tier` is stored on the Mission model and passed through from playbook steps, but `handle_mission()` never reads it. It's dead data.

**Fix:** Either:
- **(A)** Use `complexity_tier` to select agent configuration (e.g., model size, token limits, retry budget) — pass it to roster loading or agent executor construction.
- **(B)** Remove `complexity_tier` from the chain if there's no near-term routing use.

**Recommended:** Option (A) — use it in roster loading to select model tiers. A `simple` tier uses smaller/cheaper models, `complex` uses larger models. This aligns with the existing `RosterConstraintsSchema`.

**Tests:** Add test that verifies different complexity tiers produce different agent configurations (or if option B, remove the field and verify no references remain).

---

### Step P0.5: Fix extract_outputs Reliability

**File**: `modules/backend/services/mission.py` — MODIFY

**Bug 1:** `extract_outputs()` (line 351-352) returns `{}` silently when `output_mapping` or `mission_outcome` is missing. Callers have no way to distinguish "no outputs mapped" from "mapping failed."

**Bug 2:** The `by_agent` dict (line 376) overwrites when multiple tasks use the same agent. Only the last task's output survives for agent-name-based lookups.

**Fix 1:** Log a warning when returning empty due to missing mapping/outcome, so operators can diagnose pipeline issues:

```python
if not output_mapping:
    logger.debug("No output_mapping configured", extra={"mission_id": mission.id})
    return {}
if not mission.mission_outcome:
    logger.warning(
        "Mission has no outcome for output extraction",
        extra={"mission_id": mission.id},
    )
    return {}
```

**Fix 2:** Change `by_agent` to collect lists instead of overwriting:

```python
by_agent: dict[str, list[dict]] = {}
# ...
agent = tr.get("agent_name", "")
by_agent.setdefault(agent, []).append(tr.get("output_reference", {}))
```

Then in the lookup, try all entries for a given agent name.

**Tests:** Add tests for both scenarios: empty output_mapping logs debug, missing outcome logs warning, duplicate agents both accessible.

---

### Step P0.6: Add execution_id to TaskResult and Dispatch

**File**: `modules/backend/agents/mission_control/outcome.py` — MODIFY

Add `execution_id` field to `TaskResult`:

```python
class TaskResult(BaseModel):
    """Result of executing a single task."""

    # ... existing fields ...
    execution_id: str = Field(
        default="",
        description="Globally unique execution ID assigned at dispatch time",
    )
```

**File**: `modules/backend/agents/mission_control/dispatch.py` — MODIFY

In the dispatch loop, before executing each task, assign a UUID:

```python
import uuid

# In the dispatch loop, before _execute_with_retry:
execution_id = str(uuid.uuid4())

# Pass to TaskResult construction:
task_result.execution_id = execution_id
```

**File**: `modules/backend/models/mission_record.py` — MODIFY

Add `execution_id` to `TaskExecution`:

```python
    execution_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
    )
```

**File**: `modules/backend/agents/mission_control/persistence_bridge.py` — MODIFY

In `persist_mission_results`, copy `execution_id` from `TaskResult` to `TaskExecution`:

```python
task_execution = TaskExecution(
    # ... existing fields ...
    execution_id=task_result.execution_id,
)
```

**Tests:** Add test `test_execution_id_assigned_per_task` — dispatch a plan with 2 tasks, verify each TaskResult has a unique non-empty `execution_id`. Add test `test_execution_id_persisted` — verify TaskExecution row has the same `execution_id` as the TaskResult.

---

### Step P0.7: Tests for Pre-Phase 0

All Pre-Phase 0 changes must have unit tests before proceeding. Summary of required tests:

| # | Test | File |
|---|------|------|
| P0.7.1 | Budget enforcement cancels remaining tasks | `tests/unit/backend/mission_control/test_dispatch.py` |
| P0.7.2 | Retry feedback delivered to agent (not dead code) | `tests/unit/backend/mission_control/test_dispatch.py` |
| P0.7.3 | Unresolved @context.* raises ValueError | `tests/unit/backend/services/test_playbook.py` |
| P0.7.4 | complexity_tier routing (or removal) | `tests/unit/backend/mission_control/test_mission_control.py` |
| P0.7.5 | extract_outputs with duplicate agents | `tests/unit/backend/services/test_mission.py` |
| P0.7.6 | extract_outputs logs warning on missing outcome | `tests/unit/backend/services/test_mission.py` |
| P0.7.7 | execution_id assigned per task, globally unique | `tests/unit/backend/mission_control/test_dispatch.py` |
| P0.7.8 | execution_id persisted to TaskExecution | `tests/unit/backend/mission_control/test_persistence.py` |

**Verify**: `pytest tests/unit/backend/ -x` — all tests pass, including new Pre-Phase 0 tests.

---

## Sub-Phase 1: Project Entity

### Step 1.1: Project Configuration

**File**: `config/settings/projects.yaml` (NEW)

```yaml
# =============================================================================
# Project System Configuration
# =============================================================================
# Available options:
#   default_budget_ceiling_usd  - Default project budget ceiling (float, nullable)
#   max_projects_per_owner      - Maximum projects per owner (integer)
#   pcd_max_size_bytes          - PCD hard size cap in bytes (integer, 20480 = 20KB)
#   pcd_target_size_bytes       - PCD target size in bytes (integer, 15360 = 15KB)
#   pcd_prune_threshold_pct     - Trigger pruning at this % of max (integer, 80)
#   pcd_alert_threshold_pct     - Alert owner at this % of max (integer, 90)
#   history_summarize_after_days - Summarize task executions older than N days (integer)
#   enable_context_assembly     - Enable context assembly in dispatch loop (boolean)
# =============================================================================

default_budget_ceiling_usd: null
max_projects_per_owner: 50
pcd_max_size_bytes: 20480
pcd_target_size_bytes: 15360
pcd_prune_threshold_pct: 80
pcd_alert_threshold_pct: 90
history_summarize_after_days: 30
enable_context_assembly: true
```

**File**: `modules/backend/core/config_schema.py` — Add `ProjectsSchema`:

```python
class ProjectsSchema(_StrictBase):
    """Project system configuration."""

    default_budget_ceiling_usd: float | None = None
    max_projects_per_owner: int = 50
    pcd_max_size_bytes: int = 20_480  # 20KB
    pcd_target_size_bytes: int = 15_360  # 15KB
    pcd_prune_threshold_pct: int = 80
    pcd_alert_threshold_pct: int = 90
    history_summarize_after_days: int = 30
    enable_context_assembly: bool = True
```

**File**: `modules/backend/core/config.py` — Register in `AppConfig`:

Add `projects: ProjectsSchema` using `_load_validated_optional()` pattern (same as `playbooks`, `sessions`).

```python
self._projects = _load_validated_optional(ProjectsSchema, "projects.yaml")

@property
def projects(self) -> ProjectsSchema:
    """Project system settings."""
    return self._projects
```

**Verify**: `python -c "from modules.backend.core.config import get_app_config; print(get_app_config().projects.pcd_max_size_bytes)"` — should print `20480`.

---

### Step 1.2: Project Model

**File**: `modules/backend/models/project.py` (NEW, ~120 lines)

```python
"""
Project Model.

A Project is the top-level organizational boundary. It groups all missions,
playbook runs, context, and history for a single codebase or initiative.
Projects are long-lived (months to years), owned by humans, and scoped —
agents operate within a single project at a time.
"""

import enum

from sqlalchemy import Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class ProjectStatus(str, enum.Enum):
    """Project lifecycle status."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ProjectMemberRole(str, enum.Enum):
    """Project membership role."""

    OWNER = "owner"
    MAINTAINER = "maintainer"
    VIEWER = "viewer"


class Project(UUIDMixin, TimestampMixin, Base):
    """A long-lived project that groups missions, context, and history."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True,
    )
    description: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Enum(ProjectStatus, native_enum=False),
        default=ProjectStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    owner_id: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True,
    )
    team_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
    )
    default_roster: Mapped[str] = mapped_column(
        String(100), default="default", nullable=False,
    )
    budget_ceiling_usd: Mapped[float | None] = mapped_column(
        Float, nullable=True,
    )
    repo_url: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    repo_root: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Project(id={self.id}, name={self.name!r}, "
            f"status={self.status})>"
        )


class ProjectMember(UUIDMixin, TimestampMixin, Base):
    """Human membership in a project with role-based permissions."""

    __tablename__ = "project_members"

    project_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(
        Enum(ProjectMemberRole, native_enum=False),
        default=ProjectMemberRole.VIEWER,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectMember(project={self.project_id}, "
            f"user={self.user_id}, role={self.role})>"
        )
```

**Note:** Do NOT add ForeignKey constraints to `project_id` columns. The existing codebase uses string references without FK constraints (see `Mission.playbook_run_id` pattern). Follow this convention for consistency and SQLite compatibility.

---

### Step 1.3: Add project_id to Existing Models

**File**: `modules/backend/models/mission.py` — MODIFY

Add `project_id` to both `PlaybookRun` and `Mission`. Nullable because existing data has no project.

Add to `PlaybookRun` class (after `playbook_version` field):

```python
    project_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
    )
```

Add to `Mission` class (after `playbook_step_id` field):

```python
    project_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
    )
```

**File**: `modules/backend/models/mission_record.py` — MODIFY

Add to `MissionRecord` class (after `session_id` field):

```python
    project_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
    )
```

---

### Step 1.4: Project Repository

**File**: `modules/backend/repositories/project.py` (NEW, ~120 lines)

```python
"""
Project Repository.

Data access for projects and project membership.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.project import (
    Project,
    ProjectMember,
    ProjectStatus,
)
from modules.backend.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for Project CRUD and queries."""

    model = Project

    async def get_by_name(self, name: str) -> Project | None:
        """Get a project by unique name."""
        result = await self.session.execute(
            select(Project).where(Project.name == name)
        )
        return result.scalar_one_or_none()

    async def list_by_owner(
        self,
        owner_id: str,
        status: ProjectStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        """List projects owned by a user, optionally filtered by status."""
        query = select(Project).where(Project.owner_id == owner_id)
        if status:
            query = query.where(Project.status == status)
        query = query.order_by(Project.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_active(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        """List all active projects."""
        result = await self.session.execute(
            select(Project)
            .where(Project.status == ProjectStatus.ACTIVE)
            .order_by(Project.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())


class ProjectMemberRepository(BaseRepository[ProjectMember]):
    """Repository for project membership queries."""

    model = ProjectMember

    async def get_members(
        self,
        project_id: str,
    ) -> list[ProjectMember]:
        """Get all members of a project."""
        result = await self.session.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.created_at)
        )
        return list(result.scalars().all())

    async def get_membership(
        self,
        project_id: str,
        user_id: str,
    ) -> ProjectMember | None:
        """Get a specific user's membership in a project."""
        result = await self.session.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .where(ProjectMember.user_id == user_id)
        )
        return result.scalar_one_or_none()
```

---

### Step 1.5: Project Schemas (Pydantic)

**File**: `modules/backend/schemas/project.py` (NEW, ~80 lines)

```python
"""
Project API schemas.

Pydantic models for project creation, update, and response serialization.
"""

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ..., min_length=1, max_length=200,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Unique project name (lowercase, hyphens, underscores)",
    )
    description: str = Field(
        ..., min_length=1, max_length=2000,
        description="Project purpose and scope",
    )
    owner_id: str = Field(
        ..., min_length=1, max_length=200,
        description="Primary human owner identifier",
    )
    team_id: str | None = Field(
        None, max_length=200,
        description="Optional team identifier",
    )
    default_roster: str = Field(
        default="default",
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Default agent roster for this project",
    )
    budget_ceiling_usd: float | None = Field(
        None, ge=0.01,
        description="Project-level spend cap",
    )
    repo_url: str | None = Field(
        None, max_length=2000,
        description="Source repository URL",
    )
    repo_root: str | None = Field(
        None, max_length=1000,
        description="Local filesystem root path",
    )


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(None, min_length=1, max_length=2000)
    status: str | None = Field(None, pattern=r"^(active|paused|archived)$")
    default_roster: str | None = Field(None, pattern=r"^[a-z][a-z0-9_-]*$")
    budget_ceiling_usd: float | None = None
    repo_url: str | None = None
    repo_root: str | None = None


class ProjectResponse(BaseModel):
    """Schema for project API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    status: str
    owner_id: str
    team_id: str | None
    default_roster: str
    budget_ceiling_usd: float | None
    repo_url: str | None
    repo_root: str | None
    created_at: str
    updated_at: str


class ProjectMemberResponse(BaseModel):
    """Schema for project member API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    user_id: str
    role: str
    created_at: str
```

---

### Step 1.6: Project Service

**File**: `modules/backend/services/project.py` (NEW, ~200 lines)

```python
"""
Project Service.

Business logic for project lifecycle management, membership,
and project-scoping enforcement.
"""

import json as _json
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.models.project import (
    Project,
    ProjectMember,
    ProjectMemberRole,
    ProjectStatus,
)
from modules.backend.repositories.project import (
    ProjectMemberRepository,
    ProjectRepository,
)
from modules.backend.services.base import BaseService

logger = get_logger(__name__)


class ProjectService(BaseService):
    """Service for project CRUD, membership, and scoping."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._project_repo = ProjectRepository(session)
        self._member_repo = ProjectMemberRepository(session)

    @staticmethod
    @asynccontextmanager
    async def factory() -> AsyncGenerator["ProjectService", None]:
        """Create a ProjectService with its own DB session."""
        from modules.backend.core.database import get_async_session

        async with get_async_session() as db:
            yield ProjectService(db)
            await db.commit()

    async def create_project(
        self,
        *,
        name: str,
        description: str,
        owner_id: str,
        team_id: str | None = None,
        default_roster: str = "default",
        budget_ceiling_usd: float | None = None,
        repo_url: str | None = None,
        repo_root: str | None = None,
    ) -> Project:
        """Create a new project with initial PCD and owner membership.

        Creates: projects row, project_members row (owner),
        project_contexts row (seed PCD) — PCD creation is in Sub-Phase 2.
        """
        # Check unique name
        existing = await self._project_repo.get_by_name(name)
        if existing:
            from modules.backend.core.exceptions import ConflictError
            raise ConflictError(f"Project name already exists: {name}")

        project = await self._project_repo.create(
            name=name,
            description=description,
            owner_id=owner_id,
            team_id=team_id,
            default_roster=default_roster,
            budget_ceiling_usd=budget_ceiling_usd,
            repo_url=repo_url,
            repo_root=repo_root,
        )

        # Auto-create owner membership
        await self._member_repo.create(
            project_id=project.id,
            user_id=owner_id,
            role=ProjectMemberRole.OWNER,
        )

        self._log_operation(
            "Project created",
            project_id=project.id,
            project_name=name,
        )
        return project

    async def get_project(self, project_id: str) -> Project:
        """Get a project by ID. Raises NotFoundError if not found."""
        return await self._project_repo.get_by_id(project_id)

    async def get_project_by_name(self, name: str) -> Project | None:
        """Get a project by name. Returns None if not found."""
        return await self._project_repo.get_by_name(name)

    async def list_projects(
        self,
        owner_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Project]:
        """List projects, optionally filtered by owner and/or status."""
        if owner_id:
            status_enum = ProjectStatus(status) if status else None
            return await self._project_repo.list_by_owner(
                owner_id, status=status_enum, limit=limit,
            )
        return await self._project_repo.list_active(limit=limit)

    async def update_project(
        self,
        project_id: str,
        **updates,
    ) -> Project:
        """Update project fields."""
        return await self._project_repo.update(project_id, **updates)

    async def archive_project(self, project_id: str) -> Project:
        """Archive a project. No new missions can be created."""
        return await self._project_repo.update(
            project_id, status=ProjectStatus.ARCHIVED,
        )
```

---

### Step 1.7: Project CLI Handler

**File**: `modules/backend/cli/project.py` (NEW, ~180 lines)

```python
"""
CLI handler for project commands.

Thin renderer over ProjectService. Handles create, list, detail, archive.
"""

import asyncio
import sys

from modules.backend.cli.report import get_console, build_table


def run_project(
    cli_logger,
    action: str,
    *,
    name: str | None = None,
    project_id: str | None = None,
    description: str | None = None,
    owner_id: str = "user:cli",
    roster: str = "default",
    budget: float | None = None,
    repo_url: str | None = None,
    repo_root: str | None = None,
    output_format: str = "human",
) -> None:
    """Dispatch project CLI actions."""
    actions = {
        "create": _action_create,
        "list": _action_list,
        "detail": _action_detail,
        "archive": _action_archive,
    }
    fn = actions.get(action)
    if not fn:
        get_console().print(f"[red]Unknown action: {action}[/red]")
        sys.exit(1)

    asyncio.run(fn(
        cli_logger,
        name=name,
        project_id=project_id,
        description=description,
        owner_id=owner_id,
        roster=roster,
        budget=budget,
        repo_url=repo_url,
        repo_root=repo_root,
        output_format=output_format,
    ))


async def _action_create(cli_logger, *, name, description, owner_id, roster, budget, repo_url, repo_root, **_):
    """Create a new project."""
    from modules.backend.services.project import ProjectService

    console = get_console()
    if not name:
        console.print("[red]--name is required[/red]")
        sys.exit(1)
    if not description:
        console.print("[red]--description is required[/red]")
        sys.exit(1)

    async with ProjectService.factory() as svc:
        project = await svc.create_project(
            name=name,
            description=description,
            owner_id=owner_id,
            default_roster=roster,
            budget_ceiling_usd=budget,
            repo_url=repo_url,
            repo_root=repo_root,
        )
    console.print(f"[green]Project created:[/green] {project.id}")
    console.print(f"  Name: {project.name}")
    console.print(f"  Owner: {project.owner_id}")


async def _action_list(cli_logger, *, output_format, **_):
    """List all active projects."""
    from modules.backend.services.project import ProjectService

    console = get_console()
    async with ProjectService.factory() as svc:
        projects = await svc.list_projects()

    if not projects:
        console.print("[dim]No projects found.[/dim]")
        return

    table = build_table("Projects", columns=[
        ("Status", {"width": 10}),
        ("Name", {"style": "cyan", "width": 30}),
        ("ID", {"width": 38}),
        ("Roster", {"width": 15}),
        ("Description", {"ratio": 1}),
    ])
    for p in projects:
        status_display = (
            "[green]active[/green]" if p.status == "active"
            else f"[yellow]{p.status}[/yellow]"
        )
        desc = p.description[:60] + "..." if len(p.description) > 60 else p.description
        table.add_row(status_display, p.name, p.id, p.default_roster, desc)

    console.print(table)


async def _action_detail(cli_logger, *, project_id, name, output_format, **_):
    """Show project details."""
    from modules.backend.services.project import ProjectService

    console = get_console()
    if not project_id and not name:
        console.print("[red]--project or --name is required[/red]")
        sys.exit(1)

    async with ProjectService.factory() as svc:
        if project_id:
            project = await svc.get_project(project_id)
        else:
            project = await svc.get_project_by_name(name)
            if not project:
                console.print(f"[red]Project not found: {name}[/red]")
                sys.exit(1)

    console.print(f"[bold]{project.name}[/bold]  ({project.status})")
    console.print(f"  ID:          {project.id}")
    console.print(f"  Description: {project.description}")
    console.print(f"  Owner:       {project.owner_id}")
    console.print(f"  Roster:      {project.default_roster}")
    if project.budget_ceiling_usd:
        console.print(f"  Budget:      ${project.budget_ceiling_usd:.2f}")
    if project.repo_url:
        console.print(f"  Repo:        {project.repo_url}")


async def _action_archive(cli_logger, *, project_id, **_):
    """Archive a project."""
    from modules.backend.services.project import ProjectService

    console = get_console()
    if not project_id:
        console.print("[red]PROJECT_ID is required[/red]")
        sys.exit(1)

    async with ProjectService.factory() as svc:
        project = await svc.archive_project(project_id)

    console.print(f"[yellow]Project archived:[/yellow] {project.name} ({project.id})")
```

---

### Step 1.8: CLI Integration

**File**: `cli.py` — MODIFY

Add `project` command group with subcommands. Follow the exact pattern used by `mission` and `playbook` command groups.

Add after the existing command groups:

```python
@cli.group("project", cls=ShowHelpOnMissingArgs)
def project():
    """Create, list, and manage projects."""
    pass


@project.command("create")
@click.option("--name", required=True, help="Unique project name.")
@click.option("--description", required=True, help="Project purpose.")
@click.option("--roster", default="default", help="Default agent roster.")
@click.option("--budget", type=float, default=None, help="Budget ceiling (USD).")
@click.option("--repo-url", default=None, help="Repository URL.")
@click.option("--repo-root", default=None, help="Local repo root path.")
@click.pass_obj
def project_create(ctx, name, description, roster, budget, repo_url, repo_root):
    """Create a new project."""
    from modules.backend.cli.project import run_project
    run_project(ctx.logger, "create", name=name, description=description,
                roster=roster, budget=budget, repo_url=repo_url,
                repo_root=repo_root, output_format=ctx.output_format)


@project.command("list")
@click.pass_obj
def project_list(ctx):
    """List all active projects."""
    from modules.backend.cli.project import run_project
    run_project(ctx.logger, "list", output_format=ctx.output_format)


@project.command("detail")
@click.argument("project_id", required=False)
@click.option("--name", default=None, help="Look up by project name.")
@click.pass_obj
def project_detail(ctx, project_id, name):
    """Show project details."""
    from modules.backend.cli.project import run_project
    run_project(ctx.logger, "detail", project_id=project_id, name=name,
                output_format=ctx.output_format)


@project.command("archive")
@click.argument("project_id")
@click.pass_obj
def project_archive(ctx, project_id):
    """Archive a project."""
    from modules.backend.cli.project import run_project
    run_project(ctx.logger, "archive", project_id=project_id,
                output_format=ctx.output_format)
```

Also add `--project` option to the `mission run` and `playbook run` commands so missions can be scoped to a project at creation time. Add to both commands:

```python
@click.option("--project", "project_id", default=None, help="Project ID to scope this run to.")
```

Pass `project_id` through to the respective service calls.

**Verify**: `python cli.py project --help` shows create, list, detail, archive subcommands.

---

### Step 1.9: Update Info Display

**File**: `modules/backend/cli/info.py` — MODIFY

Add the `project` command to the commands list:

```python
    click.echo("  project         Create, list, and manage projects")
```

**Verify**: `python cli.py` shows `project` in the command list.

---

## Sub-Phase 2: Project Context Document

### Step 2.1: Project Context Model

**File**: `modules/backend/models/project_context.py` (NEW, ~100 lines)

```python
"""
Project Context Model.

The ProjectContext stores the Project Context Document (PCD) — a living,
curated JSON document that captures everything an agent needs to orient
itself within a project. The ContextChange table is the audit trail of
every PCD mutation.
"""

import enum

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class ChangeType(str, enum.Enum):
    """Type of PCD mutation."""

    ADD = "add"
    REPLACE = "replace"
    REMOVE = "remove"
    PRUNE = "prune"
    ARCHIVE = "archive"


class ProjectContext(UUIDMixin, TimestampMixin, Base):
    """The Project Context Document (PCD) for a single project.

    One row per project. Contains the entire PCD as a JSON blob.
    Versioned with monotonically increasing integer for optimistic concurrency.
    """

    __tablename__ = "project_contexts"

    project_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True,
    )
    context_data: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
    )
    size_characters: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    size_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectContext(project={self.project_id}, "
            f"version={self.version}, size={self.size_characters})>"
        )


class ContextChange(UUIDMixin, TimestampMixin, Base):
    """Audit trail entry for a single PCD mutation."""

    __tablename__ = "context_changes"

    context_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    change_type: Mapped[str] = mapped_column(
        Enum(ChangeType, native_enum=False), nullable=False,
    )
    path: Mapped[str] = mapped_column(
        String(500), nullable=False,
    )
    old_value: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    new_value: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
    )
    mission_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )
    execution_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
    )
    reason: Mapped[str] = mapped_column(
        Text, nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ContextChange(version={self.version}, "
            f"type={self.change_type}, path={self.path!r})>"
        )
```

---

### Step 2.2: Project Context Repository

**File**: `modules/backend/repositories/project_context.py` (NEW, ~100 lines)

```python
"""
Project Context Repository.

Data access for PCD and context change audit trail.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.project_context import (
    ContextChange,
    ProjectContext,
)
from modules.backend.repositories.base import BaseRepository


class ProjectContextRepository(BaseRepository[ProjectContext]):
    """Repository for ProjectContext CRUD."""

    model = ProjectContext

    async def get_by_project_id(self, project_id: str) -> ProjectContext | None:
        """Get PCD by project ID."""
        result = await self.session.execute(
            select(ProjectContext)
            .where(ProjectContext.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def update_context(
        self,
        project_id: str,
        context_data: dict,
        new_version: int,
        size_characters: int,
        size_tokens: int,
    ) -> int:
        """Atomically update PCD with optimistic concurrency.

        Returns number of rows updated (0 if version conflict).
        """
        result = await self.session.execute(
            update(ProjectContext)
            .where(ProjectContext.project_id == project_id)
            .where(ProjectContext.version == new_version - 1)
            .values(
                context_data=context_data,
                version=new_version,
                size_characters=size_characters,
                size_tokens=size_tokens,
            )
        )
        return result.rowcount


class ContextChangeRepository(BaseRepository[ContextChange]):
    """Repository for context change audit trail."""

    model = ContextChange

    async def list_by_context(
        self,
        context_id: str,
        limit: int = 50,
    ) -> list[ContextChange]:
        """List recent changes for a PCD."""
        result = await self.session.execute(
            select(ContextChange)
            .where(ContextChange.context_id == context_id)
            .order_by(ContextChange.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_agent(
        self,
        context_id: str,
        agent_id: str,
        limit: int = 20,
    ) -> list[ContextChange]:
        """List changes made by a specific agent."""
        result = await self.session.execute(
            select(ContextChange)
            .where(ContextChange.context_id == context_id)
            .where(ContextChange.agent_id == agent_id)
            .order_by(ContextChange.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
```

---

### Step 2.3: Project Context Schemas

**File**: `modules/backend/schemas/project_context.py` (NEW, ~80 lines)

```python
"""
Project Context schemas.

Pydantic models for PCD operations, context updates, and API responses.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContextUpdateOp(BaseModel):
    """A single context update operation (JSON Patch-like)."""

    model_config = ConfigDict(extra="forbid")

    op: str = Field(
        ..., pattern=r"^(add|replace|remove)$",
        description="Operation type",
    )
    path: str = Field(
        ..., min_length=1, max_length=500,
        description="Dot-notation path in PCD (e.g. 'architecture.components.auth')",
    )
    value: Any = Field(
        None,
        description="Value to set (required for add/replace, ignored for remove)",
    )
    reason: str = Field(
        ..., min_length=1, max_length=500,
        description="Why this change is being made",
    )


class ContextUpdateRequest(BaseModel):
    """Batch of context update operations."""

    model_config = ConfigDict(extra="forbid")

    context_updates: list[ContextUpdateOp] = Field(
        ..., min_length=1,
        description="Ordered list of update operations to apply",
    )


class PCDResponse(BaseModel):
    """PCD content with metadata."""

    model_config = ConfigDict(from_attributes=True)

    project_id: str
    version: int
    size_characters: int
    size_tokens: int
    context_data: dict


class ContextChangeResponse(BaseModel):
    """Single context change audit entry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    change_type: str
    path: str
    old_value: Any | None
    new_value: Any | None
    agent_id: str | None
    mission_id: str | None
    task_id: str | None
    reason: str
    created_at: str
```

---

### Step 2.4: ProjectContextManager Service

**File**: `modules/backend/services/project_context.py` (NEW, ~300 lines)

```python
"""
Project Context Manager.

Reads, writes, and versions the Project Context Document (PCD).
Includes in-memory cache, size tracking, and seed PCD creation.
"""

import json as _json
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.models.project_context import (
    ChangeType,
    ContextChange,
    ProjectContext,
)
from modules.backend.repositories.project_context import (
    ContextChangeRepository,
    ProjectContextRepository,
)
from modules.backend.services.base import BaseService

logger = get_logger(__name__)

# PCD size limits (bytes)
_PCD_MAX_SIZE = 20_480  # 20KB hard cap
_PCD_TARGET_SIZE = 15_360  # 15KB target

# In-memory cache: project_id -> (context_data, version, timestamp)
_cache: dict[str, tuple[dict, int, float]] = {}
_CACHE_TTL_SECONDS = 30.0


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for JSON."""
    return len(text) // 4


def _get_nested(data: dict, path: str) -> Any:
    """Get a value from a nested dict using dot notation.

    Returns _SENTINEL if path not found.
    """
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list):
            # Handle array index or append marker
            if key == "-":
                return _SENTINEL
            try:
                current = current[int(key)]
            except (ValueError, IndexError):
                return _SENTINEL
        else:
            return _SENTINEL
    return current


def _set_nested(data: dict, path: str, value: Any) -> None:
    """Set a value in a nested dict using dot notation.

    Creates intermediate dicts as needed. Supports array append with '/-'.
    """
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]

    final_key = keys[-1]
    if final_key == "-" and isinstance(current, list):
        current.append(value)
    else:
        current[final_key] = value


def _delete_nested(data: dict, path: str) -> Any:
    """Delete a value from a nested dict. Returns the old value."""
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None

    final_key = keys[-1]
    if isinstance(current, dict) and final_key in current:
        return current.pop(final_key)
    elif isinstance(current, list):
        try:
            idx = int(final_key)
            return current.pop(idx)
        except (ValueError, IndexError):
            return None
    return None


_SENTINEL = object()

# Restricted paths that agents cannot modify
_RESTRICTED_PATHS = {"version", "last_updated", "last_updated_by"}


class ProjectContextManager(BaseService):
    """Service for PCD read/write with versioning, caching, and size tracking."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._context_repo = ProjectContextRepository(session)
        self._change_repo = ContextChangeRepository(session)

    @staticmethod
    @asynccontextmanager
    async def factory() -> AsyncGenerator["ProjectContextManager", None]:
        """Create a ProjectContextManager with its own DB session."""
        from modules.backend.core.database import get_async_session

        async with get_async_session() as db:
            yield ProjectContextManager(db)
            await db.commit()

    def _build_seed_pcd(self, project_name: str, description: str) -> dict:
        """Build the initial seed PCD for a new project."""
        return {
            "version": 1,
            "last_updated": "",
            "last_updated_by": "system:project_creation",
            "identity": {
                "name": project_name,
                "purpose": description,
                "tech_stack": [],
                "repo_structure": {},
            },
            "architecture": {
                "components": {},
                "data_flow": "",
                "conventions": {},
            },
            "decisions": [],
            "current_state": {
                "active_workstreams": [],
                "recent_milestones": [],
                "known_issues": [],
                "next_priorities": [],
            },
            "guardrails": [],
        }

    async def create_context(
        self,
        project_id: str,
        project_name: str,
        description: str,
    ) -> ProjectContext:
        """Create a seed PCD for a new project."""
        seed = self._build_seed_pcd(project_name, description)
        serialized = _json.dumps(seed, ensure_ascii=False)
        ctx = await self._context_repo.create(
            project_id=project_id,
            context_data=seed,
            version=1,
            size_characters=len(serialized),
            size_tokens=_estimate_tokens(serialized),
        )
        _cache[project_id] = (seed, 1, time.monotonic())
        return ctx

    async def get_context(self, project_id: str) -> dict:
        """Get the PCD for a project. Uses in-memory cache with TTL."""
        # Check cache
        cached = _cache.get(project_id)
        if cached:
            data, version, ts = cached
            if time.monotonic() - ts < _CACHE_TTL_SECONDS:
                return data

        # Cache miss — load from DB
        ctx = await self._context_repo.get_by_project_id(project_id)
        if ctx is None:
            return {}

        _cache[project_id] = (ctx.context_data, ctx.version, time.monotonic())
        return ctx.context_data

    async def get_context_with_version(
        self,
        project_id: str,
    ) -> tuple[dict, int]:
        """Get PCD content and version (for optimistic concurrency)."""
        ctx = await self._context_repo.get_by_project_id(project_id)
        if ctx is None:
            return {}, 0
        return ctx.context_data, ctx.version

    async def get_context_size(self, project_id: str) -> dict:
        """Get PCD size metrics."""
        ctx = await self._context_repo.get_by_project_id(project_id)
        if ctx is None:
            return {"size_characters": 0, "size_tokens": 0, "version": 0,
                    "pct_of_max": 0.0}
        return {
            "size_characters": ctx.size_characters,
            "size_tokens": ctx.size_tokens,
            "version": ctx.version,
            "pct_of_max": (ctx.size_characters / _PCD_MAX_SIZE) * 100,
        }

    async def apply_updates(
        self,
        project_id: str,
        updates: list[dict],
        *,
        agent_id: str | None = None,
        mission_id: str | None = None,
        task_id: str | None = None,
    ) -> tuple[int, list[str]]:
        """Apply context updates to the PCD.

        Returns (new_version, list_of_errors).
        Errors are logged and skipped — they do not fail the operation.
        Uses optimistic concurrency on the version field.
        """
        ctx = await self._context_repo.get_by_project_id(project_id)
        if ctx is None:
            return 0, ["ProjectContext not found for project"]

        data = dict(ctx.context_data)  # shallow copy
        current_version = ctx.version
        errors: list[str] = []

        import copy
        data = copy.deepcopy(ctx.context_data)

        for update in updates:
            op = update.get("op")
            path = update.get("path", "")
            value = update.get("value")
            reason = update.get("reason", "no reason provided")

            # Validate restricted paths
            root_key = path.split(".")[0] if path else ""
            if root_key in _RESTRICTED_PATHS:
                errors.append(f"Restricted path: {path}")
                continue

            # Validate guardrails are append-only for agents
            if op == "remove" and path.startswith("guardrails") and agent_id:
                errors.append(f"Agents cannot remove guardrails: {path}")
                continue

            old_value = None
            change_type = None

            if op == "add":
                old_value = _get_nested(data, path)
                if old_value is _SENTINEL:
                    old_value = None
                _set_nested(data, path, value)
                change_type = ChangeType.ADD

            elif op == "replace":
                old_value = _get_nested(data, path)
                if old_value is _SENTINEL:
                    errors.append(f"Path not found for replace: {path}")
                    continue
                if old_value == value:
                    errors.append(f"No-op replace (value unchanged): {path}")
                    continue
                _set_nested(data, path, value)
                change_type = ChangeType.REPLACE

            elif op == "remove":
                old_value = _delete_nested(data, path)
                if old_value is None:
                    errors.append(f"Path not found for remove: {path}")
                    continue
                change_type = ChangeType.REMOVE

            else:
                errors.append(f"Unknown operation: {op}")
                continue

            # Record change
            await self._change_repo.create(
                context_id=ctx.id,
                version=current_version + 1,
                change_type=change_type,
                path=path,
                old_value=old_value if not isinstance(old_value, type(_SENTINEL)) else None,
                new_value=value,
                agent_id=agent_id,
                mission_id=mission_id,
                task_id=task_id,
                reason=reason,
            )

        # Update system fields
        from datetime import datetime, timezone
        data["version"] = current_version + 1
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        data["last_updated_by"] = agent_id or mission_id or "system"

        # Check size
        serialized = _json.dumps(data, ensure_ascii=False)
        new_size = len(serialized)
        if new_size > _PCD_MAX_SIZE:
            return current_version, [
                f"PCD would exceed size cap: {new_size} > {_PCD_MAX_SIZE} bytes. "
                "Prune before applying more updates."
            ]

        # Optimistic concurrency write
        new_version = current_version + 1
        rows_updated = await self._context_repo.update_context(
            project_id=project_id,
            context_data=data,
            new_version=new_version,
            size_characters=new_size,
            size_tokens=_estimate_tokens(serialized),
        )

        if rows_updated == 0:
            return current_version, ["Version conflict — PCD was updated concurrently"]

        # Invalidate cache
        _cache.pop(project_id, None)

        self._log_operation(
            "PCD updated",
            project_id=project_id,
            new_version=new_version,
            size_characters=new_size,
            updates_applied=len(updates) - len(errors),
            errors=len(errors),
        )

        return new_version, errors

    async def get_history(
        self,
        project_id: str,
        limit: int = 50,
    ) -> list[ContextChange]:
        """Get recent PCD change history."""
        ctx = await self._context_repo.get_by_project_id(project_id)
        if ctx is None:
            return []
        return await self._change_repo.list_by_context(ctx.id, limit=limit)
```

---

### Step 2.5: Wire PCD Creation into ProjectService

**File**: `modules/backend/services/project.py` — MODIFY

In `create_project()`, after creating the project and owner membership, create the seed PCD:

```python
        # Create seed PCD
        from modules.backend.services.project_context import ProjectContextManager
        pcd_manager = ProjectContextManager(self._session)
        await pcd_manager.create_context(
            project_id=project.id,
            project_name=name,
            description=description,
        )
```

---

### Step 2.6: CLI Context Subcommands

**File**: `modules/backend/cli/project.py` — MODIFY

Add three new actions to the `actions` dict: `"context-show"`, `"context-update"`, `"context-history"`.

```python
async def _action_context_show(cli_logger, *, project_id, output_format, **_):
    """Show the PCD for a project."""
    import json as _json
    from modules.backend.services.project_context import ProjectContextManager

    console = get_console()
    if not project_id:
        console.print("[red]PROJECT_ID is required[/red]")
        sys.exit(1)

    async with ProjectContextManager.factory() as mgr:
        data = await mgr.get_context(project_id)
        size = await mgr.get_context_size(project_id)

    if not data:
        console.print("[dim]No PCD found for this project.[/dim]")
        return

    console.print(f"[bold]Project Context Document[/bold]  (v{size['version']}, "
                  f"{size['size_characters']} chars, {size['pct_of_max']:.0f}% of cap)")
    console.print()
    console.print(_json.dumps(data, indent=2, ensure_ascii=False))


async def _action_context_history(cli_logger, *, project_id, output_format, **_):
    """Show PCD change history."""
    from modules.backend.services.project_context import ProjectContextManager

    console = get_console()
    if not project_id:
        console.print("[red]PROJECT_ID is required[/red]")
        sys.exit(1)

    async with ProjectContextManager.factory() as mgr:
        changes = await mgr.get_history(project_id, limit=20)

    if not changes:
        console.print("[dim]No changes recorded.[/dim]")
        return

    table = build_table("PCD Changes", columns=[
        ("Version", {"width": 8}),
        ("Type", {"width": 10}),
        ("Path", {"style": "cyan", "width": 40}),
        ("Agent", {"width": 25}),
        ("Reason", {"ratio": 1}),
    ])
    for c in changes:
        table.add_row(str(c.version), c.change_type, c.path,
                      c.agent_id or "—", c.reason[:60])

    console.print(table)
```

**File**: `cli.py` — MODIFY

Add context subcommands under the `project` group:

```python
@project.group("context", cls=ShowHelpOnMissingArgs)
def project_context():
    """View and manage the Project Context Document (PCD)."""
    pass


@project_context.command("show")
@click.argument("project_id")
@click.pass_obj
def project_context_show(ctx, project_id):
    """Show the PCD for a project."""
    from modules.backend.cli.project import run_project
    run_project(ctx.logger, "context-show", project_id=project_id,
                output_format=ctx.output_format)


@project_context.command("history")
@click.argument("project_id")
@click.pass_obj
def project_context_history(ctx, project_id):
    """Show PCD change audit trail."""
    from modules.backend.cli.project import run_project
    run_project(ctx.logger, "context-history", project_id=project_id,
                output_format=ctx.output_format)
```

**Verify**: `python cli.py project context show <project_id>` displays PCD JSON.

---

## Sub-Phase 3: Agent Contract

### Step 3.1: Add context_updates to TaskResult

**File**: `modules/backend/agents/mission_control/outcome.py` — MODIFY

Add `context_updates` field to `TaskResult` (note: `execution_id` was already added in Pre-Phase 0 Step P0.6):

```python
class TaskResult(BaseModel):
    """Result of executing a single task."""

    # ... existing fields ...
    # execution_id: str  ← already added in Pre-Phase 0
    context_updates: list[dict] = Field(
        default_factory=list,
        description="Structured patches to the PCD proposed by this agent",
    )
```

The `execution_id` enables tracing context_updates back to the specific task execution that produced them. When `ContextCurator` persists changes, it records the `execution_id` alongside `agent_id`, `mission_id`, and `task_id` in the `ContextChange` audit trail.

---

### Step 3.2: Context Curator Service

**File**: `modules/backend/services/context_curator.py` (NEW, ~100 lines)

```python
"""
Context Curator.

Validates and applies context_updates from agent task results to the PCD.
Enforces size caps, restricted paths, and guardrail protection.
Delegates actual PCD mutation to ProjectContextManager.
"""

from modules.backend.core.logging import get_logger
from modules.backend.services.project_context import ProjectContextManager

logger = get_logger(__name__)


class ContextCurator:
    """Validates and applies agent context_updates to the PCD."""

    def __init__(self, context_manager: ProjectContextManager) -> None:
        self._manager = context_manager

    async def apply_task_updates(
        self,
        project_id: str,
        task_result_context_updates: list[dict],
        *,
        agent_id: str | None = None,
        mission_id: str | None = None,
        task_id: str | None = None,
    ) -> tuple[int, list[str]]:
        """Apply context_updates from a task result to the PCD.

        Returns (new_version, list_of_errors).
        Errors are non-fatal — they are logged but do not fail the task.
        """
        if not task_result_context_updates:
            return 0, []

        new_version, errors = await self._manager.apply_updates(
            project_id,
            task_result_context_updates,
            agent_id=agent_id,
            mission_id=mission_id,
            task_id=task_id,
        )

        if errors:
            logger.warning(
                "Context update errors (non-fatal)",
                extra={
                    "project_id": project_id,
                    "task_id": task_id,
                    "errors": errors,
                },
            )

        return new_version, errors
```

---

### Step 3.3: Modify Dispatch Loop

**File**: `modules/backend/agents/mission_control/dispatch.py` — MODIFY

This is the critical integration point. Two changes to the `dispatch()` function:

**Change 1:** Accept `project_id` and `context_curator` as optional parameters to `dispatch()`:

In the `dispatch()` function signature, add:

```python
async def dispatch(
    plan: TaskPlan,
    roster: Roster,
    execute_agent_fn,
    mission_budget_usd: float | None = None,
    *,
    project_id: str | None = None,
    context_curator: Any | None = None,  # ContextCurator instance
) -> MissionOutcome:
```

**Change 2:** After each successful task execution in `_execute_with_retry()` or after the task result is collected in the dispatch loop, extract and apply `context_updates`:

In the dispatch loop, after `completed_outputs[task_id] = result.output_reference`, add:

```python
            # Apply context_updates to PCD (non-fatal)
            if context_curator and project_id and result.context_updates:
                try:
                    await context_curator.apply_task_updates(
                        project_id,
                        result.context_updates,
                        agent_id=result.agent_name,
                        mission_id=plan.mission_id,
                        task_id=result.task_id,
                        execution_id=result.execution_id,  # from Pre-Phase 0
                    )
                except Exception as e:
                    logger.warning(
                        "Context update failed (non-fatal)",
                        extra={"task_id": result.task_id, "error": str(e)},
                    )
```

**Important:** Context update failures must NEVER fail the task or the mission. Wrap in try/except and log warnings only.

---

### Step 3.4: Pass PCD to Agent Prompts

**File**: `modules/backend/agents/mission_control/helpers.py` — MODIFY

In the function that builds agent prompts/inputs (the function that constructs what gets passed to `execute_agent_fn`), add the PCD as a `project_context` field in the agent's input:

Find the function that assembles the agent call (likely `_build_agent_input` or similar). Add an optional `project_context: dict | None = None` parameter. When provided, include it in the agent's input dict:

```python
if project_context:
    agent_input["project_context"] = project_context
```

The PCD should be passed as a top-level key in the agent's input so it appears in the agent's context window.

---

### Step 3.5: Wire Project ID Through Mission Control

**File**: `modules/backend/agents/mission_control/mission_control.py` — MODIFY

In `handle_mission()`, pass `project_id` from the Mission to the dispatch call. The Mission model already has `project_id`.

```python
outcome = await dispatch(
    plan=validated_plan,
    roster=roster,
    execute_agent_fn=execute_agent_fn,
    mission_budget_usd=budget,
    project_id=mission_project_id,  # from Mission.project_id
    context_curator=context_curator,  # constructed if project_id is set
)
```

Construct the `ContextCurator` only if `project_id` is set:

```python
context_curator = None
if mission_project_id:
    from modules.backend.services.context_curator import ContextCurator
    from modules.backend.services.project_context import ProjectContextManager
    pcd_manager = ProjectContextManager(db_session)
    context_curator = ContextCurator(pcd_manager)
```

**Verify**: Run a mission scoped to a project. Check that `context_changes` table has new rows after mission completion.

---

## Sub-Phase 4: Context Assembly

### Step 4.1: Add domain_tags to TaskDefinition and TaskExecution

**File**: `modules/backend/schemas/task_plan.py` — MODIFY

Add `domain_tags` to `TaskDefinition`:

```python
class TaskDefinition(BaseModel):
    # ... existing fields ...
    domain_tags: list[str] = Field(
        default_factory=list,
        description="Domain tags for structured history queries (e.g. ['auth', 'api'])",
    )
```

**File**: `modules/backend/models/mission_record.py` — MODIFY

Add `domain_tags` to `TaskExecution`:

```python
    domain_tags: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
    )
```

**File**: `modules/backend/agents/mission_control/persistence_bridge.py` — MODIFY

When creating `TaskExecution` records from `TaskResult`, populate `domain_tags` from the corresponding `TaskDefinition` in the plan. Look up the task in the `TaskPlan` by `task_id` and copy its `domain_tags`.

---

### Step 4.2: History Query Service

**File**: `modules/backend/services/history_query.py` (NEW, ~150 lines)

```python
"""
History Query Service.

Structured queries over project history for Layer 2 context retrieval.
All queries are project-scoped. No semantic search — only structured filters.
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from sqlalchemy import select, and_, desc, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.models.mission_record import (
    MissionRecord,
    TaskExecution,
    TaskAttempt,
    TaskAttemptStatus,
)
from modules.backend.services.base import BaseService

logger = get_logger(__name__)


class HistoryQueryService(BaseService):
    """Structured queries over project history."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    @staticmethod
    @asynccontextmanager
    async def factory() -> AsyncGenerator["HistoryQueryService", None]:
        from modules.backend.core.database import get_async_session
        async with get_async_session() as db:
            yield HistoryQueryService(db)

    async def get_recent_task_executions(
        self,
        project_id: str,
        *,
        domain_tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Get recent task executions, optionally filtered by domain tags.

        Returns dicts with task_id, agent_name, status, domain_tags,
        output_data (summary only), cost_usd, duration_seconds.
        """
        query = (
            select(TaskExecution)
            .join(MissionRecord, TaskExecution.mission_record_id == MissionRecord.id)
            .where(MissionRecord.project_id == project_id)
            .order_by(desc(TaskExecution.completed_at))
            .limit(limit)
        )
        # Note: domain_tags filtering with JSON containment depends on DB engine.
        # For SQLite, do post-filter. For PostgreSQL, use @> operator.
        result = await self.session.execute(query)
        executions = list(result.scalars().all())

        if domain_tags:
            executions = [
                e for e in executions
                if e.domain_tags and any(tag in e.domain_tags for tag in domain_tags)
            ]

        return [
            {
                "task_id": e.task_id,
                "agent_name": e.agent_name,
                "status": e.status,
                "domain_tags": e.domain_tags,
                "cost_usd": e.cost_usd,
                "duration_seconds": e.duration_seconds,
                "completed_at": e.completed_at,
            }
            for e in executions[:limit]
        ]

    async def get_recent_failures(
        self,
        project_id: str,
        *,
        domain_tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Get recent failed task attempts for a project.

        Returns failure reason and feedback so agents don't repeat mistakes.
        """
        query = (
            select(TaskAttempt, TaskExecution)
            .join(TaskExecution, TaskAttempt.task_execution_id == TaskExecution.id)
            .join(MissionRecord, TaskExecution.mission_record_id == MissionRecord.id)
            .where(MissionRecord.project_id == project_id)
            .where(TaskAttempt.status == TaskAttemptStatus.FAILED)
            .order_by(desc(TaskAttempt.created_at))
            .limit(limit)
        )
        result = await self.session.execute(query)
        rows = result.all()

        failures = []
        for attempt, execution in rows:
            if domain_tags and execution.domain_tags:
                if not any(tag in execution.domain_tags for tag in domain_tags):
                    continue
            failures.append({
                "task_id": execution.task_id,
                "agent_name": execution.agent_name,
                "failure_tier": attempt.failure_tier,
                "failure_reason": attempt.failure_reason,
                "feedback_provided": attempt.feedback_provided,
                "domain_tags": execution.domain_tags,
            })

        return failures[:limit]

    async def get_mission_summaries(
        self,
        project_id: str,
        *,
        limit: int = 10,
    ) -> list[dict]:
        """Get recent mission outcome summaries for a project."""
        result = await self.session.execute(
            select(MissionRecord)
            .where(MissionRecord.project_id == project_id)
            .order_by(desc(MissionRecord.completed_at))
            .limit(limit)
        )
        records = list(result.scalars().all())

        return [
            {
                "id": r.id,
                "objective": r.objective_statement,
                "status": r.status,
                "total_cost_usd": r.total_cost_usd,
                "completed_at": r.completed_at,
            }
            for r in records
        ]
```

---

### Step 4.3: Context Assembler Service

**File**: `modules/backend/services/context_assembler.py` (NEW, ~200 lines)

```python
"""
Context Assembler.

Builds the complete context packet for an agent before task execution.
Combines Layer 0 (PCD), Layer 1 (task + upstream), and Layer 2 (history)
within a configurable token budget.

Priority order (last trimmed first):
  1. PCD (never trimmed)
  2. Task definition (never trimmed)
  3. Upstream outputs (summarized if over budget)
  4. History (reduced/removed if over budget)
"""

import json as _json
from typing import Any

from modules.backend.core.logging import get_logger
from modules.backend.services.history_query import HistoryQueryService
from modules.backend.services.project_context import ProjectContextManager

logger = get_logger(__name__)

# Default token budget for context assembly
DEFAULT_TOKEN_BUDGET = 12_000  # ~48KB of JSON


def _estimate_tokens(data: Any) -> int:
    """Estimate token count for a data structure."""
    serialized = _json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
    return len(serialized) // 4


class ContextAssembler:
    """Builds context packets for agents within token budgets."""

    def __init__(
        self,
        context_manager: ProjectContextManager,
        history_service: HistoryQueryService,
    ) -> None:
        self._context_manager = context_manager
        self._history_service = history_service

    async def build(
        self,
        project_id: str,
        task_definition: dict,
        resolved_inputs: dict,
        *,
        domain_tags: list[str] | None = None,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> dict:
        """Build the context packet for a task.

        Returns a dict with keys:
          - project_context: the PCD (Layer 0)
          - task: task definition (Layer 1)
          - inputs: resolved inputs (Layer 1)
          - history: relevant past work (Layer 2, if budget allows)
        """
        packet: dict[str, Any] = {}
        remaining_budget = token_budget

        # Layer 0: PCD (always, never trimmed)
        pcd = await self._context_manager.get_context(project_id)
        pcd_tokens = _estimate_tokens(pcd)
        packet["project_context"] = pcd
        remaining_budget -= pcd_tokens

        # Layer 1: Task definition (always, never trimmed)
        task_tokens = _estimate_tokens(task_definition)
        packet["task"] = task_definition
        remaining_budget -= task_tokens

        # Layer 1: Resolved inputs (high priority, summarized if needed)
        input_tokens = _estimate_tokens(resolved_inputs)
        if input_tokens <= remaining_budget:
            packet["inputs"] = resolved_inputs
            remaining_budget -= input_tokens
        else:
            # Summarize: include keys only, not full values
            summarized = {
                k: f"<{type(v).__name__}, {len(str(v))} chars>"
                if not isinstance(v, (str, int, float, bool))
                else v
                for k, v in resolved_inputs.items()
            }
            packet["inputs"] = summarized
            remaining_budget -= _estimate_tokens(summarized)

        # Layer 2: History (optional, trimmed first)
        if remaining_budget > 500 and domain_tags:  # minimum useful history
            history: dict[str, Any] = {}

            # Recent failures (always if available — agents must not repeat)
            failures = await self._history_service.get_recent_failures(
                project_id, domain_tags=domain_tags, limit=3,
            )
            if failures:
                failure_tokens = _estimate_tokens(failures)
                if failure_tokens <= remaining_budget:
                    history["recent_failures"] = failures
                    remaining_budget -= failure_tokens

            # Recent executions in same domain
            if remaining_budget > 200:
                executions = await self._history_service.get_recent_task_executions(
                    project_id, domain_tags=domain_tags, limit=5,
                )
                if executions:
                    exec_tokens = _estimate_tokens(executions)
                    if exec_tokens <= remaining_budget:
                        history["recent_executions"] = executions
                        remaining_budget -= exec_tokens

            if history:
                packet["history"] = history

        logger.debug(
            "Context assembled",
            extra={
                "project_id": project_id,
                "budget": token_budget,
                "used": token_budget - remaining_budget,
                "layers": list(packet.keys()),
            },
        )

        return packet
```

---

### Step 4.4: Wire Context Assembly into Dispatch

**File**: `modules/backend/agents/mission_control/dispatch.py` — MODIFY

Accept `context_assembler` as an optional parameter in `dispatch()`:

```python
async def dispatch(
    plan: TaskPlan,
    roster: Roster,
    execute_agent_fn,
    mission_budget_usd: float | None = None,
    *,
    project_id: str | None = None,
    context_curator: Any | None = None,
    context_assembler: Any | None = None,  # ContextAssembler instance
) -> MissionOutcome:
```

Before each task execution, if `context_assembler` is available, build the context packet and pass it to the agent:

```python
            # Build context packet (Layer 0 + Layer 2)
            context_packet = None
            if context_assembler and project_id:
                try:
                    context_packet = await context_assembler.build(
                        project_id,
                        task_def.model_dump(),
                        resolved_inputs,
                        domain_tags=getattr(task_def, 'domain_tags', None),
                    )
                except Exception as e:
                    logger.warning("Context assembly failed (non-fatal)",
                                   extra={"task_id": task_def.task_id, "error": str(e)})
```

Pass `context_packet` to `execute_agent_fn` as an additional keyword argument. The agent execution function should merge it into the agent's input if provided.

**File**: `modules/backend/agents/mission_control/mission_control.py` — MODIFY

Construct `ContextAssembler` when `project_id` is set:

```python
context_assembler = None
if mission_project_id:
    from modules.backend.services.context_assembler import ContextAssembler
    from modules.backend.services.history_query import HistoryQueryService
    history_svc = HistoryQueryService(db_session)
    context_assembler = ContextAssembler(pcd_manager, history_svc)
```

**Verify**: Run a mission with `--project`. Check that the agent receives `project_context` in its input.

---

## Sub-Phase 5: Fractal Summarization

### Step 5.1: Project History Models

**File**: `modules/backend/models/project_history.py` (NEW, ~100 lines)

```python
"""
Project History Models.

Archived decisions and milestone summaries for Layer 2 history queries.
"""

import enum

from sqlalchemy import Enum, Float, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class DecisionStatus(str, enum.Enum):
    """Decision lifecycle status."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVERSED = "reversed"


class ProjectDecision(UUIDMixin, TimestampMixin, Base):
    """Archived decision from PCD pruning, queryable by domain."""

    __tablename__ = "project_decisions"

    project_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
    )
    decision_id: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    domain: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
    )
    decision: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    rationale: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    made_by: Mapped[str] = mapped_column(
        String(200), nullable=False,
    )
    mission_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        Enum(DecisionStatus, native_enum=False),
        default=DecisionStatus.ACTIVE,
        nullable=False,
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectDecision(id={self.decision_id}, "
            f"domain={self.domain!r}, status={self.status})>"
        )


class MilestoneSummary(UUIDMixin, TimestampMixin, Base):
    """Compressed summary of a completed project phase."""

    __tablename__ = "milestone_summaries"

    project_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
    )
    title: Mapped[str] = mapped_column(
        String(300), nullable=False,
    )
    summary: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    mission_ids: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
    )
    key_outcomes: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
    )
    domain_tags: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False,
    )
    period_start: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
    )
    period_end: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<MilestoneSummary(title={self.title!r}, "
            f"missions={len(self.mission_ids)})>"
        )
```

---

### Step 5.2: Project History Repositories

**File**: `modules/backend/repositories/project_history.py` (NEW, ~80 lines)

```python
"""
Project History Repository.

Data access for archived decisions and milestone summaries.
"""

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.project_history import (
    DecisionStatus,
    MilestoneSummary,
    ProjectDecision,
)
from modules.backend.repositories.base import BaseRepository


class ProjectDecisionRepository(BaseRepository[ProjectDecision]):
    """Repository for project decisions."""

    model = ProjectDecision

    async def list_by_domain(
        self,
        project_id: str,
        domain: str,
        limit: int = 20,
    ) -> list[ProjectDecision]:
        """Get decisions for a domain, most recent first."""
        result = await self.session.execute(
            select(ProjectDecision)
            .where(ProjectDecision.project_id == project_id)
            .where(ProjectDecision.domain == domain)
            .where(ProjectDecision.status == DecisionStatus.ACTIVE)
            .order_by(desc(ProjectDecision.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_active(
        self,
        project_id: str,
        limit: int = 50,
    ) -> list[ProjectDecision]:
        """Get all active decisions for a project."""
        result = await self.session.execute(
            select(ProjectDecision)
            .where(ProjectDecision.project_id == project_id)
            .where(ProjectDecision.status == DecisionStatus.ACTIVE)
            .order_by(desc(ProjectDecision.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())


class MilestoneSummaryRepository(BaseRepository[MilestoneSummary]):
    """Repository for milestone summaries."""

    model = MilestoneSummary

    async def list_by_project(
        self,
        project_id: str,
        limit: int = 20,
    ) -> list[MilestoneSummary]:
        """Get milestones for a project, most recent first."""
        result = await self.session.execute(
            select(MilestoneSummary)
            .where(MilestoneSummary.project_id == project_id)
            .order_by(desc(MilestoneSummary.period_end))
            .limit(limit)
        )
        return list(result.scalars().all())
```

---

### Step 5.3: Summarization Service

**File**: `modules/backend/services/summarization.py` (NEW, ~250 lines)

```python
"""
Summarization Service.

Fractal compression pipeline for project history:
  Task executions → Mission summaries → Milestone summaries → PCD

Runs periodically or on-demand. Uses Haiku-class model for compression.
Never deletes raw data — only marks as summarized and excludes from default queries.
"""

import json as _json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

from sqlalchemy import select, update, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.models.mission_record import MissionRecord
from modules.backend.models.project_context import ChangeType
from modules.backend.models.project_history import (
    DecisionStatus,
    MilestoneSummary,
    ProjectDecision,
)
from modules.backend.repositories.project_history import (
    MilestoneSummaryRepository,
    ProjectDecisionRepository,
)
from modules.backend.services.base import BaseService
from modules.backend.services.project_context import ProjectContextManager

logger = get_logger(__name__)


class SummarizationService(BaseService):
    """Fractal compression pipeline for project history."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._decision_repo = ProjectDecisionRepository(session)
        self._milestone_repo = MilestoneSummaryRepository(session)
        self._context_manager = ProjectContextManager(session)

    @staticmethod
    @asynccontextmanager
    async def factory() -> AsyncGenerator["SummarizationService", None]:
        from modules.backend.core.database import get_async_session
        async with get_async_session() as db:
            yield SummarizationService(db)
            await db.commit()

    async def prune_pcd_decisions(
        self,
        project_id: str,
        max_age_days: int = 90,
    ) -> int:
        """Archive decisions older than max_age_days from PCD to project_decisions table.

        Returns count of decisions archived.
        """
        data, version = await self._context_manager.get_context_with_version(project_id)
        if not data:
            return 0

        decisions = data.get("decisions", [])
        if not decisions:
            return 0

        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()[:10]
        to_archive = []
        to_keep = []

        for d in decisions:
            if d.get("date", "") < cutoff:
                to_archive.append(d)
            else:
                to_keep.append(d)

        if not to_archive:
            return 0

        # Archive to project_decisions table
        for d in to_archive:
            await self._decision_repo.create(
                project_id=project_id,
                decision_id=d.get("id", ""),
                domain=d.get("domain", "general"),
                decision=d.get("decision", ""),
                rationale=d.get("rationale", ""),
                made_by=d.get("made_by", "unknown"),
                mission_id=d.get("mission_id"),
                status=DecisionStatus.ACTIVE,
            )

        # Update PCD with pruned decisions list
        updates = [{
            "op": "replace",
            "path": "decisions",
            "value": to_keep,
            "reason": f"Archived {len(to_archive)} decisions older than {max_age_days} days",
        }]

        await self._context_manager.apply_updates(
            project_id,
            updates,
            agent_id="system:summarization",
        )

        self._log_operation(
            "PCD decisions pruned",
            project_id=project_id,
            archived=len(to_archive),
            remaining=len(to_keep),
        )

        return len(to_archive)

    async def prune_completed_workstreams(
        self,
        project_id: str,
    ) -> int:
        """Move completed items from current_state to milestone summaries.

        Returns count of items processed.
        """
        data, version = await self._context_manager.get_context_with_version(project_id)
        if not data:
            return 0

        current_state = data.get("current_state", {})
        milestones = current_state.get("recent_milestones", [])

        if not milestones:
            return 0

        # Keep only recent milestones (last 5), archive the rest
        if len(milestones) <= 5:
            return 0

        to_archive = milestones[5:]
        to_keep = milestones[:5]

        # Create milestone summary for archived items
        await self._milestone_repo.create(
            project_id=project_id,
            title=f"Milestones batch ({len(to_archive)} items)",
            summary="; ".join(to_archive),
            mission_ids=[],
            key_outcomes={"milestones": to_archive},
            domain_tags=[],
            period_start=None,
            period_end=datetime.now(timezone.utc).isoformat(),
        )

        updates = [{
            "op": "replace",
            "path": "current_state.recent_milestones",
            "value": to_keep,
            "reason": f"Archived {len(to_archive)} old milestones",
        }]

        await self._context_manager.apply_updates(
            project_id,
            updates,
            agent_id="system:summarization",
        )

        return len(to_archive)

    async def run_full_pipeline(
        self,
        project_id: str,
    ) -> dict:
        """Run the full summarization pipeline for a project.

        Returns summary of actions taken.
        """
        results = {
            "decisions_archived": 0,
            "milestones_archived": 0,
        }

        results["decisions_archived"] = await self.prune_pcd_decisions(project_id)
        results["milestones_archived"] = await self.prune_completed_workstreams(project_id)

        self._log_operation(
            "Summarization pipeline complete",
            project_id=project_id,
            **results,
        )

        return results
```

---

### Step 5.4: Summarization Agent (Optional — Can Be Deferred)

**File**: `modules/backend/agents/horizontal/summarization/agent.py` (NEW, ~60 lines)

A lightweight agent that uses Haiku-class model to generate narrative summaries from structured data. This is optional for the initial implementation — the `SummarizationService` handles deterministic compression. The agent is needed for narrative summarization of mission outcomes into human-readable milestone summaries.

```python
"""
Summarization Agent.

Generates narrative summaries from structured mission outcomes.
Uses a cost-efficient model (Haiku-class) for compression tasks.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class SummarizationInput(BaseModel):
    """Input to the summarization agent."""
    mission_outcomes: list[dict] = Field(
        ..., description="List of mission outcome summaries to compress",
    )
    target_length: int = Field(
        default=500, description="Target summary length in characters",
    )


class SummarizationOutput(BaseModel):
    """Output from the summarization agent."""
    title: str = Field(..., description="Short title for the milestone")
    summary: str = Field(..., description="Compressed narrative summary")
    key_outcomes: list[str] = Field(
        default_factory=list,
        description="Bullet-point key outcomes",
    )
    domain_tags: list[str] = Field(
        default_factory=list,
        description="Domain tags derived from the missions",
    )
```

**File**: `config/agents/horizontal/summarization/agent.yaml` (NEW)

```yaml
agent_name: horizontal.summarization.agent
version: "1.0.0"
description: "Compresses mission outcomes into concise milestone summaries"
category: horizontal
model:
  name: "anthropic:claude-haiku-4-5-20251001"
  temperature: 0.0
  max_tokens: 2048
```

**File**: `config/prompts/agents/horizontal/summarization/system.md` (NEW)

```markdown
You are a summarization agent. Your job is to compress structured mission outcomes into concise, informative milestone summaries.

Given a list of mission outcomes, produce:
1. A short title (under 60 characters)
2. A narrative summary (under the target length)
3. Key outcomes as bullet points (3-5 items)
4. Domain tags derived from the mission content

Focus on: what was achieved, what decisions were made, what patterns were established.
Omit: individual task details, cost breakdowns, timing data.
```

---

### Step 5.5: CLI Summarization Command

**File**: `cli.py` — MODIFY

Add a `summarize` subcommand under the `project` group:

```python
@project.command("summarize")
@click.argument("project_id")
@click.pass_obj
def project_summarize(ctx, project_id):
    """Run the summarization pipeline for a project."""
    from modules.backend.cli.project import run_project
    run_project(ctx.logger, "summarize", project_id=project_id,
                output_format=ctx.output_format)
```

**File**: `modules/backend/cli/project.py` — MODIFY

Add `"summarize": _action_summarize` to the actions dict:

```python
async def _action_summarize(cli_logger, *, project_id, output_format, **_):
    """Run the summarization pipeline."""
    from modules.backend.services.summarization import SummarizationService

    console = get_console()
    if not project_id:
        console.print("[red]PROJECT_ID is required[/red]")
        sys.exit(1)

    async with SummarizationService.factory() as svc:
        results = await svc.run_full_pipeline(project_id)

    console.print("[bold]Summarization complete[/bold]")
    console.print(f"  Decisions archived:  {results['decisions_archived']}")
    console.print(f"  Milestones archived: {results['milestones_archived']}")
```

**Verify**: `python cli.py project summarize <project_id>` runs without error and reports results.

---

## Files Summary

| File | Action | Est. Lines | Sub-Phase |
|------|--------|-----------|-----------|
| `modules/backend/agents/mission_control/dispatch.py` | MODIFY | +40 | P0 |
| `modules/backend/agents/mission_control/outcome.py` | MODIFY | +5 | P0 |
| `modules/backend/agents/mission_control/mission_control.py` | MODIFY | +15 | P0 |
| `modules/backend/agents/mission_control/persistence_bridge.py` | MODIFY | +5 | P0 |
| `modules/backend/models/mission_record.py` | MODIFY | +5 | P0 |
| `modules/backend/services/playbook.py` | MODIFY | +5 | P0 |
| `modules/backend/services/mission.py` | MODIFY | +15 | P0 |
| `tests/unit/backend/mission_control/test_dispatch.py` | MODIFY | +60 | P0 |
| `tests/unit/backend/services/test_playbook.py` | NEW/MODIFY | +30 | P0 |
| `tests/unit/backend/services/test_mission.py` | MODIFY | +40 | P0 |
| `config/settings/projects.yaml` | NEW | 15 | 1 |
| `modules/backend/core/config_schema.py` | MODIFY | +15 | 1 |
| `modules/backend/core/config.py` | MODIFY | +10 | 1 |
| `modules/backend/models/project.py` | NEW | 120 | 1 |
| `modules/backend/models/mission.py` | MODIFY | +10 | 1 |
| `modules/backend/models/mission_record.py` | MODIFY | +5 | 1 |
| `modules/backend/repositories/project.py` | NEW | 120 | 1 |
| `modules/backend/schemas/project.py` | NEW | 80 | 1 |
| `modules/backend/services/project.py` | NEW | 200 | 1 |
| `modules/backend/cli/project.py` | NEW | 180 | 1 |
| `cli.py` | MODIFY | +60 | 1 |
| `modules/backend/cli/info.py` | MODIFY | +1 | 1 |
| `modules/backend/models/project_context.py` | NEW | 100 | 2 |
| `modules/backend/repositories/project_context.py` | NEW | 100 | 2 |
| `modules/backend/schemas/project_context.py` | NEW | 80 | 2 |
| `modules/backend/services/project_context.py` | NEW | 300 | 2 |
| `modules/backend/services/project.py` | MODIFY | +10 | 2 |
| `modules/backend/cli/project.py` | MODIFY | +60 | 2 |
| `cli.py` | MODIFY | +25 | 2 |
| `modules/backend/agents/mission_control/outcome.py` | MODIFY | +5 | 3 |
| `modules/backend/services/context_curator.py` | NEW | 100 | 3 |
| `modules/backend/agents/mission_control/dispatch.py` | MODIFY | +30 | 3 |
| `modules/backend/agents/mission_control/helpers.py` | MODIFY | +10 | 3 |
| `modules/backend/agents/mission_control/mission_control.py` | MODIFY | +20 | 3 |
| `modules/backend/schemas/task_plan.py` | MODIFY | +5 | 4 |
| `modules/backend/models/mission_record.py` | MODIFY | +5 | 4 |
| `modules/backend/agents/mission_control/persistence_bridge.py` | MODIFY | +10 | 4 |
| `modules/backend/services/history_query.py` | NEW | 150 | 4 |
| `modules/backend/services/context_assembler.py` | NEW | 200 | 4 |
| `modules/backend/agents/mission_control/dispatch.py` | MODIFY | +15 | 4 |
| `modules/backend/agents/mission_control/mission_control.py` | MODIFY | +10 | 4 |
| `modules/backend/models/project_history.py` | NEW | 100 | 5 |
| `modules/backend/repositories/project_history.py` | NEW | 80 | 5 |
| `modules/backend/services/summarization.py` | NEW | 250 | 5 |
| `modules/backend/agents/horizontal/summarization/agent.py` | NEW | 60 | 5 |
| `config/agents/horizontal/summarization/agent.yaml` | NEW | 10 | 5 |
| `config/prompts/agents/horizontal/summarization/system.md` | NEW | 15 | 5 |
| `modules/backend/cli/project.py` | MODIFY | +20 | 5 |
| `cli.py` | MODIFY | +10 | 5 |

**Total new files:** 18 (+ 1 new test file in Pre-Phase 0)
**Total modified files:** 17 (some modified in multiple sub-phases, +7 in Pre-Phase 0)
**Estimated new code:** ~2,620 lines (~220 in Pre-Phase 0, ~2,400 in Sub-Phases 1-5)

---

## Anti-Patterns

- **DO NOT** use vector embeddings, RAG, or semantic search for agent coordination. All history retrieval is structured queries by domain tag, component, time range, or failure status.
- **DO NOT** store the PCD as multiple relational rows. It is a single JSONB column — one read, no joins, flexible schema.
- **DO NOT** allow context_updates failures to fail tasks or missions. They are non-fatal. Log and skip.
- **DO NOT** delete raw history data during summarization. Mark as summarized, exclude from default queries.
- **DO NOT** allow agents to remove guardrails from the PCD. Only human project owners can do this.
- **DO NOT** add ForeignKey constraints on `project_id` columns. Follow the existing pattern (Mission.playbook_run_id uses string references without FK).
- **DO NOT** make `project_id` NOT NULL on existing tables during initial migration. Make it nullable first, backfill later.
- **DO NOT** create a separate execution engine for context updates. Everything flows through the existing dispatch loop.
- **DO NOT** load Layer 2 history when token budget is insufficient. PCD and task definition have absolute priority.
- **DO NOT** create agent prompt text in the context assembler. It builds a data structure. The existing prompt construction in helpers.py consumes it.
