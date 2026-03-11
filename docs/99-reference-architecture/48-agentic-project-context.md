# 48 - Agentic Project Context Architecture

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-03-10*

## Changelog

- 1.0.0 (2026-03-10): Initial standard — Project entity, Project Context Document, three-layer memory model, agent contract, context assembly, fractal summarization

---

## Module Status: Required (AI-First Profile)

This module is **required** for all AI-First Platform (BFA) projects. Adopt when your project:
- Runs agentic workloads across multiple missions or playbook runs
- Requires persistent context that survives beyond a single mission lifecycle
- Operates over timescales longer than a single session (days, weeks, months, years)
- Uses ephemeral agents that must inherit accumulated project knowledge

**Dependencies**: This module requires **40-agentic-architecture.md** (orchestration patterns, agent lifecycle), **41-agentic-pydanticai.md** (implementation framework), and **47-agentic-module-organization.md** (agent layout and naming). It extends the orchestration model from 40/41 with persistent cross-mission memory.

This module builds on the dispatch and planning primitives defined in 40/41. It does not replace them — it adds a persistence layer beneath them.

---

## Purpose

This document defines the standard architecture for **persistent project context** in agentic systems — the mechanism that allows ephemeral agents to operate on long-running projects with full situational awareness.

Without this standard, every agent starts cold. It has no knowledge of prior missions, architectural decisions, established conventions, or failed approaches. Over a project's lifetime spanning thousands of missions, this produces agents that repeatedly re-discover known information, violate established patterns, and repeat failed approaches.

This standard eliminates that problem. It defines:

1. **What** persistent context contains (the Project Context Document)
2. **How** context reaches agents (Context Assembly)
3. **How** agents contribute back (the Agent Contract)
4. **How** context scales over time (Fractal Summarization)
5. **How** projects are organized (the Project entity)

---

## The Problem: Ephemeral Agents, Long-Lived Projects

An agent lives for minutes. A project lives for years.

| Timescale | Entity | Context Size |
|-----------|--------|-------------|
| Minutes | Single task execution | ~5KB (task definition + inputs) |
| Hours | Single mission (5-10 tasks) | ~50KB (plan + all task I/O) |
| Days | Playbook run (multiple missions) | ~200KB (upstream context chains) |
| Weeks | Active development sprint | ~1MB (accumulated outcomes) |
| Months | Project phase | ~5MB (decisions, patterns, failures) |
| Years | Project lifetime | ~50MB+ (full history) |

No agent can consume 50MB of history. But agent #847 on day 193 must operate with the same situational awareness as a senior engineer who has been on the project since day one.

The solution is **layered memory with active curation** — not a growing log, but a living brief that stays small while the history it summarizes grows without bound.

---

## Core Concepts

### Project

The **Project** is the top-level organizational boundary in the platform. Every mission, playbook run, context document, and history record belongs to exactly one project.

**Properties:**
- Long-lived (months to years)
- Owned by humans (individuals or teams)
- Scoped: agents operate within a single project at a time
- Isolated: one project's context never bleeds into another

**A platform hosts many concurrent projects.** Each has its own context, history, roster, and budget. Projects are independent — they share platform infrastructure (agent registry, model rosters, API keys) but nothing else.

### Project Context Document (PCD)

The **PCD** is a living, curated JSON document that captures everything an agent needs to orient itself within a project. It is the "executive brief."

**Properties:**
- Always loaded into every agent's context window (non-negotiable)
- Size-bounded (hard cap: 20KB, target: 10-15KB)
- Versioned (monotonically increasing integer)
- Agent-maintained (updated as a byproduct of normal task execution)
- Auditable (every change tracked with who, what, why)

The PCD is **not a log**. It is not appended to. Old entries are archived, stale information is pruned, and the document is actively curated to stay within its size budget.

### Context Assembly

**Context Assembly** is the process of building the complete context packet for an agent before task execution. It combines layers of context within a token budget, prioritizing the most critical information.

### Agent Contract

The **Agent Contract** is a mandatory behavioral requirement. Every agent must return structured context updates alongside its task output. This is how collective knowledge accumulates.

---

## Three-Layer Memory Model

All persistent context is organized into three layers. Each layer has different lifetime, size, retrieval strategy, and priority.

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

The PCD is loaded into every agent's context window for every task. No exceptions. No conditional loading.

#### Required Sections

Every PCD must contain these top-level sections. Implementations may add project-specific sections but must not remove or rename these.

| Section | Purpose | Example Content |
|---------|---------|----------------|
| `version` | Monotonically increasing integer | `312` |
| `last_updated` | ISO 8601 timestamp | `"2026-03-10T14:32:00Z"` |
| `last_updated_by` | Agent/human identifier | `"mission:abc/task:005"` |
| `identity` | Project name, purpose, tech stack, repo structure | What this project is |
| `architecture` | Components, interfaces, data flow, conventions | How this project is built |
| `decisions` | Recent, actively relevant architectural decisions | What was decided and why |
| `current_state` | Active workstreams, recent milestones, known issues, priorities | Where we are right now |
| `guardrails` | Hard constraints every agent must respect | What must never be violated |

#### PCD Schema

```json
{
  "version": "<integer>",
  "last_updated": "<ISO 8601>",
  "last_updated_by": "<identifier>",

  "identity": {
    "name": "<string>",
    "purpose": "<string — one sentence>",
    "tech_stack": ["<string>"],
    "repo_structure": {
      "<path>": "<purpose>"
    }
  },

  "architecture": {
    "components": {
      "<component_key>": {
        "purpose": "<string>",
        "key_files": ["<relative path>"],
        "interfaces": ["<function or class name>"]
      }
    },
    "data_flow": "<string — end-to-end flow description>",
    "conventions": {
      "<convention_key>": "<string — the rule>"
    }
  },

  "decisions": [
    {
      "id": "<string — unique, e.g. d-041>",
      "date": "<ISO 8601 date>",
      "domain": "<string — component or cross-cutting concern>",
      "decision": "<string — what was decided>",
      "rationale": "<string — why>"
    }
  ],

  "current_state": {
    "active_workstreams": ["<string>"],
    "recent_milestones": ["<string>"],
    "known_issues": ["<string>"],
    "next_priorities": ["<string>"]
  },

  "guardrails": ["<string — hard constraint>"]
}
```

#### What Belongs in the PCD

| Include | Exclude |
|---------|---------|
| Project identity, purpose, tech stack | Full mission history |
| Architecture: components, interfaces, data flow | Task-level execution details |
| Active conventions and coding patterns | Code snippets or file contents |
| Recent decisions that affect current work | Credentials, secrets, environment config |
| Current state: workstreams, blockers, priorities | Speculative or unverified information |
| Hard constraints (guardrails) | Historical decisions no longer relevant |

#### Size Management

The PCD has a hard cap of **20KB** (measured as UTF-8 encoded JSON). Target operating size is **10-15KB**.

When size exceeds 80% of cap:
1. Decisions older than 90 days with no recent references are archived to the `project_decisions` table
2. Completed workstreams are moved from `active_workstreams` to a milestone summary
3. Resolved known issues are removed

When size exceeds 90% of cap:
1. All of the above, plus alert to project owner
2. Oldest decisions are force-archived regardless of age
3. Component descriptions are truncated to purpose-only (key_files and interfaces removed)

The PCD is never allowed to exceed 100% of cap. Updates that would cause overflow are rejected until pruning creates space.

### Layer 1: Mission Context

This layer is defined by **40-agentic-architecture.md** and **41-agentic-pydanticai.md**. It consists of:

- **TaskPlan DAG**: The directed acyclic graph of tasks for the current mission
- **upstream_context**: Context passed from upstream playbook steps via output_mapping
- **from_upstream resolution**: Dynamic input resolution from completed sibling tasks
- **Task inputs**: Static inputs merged with resolved upstream values

No changes to Layer 1 are required by this standard. It handles the "what am I doing right now?" question through existing mechanisms.

### Layer 2: Project History

A queryable store of past work. **Not loaded by default.** Retrieved on demand when the Context Assembler determines a task needs historical context.

#### Retrieval Strategy: Structured Queries, Not Semantic Search

History retrieval uses structured database queries, not vector similarity search. Agents need precise, deterministic data — not fuzzy matches.

| Query Pattern | Use Case |
|---------------|----------|
| By domain tag | "What decisions were made about authentication?" |
| By component | "What was the last mission that touched this module?" |
| By failure | "What approaches failed for this objective?" |
| By time range | "What milestones were completed last month?" |
| By agent type | "What has the security agent flagged recently?" |

#### Required Data Sources

Implementations must provide these queryable data sources for Layer 2:

| Data Source | Content | Retention |
|-------------|---------|-----------|
| Task executions | Per-task results, outputs, costs, durations, domain tags | Indefinite (audit) |
| Task attempts | Retry history, failure reasons, feedback provided | Indefinite (audit) |
| Mission outcome summaries | Key outcomes per mission, compressed from task executions | Indefinite |
| Project decisions | Archived decisions from PCD, queryable by domain | Indefinite |
| Milestone summaries | Compressed narratives of completed project phases | Indefinite |

#### Domain Tagging

For structured history queries to work, task executions must carry **domain tags** — flat string labels indicating which areas of the project a task touches.

**Tag sources** (in priority order):
1. Planning Agent assigns initial tags when generating the TaskPlan, derived from the task objective and PCD components
2. Executing Agent adds tags via context_updates if it discovers the task touches unanticipated domains
3. File-based inference from the PCD's `repo_structure` mapping

**Tag taxonomy** is project-specific, not global. Tags emerge from the PCD's `architecture.components` keys plus standard cross-cutting concerns: `auth`, `api`, `database`, `testing`, `deployment`, `security`, `performance`, `documentation`.

Tags are flat labels, not a hierarchy. A task may have multiple tags.

---

## Agent Contract

Every agent in the system must follow this protocol. This is enforced by the dispatch loop, not by convention.

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

### Context Updates

After completing a task, agents return structured patches to the PCD. Updates use a JSON Patch-inspired format with mandatory `reason` fields.

```json
{
  "context_updates": [
    {
      "op": "add",
      "path": "architecture.components.new_component",
      "value": { "purpose": "...", "key_files": [...] },
      "reason": "Implemented new component during this task"
    },
    {
      "op": "replace",
      "path": "current_state.known_issues",
      "value": ["updated issue list"],
      "reason": "Previous issue resolved by this task"
    },
    {
      "op": "remove",
      "path": "current_state.active_workstreams.0",
      "reason": "Workstream completed"
    }
  ]
}
```

**Supported operations:**

| Operation | Semantics |
|-----------|-----------|
| `add` | Add a new key or append to an array (use `/-` suffix for array append) |
| `replace` | Replace the value at an existing path |
| `remove` | Remove a key or array element at path |

**Every operation requires a `reason` field.** The reason is stored in the `context_changes` audit table and is used for context forensics.

### Validation Rules

The Context Curator validates all proposed updates before applying:

| Rule | Behavior on Violation |
|------|----------------------|
| Path must exist for `replace` and `remove` | Update rejected, logged |
| Value must differ for `replace` | Update rejected (no-op) |
| Size cap not exceeded after applying | Update queued, pruning triggered |
| System fields (`version`, `last_updated`, `last_updated_by`) not modified | Update rejected |
| Guardrails are append-only for agents | `remove` on guardrails rejected; only human project owners can remove guardrails |

Invalid updates are logged and skipped. They do not cause task failure. An agent producing invalid context updates is not penalized — the task output is still accepted.

### Context Update Concurrency

PCD uses **optimistic concurrency control** on the `version` field.

1. Agent receives PCD at version N as part of context assembly
2. Agent completes task, returns context_updates
3. Context Curator checks current PCD version
4. If version is still N: apply updates, increment to N+1
5. If version has changed (another task updated it): re-apply updates against latest version. If the same path was modified by both updates, the later update is rejected and logged as a conflict

This is safe because:
- Tasks within a mission execute in topological order (DAG layers)
- Tasks in the same DAG layer execute concurrently but typically touch different domains
- Cross-mission concurrency is rare (playbook steps are sequential)

---

## Context Assembly

The **Context Assembler** builds the context packet for each agent before task execution. It operates within a configurable token budget.

### Assembly Process

```
Input:  task_definition, project_id, token_budget

Step 1: Load PCD (Layer 0)                          ~4K tokens
        Always included. Non-negotiable.

Step 2: Load task definition + inputs (Layer 1)      ~1-2K tokens
        From TaskPlan: objective, inputs, verification spec.

Step 3: Resolve upstream outputs (Layer 1)           ~1-4K tokens
        From completed sibling tasks via from_upstream refs.

Step 4: Query relevant history (Layer 2)             ~1-4K tokens
        Structured queries based on task domain_tags.
        Recent decisions in the task's domain.
        Failed approaches for similar objectives.
        Only if token budget allows.

Step 5: Trim to budget
        If total exceeds budget, trim in reverse priority:
        Layer 2 first, then Layer 1 upstream, never Layer 0.

Output: context_packet (dict)
```

### Priority Order

When the token budget is constrained, layers are trimmed in this order (last trimmed first):

| Priority | Layer | Trim Strategy |
|----------|-------|---------------|
| 1 (never trimmed) | Layer 0 — PCD | Never trimmed. If PCD alone exceeds budget, the budget is wrong. |
| 2 (high) | Layer 1 — Task definition | Never trimmed. Task definition is the work order. |
| 3 (high) | Layer 1 — Upstream outputs | Summarized if over budget. Full outputs replaced with key-value summaries. |
| 4 (normal) | Layer 2 — History | Reduced result count. Oldest entries dropped first. Removed entirely if budget requires. |

### History Retrieval Heuristics

The Context Assembler uses these signals to determine what history to retrieve:

1. **Domain tags** on the task definition drive queries against `project_decisions` and `task_executions`
2. **Recent failures** for the same domain are always retrieved — agents must not repeat known failed approaches
3. **Component references** — if the task targets components in the PCD's architecture section, recent executions for those components are retrieved
4. **Active workstream** — if the task belongs to a workstream in `current_state.active_workstreams`, the most recent milestone summary for that workstream is included

---

## Fractal Summarization

Over time, raw history grows beyond usable size. Fractal summarization compresses old records at decreasing granularity while preserving key information.

```
Task Results (full detail, ~3KB each)
  │  summarized after 30 days
  ▼
Mission Summaries (key outcomes, ~1KB each)
  │  compressed after 6 months
  ▼
Milestone Summaries (major achievements, ~500B each)
  │  curated into
  ▼
Project Context Document (the living brief, ~15KB total)
```

Each level compresses approximately 5-10x from the level below.

### Compression Pipeline

| Stage | Input | Output | Trigger | Retention |
|-------|-------|--------|---------|-----------|
| Task → Mission | Individual TaskExecution records | Single mission_outcome_summary on MissionRecord | Mission older than 30 days | Raw records retained for audit, excluded from default queries |
| Mission → Milestone | Related mission summaries | milestone_summary record | Workstream completed or time period closed | Mission summaries retained, milestone linked to source missions |
| Milestone → PCD | Milestone summaries | Updates to PCD current_state and decisions | Ongoing, part of PCD curation | Milestones retained indefinitely |
| PCD Pruning | PCD content | Archived decisions, removed stale entries | PCD exceeds 80% size cap | Archived items moved to project_decisions table |

### Summarization Agent

The Summarization Agent is a horizontal agent (see 47-agentic-module-organization.md) that runs periodically or on-demand. It uses a cost-efficient model (Haiku-class) for compression tasks.

**Responsibilities:**
- Compress task executions older than 30 days into mission summaries
- Compress completed workstreams into milestone summaries
- Prune PCD: archive old decisions, remove resolved issues, trim completed workstreams
- Maintain size invariants on the PCD

**The Summarization Agent never deletes raw data.** It only marks records as "summarized" and excludes them from default history queries. Full detail is always available for audit and debugging.

---

## Data Model

### Required Tables

Implementations must provide these tables. Column types shown are logical — adapt to your database engine.

#### projects

The top-level organizational boundary.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | UUID | PK | Unique identifier |
| name | VARCHAR(200) | NOT NULL, UNIQUE | Human-readable project name |
| description | TEXT | NOT NULL | Project purpose |
| status | ENUM(active, paused, archived) | NOT NULL, DEFAULT active | Lifecycle state |
| owner_id | VARCHAR(200) | NOT NULL | Primary human owner identifier |
| team_id | VARCHAR(200) | NULLABLE | Optional team identifier |
| default_roster | VARCHAR(100) | NOT NULL, DEFAULT 'default' | Default agent roster for this project |
| budget_ceiling_usd | FLOAT | NULLABLE | Project-level spend cap |
| repo_url | TEXT | NULLABLE | Source repository URL |
| repo_root | TEXT | NULLABLE | Local filesystem root |
| created_at | TIMESTAMP | NOT NULL | Creation time |
| updated_at | TIMESTAMP | NOT NULL | Last modification time |

#### project_contexts

The PCD store. One row per project.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | UUID | PK | Unique identifier |
| project_id | UUID | FK → projects, UNIQUE, NOT NULL | Owning project |
| context_data | JSON/JSONB | NOT NULL | The PCD content |
| version | INTEGER | NOT NULL, DEFAULT 1 | Optimistic concurrency version |
| size_characters | INTEGER | NOT NULL | Current PCD size in characters |
| size_tokens | INTEGER | NOT NULL | Estimated token count |
| created_at | TIMESTAMP | NOT NULL | Creation time |
| updated_at | TIMESTAMP | NOT NULL | Last modification time |

#### context_changes

Audit trail of every PCD mutation.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | UUID | PK | Unique identifier |
| context_id | UUID | FK → project_contexts, NOT NULL, IDX | Which PCD |
| version | INTEGER | NOT NULL | PCD version after this change |
| change_type | ENUM(add, replace, remove, prune, archive) | NOT NULL | Type of mutation |
| path | VARCHAR(500) | NOT NULL | JSON path (dot notation) |
| old_value | JSON | NULLABLE | Previous value |
| new_value | JSON | NULLABLE | New value |
| agent_id | VARCHAR(200) | NULLABLE | Which agent made the change |
| mission_id | VARCHAR(36) | NULLABLE | During which mission |
| task_id | VARCHAR(100) | NULLABLE | During which task |
| reason | TEXT | NOT NULL | Why the change was made |
| created_at | TIMESTAMP | NOT NULL, IDX | When the change occurred |

#### project_members

Human membership and roles.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | UUID | PK | Unique identifier |
| project_id | UUID | FK → projects, NOT NULL, IDX | Which project |
| user_id | VARCHAR(200) | NOT NULL, IDX | Human user identifier |
| role | ENUM(owner, maintainer, viewer) | NOT NULL | Permission level |
| created_at | TIMESTAMP | NOT NULL | Membership start |
| updated_at | TIMESTAMP | NOT NULL | Last role change |

**Unique constraint** on (project_id, user_id).

#### project_decisions

Archived decisions from PCD pruning, queryable for Layer 2 history.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | UUID | PK | Unique identifier |
| project_id | UUID | FK → projects, NOT NULL, IDX | Which project |
| decision_id | VARCHAR(50) | NOT NULL | Original decision ID from PCD (e.g., "d-041") |
| domain | VARCHAR(100) | NOT NULL, IDX | Domain tag for structured queries |
| decision | TEXT | NOT NULL | What was decided |
| rationale | TEXT | NOT NULL | Why |
| made_by | VARCHAR(200) | NOT NULL | Agent or human who made the decision |
| mission_id | VARCHAR(36) | NULLABLE | Mission during which decision was made |
| status | ENUM(active, superseded, reversed) | NOT NULL, DEFAULT active | Decision lifecycle |
| superseded_by | VARCHAR(50) | NULLABLE | decision_id of replacement |
| created_at | TIMESTAMP | NOT NULL, IDX | When decided |
| updated_at | TIMESTAMP | NOT NULL | Last status change |

#### milestone_summaries

Compressed summaries of completed project phases.

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | UUID | PK | Unique identifier |
| project_id | UUID | FK → projects, NOT NULL, IDX | Which project |
| title | VARCHAR(300) | NOT NULL | Milestone name |
| summary | TEXT | NOT NULL | Compressed narrative |
| mission_ids | JSON | NOT NULL | Array of mission IDs included |
| key_outcomes | JSON | NOT NULL | Structured outcomes |
| domain_tags | JSON | NOT NULL, IDX | Array of domain tags for retrieval |
| period_start | TIMESTAMP | NOT NULL | Start of summarized period |
| period_end | TIMESTAMP | NOT NULL | End of summarized period |
| created_at | TIMESTAMP | NOT NULL | When summary was created |

### Required Modifications to Existing Tables

| Table | Change | Purpose |
|-------|--------|---------|
| missions | Add `project_id` (FK → projects, NOT NULL, IDX) | Scope missions to projects |
| playbook_runs | Add `project_id` (FK → projects, NOT NULL, IDX) | Scope playbook runs to projects |
| mission_records | Add `project_id` (FK → projects, IDX) | Enable project-scoped history queries |
| task_executions | Add `domain_tags` (JSON array, IDX) | Enable structured history queries by domain |

---

## Service Architecture

### Required Services

| Service | Responsibility | Dependencies |
|---------|---------------|-------------|
| ProjectService | CRUD for projects and membership. Project-scoping enforcement on all queries. | Database layer |
| ProjectContextManager | Read, write, and version the PCD. In-memory cache with TTL. | ProjectService, database layer |
| ContextAssembler | Build context packets for agents. Layer assembly with token budgeting. | ProjectContextManager, HistoryQueryService |
| ContextCurator | Validate and apply context_updates from agents. Enforce size caps. Trigger pruning. | ProjectContextManager |
| SummarizationService | Fractal compression pipeline. Task → mission → milestone summarization. PCD pruning. | ProjectContextManager, HistoryQueryService |
| HistoryQueryService | Structured queries over project history by domain, component, time range, failure status. | Database layer |

### Integration with Dispatch Loop

The dispatch loop (defined in 40/41) is extended with two hooks:

```
┌────────────────────────────────────────────────────────┐
│                    DISPATCH LOOP                        │
│                                                        │
│  FOR EACH task in topological_order(TaskPlan):         │
│                                                        │
│    1. context_packet = ContextAssembler.build(          │
│         task, project_id, token_budget                  │  ← NEW
│       )                                                │
│                                                        │
│    2. result = agent.execute(                           │
│         task, context_packet                            │  ← MODIFIED (was task + inputs only)
│       )                                                │
│                                                        │
│    3. ContextCurator.apply(                             │
│         project_id, result.context_updates              │  ← NEW
│       )                                                │
│                                                        │
│    4. completed_outputs[task.id] = result.output        │  (existing)
│                                                        │
└────────────────────────────────────────────────────────┘
```

Steps 1 and 3 are the only additions. The core dispatch loop — topological sort, agent execution, output collection — remains unchanged.

---

## Project Scoping

### Isolation Guarantees

| Resource | Scoping | Enforcement |
|----------|---------|-------------|
| PCD | One per project, never shared | FK constraint + service layer |
| Missions | Belong to exactly one project | `project_id` NOT NULL FK |
| Playbook runs | Belong to exactly one project | `project_id` NOT NULL FK |
| History queries | Always filtered by project_id | HistoryQueryService enforces |
| Budgets | Per-project ceiling | ProjectService checks before mission creation |
| Rosters | Project has a default roster | Agents instantiated with project's roster |
| Members | Per-project membership | ProjectMember table |

### Shared Resources

These resources are platform-wide, not project-scoped:

| Resource | Rationale |
|----------|-----------|
| Agent type registry | Agent implementations are reusable across projects |
| Model rosters | LLM configurations are infrastructure, not project data |
| Platform configuration | API keys, infrastructure settings |
| User accounts | A human can be a member of multiple projects |

### Multi-Project Platform View

```
┌──────────────────────────────────────────────────────────────────┐
│                          PLATFORM                                │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │   Project A       │  │   Project B       │  │  Project C     │ │
│  │   Owner: Team α   │  │   Owner: Solo Dev │  │  Owner: Team β │ │
│  │                    │  │                    │  │                │ │
│  │   Roster: full     │  │   Roster: minimal  │  │  Roster: full  │ │
│  │   PCD v312         │  │   PCD v47          │  │  PCD v1,204    │ │
│  │   847 missions     │  │   23 missions      │  │  3,100 miss.   │ │
│  │   $142.30 spent    │  │   $8.50 spent      │  │  $2,847 spent  │ │
│  └──────────────────┘  └──────────────────┘  └────────────────┘ │
│                                                                  │
│  Shared: agent registry, model rosters, platform config, users   │
│  Isolated: PCD, missions, history, budgets, members              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Project Lifecycle

### Creation

When a project is created:

1. Insert `projects` row with name, owner, description, default roster
2. Create `project_contexts` row with seed PCD:
   ```json
   {
     "version": 1,
     "last_updated": "<now>",
     "last_updated_by": "system:project_creation",
     "identity": { "name": "<project_name>", "purpose": "<description>" },
     "architecture": { "components": {}, "data_flow": "", "conventions": {} },
     "decisions": [],
     "current_state": {
       "active_workstreams": [],
       "recent_milestones": [],
       "known_issues": [],
       "next_priorities": []
     },
     "guardrails": []
   }
   ```
3. Create `project_members` row for the owner with role `owner`

The PCD starts nearly empty. It is populated by agents during the first missions. The first playbook run on a new project should include a "project discovery" mission that populates the PCD with architecture, conventions, and structure derived from the codebase.

### Steady State

During normal operation:
- Every mission is scoped to a project via `project_id`
- Every agent receives the project's PCD as part of context assembly
- Every agent returns `context_updates` which are validated and applied to the PCD
- The Summarization Agent runs periodically to compress old history and prune the PCD

### Pausing

A paused project:
- Cannot create new missions or playbook runs
- PCD is frozen (no updates accepted)
- History remains queryable
- Can be resumed by setting status back to `active`

### Archival

An archived project:
- Cannot create new missions or playbook runs
- PCD is frozen
- All history retained for audit
- Can be re-activated by an owner

---

## Failure Modes and Mitigations

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Agent returns invalid context_updates | PCD could be corrupted | ContextCurator validates all patches before applying. Invalid patches are logged and skipped. Task output is still accepted. |
| PCD grows beyond size cap | Bloated agent context, increased cost | Automatic pruning at 80% cap. Alert at 90%. Hard rejection at 100%. |
| Agent ignores PCD conventions | Inconsistent work output | PCD guardrails included in agent system prompts. Verification tiers check convention adherence. |
| Context Assembler exceeds token budget | Agent receives truncated context | Strict priority ordering. Layer 2 trimmed first, then Layer 1 upstream. Layer 0 never trimmed. |
| Summarization produces poor summaries | Loss of important historical context | Raw data never deleted. Only excluded from default queries. Full detail available for audit. |
| Concurrent context_updates conflict | Lost updates | Optimistic concurrency on PCD version. Same-path conflicts rejected and logged. |
| Empty PCD (new project) | Agents have no orientation | Seed PCD provides minimal structure. First mission populates it. Agents function without PCD content — it is additive. |
| Project owner unavailable | Stale guardrails, unreviewed alerts | Maintainer role has escalated privileges. Platform alerts on projects with no owner activity beyond threshold. |

---

## Implementation Sequence

This architecture is implemented incrementally. Each phase is independently valuable and deployable.

### Phase 1: Project Entity

Add `projects` and `project_members` tables. Add `project_id` FK to `missions` and `playbook_runs`. Wire through CLI and API.

**Deliverable:** Missions are grouped by project. CLI supports `--project` flag.

**Test:** Can a mission be created, scoped to a project, and queried by project?

### Phase 2: Project Context Document

Add `project_contexts` and `context_changes` tables. Implement `ProjectContextManager`. PCD is loaded but not yet agent-maintained — manually seeded and updated via CLI.

**Deliverable:** PCD exists and can be viewed/edited. Agents receive it in context.

**Test:** Can a human update the PCD via CLI and see it reflected in the next agent's context?

### Phase 3: Agent Contract

Modify dispatch loop to extract `context_updates` from agent responses. Implement `ContextCurator` with validation rules. Agents now maintain the PCD automatically.

**Deliverable:** Every task execution contributes to collective project knowledge.

**Test:** Does the PCD version increment after a mission? Do context_changes records exist?

### Phase 4: Context Assembly

Implement `ContextAssembler` with token budgeting. Add `domain_tags` to task executions. Implement `HistoryQueryService`.

**Deliverable:** Agents receive tailored context packets with relevant history.

**Test:** Does an agent working on auth receive auth-related decisions from past missions?

### Phase 5: Fractal Summarization

Implement `SummarizationService`. Add `milestone_summaries` and `project_decisions` tables. Implement automatic PCD pruning.

**Deliverable:** Projects can run for years without context degradation.

**Test:** After running the summarizer, is the PCD within size cap? Are old task executions excluded from default queries but still accessible for audit?

---

## Relationship to Other Standards

| Standard | Relationship |
|----------|-------------|
| 40-agentic-architecture.md | This standard extends the orchestration model with persistent memory. Layer 1 (mission context) is defined there. |
| 41-agentic-pydanticai.md | Implementation framework. Context assembly and agent contract integrate with PydanticAI's RunContext and output_type patterns. |
| 47-agentic-module-organization.md | The Summarization Agent and Context Curator follow the horizontal agent layout defined there. |
| 46-agentic-event-session-architecture.md | Sessions and streaming are orthogonal. A session may span multiple missions within a project, but session state and project context are separate concerns. |
| 03-core-backend-architecture.md | New services follow the standard service layer pattern: service → repository → model. |
| 20-opt-data-layer.md | New tables follow SQLAlchemy 2.0 mapped_column style. Migrations via Alembic. |

---

## Compliance

All AI-First Platform (BFA) projects must implement this standard when operating agentic workloads that span multiple missions.

Projects that only run single, ad-hoc missions without playbook orchestration may defer adoption until multi-mission workflows are introduced.

Deviations from the PCD schema, agent contract, or context assembly priority order require documented justification and architecture team approval.
