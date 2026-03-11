# Platform Flow: End-to-End Execution Model

*How work flows through the BFA agentic platform — from project creation to task execution and back.*

---

## Overview

The platform executes work through a five-layer chain:

```
Project → Playbook → Mission → Mission Control → Agents
```

Each layer has a clear responsibility, a distinct identity, and well-defined boundaries. Work flows **down** through planning and dispatch. Results flow **back up** through persistence, output extraction, and context updates.

---

## The Full Flow

```
Project (id: UUID)                          ← Owner of everything
│
├── Session (id: UUID, project_id)          ← Tracks cost, conversation history
│
├── PlaybookRun (id: UUID, project_id)      ← One execution of a playbook template
│   ├── playbook_name: "ai-news-digest"     ← Which template
│   ├── version: "1.0.0"                    ← Frozen at creation
│   │
│   └── Step "fetch-news"                   ← Playbook-authored, static
│       │
│       └── Mission (id: UUID, project_id, playbook_run_id, step_id)
│           ├── session_id: UUID            ← Inherits from playbook run
│           ├── objective: "Fetch today's AI news from 5 sources"
│           ├── roster_ref: "default"
│           ├── cost_ceiling_usd: 2.0
│           ├── upstream_context: {from prior steps}
│           │
│           └── handle_mission()
│               │
│               ├── Planning Agent → TaskPlan
│               │   ├── mission_id: "mission-{UUID}"
│               │   └── tasks:
│               │       ├── task_id: "scrape-arxiv"      ← LLM-assigned, local
│               │       ├── task_id: "scrape-hackernews"  ← LLM-assigned, local
│               │       └── task_id: "merge-results"      ← LLM-assigned, local
│               │
│               └── dispatch()
│                   │
│                   └── For each task (topological order, parallel within layer):
│                       │
│                       │  execution_id = uuid4()   ← Assigned HERE by code
│                       │
│                       ├── _execute_with_retry()
│                       │   ├── attempt 0 → agent.run()
│                       │   ├── verify_task() (3-tier verification)
│                       │   ├── attempt 1 (if needed) → agent.run() with feedback
│                       │   └── ...up to retry_budget
│                       │
│                       └── TaskResult
│                           ├── task_id: "scrape-arxiv"       ← LLM label
│                           ├── execution_id: UUID             ← Correlation ID
│                           ├── agent_name: "web.scraper.agent"
│                           ├── status: SUCCESS
│                           ├── output_reference: {...}
│                           └── context_updates: [...]         ← PCD patches
│
│           ← persist_mission_results()
│               ├── MissionRecord (id: UUID, project_id, session_id)
│               ├── TaskExecution (id: UUID, execution_id, mission_record_id, task_id)
│               │   └── TaskAttempt (id: UUID, task_execution_id, attempt_number)
│               └── MissionDecision (id: UUID, mission_record_id)
│
│           ← extract_outputs(output_mapping)
│               └── {"news_items": [...], "source_count": 5}
│                   └── feeds next step's upstream_context
│
└── PCD (project_id)                         ← Living knowledge brief
    ├── Updated after each mission via context_updates
    └── Loaded into every agent's context window
```

---

## Layer-by-Layer Breakdown

### Layer 1: Project

The **organizational boundary**. Everything belongs to a project — sessions, playbook runs, missions, context, history. Projects are long-lived (months to years), owned by humans, and scoped so agents operate within a single project at a time.

```
Project
├── id: UUID                    ← Primary identity
├── name: "my-saas-platform"    ← Human-readable, unique
├── owner_id: "user:alice"      ← Human owner
├── default_roster: "default"   ← Which agents to use
├── budget_ceiling_usd: 100.0   ← Spend cap
└── status: active | paused | archived
```

**Key files:** `modules/backend/models/project.py`, `modules/backend/services/project.py`

### Layer 2: Playbook

A **template** defining a sequence of steps. Written in YAML by humans. Each step declares a capability (e.g., `web.scraper`), inputs, outputs, dependencies, and cost constraints. Steps form a DAG — independent steps run in parallel.

```yaml
# config/playbooks/ai-news-digest.yaml
playbook_name: ai-news-digest
version: "1.0.0"
steps:
  - id: fetch-news
    capability: web.scraper
    description: "Fetch today's AI news from 5 sources"
    cost_ceiling_usd: 2.0
    input:
      sources: ["arxiv", "hackernews", "techcrunch", "reddit", "twitter"]
    depends_on: []

  - id: summarize
    capability: content.summarizer
    description: "Create executive summary"
    input:
      articles: "@context.news_items"    ← References output from prior step
    depends_on: [fetch-news]
```

A **PlaybookRun** is one execution of a playbook template. It freezes the version at creation time and tracks overall progress.

**Key files:** `modules/backend/services/playbook.py`, `modules/backend/services/playbook_run.py`

### Layer 3: Mission

A **single unit of orchestrated work** — one playbook step becomes one mission. The mission carries the objective, the agent roster to use, cost constraints, and upstream context from prior steps.

```
Mission
├── id: UUID                        ← DB identity
├── project_id: UUID                ← Scoped to project
├── playbook_run_id: UUID           ← Which run spawned this
├── playbook_step_id: "fetch-news"  ← Which step
├── objective: "Fetch today's..."   ← What to accomplish
├── roster_ref: "default"           ← Which agents
├── cost_ceiling_usd: 2.0          ← Budget
├── upstream_context: {...}         ← Data from prior missions
├── status: PENDING → RUNNING → COMPLETED | FAILED | CANCELLED
└── mission_outcome: {...}          ← Result after execution
```

Missions can also be created **ad-hoc** (not from a playbook) via `create_adhoc_mission()`.

**State machine:**
```
PENDING → RUNNING → COMPLETED
                  → FAILED
                  → CANCELLED
```

**Key files:** `modules/backend/models/mission.py`, `modules/backend/services/mission.py`

### Layer 4: Mission Control

The **orchestration brain**. Takes a mission's objective and breaks it into executable tasks via the Planning Agent, then dispatches tasks to specialist agents.

```
handle_mission(mission)
│
├── 1. Load Roster                      ← Which agents are available
│      roster = load_roster(roster_ref)
│
├── 2. Planning Agent                   ← LLM generates the plan
│      task_plan = planning_agent.run(objective, roster)
│      └── TaskPlan
│          ├── tasks: [TaskDefinition, ...]
│          ├── estimated_cost_usd: 1.50
│          └── execution_hints: {critical_path: [...]}
│
├── 3. Topological Sort                 ← Deterministic ordering
│      layers = topological_sort(task_plan)
│      └── [[task_a, task_b], [task_c]]  ← Parallel within layers
│
├── 4. Dispatch Loop                    ← Execute tasks
│      for layer in layers:
│          gather(execute_task(t) for t in layer)  ← Parallel
│
└── 5. Build MissionOutcome             ← Aggregate results
       └── MissionOutcome
           ├── status: SUCCESS | PARTIAL | FAILED
           ├── task_results: [TaskResult, ...]
           ├── total_cost_usd: 1.23
           └── summary: "Fetched 47 articles from 5 sources"
```

**Key files:** `modules/backend/agents/mission_control/mission_control.py`, `modules/backend/agents/mission_control/dispatch.py`

### Layer 5: Agent Execution

Individual **specialist agents** execute tasks. Each agent is a PydanticAI agent with a YAML config, system prompt, and defined interface (input/output schema).

```
_execute_with_retry(task, roster_entry, execute_agent_fn)
│
├── execution_id = uuid4()            ← Globally unique correlation ID
│
├── Attempt 0:
│   ├── agent.run(instructions, inputs)
│   ├── verify_task()                  ← 3-tier verification
│   │   ├── Tier 1: Schema validation (required fields present?)
│   │   ├── Tier 2: Deterministic checks (custom rules)
│   │   └── Tier 3: AI evaluation (optional, for complex tasks)
│   └── Pass? → TaskResult(status=SUCCESS)
│
├── Attempt 1 (on failure):
│   ├── Enrich instructions with feedback from prior failure
│   ├── agent.run(enriched_instructions, inputs)
│   └── verify_task() again
│
└── Exhausted retries? → TaskResult(status=FAILED)
```

**Key files:** `modules/backend/agents/mission_control/helpers.py`, agent configs in `config/agents/`

---

## Identity Model

Five layers of identity, each with a distinct purpose:

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer   ID              Assigned By          Scope              │
├─────────────────────────────────────────────────────────────────┤
│ 1       project_id      User (CLI/API)       Cross-session     │
│ 2       step.id         YAML author          Within playbook   │
│ 3       mission.id      Database (UUID)      Per execution     │
│ 4       task_id         Planning Agent (LLM) Within TaskPlan   │
│ 5       execution_id    Dispatch loop (code) Global            │
└─────────────────────────────────────────────────────────────────┘
```

**Why two task-level IDs?**

- `task_id` (layer 4) is assigned by the Planning Agent (LLM). It's a human-readable label like `"scrape-arxiv"` used for DAG dependencies within a single TaskPlan. It is **not stable** — the LLM assigns fresh IDs each run.

- `execution_id` (layer 5) is assigned by deterministic code at dispatch time. It's a UUID that uniquely identifies one execution of one task across the entire platform. Use this for monitoring dashboards, log correlation, tracing, and cross-project queries.

---

## Data Flow: Down and Back Up

### Downward: Planning & Dispatch

```
Playbook YAML
  → PlaybookService.generate_mission_briefs()
    → MissionService.create_mission_from_step()
      → MissionControl.handle_mission()
        → PlanningAgent.run() → TaskPlan
          → dispatch() → execute tasks in topological order
```

### Upward: Results & Context

```
Agent returns output
  → verify_task() (3-tier)
    → TaskResult (with execution_id)
      → persist_mission_results()
        → MissionRecord + TaskExecution + TaskAttempt (DB)
      → context_updates → ContextCurator → PCD (if project-scoped)
  → extract_outputs(output_mapping)
    → upstream_context for next step
      → next Mission in PlaybookRun
```

### Cross-Step Data Flow

Playbook steps pass data via `upstream_context` and `output_mapping`:

```
Step A completes
  → extract_outputs() pulls specific fields from MissionOutcome
    → {"news_items": [...], "source_count": 5}

Step B starts
  → resolve_upstream_context() merges prior outputs
    → step.input references @context.news_items
      → resolved to actual data from Step A
```

---

## Persistence Model

Every execution is fully recorded for audit, debugging, and history queries:

```
MissionRecord                          ← One per mission execution
├── id: UUID
├── project_id: UUID
├── session_id: UUID
├── task_plan_json: {full TaskPlan}    ← What the LLM planned
├── outcome_json: {MissionOutcome}     ← What actually happened
│
├── TaskExecution                      ← One per task
│   ├── id: UUID
│   ├── execution_id: UUID             ← Global correlation ID
│   ├── task_id: "scrape-arxiv"        ← LLM-assigned label
│   ├── agent_name: "web.scraper.agent"
│   ├── status: success | failed | timeout
│   ├── cost_usd: 0.03
│   │
│   └── TaskAttempt                    ← One per retry attempt
│       ├── attempt_number: 0
│       ├── input_data: {...}
│       ├── output_data: {...}
│       └── verification_result: {...}
│
└── MissionDecision                    ← Audit trail for decisions
    ├── decision_type: "plan_approved"
    └── rationale: "..."
```

---

## Verification Pipeline

Every task output goes through up to three tiers of verification:

```
Agent Output
│
├── Tier 1: Structural Validation
│   ├── Required output fields present?
│   ├── Schema matches roster interface?
│   └── FAIL → retry with feedback
│
├── Tier 2: Deterministic Checks
│   ├── Custom validation rules (e.g., "confidence > 0.5")
│   └── FAIL → retry with feedback
│
└── Tier 3: AI Evaluation (optional)
    ├── LLM judges output quality
    └── FAIL → retry with feedback
```

---

## Cost Control

Budget enforcement at every level:

```
Project.budget_ceiling_usd          ← Total project spend cap
  └── Mission.cost_ceiling_usd      ← Per-mission budget
        └── dispatch() tracks cumulative cost
              └── Cancels remaining tasks if budget exceeded
                    └── RosterConstraints.cost_ceiling_usd  ← Per-agent limit
```

---

## Ad-Hoc Missions

Not everything comes from a playbook. Missions can be created directly:

```
MissionService.create_adhoc_mission(
    objective="Analyze this PR for security issues",
    triggered_by="user:alice",
    session_id=session.id,
    roster_ref="security",
    cost_ceiling_usd=5.0,
)
```

Ad-hoc missions skip the playbook layer entirely — no PlaybookRun, no step dependencies, no output_mapping. They go straight to Mission Control.

---

## Key Files

| Concern | File |
|---------|------|
| Playbook loading & resolution | `modules/backend/services/playbook.py` |
| Playbook run orchestration | `modules/backend/services/playbook_run.py` |
| Mission lifecycle | `modules/backend/services/mission.py` |
| Mission Control orchestration | `modules/backend/agents/mission_control/mission_control.py` |
| Dispatch loop (topo sort, parallel exec) | `modules/backend/agents/mission_control/dispatch.py` |
| Agent executor construction | `modules/backend/agents/mission_control/helpers.py` |
| TaskPlan schema | `modules/backend/schemas/task_plan.py` |
| TaskResult / MissionOutcome | `modules/backend/agents/mission_control/outcome.py` |
| Roster (agent registry) | `modules/backend/agents/mission_control/roster.py` |
| Persistence bridge | `modules/backend/agents/mission_control/persistence_bridge.py` |
| DB models (Mission, PlaybookRun) | `modules/backend/models/mission.py` |
| DB models (MissionRecord, TaskExecution) | `modules/backend/models/mission_record.py` |
| Project entity (Plan 18) | `modules/backend/models/project.py` |
| PCD (Plan 18) | `modules/backend/models/project_context.py` |
