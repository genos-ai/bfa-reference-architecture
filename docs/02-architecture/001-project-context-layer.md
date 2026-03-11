# Project Context Layer

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-03-10*

## Changelog

- 1.0.0 (2026-03-10): Initial architecture — Project entity, Project Context Document, three-layer memory model, context assembly, fractal summarization, agent contract

---

## Purpose

This document defines the architecture for **persistent, cross-mission project context** — the system that allows ephemeral agents to operate on long-running projects spanning days, weeks, months, or years.

Every agent is ephemeral. It spins up, receives context, executes a task, writes back what it learned, and exits. The next agent picks up where it left off. Over a year, a project may execute thousands of missions across hundreds of playbook runs. Without a persistent context layer, each agent starts cold — unaware of architectural decisions, established patterns, failed approaches, or the current state of the codebase.

The Project Context Layer solves this. It is the system's long-term memory.

---

## Design Goals

1. **Agent #847 on day 193 operates with the same situational awareness as a senior engineer who has been on the project since day one.** No agent should need to re-discover what has already been established.

2. **Context scales with project lifetime, not linearly with history size.** A project with 3,000 completed missions must not require 3,000 missions worth of context in every agent's prompt.

3. **Every agent contributes to collective knowledge.** Context is not maintained by a separate process — it is a byproduct of normal task execution.

4. **Context is structured, not semantic.** Agents need precise, deterministic data (what components exist, what decisions were made, what interfaces are defined), not fuzzy similarity matches.

5. **Projects are isolated.** One project's context never bleeds into another.

---

## Core Concepts

### Project

A **Project** is the top-level organizational boundary. It is a long-lived entity that groups all missions, playbook runs, context, and history for a single codebase or initiative.

Projects are owned by humans (individuals or teams). Agents operate within the scope of a single project. All queries, context, budgets, and rosters are project-scoped.

A platform hosts many concurrent projects with independent lifecycles.

### Project Context Document (PCD)

The **PCD** is a living, curated JSON document that captures everything an agent needs to know about a project to orient itself. It is the "executive brief" — always current, always concise, always loaded into every agent's context window.

The PCD is not a log. It is not appended to. It is actively maintained: old entries are archived, stale information is pruned, and the document is kept within a strict size budget.

### Context Assembly

**Context Assembly** is the process of building the complete context packet for an agent before it executes a task. It draws from multiple layers and respects a token budget. No agent receives raw, unfiltered history.

### Agent Contract

The **Agent Contract** is a behavioral requirement on every agent in the system. After completing a task, agents must return not only their task output but also structured updates to the PCD. This is how collective knowledge accumulates.

---

## Three-Layer Memory Model

Context is organized into three layers with different lifetimes, sizes, and retrieval strategies.

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 0: PROJECT CONTEXT DOCUMENT (PCD)                        │
│                                                                 │
│  Always loaded. Size-bounded (~15KB). Actively curated.         │
│  Contains: identity, architecture, conventions, decisions,      │
│  current state, guardrails.                                     │
│                                                                 │
│  Answers: "What is this project and how does it work?"          │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 1: MISSION CONTEXT                                       │
│                                                                 │
│  Loaded per-mission. Variable size. From current execution.     │
│  Contains: TaskPlan DAG, upstream_context, task inputs,         │
│  sibling task outputs (from_upstream resolution).               │
│                                                                 │
│  Answers: "What am I doing right now?"                          │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2: PROJECT HISTORY                                       │
│                                                                 │
│  Retrieved on demand. Queried by structure, not semantics.      │
│  Contains: past decisions, mission outcomes, failed approaches, │
│  component change history, milestone summaries.                 │
│                                                                 │
│  Answers: "What has been tried before? What was decided?"       │
└─────────────────────────────────────────────────────────────────┘
```

### Layer 0: Project Context Document

The PCD is the critical piece. It is loaded into every agent's context window for every task, without exception.

**Structure:**

```json
{
  "version": 312,
  "last_updated": "2026-03-10T14:32:00Z",
  "last_updated_by": "mission:abc123/task:task_005",

  "identity": {
    "name": "BFA Reference Architecture",
    "purpose": "Production agent orchestration platform",
    "tech_stack": ["Python 3.12", "FastAPI", "SQLAlchemy", "PydanticAI"],
    "repo_structure": {
      "modules/backend/agents/": "agent implementations",
      "modules/backend/services/": "business logic",
      "modules/backend/models/": "SQLAlchemy ORM models",
      "modules/backend/schemas/": "Pydantic schemas",
      "modules/backend/api/": "FastAPI endpoints"
    }
  },

  "architecture": {
    "components": {
      "mission_control": {
        "purpose": "Orchestrates mission lifecycle: planning, dispatch, verification",
        "key_files": [
          "agents/mission_control/mission_control.py",
          "agents/mission_control/dispatch.py"
        ],
        "interfaces": ["handle_mission()", "dispatch()"]
      },
      "planning_agent": {
        "purpose": "Generates TaskPlan DAGs from objectives using extended thinking",
        "key_files": ["agents/horizontal/planning/agent.py"],
        "interfaces": ["PlanningAgent.run()"]
      }
    },
    "data_flow": "playbooks → missions → task plans → dispatch → agents → outcomes",
    "conventions": {
      "naming": "snake_case for modules and functions, PascalCase for classes",
      "imports": "absolute only, no relative imports",
      "models": "SQLAlchemy ORM with mapped_column, Pydantic for API schemas",
      "error_handling": "structured error dicts, never silent failures"
    }
  },

  "decisions": [
    {
      "id": "d-041",
      "date": "2026-03-10",
      "domain": "context",
      "decision": "Structured JSON context over RAG for agent coordination",
      "rationale": "Agents need precise, deterministic data — not fuzzy semantic similarity"
    },
    {
      "id": "d-038",
      "date": "2026-03-05",
      "domain": "verification",
      "decision": "3-tier verification: structural, quality, integration",
      "rationale": "Cheap checks first, expensive checks only if cheap ones pass"
    }
  ],

  "current_state": {
    "active_workstreams": ["project context layer", "agent SDK migration"],
    "recent_milestones": [
      "CLI mission plan view with execution join",
      "Global --output format flag"
    ],
    "known_issues": ["no cross-run context persistence"],
    "next_priorities": ["Project model", "PCD table", "context assembly service"]
  },

  "guardrails": [
    "Never bypass 3-tier verification",
    "All database changes require Alembic migrations",
    "Agents must return context_updates after every task",
    "No relative imports — absolute paths only"
  ]
}
```

**Properties:**

| Property | Requirement |
|----------|-------------|
| Size | Hard cap at 20KB. Target 10-15KB. |
| Loaded | Every agent, every task, no exceptions. |
| Updates | After every completed task, via agent context_updates. |
| Versioning | Monotonically increasing integer. Every mutation increments. |
| Audit | Every change recorded with agent identity, path, old value, new value, reason. |
| Pruning | Automatic. Old decisions archived. Stale workstreams removed. Oldest entries evicted first when size cap approached. |
| Isolation | One PCD per project. Never shared across projects. |

**What belongs in the PCD:**

- Project identity, purpose, tech stack
- Architecture: components, their purposes, key interfaces, data flow
- Active conventions and patterns that agents must follow
- Recent, actively relevant decisions (not historical record — that lives in Layer 2)
- Current state: what's being worked on, what's next, known blockers
- Guardrails: hard constraints that every agent must respect

**What does NOT belong in the PCD:**

- Full mission history (Layer 2)
- Task-level execution details (Layer 1)
- Code snippets or file contents (retrieved from codebase directly)
- Credentials, secrets, or environment-specific configuration
- Speculative or unverified information

### Layer 1: Mission Context

This layer already exists in the current architecture. It is the `TaskPlan` DAG, `upstream_context`, `from_upstream` resolution, and task inputs assembled during mission execution.

No changes are required to this layer. It handles the "what am I doing right now?" question through:

- **TaskPlan**: The DAG of tasks with dependencies, inputs, verification specs
- **upstream_context**: Context passed from upstream playbook steps via `output_mapping`
- **from_upstream resolution**: Dynamic input resolution from completed sibling tasks in the dispatch loop
- **Task inputs**: Static inputs merged with resolved upstream values

### Layer 2: Project History

A queryable store of past work, decisions, and outcomes. Not loaded by default — retrieved on demand when the Context Assembler determines a task needs historical context.

**This is NOT RAG.** Retrieval is by structured query, not semantic similarity.

**Query patterns:**

| Question | Query Strategy |
|----------|---------------|
| What decisions were made about auth? | `SELECT FROM project_decisions WHERE domain = 'auth'` |
| What was the last mission that touched this component? | `SELECT FROM task_executions WHERE domain_tags @> '{"auth"}'` |
| What approaches failed for this? | `SELECT FROM task_attempts WHERE status = 'failed' AND domain_tags @> '{"auth"}'` |
| What milestones were completed last month? | `SELECT FROM milestone_summaries WHERE completed_at > ...` |

**Data sources (already exist):**

- `mission_records` — full mission outcomes with `task_plan_json` and `mission_outcome_json`
- `task_executions` — per-task results with outputs, costs, durations
- `task_attempts` — retry history with failure reasons and feedback

**Data sources (new):**

- `project_decisions` — extracted from PCD when decisions are archived
- `milestone_summaries` — compressed summaries of completed work phases

---

## Data Model

### New Tables

```
┌─────────────────────┐
│      projects       │
├─────────────────────┤
│ id (UUID, PK)       │
│ name (VARCHAR 200)  │
│ description (TEXT)   │
│ status (ENUM)       │  active | paused | archived
│ owner_id (VARCHAR)  │
│ team_id (VARCHAR?)  │
│ default_roster (VARCHAR) │
│ budget_ceiling_usd  │
│   (FLOAT?)          │
│ repo_url (TEXT?)    │
│ repo_root (TEXT?)   │
│ created_at          │
│ updated_at          │
└────────┬────────────┘
         │
         │ 1:1
         ▼
┌─────────────────────────┐
│   project_contexts      │
├─────────────────────────┤
│ id (UUID, PK)           │
│ project_id (FK, UNIQUE) │
│ context_data (JSON)     │  ← the PCD
│ version (INTEGER)       │
│ size_characters (INT)   │
│ size_tokens (INT)       │
│ created_at              │
│ updated_at              │
└────────┬────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────┐
│   context_changes       │
├─────────────────────────┤
│ id (UUID, PK)           │
│ context_id (FK, IDX)    │
│ version (INTEGER)       │  version AFTER this change
│ change_type (ENUM)      │  add | update | remove | prune | archive
│ path (VARCHAR)          │  JSON path (dot notation)
│ old_value (JSON?)       │
│ new_value (JSON?)       │
│ agent_id (VARCHAR?)     │  which agent made the change
│ mission_id (VARCHAR?)   │  during which mission
│ task_id (VARCHAR?)      │  during which task
│ reason (TEXT)           │  why the change was made
│ created_at              │
└─────────────────────────┘

┌─────────────────────────┐
│   project_members       │
├─────────────────────────┤
│ id (UUID, PK)           │
│ project_id (FK, IDX)    │
│ user_id (VARCHAR, IDX)  │
│ role (ENUM)             │  owner | maintainer | viewer
│ created_at              │
│ updated_at              │
└─────────────────────────┘

┌─────────────────────────┐
│   project_decisions     │
├─────────────────────────┤
│ id (UUID, PK)           │
│ project_id (FK, IDX)    │
│ decision_id (VARCHAR)   │  e.g. "d-041"
│ domain (VARCHAR, IDX)   │  e.g. "auth", "storage", "verification"
│ decision (TEXT)         │
│ rationale (TEXT)        │
│ made_by (VARCHAR)       │  agent or human identifier
│ mission_id (VARCHAR?)   │  mission during which decision was made
│ status (ENUM)           │  active | superseded | reversed
│ superseded_by (VARCHAR?)│  decision_id of replacement
│ created_at              │
│ updated_at              │
└─────────────────────────┘

┌─────────────────────────┐
│  milestone_summaries    │
├─────────────────────────┤
│ id (UUID, PK)           │
│ project_id (FK, IDX)    │
│ title (VARCHAR 300)     │
│ summary (TEXT)          │  compressed narrative
│ mission_ids (JSON)      │  array of mission IDs included
│ key_outcomes (JSON)     │  structured outcomes
│ domain_tags (JSON)      │  array of domain tags
│ period_start (TIMESTAMP)│
│ period_end (TIMESTAMP)  │
│ created_at              │
└─────────────────────────┘
```

### Modified Tables

| Table | Change |
|-------|--------|
| `missions` | Add `project_id` (FK → projects, indexed, NOT NULL) |
| `playbook_runs` | Add `project_id` (FK → projects, indexed, NOT NULL) |
| `mission_records` | Add `project_id` (FK → projects, indexed) |
| `task_executions` | Add `domain_tags` (JSON array, indexed) for structured history queries |

### Entity Relationships

```
                    ┌──────────────┐
                    │   Project    │
                    └──────┬───────┘
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
   ┌───────────────┐ ┌──────────┐  ┌──────────────┐
   │ ProjectContext │ │ Missions │  │ PlaybookRuns │
   │ (PCD, 1:1)    │ │ (1:N)    │  │ (1:N)        │
   └───────┬───────┘ └────┬─────┘  └──────┬───────┘
           │              │               │
           ▼              ▼               ▼
   ┌───────────────┐ ┌──────────────┐ ┌──────────┐
   │ContextChanges │ │MissionRecords│ │ Missions │
   │ (1:N)         │ │ (1:1)        │ │ (1:N)    │
   └───────────────┘ └──────┬───────┘ └──────────┘
                            │
                      ┌─────┴──────┐
                      ▼            ▼
               ┌────────────┐ ┌──────────────┐
               │TaskExec.   │ │MissionDecis. │
               │(1:N)       │ │(1:N)         │
               └────────────┘ └──────────────┘
```

---

## Agent Contract

Every agent in the system must follow this protocol. This is not optional. It is enforced by the dispatch loop.

### Lifecycle

```
┌──────────────────────────────────────────────────────────┐
│                   AGENT LIFECYCLE                         │
│                                                          │
│  1. RECEIVE CONTEXT                                      │
│     ├── Task definition (from TaskPlan)                  │
│     ├── PCD (always — Layer 0)                           │
│     ├── Upstream outputs (from DAG — Layer 1)            │
│     └── Retrieved history (if relevant — Layer 2)        │
│                                                          │
│  2. EXECUTE TASK                                         │
│     └── Perform the work described in the task def       │
│                                                          │
│  3. RETURN RESULTS                                       │
│     ├── output_reference (the task deliverable)          │
│     └── context_updates (patches to the PCD)             │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Context Updates Format

After completing a task, agents return structured patches to the PCD using JSON Patch-like operations:

```json
{
  "context_updates": [
    {
      "op": "add",
      "path": "architecture.components.context_layer",
      "value": {
        "purpose": "Persistent cross-mission project context",
        "key_files": ["services/context_manager.py", "models/project.py"],
        "interfaces": ["ContextAssembler.build()", "ProjectContextManager.update()"]
      },
      "reason": "Implemented new context layer component"
    },
    {
      "op": "replace",
      "path": "current_state.known_issues",
      "value": ["stale milestone summaries after bulk imports"],
      "reason": "Previous issue (no cross-run context) resolved by this task"
    },
    {
      "op": "add",
      "path": "decisions/-",
      "value": {
        "id": "d-042",
        "date": "2026-03-10",
        "domain": "storage",
        "decision": "Use JSONB for PCD storage, not separate relational tables",
        "rationale": "Flexible schema, single read per context load, no joins"
      },
      "reason": "Architecture decision made during implementation"
    },
    {
      "op": "remove",
      "path": "current_state.active_workstreams.0",
      "reason": "Context layer workstream completed"
    }
  ]
}
```

**Supported operations:**

| Operation | Description |
|-----------|-------------|
| `add` | Add a new key or append to an array (use `/-` for append) |
| `replace` | Replace the value at an existing path |
| `remove` | Remove a key or array element |

Every operation requires a `reason` field explaining why the change was made. This reason is stored in the `context_changes` audit table.

### Validation Rules for Context Updates

The Context Curator validates all proposed updates before applying them:

1. **Path must exist for `replace` and `remove`** — cannot replace or remove a nonexistent path.
2. **Value must differ for `replace`** — no-op updates are rejected.
3. **Size check** — if applying the update would exceed the PCD size cap, the update is queued for review and the Context Curator triggers pruning.
4. **No restricted paths** — agents cannot modify `version`, `last_updated`, `last_updated_by` (system-managed fields).
5. **Guardrails are append-only for agents** — only human project owners can remove guardrails.

---

## Context Assembly

The **Context Assembler** is a service that builds the complete context packet for each agent before task execution. It operates within a configurable token budget.

### Assembly Process

```
┌──────────────────────────────────────────────────────────────────┐
│                     CONTEXT ASSEMBLY                             │
│                                                                  │
│  Input:  task_definition, project_id, token_budget               │
│                                                                  │
│  Step 1: Load PCD (Layer 0)                          ~15KB       │
│          Always included. Non-negotiable.                        │
│                                                                  │
│  Step 2: Load task definition + inputs (Layer 1)     ~2-5KB      │
│          From TaskPlan: objective, inputs, verification spec.    │
│                                                                  │
│  Step 3: Resolve upstream outputs (Layer 1)          ~2-10KB     │
│          From completed sibling tasks via from_upstream refs.    │
│                                                                  │
│  Step 4: Query relevant history (Layer 2)            ~2-10KB     │
│          Structured queries based on task domain_tags.           │
│          Recent decisions in the task's domain.                  │
│          Failed approaches for similar objectives.               │
│          Only if token budget allows.                            │
│                                                                  │
│  Step 5: Trim to budget                                          │
│          If total exceeds budget, Layer 2 is trimmed first,      │
│          then Layer 1 upstream outputs are summarized.           │
│          Layer 0 (PCD) is never trimmed.                         │
│                                                                  │
│  Output: context_packet (dict)                                   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Token Budget Allocation

| Layer | Priority | Budget Share | Trim Strategy |
|-------|----------|-------------|---------------|
| Layer 0 (PCD) | Mandatory | Fixed (~4K tokens) | Never trimmed |
| Layer 1 (Task + upstream) | High | 40-60% of remaining | Summarize upstream outputs if over budget |
| Layer 2 (History) | Optional | Remaining budget | Reduce result count, drop oldest first |

### History Retrieval Strategy

The Context Assembler determines what history to retrieve based on the task definition:

1. **Domain tags** from the task's `domain_tags` field (e.g., `["auth", "api"]`) drive structured queries against `project_decisions` and `task_executions`.
2. **Recent failures** for the same domain are always retrieved if they exist — agents must not repeat known failed approaches.
3. **Component history** — if the task targets specific components listed in the PCD's architecture section, recent task executions for those components are retrieved.
4. **Milestone context** — if the task is part of a workstream listed in `current_state.active_workstreams`, the most recent milestone summary for that workstream is included.

---

## Fractal Summarization

Over time, raw history accumulates beyond any useful size. Fractal summarization compresses old records at decreasing granularity.

```
Task Results (full detail)                    ~3KB each
  │  kept for 30 days, then summarized
  ▼
Mission Summaries (key outcomes per mission)  ~1KB each
  │  kept for 6 months, then compressed
  ▼
Milestone Summaries (major achievements)      ~500B each
  │  kept indefinitely
  ▼
Project Context Document (the living brief)   curated from all above
```

### Summarization Pipeline

The **Summarization Agent** runs periodically (daily or on-demand) and performs:

1. **Task → Mission compression**: For missions older than 30 days, individual `TaskExecution` records are summarized into a single `mission_outcome_summary` on the `MissionRecord`. The full `TaskExecution` rows are retained in the database for audit but are excluded from history queries by default.

2. **Mission → Milestone compression**: For completed workstreams or time periods, related mission summaries are compressed into `milestone_summaries`. A milestone captures: what was achieved, key decisions made, patterns established, and domain tags for future retrieval.

3. **PCD pruning**: The Summarization Agent reviews the PCD for stale entries:
   - Decisions older than 90 days with no recent references → archived to `project_decisions` table
   - Completed workstreams → moved from `active_workstreams` to milestone summary
   - Resolved known issues → removed
   - The PCD is trimmed to stay within its size cap

### Retention Policy

| Data Level | Retention | Query Access |
|------------|-----------|-------------|
| Raw task attempts | Indefinite (audit) | Not queried by default, available for debugging |
| Task executions | Indefinite (audit) | Queried for tasks < 30 days old |
| Mission outcome summaries | Indefinite | Always queryable |
| Milestone summaries | Indefinite | Always queryable |
| PCD | Current version only | Always loaded |
| PCD change history | Indefinite (audit) | Queryable for context forensics |

---

## Project Lifecycle

### Creation

A project is created explicitly by a human. At creation time:

1. A `projects` row is inserted with name, owner, description, default roster.
2. An empty `project_contexts` row is created with a seed PCD:
   ```json
   {
     "version": 1,
     "identity": { "name": "...", "purpose": "..." },
     "architecture": { "components": {}, "conventions": {} },
     "decisions": [],
     "current_state": { "active_workstreams": [], "recent_milestones": [], "known_issues": [], "next_priorities": [] },
     "guardrails": []
   }
   ```
3. A `project_members` row is created for the owner.

The PCD starts nearly empty. It is populated by agents as they execute the first missions. The first playbook run on a new project typically includes a "project discovery" mission that populates the PCD with initial architecture, conventions, and structure derived from the codebase.

### Steady State

During normal operation:
- Every mission is scoped to a project via `project_id`.
- Every agent receives the project's PCD as part of context assembly.
- Every agent returns `context_updates` which are applied to the PCD.
- The Summarization Agent runs periodically to compress old history and prune the PCD.

### Archival

When a project is archived:
- Status set to `archived`. No new missions can be created.
- PCD is frozen (no more updates).
- All history is retained for audit.
- The project can be re-activated by changing status back to `active`.

---

## Multi-Project Platform View

```
┌──────────────────────────────────────────────────────────────────┐
│                          PLATFORM                                │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │   Project A       │  │   Project B       │  │  Project C     │ │
│  │   Owner: Team     │  │   Owner: Solo     │  │  Owner: Team   │ │
│  │   Alpha           │  │   Dev             │  │  Beta          │ │
│  │                    │  │                    │  │                │ │
│  │   Roster:          │  │   Roster:          │  │  Roster:       │ │
│  │   - Planner        │  │   - Planner        │  │  - Planner     │ │
│  │   - 3 Coders       │  │   - 1 Coder        │  │  - 2 Coders    │ │
│  │   - Security       │  │   - Reviewer       │  │  - Architect   │ │
│  │   - Reviewer       │  │                    │  │  - QA          │ │
│  │                    │  │                    │  │                │ │
│  │   PCD v312         │  │   PCD v47          │  │  PCD v1,204    │ │
│  │   847 missions     │  │   23 missions      │  │  3,100 miss.   │ │
│  │   $142.30 spent    │  │   $8.50 spent      │  │  $2,847 spent  │ │
│  └──────────────────┘  └──────────────────┘  └────────────────┘ │
│                                                                  │
│  Shared: Agent registry, model rosters, platform config          │
│  Isolated: PCD, missions, history, budgets, members              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Shared across projects:**
- Agent type registry (what agents exist and their capabilities)
- Model rosters (available LLM configurations)
- Platform configuration (API keys, infrastructure settings)

**Isolated per project:**
- Project Context Document
- All missions and playbook runs
- All history (task executions, decisions, milestones)
- Budget tracking and ceilings
- Team membership and permissions

---

## Service Architecture

### New Services

| Service | Responsibility |
|---------|---------------|
| `ProjectService` | CRUD for projects and membership. Scoping enforcement. |
| `ProjectContextManager` | Read/write PCD. Apply context_updates. Version management. Cache layer. |
| `ContextAssembler` | Build context packets for agents. Layer assembly. Token budgeting. |
| `ContextCurator` | Validate context_updates. Enforce size caps. Prune stale entries. |
| `SummarizationService` | Fractal compression pipeline. Task → mission → milestone summarization. |
| `HistoryQueryService` | Structured queries over project history by domain, component, time range. |

### Integration Points

```
                         ┌───────────────┐
                         │  CLI / API     │
                         └───────┬───────┘
                                 │
                    ┌────────────┴────────────┐
                    │    PlaybookRunService    │
                    │    (adds project_id)     │
                    └────────────┬────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │     MissionService       │
                    │    (adds project_id)     │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                   │
              ▼                  ▼                   ▼
   ┌──────────────────┐ ┌──────────────┐  ┌─────────────────┐
   │ ContextAssembler │ │ MissionCtrl  │  │ PersistenceBridge│
   │                  │ │              │  │                  │
   │ Builds context   │ │ Orchestrates │  │ Stores outcomes  │
   │ packet per task  │ │ plan+dispatch│  │ + context_updates│
   └────────┬─────────┘ └──────────────┘  └────────┬────────┘
            │                                       │
            ▼                                       ▼
   ┌──────────────────┐                  ┌──────────────────┐
   │ ProjectContext    │◄────────────────│  ContextCurator   │
   │ Manager           │                 │                   │
   │                   │                 │ Validates+applies │
   │ Reads/writes PCD  │                 │ context_updates   │
   └──────────────────┘                  └──────────────────┘
```

### Dispatch Loop Changes

The dispatch loop in `dispatch.py` is modified to:

1. **Before dispatch**: Call `ContextAssembler.build()` to create the context packet for each task, including the PCD.
2. **After each task**: Extract `context_updates` from the agent's response and pass to `ContextCurator.apply()`.
3. **After all tasks**: No change — `PersistenceBridge` stores outcomes as before.

The dispatch loop remains the single point of agent execution. Context assembly and curation are injected into this existing flow, not added as parallel systems.

---

## Domain Tagging

For Layer 2 history queries to work, tasks must be tagged with the domains they touch. Domain tags are structured labels, not free text.

### Tag Sources

1. **Planning Agent** assigns initial domain tags when generating the TaskPlan. Tags are derived from the task objective and the PCD's architecture.components section.
2. **Executing Agent** can add domain tags via context_updates if it discovers the task touches domains not anticipated by the planner.
3. **File-based inference** — if the task output references specific files, domain tags can be inferred from the PCD's repo_structure mapping.

### Tag Taxonomy

Domain tags are project-specific, derived from the PCD's `architecture.components` keys plus a set of cross-cutting concerns:

**Component tags** (from PCD): `mission_control`, `planning_agent`, `dispatch`, `verification`, `context_layer`, etc.

**Cross-cutting tags** (standard): `auth`, `api`, `database`, `testing`, `deployment`, `security`, `performance`, `documentation`

Tags are not an ontology. They are flat labels used for structured filtering. A task can have multiple tags. New tags emerge naturally as the PCD's component list grows.

---

## Failure Modes and Mitigations

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Agent returns invalid context_updates | PCD corruption | ContextCurator validates all patches before applying. Invalid patches are logged and skipped, not applied. |
| PCD grows beyond size cap | Bloated agent context, increased cost | Automatic pruning triggered when size exceeds 80% of cap. Oldest decisions archived first. Alert to project owner at 90%. |
| Agent ignores PCD conventions | Inconsistent work | PCD guardrails are included in agent system prompts. Verification tiers check for convention adherence. |
| Context Assembler overloads token budget | Agent receives truncated context | Strict priority ordering: PCD first, task definition second, upstream third, history last. History is always the first to be trimmed. |
| Summarization Agent produces poor summaries | Loss of important historical context | Raw data is never deleted — only excluded from default queries. Full history always available for audit and manual review. |
| Concurrent context_updates conflict | Lost updates | Optimistic concurrency on PCD version. If version has changed since context was loaded, the update is re-applied against the latest version. Conflicts on the same path are rejected and logged. |
| Project PCD is empty (new project) | Agents have no orientation | First mission should include a "project discovery" task. Seed PCD template provides minimal structure. Agents function without PCD content — it is additive, not required for basic operation. |

---

## Implementation Sequence

This architecture is implemented incrementally. Each phase is independently valuable.

### Phase 1: Project Entity

Add the `projects` and `project_members` tables. Add `project_id` to `missions` and `playbook_runs`. Wire through CLI and API. All missions are scoped to a project.

**Deliverable:** Missions are grouped by project. CLI supports `--project` flag. No context layer yet — just organizational grouping.

### Phase 2: Project Context Document

Add `project_contexts` and `context_changes` tables. Implement `ProjectContextManager` with read/write/version operations. PCD is loaded but not yet agent-maintained — manually seeded and updated.

**Deliverable:** PCD exists and is loaded into agent context. Humans can view and edit it via CLI (`project context show`, `project context update`).

### Phase 3: Agent Contract

Modify the dispatch loop to pass PCD to agents and extract `context_updates` from responses. Implement `ContextCurator` to validate and apply updates. Agents now maintain the PCD automatically.

**Deliverable:** Every task execution contributes to collective project knowledge. PCD evolves with the project.

### Phase 4: Context Assembly

Implement `ContextAssembler` with token budgeting. Add `domain_tags` to task executions. Implement `HistoryQueryService` for structured history retrieval.

**Deliverable:** Agents receive tailored context packets with relevant history, not just the PCD.

### Phase 5: Fractal Summarization

Implement `SummarizationService` with the compression pipeline. Add `milestone_summaries` table. Implement automatic PCD pruning.

**Deliverable:** Projects can run for years without context degradation. Old history is compressed, not lost.

---

## Relationship to Existing Architecture

This architecture extends the existing BFA platform without replacing any current systems.

| Existing System | Relationship to Context Layer |
|----------------|-------------------------------|
| TaskPlan (schemas/task_plan.py) | Unchanged. Remains the DAG for a single mission. PCD is loaded alongside it, not embedded in it. |
| MissionOutcome (outcome.py) | Extended with `context_updates` field. Otherwise unchanged. |
| upstream_context (Mission model) | Unchanged. Continues to flow between playbook steps. PCD is a separate, persistent layer. |
| output_mapping (PlaybookSchema) | Unchanged. Continues to distill mission outputs for downstream steps. |
| PersistenceBridge | Extended to persist context_updates to the ContextCurator after mission completion. |
| Dispatch loop (dispatch.py) | Extended with pre-task context assembly and post-task context update hooks. Core loop unchanged. |
| Rosters | Become project-scoped. Each project can have its own default roster. |
| Playbooks | Gain `project_id` scoping. A playbook run always belongs to a project. |

No existing table is removed. No existing service is replaced. The context layer is additive — it provides new capabilities without breaking the current execution model.
