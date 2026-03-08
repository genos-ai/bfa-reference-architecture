# 40 - Agentic AI Architecture (Optional Module)

*Version: 2.1.0*
*Author: Architecture Team*
*Created: 2026-02-18*

## Changelog

- 2.1.0 (2026-02-24): Added channel adapters to architecture diagram, added channel/session_type/tool_access_level to AgentTask primitive, updated orchestrator responsibilities to reference gateway (44-multi-channel-gateway.md)
- 2.0.0 (2026-02-18): Split into conceptual architecture (this document) and implementation guide (41-agentic-pydanticai.md); this document is now framework-agnostic
- 1.2.0 (2026-02-18): Expanded to 5 phases (Execute, Plan, Remember, Learn, Autonomy); added orchestrator evolution diagrams, tiered delegation pattern (Thinker/Specialist/Worker), agent-as-tool mechanism
- 1.1.0 (2026-02-18): Added orchestration patterns section (Options A-D) with rationale for hybrid approach
- 1.0.0 (2026-02-18): Initial agentic AI architecture standard

---

## Module Status: Optional

This module is **optional**. Adopt when your project:
- Implements autonomous AI agents that reason and act
- Requires multi-step AI workflows with tool use
- Needs orchestrated collaboration between multiple AI agents
- Requires persistent agent memory across sessions

**Dependencies**: This module requires **24-llm-integration.md** and **21-event-architecture.md**. It builds on top of their standards rather than replacing them.

For simple LLM integrations (single-call summarization, classification, extraction), use 24-llm-integration.md alone. Adopt this module when agents need to reason, plan, use tools, and maintain state.

**This document is the conceptual architecture** — framework-agnostic principles, patterns, phases, and data models that remain valid regardless of which agent framework is used. For the concrete implementation using PydanticAI, see **[41-agentic-pydanticai.md](41-agentic-pydanticai.md)**.

---

## Purpose

This document defines the architecture for agentic AI systems — software where AI agents autonomously reason about tasks, use tools, collaborate with other agents, and learn from outcomes. It covers the skeleton (what to build now) and the expansion path (what to build later), ensuring early decisions do not block future capabilities.

The architecture follows a phased approach, progressing from simple task routing (Option A) through collaborative teams (Option B) toward persistent, self-improving, autonomous agents (Option C). See "Orchestration Patterns" below for detailed descriptions of each option.

| Phase | Option | Pattern | Capability |
|-------|--------|---------|------------|
| **Phase 1: Execute** | A | Orchestrator + Agent Pool | Single agent executes tasks, tool use, full audit trail |
| **Phase 2: Plan** | A → B | Multi-step Plans | Orchestrator chains agents, shared context within plans |
| **Phase 3: Remember** | B + Memory | Persistent Memory | Vector DB, RAG, agents recall past work across sessions |
| **Phase 4: Learn** | B + Learning | Feedback Loops | Agents receive feedback, memory quality improves over time |
| **Phase 5: Autonomy** | B → C | Self-Directing Agents | Agents propose approaches, delegate to workers, orchestrator facilitates |

Each phase builds on the previous. No phase requires rewriting earlier work.

---

## Orchestration Patterns: Choosing the Right Model

Before diving into implementation, it is important to understand the fundamental architectural choices available for agent orchestration. The core question is: **what is the unit of work?** The answer shapes every decision that follows.

There are three fundamentally different paradigms, plus a hybrid approach that this architecture adopts.

### Option A: Task-Centric (Orchestrator + Agent Pool)

The **task** is king. Agents are stateless workers.

```
User Request
    │
    ▼
┌──────────────┐
│ Orchestrator  │  ← decomposes into subtasks
└──────┬───────┘
       │
       ├──→ [Subtask 1] ──→ Any capable agent picks it up
       ├──→ [Subtask 2] ──→ Any capable agent picks it up
       └──→ [Subtask 3] ──→ Any capable agent picks it up
       │
       ▼
   Orchestrator collects results, synthesizes answer
```

**How it works:**
- One orchestrator receives user input, creates a plan (list of subtasks)
- Each subtask goes onto a queue with required capabilities (e.g., "needs code generation", "needs web search")
- Any agent with matching tools/skills picks it up, completes it, returns the result
- Orchestrator collects all results and produces the final output
- Agents have no memory of each other — all context comes via the task payload

Agents are like functions. Call them with input, get output. No persistent identity between tasks.

**Pros:**
- Simplest to implement — maps directly onto existing Taskiq patterns
- Easy to scale — add more agents to the pool
- Easy to test — each agent is a pure function with input/output
- No coupling between agents
- Familiar: this is essentially how microservice task queues work

**Cons:**
- Complex tasks requiring back-and-forth between specialists are awkward (orchestrator must shuttle context)
- Orchestrator becomes a bottleneck and single point of failure
- No collaborative reasoning — agents can't challenge each other's work
- Context is limited to what fits in each subtask payload

**Best for:** Well-defined workflows, parallelizable tasks, automation pipelines. When you know the steps in advance.

### Option B: Plan-Centric (Assembled Teams)

The **plan** is king. Agents are grouped for the duration of a plan.

```
User Request
    │
    ▼
┌──────────────┐
│   Planner     │  ← creates plan + selects agents for team
└──────┬───────┘
       │
       ▼
┌────────────────────────────────┐
│  Team (lives for this plan)    │
│                                │
│  Agent A ←──→ Agent B          │
│     ↕            ↕             │
│  Agent C ←──→ Agent D          │
│                                │
│  Shared context / memory       │
└────────────────────────────────┘
       │
       ▼
   Final output
```

**How it works:**
- A planner/orchestrator receives the request and creates a plan
- It selects which agent types are needed and assembles a team
- The team shares a context space (conversation history, working memory)
- Agents within the team can communicate — one agent's output feeds another
- Team dissolves when the plan completes
- Agents can exist on multiple teams simultaneously (they're templates, not singletons)

**Two sub-variants:**

**B1: Static teams** — Pre-configured for known workflows. A "code review team" always has Architect + Coder + Reviewer. You configure the team once, activate it when needed. Rigid but predictable.

**B2: Dynamic teams** — Planner looks at the task and picks agents from a registry based on what's needed. A writing task gets Writer + Researcher + Editor. A coding task gets Architect + Coder + Tester. Flexible but the planner needs to be smart.

**Pros:**
- Agents can collaborate — reviewer can push back on coder, researcher can ask clarifying questions
- Shared context means richer understanding
- Models real-world team dynamics
- Plans can adapt mid-execution (agent realizes more help needed)

**Cons:**
- More complex state management (shared context per team)
- Harder to test — team behavior is emergent
- Risk of agents talking past each other or looping
- Need termination conditions (when is the plan "done"?)
- Resource usage is higher (multiple agents active simultaneously)

**Best for:** Creative tasks, complex multi-step problems, tasks requiring judgment and iteration. When you don't fully know the steps upfront.

### Option C: Agent-Centric (Persistent Agents, Actor Model)

The **agent** is king. Agents are long-lived entities with identity and memory.

```
┌─────────────────────────────────────────────┐
│  Agent Registry (always running)             │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Coder    │  │ Writer   │  │ Analyst  │  │
│  │ (has     │  │ (has     │  │ (has     │  │
│  │  memory) │  │  memory) │  │  memory) │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │              │              │        │
│       └──────────────┼──────────────┘        │
│                      │                       │
│              ┌───────▼───────┐               │
│              │  Message Bus   │               │
│              └───────────────┘               │
└─────────────────────────────────────────────┘
         │
    Tasks arrive, agents self-organize
```

**How it works:**
- Agents are persistent — they have identity, memory across tasks, and evolving expertise
- They receive messages (from users, orchestrator, or other agents) and decide what to do
- An agent remembers past work: "last time I coded this module, the user preferred async patterns"
- Communication is peer-to-peer via a message bus
- An orchestrator may still exist but as a peer, not a hierarchy

**Pros:**
- Agents accumulate expertise over time (learning)
- Most flexible — agents can self-organize
- Closest to the "AI team" vision
- Persistent memory enables continuity across sessions

**Cons:**
- Most complex to implement and debug
- Hardest to reason about — emergent behavior
- Memory management becomes critical (what to remember, what to forget)
- Risk of runaway agents, infinite loops, incoherent state
- Resource intensive — agents are always "alive"
- Requires vector DB / RAG from day one

**Best for:** Long-running projects, domains requiring accumulated knowledge, autonomous operation. This is the end-state vision.

### Option D: Hybrid (This Architecture's Approach)

Start with **A**, design the interfaces for **B**, evolve toward **C**. The orchestrator never disappears — its role evolves from controller to facilitator.

**Phase 1-2: Orchestrator as Controller**

```
User Request
    │
    ▼
┌──────────────┐
│ Orchestrator  │  ← routes tasks, creates plans
│  (controller) │
└──────┬───────┘
       │
       │  Simple task?          Complex task?
       │  ──────────────        ──────────────
       ▼                        ▼
  Single agent             Assemble team
  executes task            (sequential or parallel)
       │                        │
       ▼                        ▼
    Result                   Result

Agents are stateless. Context lives in the task/plan.
Orchestrator decides everything.
```

**Phase 3: Orchestrator as Memory-Aware Planner**

Agents gain persistent memory across sessions. The orchestrator queries agent expertise and past performance when assigning work. Agents bring learned context to every task.

**Phase 4: Orchestrator as Performance-Aware Planner**

Agents receive feedback on their outputs. Memory entries carry quality scores. The orchestrator routes tasks to agents with the best track record. The system gets smarter passively — agents don't change, but the context they receive improves.

```
User Request
    │
    ▼
┌──────────────────┐
│   Orchestrator    │  ← plans with awareness of agent expertise
│  (smart planner)  │
└──────┬───────────┘
       │
       │  Queries agent performance history
       │  Retrieves relevant memory for context
       │
       ▼
┌─────────────────────────────────────────────┐
│  Agents (with memory + feedback scores)      │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Coder    │  │ Writer   │  │ Analyst  │  │
│  │          │  │          │  │          │  │
│  │ memory ▓▓│  │ memory ▓▓│  │ memory ▓▓│  │
│  │ score 94%│  │ score 87%│  │ score 91%│  │
│  └──────────┘  └──────────┘  └──────────┘  │
│                                              │
│  Agents execute with past experience         │
│  Orchestrator still dictates the plan        │
└─────────────────────────────────────────────┘
       │
       ▼
    Result (feedback stored for future learning)
```

**Phase 5: Orchestrator as Facilitator**

Agents have enough accumulated expertise to propose their own approaches. The orchestrator shifts from dictating plans to approving agent proposals and monitoring quality. Intelligent agents delegate mechanical subtasks to cheap, stateless worker agents.

```
User Request
    │
    ▼
┌──────────────────┐
│   Orchestrator    │  ← approves, monitors, quality gate
│   (facilitator)   │
└──────┬───────────┘
       │
       │  Assigns to expert agent
       │  Reviews agent's proposed approach
       │
       ▼
┌──────────────────────────────────────────────────┐
│  Intelligent Agent (Specialist model)             │
│  Has: memory, expertise, learned patterns         │
│                                                   │
│  Proposes: "I've seen this before. I'll need      │
│  search data and formatting. Here's my plan..."   │
│                                                   │
│  ├── delegates: Search Worker ─────────────────┐  │
│  │   (Worker model, stateless, cheap)          │  │
│  │◄── results ─────────────────────────────────┘  │
│  │                                                │
│  ├── delegates: Format Worker ─────────────────┐  │
│  │   (Worker model, stateless, cheap)          │  │
│  │◄── results ─────────────────────────────────┘  │
│  │                                                │
│  └── applies own expertise to produce             │
│      final analysis                               │
└──────────────────────────────────────────────────┘
       │
       ▼
    Result (with feedback loop back to agent memory)
```

**How the orchestrator's role evolves:**

| Phase | Orchestrator Role | Agent Autonomy | What Changes |
|-------|------------------|----------------|--------------|
| Phase 1 | **Router** — picks one agent, hands off task | None — agents are stateless functions | Starting point |
| Phase 2 | **Planner** — decomposes tasks, sequences steps | Low — agents execute assigned steps | Orchestrator creates multi-step plans |
| Phase 3 | **Memory-aware planner** — considers agent expertise when assigning | Medium — agents bring learned context to every task | Agents have persistent memory |
| Phase 4 | **Performance-aware planner** — routes based on proven track record | Medium-high — feedback improves agent effectiveness | Feedback loops refine memory quality |
| Phase 5 | **Facilitator** — approves what agents propose, monitors quality | High — agents propose plans, delegate to workers | Orchestrator shifts from command to quality gate |

**Tiered Delegation (Phase 5):**

At Phase 5, a natural hierarchy emerges. Intelligent agents delegate specific mechanical work to cheap, stateless worker agents. This mirrors how a senior engineer delegates to tools and juniors — the senior thinks, the juniors execute.

| Tier | Role | Model Class | When Used |
|------|------|-------------|-----------|
| **Thinker** | Orchestration, planning, complex judgment | Most capable reasoning model | Orchestrator, complex decisions |
| **Specialist** | Domain-specific work requiring skill | Best model for that domain | Coding agents, analysis agents, writing agents |
| **Worker** | Mechanical tasks — search, format, classify, summarize | Cheapest model that can do the job | Stateless workers delegated to by Tier 1 |

**The orchestrator is not an agent itself** — it is application code (a service class) that coordinates agents. It delegates LLM-requiring subtasks to specialized internal agents:

| Subtask | Who Handles It | Phase |
|---------|---------------|-------|
| Route to the right agent | Rule-based router (Python) + Router Agent (lightweight LLM classification) | 1 |
| Conversational fallback | Fallback Agent (vertical agent, general-purpose) | 1 |
| Decompose into multi-step plan | Planner Agent (vertical agent, task decomposition) | 2 |
| Evaluate agent proposals | Evaluator Agent (vertical agent, judgment) | 5 |

The human never "talks to the orchestrator" — the orchestrator is invisible infrastructure. What the human perceives as "the system" is the agent that handles their request. The orchestrator routes, composes middleware, enforces safety, and monitors — but it doesn't have a personality, system prompt, or conversational presence.

**How it works:**
- **Orchestrator always exists** — it's the entry point. Every request enters through it.
- For simple tasks, it routes to a single agent (Phase 1 behavior)
- For complex tasks, it creates a plan with multiple agents (Phase 2 behavior)
- As agents accumulate memory (Phase 3) and feedback (Phase 4):
  - The orchestrator considers performance history when assigning work
  - Agents bring their own learned context to every task
- At Phase 5:
  - Agents propose approaches based on accumulated expertise
  - The orchestrator approves rather than dictates
  - Intelligent agents delegate mechanical subtasks to cheap worker agents
- Agent definitions are in a registry — the orchestrator knows what's available
- Teams are assembled dynamically based on the task, not pre-configured

**Why this works for a skeleton:**
- The orchestrator is trivial to implement initially — it's a Python class with rule-based routing
- Single-agent execution works immediately (day one value)
- Multi-agent chaining is a small step from there
- Tiered delegation uses the same AgentTask primitive — a worker agent call is just a child task
- Full team collaboration can be added later without changing the core interfaces
- You don't need vector DB, complex memory, or a message bus on day one
- The evolution to C happens gradually — you give agents more autonomy as they earn trust

**The key insight:** you don't get to Option C by removing the orchestrator. You get there by making the orchestrator trust agents more. The orchestrator goes from micromanager to facilitator. Intelligent agents emerge not by design but by accumulating memory and proven results. The interface stays the same — only the intelligence behind it deepens.

### How Phases Map to Options

| Phase | Orchestration Pattern | Option | Model Tiers Active |
|-------|----------------------|--------|--------------------|
| Phase 1: Execute | Single agent routing | A | Thinker + Specialist |
| Phase 2: Plan | Multi-step plans with shared context | A → B | Thinker + Specialist + Worker |
| Phase 3: Remember | Persistent memory across sessions | B + Memory | All tiers, agents have memory |
| Phase 4: Learn | Feedback improves memory quality | B + Learning | All tiers, feedback refines performance |
| Phase 5: Autonomy | Agents self-direct, orchestrator facilitates | B → C | Intelligent agents delegate to workers |

The architecture is designed so that each phase transition is an expansion, not a rewrite. The same AgentTask primitive, the same orchestrator interface, the same tool registry, and the same tiered model pattern serve all five phases.

The remainder of this document specifies the implementation of **Option D** — starting with the design principles, then the data model, core components, and phase-by-phase behavior.

---

## Design Principles

These 28 principles govern all agentic architecture decisions. Not all are implemented in Phase 1, but all are **designed for** from day one — the data model, interfaces, and extension points accommodate every principle.

### Memory

| # | Principle | Phase |
|---|-----------|-------|
| 1 | Shared memory and context between agents within a plan | 2 |
| 2 | Context window budget management — system knows model limits and manages what fits | 1 |
| 3 | Memory lifecycle — entries have metadata, can be archived, purged, or summarized | 3 |

### Transparency

| # | Principle | Phase |
|---|-----------|-------|
| 4 | Human-visible, inspectable memory — all context and memory viewable by humans at any time | 1 |

### Audit

| # | Principle | Phase |
|---|-----------|-------|
| 5 | Full audit trail — every action, decision, tool call, and LLM interaction logged | 1 |

### Control

| # | Principle | Phase |
|---|-----------|-------|
| 6 | Human-in-the-loop — humans can interject, approve, reject, or be asked for input | 1 |
| 7 | Kill switch — halt a running agent, plan, or all agents instantly via API and CLI | 1 |

### Safety

| # | Principle | Phase |
|---|-----------|-------|
| 8 | Runaway prevention — system cannot spiral out of control | 1 |
| 9 | Budget caps at every level — per call, per step, per plan, per user, per day. Hard limits that stop execution | 1 |
| 10 | Maximum steps per plan — configurable ceiling prevents recursive decomposition spirals | 1 |
| 11 | Timeout on every operation — LLM calls, tool executions, and plans all have wall-clock timeouts | 1 |

### Cost

| # | Principle | Phase |
|---|-----------|-------|
| 12 | Cost tracking — every LLM call tracked by token count, model, and computed cost | 1 |

### Observability

| # | Principle | Phase |
|---|-----------|-------|
| 13 | Full reasoning chain preserved — agent "thinking", tool considerations, path choices stored | 1 |
| 14 | Decision points as discrete events — each choice and its rationale is a separate auditable record | 1 |
| 15 | Timing data on all operations — duration of every LLM call, tool execution, and plan | 1 |

### Reproducibility

| # | Principle | Phase |
|---|-----------|-------|
| 16 | Model version tracking — exact model recorded for each call | 1 |
| 17 | Prompt version tracking — system prompt version recorded for each agent execution | 1 |
| 18 | Data shape supports replay — enough data logged to theoretically replay any plan | 1 |

### Human-in-the-Loop

| # | Principle | Phase |
|---|-----------|-------|
| 19 | Approval gates — plan steps can require human approval before proceeding | 1 |
| 20 | Confidence signaling — agents express uncertainty, escalate below threshold | 2 |
| 21 | Escalation path to human — agents flag what they tried and why they stopped | 1 |
| 22 | Notification on human-needed events — triggers via configured channels | 1 |

### Error Handling

| # | Principle | Phase |
|---|-----------|-------|
| 23 | Partial results preserved — failed plans retain completed steps | 1 |
| 24 | Fallback models with audit record — fallback is recorded, never silent | 1 |
| 25 | Graceful degradation — agent module failure does not bring down the application | 1 |

### Security

| # | Principle | Phase |
|---|-----------|-------|
| 26 | Tool sandboxing — agents can only use explicitly assigned tools | 1 |
| 27 | Output validation — agent outputs validated before delivery or handoff | 1 |
| 28 | No credential exposure — secrets never appear in agent context, prompts, or outputs | 1 |

---

## Primitive: AgentTask

Per **02-primitive-identification.md**, the system declares a single primitive through which all work flows.

```
Primitive: AgentTask

| Attribute       | Type     | Description                                         |
|-----------------|----------|-----------------------------------------------------|
| id              | UUID     | Unique identifier                                   |
| plan_id         | UUID     | Groups related tasks into a plan (nullable for standalone) |
| agent_type      | string   | Agent definition that handles this task              |
| type            | Enum     | Categorizes the task (see types below)               |
| status          | Enum     | Lifecycle state (see states below)                   |
| sequence        | int      | Order within a plan (nullable for standalone)        |
| input           | JSON     | What the agent receives                              |
| output          | JSON     | What the agent produced                              |
| context         | JSON     | Accumulated context from prior steps                 |
| reasoning       | JSON     | Agent's reasoning chain and decision log             |
| feedback        | JSON     | Outcome evaluation (null until Phase 4)              |
| parent_task_id  | UUID     | For subtask hierarchies (nullable)                   |
| created_by      | UUID     | User who initiated (or system for scheduled)         |
| channel         | string   | Originating channel (telegram, slack, websocket, cli, tui, api) |
| session_type    | Enum     | Session type: direct or group (see 44-multi-channel-gateway.md) |
| tool_access_level | Enum   | Allowed tool scope: full, sandbox, or readonly (enforced before execution) |
| model_used      | string   | Exact model identifier for the primary LLM call      |
| prompt_version  | string   | System prompt version used                           |
| token_input     | int      | Input tokens consumed                                |
| token_output    | int      | Output tokens generated                              |
| cost            | decimal  | Computed cost in USD                                 |
| duration_ms     | int      | Wall-clock execution time in milliseconds            |
| error           | JSON     | Error details if failed (nullable)                   |
| created_at      | datetime | Creation timestamp (UTC, timezone-naive)             |
| updated_at      | datetime | Last update timestamp (UTC, timezone-naive)          |
```

### Task Types

| Type | Description |
|------|-------------|
| `user_request` | Direct user input requiring agent processing |
| `orchestration` | Orchestrator planning and routing |
| `agent_work` | Agent executing a specific subtask |
| `tool_call` | Agent invoking an external tool |
| `human_decision` | Waiting for human input or approval |
| `evaluation` | Agent evaluating its own or another agent's output (Phase 5) |

### Task States

```
                    ┌──────────────┐
                    │   pending    │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
     ┌──────────────┐ ┌──────────┐ ┌────────────────────┐
     │   running    │ │ awaiting │ │     cancelled      │
     │              │ │ approval │ │                    │
     └──────┬───────┘ └────┬─────┘ └────────────────────┘
            │              │
            │         Human approves
            │         or rejects
            │              │
            ├──────────────┘
            │
       ┌────┴────┐
       │         │
       ▼         ▼
┌──────────┐ ┌──────────┐
│completed │ │  failed  │
└──────────┘ └──────┬───┘
                    │
                    ▼
              ┌──────────┐
              │  partial  │
              │ (plan-level│
              │  status)  │
              └──────────┘
```

| State | Description |
|-------|-------------|
| `pending` | Created, waiting to execute |
| `running` | Agent is actively processing |
| `awaiting_approval` | Paused, waiting for human decision |
| `completed` | Successfully finished |
| `failed` | Execution failed (error details in `error` field) |
| `cancelled` | Halted by human or system (kill switch, budget exceeded) |

### How Operations Map to the Primitive

| Operation | Primitive Expression |
|-----------|---------------------|
| User asks a question | Create AgentTask (type=user_request) |
| Orchestrator plans steps | Create AgentTask (type=orchestration, children created) |
| Agent processes a subtask | Create AgentTask (type=agent_work, parent_task_id=plan) |
| Agent calls a tool | Create AgentTask (type=tool_call, parent_task_id=step) |
| System needs human input | Update AgentTask (status=awaiting_approval) |
| Human approves | Update AgentTask (status=running) |
| Kill switch activated | Update AgentTask (status=cancelled) for all running tasks |
| View plan progress | Query AgentTasks (plan_id, ordered by sequence) |
| View costs | Query AgentTasks (aggregate cost, token_input, token_output) |
| Review audit trail | Query AgentTasks (all fields, ordered by created_at) |

---

## Core Components

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Entry Points                                │
│                                                               │
│  ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │  REST API  │ │ Telegram │ │  Slack   │ │  WebSocket   │  │
│  │  (FastAPI) │ │ Webhook  │ │  Bolt    │ │  (TUI, Web)  │  │
│  └─────┬──────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘  │
│        │              │            │              │           │
│        │    ┌─────────┴────────────┴──────────────┘           │
│        │    │  Channel Adapters (44-multi-channel-gateway.md) │
│        │    │  Security → Session → Router                    │
│        │    └──────────────────┬───────────────────           │
│        │                      │                               │
│        └──────────┬───────────┘                               │
│                   │                                           │
│  POST /api/v1/agent/run     GET /api/v1/agent/tasks          │
│  POST /api/v1/agent/cancel  GET /api/v1/agent/tasks/{id}     │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                    Orchestrator (Coordinator)                   │
│                                                               │
│  Receives requests → Routes to agents → Composes middleware   │
│  Monitors progress → Handles failures → Returns results       │
│  Delegates LLM subtasks to specialized agents (router,        │
│  planner, evaluator) — does not reason itself                 │
└──────┬──────────────┬──────────────┬────────────────────────┘
       │              │              │
       ▼              ▼              ▼
┌────────────┐ ┌────────────┐ ┌────────────┐
│   Agent    │ │    Tool    │ │    LLM     │
│  Registry  │ │  Registry  │ │  Provider  │
│            │ │            │ │   Layer    │
│ Agent defs │ │ Tool defs  │ │ Model      │
│ Prompts    │ │ Permissions│ │ abstraction│
│ Config     │ │ Execution  │ │ Cost track │
└────────────┘ └────────────┘ └────────────┘
       │              │              │
       └──────────────┼──────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────┐
│                    Execution Engine                            │
│                                                               │
│  Runs agent reasoning loop: Prompt → LLM → Parse → Act       │
│  Enforces timeouts, budgets, step limits                      │
│  Logs reasoning chain, decisions, tool calls                  │
└──────────────────────────┬───────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
       ┌────────────┐ ┌────────┐ ┌──────────┐
       │ PostgreSQL │ │ Redis  │ │ pgvector │
       │ (tasks,    │ │ (cache,│ │ (Phase 3)│
       │  agents,   │ │  state,│ │          │
       │  audit)    │ │  locks)│ │          │
       └────────────┘ └────────┘ └──────────┘
```

### 1. Agent Registry

The agent registry stores all agent definitions. An agent definition is a template — it describes what an agent can do, not a running instance.

The registry provides:
- `get_agent(name)` — retrieve an agent definition
- `list_agents()` — list all available agent types
- `get_agents_for_capability(capability)` — find agents that can handle a task type

Agent definitions include: name, description, model configuration, system prompt reference, tool list, limits (steps, timeout, cost), output schema, and capability declaration (keywords and description used for routing).

The registry is read-only at runtime. Agent definitions change through config file updates and application restart. Agents can be disabled via feature flag (`enabled: false`) without code deployment.

For concrete agent definition YAML schema and registry implementation, see **[41-agentic-pydanticai.md](41-agentic-pydanticai.md)**.

### 2. Orchestrator (Coordinator)

The orchestrator is the entry point for all agent work. Every request flows through it.

**Responsibilities:**
- Receive user requests from any entry point (API, CLI, Telegram, Slack, WebSocket, scheduled task). When requests arrive through channel adapters (**[44-multi-channel-gateway.md](44-multi-channel-gateway.md)**), the gateway has already enforced security, resolved the session, and set the `tool_access_level` before the orchestrator sees the request.
- Route to the appropriate agent using hybrid routing (deterministic rules first, LLM classification fallback)
- Compose horizontal middleware (guardrails, memory, cost tracking, output validation) around agents
- Enforce `tool_access_level` from the session — filter the agent's available tools based on the session's access level (`full`, `sandbox`, `readonly`) before execution
- Create AgentTask records (including `channel`, `session_type`, and `tool_access_level` from the request)
- Monitor execution progress
- Handle failures, retries, and escalation
- Enforce plan-level budgets and step limits
- Return final results

**The orchestrator is not an agent itself** — it is application code (a service class) that coordinates agents. It delegates LLM-requiring subtasks to specialized internal agents:

| Subtask | Who Handles It | Phase |
|---------|---------------|-------|
| Route to the right agent | Rule-based router (Python) + Router Agent (lightweight LLM classification) | 1 |
| Conversational fallback | Fallback Agent (vertical agent, general-purpose) | 1 |
| Decompose into multi-step plan | Planner Agent (vertical agent, task decomposition) | 2 |
| Evaluate agent proposals | Evaluator Agent (vertical agent, judgment) | 5 |

**Phase 1 behavior:** Simple routing. Analyze the request via rules (keyword matching) or lightweight LLM classification, pick one agent, execute, return result.

**Phase 2 behavior:** Plan creation. The orchestrator delegates to a Planner Agent to create a multi-step plan, then manages step sequencing and context passing between steps.

For concrete coordinator implementation, see **[41-agentic-pydanticai.md](41-agentic-pydanticai.md)**.

### 3. Tool Registry

Tools are functions that agents can invoke to interact with the outside world. The tool registry manages their definitions, permissions, and execution.

Tools have: name, description, parameter schema (JSON Schema), return schema, permission settings (which agents can use it, whether it requires human approval), and execution configuration (module path, function name, timeout).

**Sandboxing:** An agent can only invoke tools listed in its agent definition. The execution engine checks the tool registry to verify the agent has permission before executing. This is enforced at the system level, not by the agent's judgment.

**Tool execution is always logged** as an AgentTask record (type=tool_call) with full input, output, and timing.

For concrete tool definition YAML schema and registry implementation, see **[41-agentic-pydanticai.md](41-agentic-pydanticai.md)**.

### 4. LLM Provider Layer

The provider layer is defined in **24-llm-integration.md** and provides the `LLMProvider` interface, `LLMResponse`, `ToolDefinition`, `ToolCall`, and `TokenUsage` types. See that document for the full interface definition, fallback model configuration, and provider comparison.

The agents module uses the provider layer through this interface. It does not interact with provider-specific APIs directly.

**Agent-specific requirements on top of 24:**
- Every LLM call returns cost and usage data. The execution engine accumulates these into the AgentTask record.
- Fallback model usage is recorded in both the `LLMResponse` metadata and the AgentTask audit trail.
- The exact model version (from the provider response, not the requested alias) is stored on every AgentTask for reproducibility.

### 5. Execution Engine

The execution engine runs the agent reasoning loop. This is where an agent "thinks."

**The ReAct Loop:**

```
┌─────────────────────────────────────────────────┐
│                                                   │
│  1. Assemble context (system prompt + input +     │
│     conversation history + tool descriptions)     │
│                              │                    │
│                              ▼                    │
│  2. Call LLM                                      │
│                              │                    │
│                              ▼                    │
│  3. Parse response                                │
│     ├── Tool call requested? ──→ Execute tool     │
│     │                            │                │
│     │                   Return result to context  │
│     │                            │                │
│     │                   Loop back to step 2 ──────┤
│     │                                             │
│     └── Final answer? ──→ Validate output         │
│                              │                    │
│                              ▼                    │
│  4. Return result                                 │
│                                                   │
└─────────────────────────────────────────────────┘
```

**Safety enforcement at each iteration:**
- Check step count against `max_steps` — stop if exceeded
- Check elapsed time against `timeout_seconds` — stop if exceeded
- Check accumulated cost against `max_cost_per_task` — stop if exceeded
- Check for tool call requiring human approval — pause if needed
- Log the full reasoning step (LLM input, output, decision, timing)

**Each iteration** of this loop creates a reasoning entry in the AgentTask's `reasoning` JSON field, preserving the complete chain of thought for audit and future learning.

### 6. Agent-to-Agent Communication

When an intelligent agent delegates work to a worker agent, the execution engine mediates the entire interaction. The intelligent agent's LLM has no idea it's calling another agent — it sees a tool definition like any other.

**Execution hierarchy:**

```
Orchestrator (Thinker model — plans, routes)
    │
    ▼
Intelligent Agent (Specialist model — reasons, judges)
    │
    ├── Worker Agent (Worker model — executes with light reasoning)
    │       │
    │       ├── Tool (deterministic function — no LLM)
    │       └── Tool (deterministic function — no LLM)
    │
    ├── Worker Agent (Worker model)
    │       │
    │       └── Tool (deterministic function)
    │
    └── Tool (intelligent agents can also call tools directly)
```

Three levels:
- **Intelligent agents** use worker agents and tools. They decide what to delegate and what to do themselves.
- **Worker agents** use tools. They apply light reasoning (cheap model) to get better results from their tools — refining queries, interpreting results, structuring output.
- **Tools** are deterministic functions. No LLM, no reasoning. Input in, output out.

**Communication flow:**

When an intelligent agent's LLM outputs a tool call for a worker agent, the execution engine:
1. Recognizes it as an agent-tool (worker agent registered as a tool in the parent's tool list)
2. Creates a child AgentTask (type=agent_work, parent_task_id=parent agent's task)
3. Runs the worker agent's own ReAct loop (own system prompt, own tools, own budget/timeout)
4. Returns the worker's output as a tool result to the intelligent agent's conversation
5. The intelligent agent's LLM receives the result and continues reasoning

**Isolation rules:**

The worker agent does NOT receive:
- The intelligent agent's memory or accumulated context
- The intelligent agent's system prompt
- Knowledge of who called it or why
- Access to the intelligent agent's tools

The worker is a black box. It receives only the input specified in the tool call, executes independently, and returns structured output. This ensures workers are reusable, independently testable, and cannot corrupt the caller's state.

**Cost rollup:**

The child AgentTask records its own cost. The parent AgentTask's accumulated cost includes all children. Budget enforcement checks the parent's total (including children) before each new call.

**When to use a worker agent vs a regular tool:**

| Use a regular tool when | Use a worker agent when |
|------------------------|------------------------|
| The operation is deterministic | The operation benefits from reasoning |
| One call, one result | May need multiple calls or query refinement |
| No interpretation needed | Results need filtering or structuring |
| Speed is critical | Quality of result matters more than speed |
| Examples: file_reader, calculator, database_query | Examples: web_search, code_analysis, document_summary |

For concrete implementation of agent-as-tool delegation, see **[41-agentic-pydanticai.md](41-agentic-pydanticai.md)**.

---

## Module Structure, Configuration, and Implementation

The agent module lives under `modules/backend/agents/`, separate from `modules/backend/`, following the module boundaries defined in **04-module-structure.md**. It contains the orchestrator, agent definitions, tool definitions, execution engine, and memory components.

For the concrete directory layout, configuration files, YAML schemas, database models, API endpoints, and testing patterns, see **[41-agentic-pydanticai.md](41-agentic-pydanticai.md)**.

---

## Orchestration: Phase-by-Phase Behavior

This section details how the hybrid approach (Option D) described in "Orchestration Patterns: Choosing the Right Model" is implemented at each phase.

### Phase 1: Execute — Single Agent Routing (Option A)

The orchestrator receives a request, selects one agent, executes, and returns.

```
User: "Review this code for security issues"
  │
  ▼
Orchestrator: rule match → "code_reviewer" agent
  │
  ▼
code_reviewer executes (ReAct loop with tools)
  │
  ▼
Result returned to user
```

**Task records created:**
1. AgentTask (type=user_request, status=completed)
2. AgentTask (type=orchestration, parent=1)
3. AgentTask (type=agent_work, parent=1, agent_type=code_reviewer)
4. AgentTask (type=tool_call, parent=3) — for each tool the agent used

### Phase 2: Plan — Multi-Step Plans (Option A → B)

The orchestrator decomposes complex requests into sequential or parallel steps.

```
User: "Research competitors and write a summary report"
  │
  ▼
Orchestrator delegates to Planner Agent:
  Step 1: researcher → gather competitor data
  Step 2: researcher → analyze market positioning
  Step 3: writer → draft summary report (depends on steps 1,2)
  │
  ▼
Steps 1 and 2 execute (parallel if independent)
  │
  ▼
Context from steps 1,2 passed to step 3
  │
  ▼
Step 3 executes with accumulated context
  │
  ▼
Final report returned to user
```

**Shared context:** Each step's output is added to a shared context object (JSON). Subsequent steps receive the accumulated context. The execution engine manages context size — if accumulated context exceeds the model's window, it applies the priority rules from 24-llm-integration.md (current step input > recent results > older results).

**Step dependencies:** Steps can declare dependencies. The orchestrator runs independent steps in parallel and waits for dependencies before starting dependent steps.

### Phase 3: Remember — Persistent Memory (Option B + Memory)

Agents gain persistent memory across sessions. Before executing, the engine queries the vector database for relevant prior work and injects it into the agent's context. After executing, meaningful results are stored as memory entries.

The orchestrator becomes memory-aware — it queries agent performance history when deciding which agent to assign to a step.

### Phase 4: Learn — Feedback Loops (Option B + Learning)

Agents receive feedback on their outputs (human ratings, downstream success/failure). This feedback is stored alongside memory entries. When retrieving memory, entries with positive feedback are prioritized.

The orchestrator becomes performance-aware — it routes tasks to agents with the best track record for that task type.

### Phase 5: Autonomy — Self-Directing Agents (Option B → C)

Agents have accumulated enough expertise to propose their own approaches. The orchestrator shifts from dictating plans to approving agent proposals. Intelligent agents delegate mechanical subtasks to cheap, stateless worker agents.

This is where the system approaches Option C behavior — not by removing the orchestrator, but by the orchestrator trusting agents to self-direct based on proven performance. Agents can request help from other agents mid-execution, and the execution engine routes these requests back through the orchestrator.

### Orchestrator Failure Modes

| Scenario | Response |
|----------|----------|
| Agent exceeds step limit | Task marked `failed`, error explains limit hit, partial output preserved |
| Agent exceeds timeout | Task marked `failed`, in-flight LLM call abandoned, partial output preserved |
| Agent exceeds cost budget | Task marked `cancelled`, error explains budget exceeded |
| LLM provider outage | Retry with fallback model, record fallback in audit |
| Tool execution failure | Agent receives error, decides whether to retry or report failure |
| All retries exhausted | Task marked `failed`, escalation to human if configured |

For the concrete DAG-based implementation with PostgreSQL schema, ready-task queries, and plan revision patterns, see `46-event-session-architecture.md`, Section 4.

---

## Human-in-the-Loop

### Approval Gates

Any plan step can be configured to require human approval before execution. When a step reaches `awaiting_approval`:
1. AgentTask status set to `awaiting_approval`
2. Notification sent via configured channel (Telegram, email, webhook)
3. Execution pauses — no timeout clock runs during approval wait
4. Human approves → status changes to `running`, execution continues
5. Human rejects → status changes to `cancelled`, plan may abort or skip

### Escalation

Agents can escalate to humans when they cannot proceed. The agent includes an escalation object in its output with the reason, options for the human, and context about what was attempted. The execution engine detects escalation, sets the task to `awaiting_approval`, and notifies the human.

### Confidence Signaling (Phase 2)

Agents include a confidence score in structured output. The orchestrator compares against the configured threshold:

- Above threshold → proceed automatically
- Below threshold → escalate to human with the agent's reasoning

The threshold is configurable per agent type and per task type.

### Kill Switch

The kill switch halts execution immediately:

**API:** `POST /api/v1/agent/cancel` with body `{"scope": "task|plan|all", "id": "uuid"}`

**CLI:** `python cli.py agent cancel --scope plan --id <uuid>`

**Behavior:**
- All running AgentTasks in scope set to `cancelled`
- In-flight LLM calls abandoned (not awaited)
- Partial results preserved in completed steps
- Event published: `agents.execution.cancelled`
- Audit log entry created with who cancelled and why

For the concrete unified responder pattern with Temporal Signals, escalation chains, and durable approval workflows, see `46-event-session-architecture.md`, Section 6.

---

## Safety and Limits

### Budget Enforcement

Budgets are checked before every LLM call and tool execution:

```
Before each LLM call:
  1. Calculate accumulated cost for this task
  2. Calculate accumulated cost for this plan (if part of plan)
  3. Calculate accumulated cost for this user today
  4. If ANY limit exceeded → stop execution, set status to cancelled
```

| Limit | Scope | Configured In |
|-------|-------|---------------|
| Per LLM call | Single call token limit | Agent definition |
| Per task | Total cost for one agent's work | Agent definition |
| Per plan | Total cost across all steps | Global settings |
| Per user daily | Total cost for a user in 24 hours | Global settings |
| System-wide | Circuit breaker for total platform spend | Global settings |

### Step Limits

| Limit | Description | Default |
|-------|-------------|---------|
| Max steps per task | ReAct loop iterations for a single agent | 20 |
| Max steps per plan | Total steps across all agents in a plan | 50 |

When a limit is hit, the task status is set to `failed` with a clear error message. Partial results are preserved.

### Timeout Enforcement

| Timeout | Scope | Default |
|---------|-------|---------|
| LLM call | Single provider API call | 120 seconds |
| Tool execution | Single tool invocation | 60 seconds |
| Task | Total wall-clock for one agent's work | 300 seconds |
| Plan | Total wall-clock for all steps | 1800 seconds |

Timeouts use `asyncio.timeout()` per **03-backend-architecture.md**. When a timeout fires, the task is marked `failed` and partial results are preserved.

---

## Cost Management

This extends the cost tracking from **24-llm-integration.md** with agent-specific aggregation.

### What Gets Tracked

Every AgentTask records:
- `model_used` — exact model identifier
- `token_input` — input tokens consumed
- `token_output` — output tokens generated
- `cost` — computed cost in USD
- `duration_ms` — wall-clock time

For tasks with multiple LLM calls (ReAct loop), these are **accumulated totals** across all calls in that task. Individual call details are in the `reasoning` JSON field.

### Cost Reporting

The API provides aggregated cost views:

- Per task: single task cost
- Per plan: sum of all tasks in the plan
- Per user: sum of all tasks by a user (daily, monthly)
- Per agent type: which agent types cost the most
- Per model: cost breakdown by LLM model
- System total: total platform spend

### Cost Alerts

Configure alerts:
- Warning at 80% of daily user budget
- Hard stop at 100% of daily user budget
- Warning at 80% of system budget
- Hard stop at 100% of system budget

Alerts fire as events via **21-event-architecture.md** and can trigger notifications.

---

## Observability

This extends **10-observability.md** with agent-specific logging.

### What Gets Logged

Every agent execution produces structured log entries:

| Event | Logged Data |
|-------|-------------|
| Task created | task_id, type, agent_type, input summary, created_by |
| LLM call started | task_id, model, prompt length (tokens), temperature |
| LLM call completed | task_id, model, response length, cost, duration_ms |
| Tool call started | task_id, tool_name, parameters |
| Tool call completed | task_id, tool_name, result summary, duration_ms |
| Decision point | task_id, decision description, options considered, choice made |
| Approval requested | task_id, reason, options presented |
| Approval received | task_id, approved_by, decision |
| Task completed | task_id, status, total_cost, total_duration_ms |
| Task failed | task_id, error type, error message, partial results available |
| Budget exceeded | task_id, limit_type, limit_value, actual_value |
| Kill switch | scope, target_id, cancelled_by |

### Log Source

Agent logs are written to `logs/system.jsonl` with `source="agents"` per 10-observability.md.

### Reasoning Chain Storage

The `reasoning` field on AgentTask stores the complete reasoning chain as a JSON array of step objects, each containing: step number, timestamp, LLM input summary, LLM output, action taken (tool_call or final_answer), tool details if applicable, token counts, cost, and duration.

This data is the foundation for Phase 4 (Learn) and Phase 5 (Autonomy). Every reasoning chain is preserved, enabling feedback collection (Phase 4) and self-evaluation (Phase 5).

---

## Memory Architecture

### Phase 1: Task-Scoped Context (Skeleton)

Memory is scoped to a single task or plan. Context is assembled from:
- The task's input
- Previous steps' outputs (within the same plan)
- The agent's system prompt

Storage: PostgreSQL (AgentTask.context field) and Redis (ephemeral working state during execution).

No persistence across plans. When a plan completes, its context is archived in the AgentTask records but not searchable by future agents.

### Phase 2: Shared Plan Context

Agents within a plan share a context space. When agent A completes a step, its output is available to agent B in the next step.

The orchestrator manages context accumulation. Context size management: if accumulated context exceeds the target model's window, the execution engine summarizes older steps (using a fast/cheap model) before injecting into the next step's prompt.

### Phase 3: Remember — Persistent Memory (pgvector)

Add the pgvector extension to the existing PostgreSQL instance for semantic memory. No separate vector database deployment required.

**Memory entries:**
- Created when an agent produces a meaningful result
- Tagged with: agent_type, task_type, timestamp, quality score (added in Phase 4)
- Embedded and stored in pgvector
- Searchable by semantic similarity

**Memory retrieval:**
- Before an agent executes, the execution engine queries memory for relevant prior work
- Retrieved entries are injected into the agent's context (after system prompt, before current input)
- The agent "remembers" similar past tasks and their outcomes

**Memory lifecycle:**
- Entries have access counts and recency scores
- Stale entries (old, rarely accessed) are candidates for archival
- Archival = removed from vector index, kept in PostgreSQL for audit
- Summarization: clusters of related entries periodically condensed into summary entries

### Phase 4: Learn — Feedback-Weighted Memory

Agents receive feedback on their outputs (human rating, downstream success/failure). This feedback is stored alongside the memory entry.

When retrieving memory, entries with positive feedback are prioritized. This is **passive learning** — the agent doesn't know it's learning, but the system serves it better examples over time.

Feedback loop:
1. Agent completes task → output stored with reasoning chain
2. Outcome evaluated (human feedback or automated check)
3. Feedback attached to memory entry
4. Future similar tasks retrieve this entry with feedback
5. Agent receives better context because high-quality examples are prioritized

### Phase 5: Autonomy — Self-Directed Memory Use

Agents actively use their accumulated expertise to propose approaches. This is **active learning** — the agent explicitly reasons about its past experience.

- Agents generate proposals: "Based on my experience with similar tasks, I recommend approach X because it succeeded 4 out of 5 times"
- Self-evaluation agent reviews past work and identifies improvement patterns
- Orchestrator tracks per-agent performance metrics and adjusts trust levels
- Intelligent agents choose which worker agents to delegate to based on past outcomes

For the concrete three-tier memory architecture (episodic, semantic, procedural) with anchored rolling summaries and context window assembly, see `46-event-session-architecture.md`, Section 5.

---

## Security

### Tool Sandboxing

Tool access is a whitelist, not a blacklist:

1. Agent definition lists allowed tools
2. Before every tool execution, the engine checks: is this tool in the agent's allowed list?
3. If not → execution blocked, error logged, agent receives "tool not available" response
4. Tool definitions can also restrict which agents may use them (bidirectional)

### Credential Isolation

- Agent prompts never contain API keys, database passwords, or secrets
- Tools access credentials internally through the config system
- Agent context is safe to log and display to humans without redaction of credentials
- If an agent's LLM output contains something that looks like a credential, the output validator flags it

### Output Validation

Before an agent's output is returned to the user or passed to the next step:

1. Schema validation — if the agent definition specifies an output schema, validate against it
2. Content filtering — check for credential patterns, PII if configured
3. Sanity check — output is not empty, not excessively long, not a repeat of the input

Invalid output → retry once with a clarified prompt. Still invalid → mark task as `failed`.

---

## Testing

Agent testing requires deterministic results without calling real LLMs. The testing approach must support:

- **Unit tests** — test individual agents in isolation with mocked LLM responses
- **Integration tests** — test orchestrator routing with real agent logic but mocked LLM
- **Evaluation tests** — test prompt quality against evaluation datasets (per 24-llm-integration.md)
- **CI guardrails** — prevent accidental LLM calls in test environments

All LLM calls must be mockable. No test should require a real provider API key to pass. Cost tracking should still function in mock mode (with mock costs).

For concrete testing patterns, test fixtures, and CI configuration, see **[41-agentic-pydanticai.md](41-agentic-pydanticai.md)**.

---

## API Endpoints

The agent module exposes REST endpoints for:

| Capability | Endpoints |
|-----------|-----------|
| Task submission | Submit requests for agent processing (sync, async, streaming) |
| Task status | Query task status, view reasoning chains, retrieve results |
| Human approval | Approve/reject tasks awaiting human decision |
| Kill switch | Cancel running tasks at task, plan, or system scope |
| Cost reporting | Aggregated cost views by user, agent, model, date |
| Registry | List available agent types and tools |

All endpoints follow the API design standards in **03-backend-architecture.md** (versioned under `/api/v1/`, consistent response envelope, cursor pagination for lists).

For concrete endpoint definitions, request/response schemas, and examples, see **[41-agentic-pydanticai.md](41-agentic-pydanticai.md)**.

---

## Expansion Roadmap

### Phase 1: Execute — Option A (Build Now)

**Delivers:** Single agent execution with full safety, audit, and human control.

| Component | Status |
|-----------|--------|
| AgentTask primitive and data model | Implement |
| Agent registry | Implement |
| Tool registry | Implement |
| LLM provider abstraction | Implement |
| Orchestrator (single agent routing) | Implement |
| Execution engine (ReAct loop) | Implement |
| Safety enforcement (budgets, timeouts, step limits) | Implement |
| Full audit logging | Implement |
| Cost tracking | Implement |
| Human approval gates | Implement |
| Kill switch (API + CLI) | Implement |
| Output validation | Implement |
| Tool sandboxing | Implement |
| Mock mode for testing | Implement |
| API endpoints | Implement |

**What this enables:** A user submits a request, the orchestrator picks an agent, the agent reasons and uses tools, the result comes back with full audit trail and cost tracking. Humans can approve destructive actions and halt runaway agents.

### Phase 2: Plan — Option A → B (When Needed)

**Delivers:** Multi-agent plans with shared context, confidence signaling.

| Component | Status |
|-----------|--------|
| Planner Agent for task decomposition | Implement |
| Step sequencing and dependency management | Implement |
| Shared context between plan steps | Implement |
| Context summarization for long plans | Implement |
| Parallel step execution | Implement |
| Confidence scoring and thresholds | Implement |
| Mid-execution agent escalation to other agents | Implement |

**What this enables:** Complex tasks are broken into steps, each handled by the best agent. Agents share context. The orchestrator manages the flow.

### Phase 3: Remember — Option B + Memory (When Needed)

**Delivers:** Persistent memory across sessions, semantic retrieval.

| Component | Status |
|-----------|--------|
| pgvector extension on PostgreSQL | Implement |
| Memory store service | Implement |
| Memory retrieval (RAG) | Implement |
| Memory lifecycle management | Implement |
| Memory inspection API (human-visible) | Implement |
| Context injection from memory | Implement |

**What this enables:** Agents remember past work. An agent working on a code review can recall patterns from previous reviews. Memory is searchable and inspectable by humans. The orchestrator considers agent expertise when assigning work.

### Phase 4: Learn — Option B + Learning (When Needed)

**Delivers:** Feedback-weighted memory, passive learning through better context.

| Component | Status |
|-----------|--------|
| Feedback collection (human ratings, automated checks) | Implement |
| Feedback storage linked to memory entries | Implement |
| Quality scoring on memory entries | Implement |
| Outcome-weighted memory retrieval | Implement |
| Performance tracking per agent type | Implement |
| Performance-based routing in orchestrator | Implement |

**What this enables:** Agent memory gets better over time. The system serves higher-quality examples from memory. The orchestrator routes tasks to agents with the best track record. This is passive learning — the agent doesn't change, the context it receives improves.

### Phase 5: Autonomy — Option B → C (Future)

**Delivers:** Self-directing agents that propose approaches, delegate to workers, and self-evaluate.

| Component | Status |
|-----------|--------|
| Agent proposal mechanism (agents suggest plans) | Implement |
| Orchestrator approval workflow for agent proposals | Implement |
| Tiered delegation (agent-as-tool) | Implement |
| Trust levels per agent (based on performance history) | Implement |
| Self-evaluation agent (reviews own past work) | Implement |
| Orchestrator role shift to facilitator | Implement |

**What this enables:** Intelligent agents propose approaches based on accumulated expertise. The orchestrator approves rather than dictates. Agents delegate mechanical subtasks to cheap worker agents. The system approaches Option C behavior — agents self-direct, the orchestrator facilitates.

---

## Integration with Existing Architecture

### Module Boundaries

Per **04-module-structure.md**, the agents module:
- Owns its database tables (agent_tasks, agent_memory)
- Exposes a public API via `api.py`
- Communicates with other modules via events and public APIs
- Does not import other modules' internals

### Event Integration

Per **21-event-architecture.md**, the agents module publishes:

| Event | When |
|-------|------|
| `agents.task.created` | New task created |
| `agents.task.completed` | Task finished successfully |
| `agents.task.failed` | Task failed |
| `agents.task.awaiting_approval` | Human input needed |
| `agents.task.cancelled` | Task cancelled (kill switch or budget) |
| `agents.plan.completed` | All steps in a plan completed |
| `agents.cost.warning` | Cost approaching limit |
| `agents.cost.exceeded` | Cost limit hit, execution stopped |

Other modules subscribe to these events. For example, the Telegram module could subscribe to `agents.task.awaiting_approval` to notify the user.

### Background Task Integration

Per **14-background-tasks.md**, agent execution can be triggered by:
- API request (synchronous start, async execution)
- Scheduled task (Taskiq cron triggers orchestrator with predefined input)
- Event subscription (another module's event triggers agent work)

Long-running agent plans execute as background tasks via Taskiq. The API returns the task ID immediately; clients poll or subscribe to events for completion.

---

## Adoption Checklist

When adopting this module:

### Prerequisites
- [ ] 24-llm-integration.md adopted (LLM provider, cost tracking, prompt management)
- [ ] 21-event-architecture.md adopted (Redis Streams for events)
- [ ] 41-agentic-pydanticai.md reviewed for implementation details

### Conceptual Decisions (before implementation)
- [ ] Declare AgentTask as project primitive per 02-primitive-identification.md
- [ ] Decide which phases to implement initially (Phase 1 minimum)
- [ ] Identify initial agent types needed for your domain
- [ ] Identify tools agents will need access to
- [ ] Define budget limits (per task, per plan, per user, system-wide)
- [ ] Define human-in-the-loop requirements (which actions need approval)
- [ ] Decide notification channel for human-needed events

### Implementation
Follow the phase-by-phase implementation checklist in **[41-agentic-pydanticai.md](41-agentic-pydanticai.md)**.

---

## Related Documentation

- [41-agentic-pydanticai.md](41-agentic-pydanticai.md) — **Implementation guide** using PydanticAI (module structure, code patterns, testing, configuration)
- [44-multi-channel-gateway.md](44-multi-channel-gateway.md) — Multi-channel delivery, session management, channel adapters, real-time push
- [02-primitive-identification.md](02-primitive-identification.md) — Primitive definition process
- [24-llm-integration.md](24-llm-integration.md) — LLM provider, prompts, cost management
- [21-event-architecture.md](21-event-architecture.md) — Event bus for agent events
- [14-background-tasks.md](14-background-tasks.md) — Taskiq for scheduled agent work
- [10-observability.md](10-observability.md) — Logging standards
- [05-authentication.md](05-authentication.md) — RBAC for agent API access
- [04-module-structure.md](04-module-structure.md) — Module boundaries and communication
- [46-event-session-architecture.md](46-event-session-architecture.md) — Concrete implementation of session model, plan management (mutable DAGs with dependency tracking), memory architecture (episodic/semantic/procedural with anchored rolling summaries), and approval gates (unified responder pattern with Temporal Signals). Read this for implementation; read doc 40 for concepts.
