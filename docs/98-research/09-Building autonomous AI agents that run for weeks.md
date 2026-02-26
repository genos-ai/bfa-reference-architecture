# Building autonomous AI agents that run for weeks

**PydanticAI now offers native durable execution through Temporal and DBOS, making it possible to build AI agents that maintain full state, recover from crashes, and accept human input across tasks spanning days or weeks.** This represents a fundamental shift from ephemeral agent runs to persistent, observable, interruptible autonomous systems. The key architectural insight: separate orchestration durability (owned by Temporal or DBOS) from domain state (owned by PostgreSQL), with PydanticAI's type-safe agent framework bridging both layers. Combined with hierarchical coordinator-worker patterns, DAG-based plan management, and structured memory systems, production teams can now deploy agents that plan, execute, pause for human review, recover from failures, and resume — all without losing a single step of progress.

---

## Durable execution is the foundation — and PydanticAI ships it natively

The single most important capability for long-running agents is **durable execution**: the guarantee that a multi-step workflow survives crashes, deploys, API timeouts, and infrastructure failures without re-executing completed work. PydanticAI (v1.63.0, GA since September 2025) provides first-party integration with three durable execution engines.

**Temporal + PydanticAI** is the most battle-tested option. The `TemporalAgent` wrapper automatically separates agent code into deterministic Workflows (coordination logic) and non-deterministic Activities (LLM calls, tool invocations, MCP communication). On failure, Temporal replays the workflow history, skipping completed activities and resuming from the exact failure point. The official `pydantic-ai-temporal-example` repository demonstrates a Slack bot with multi-agent coordination and human-in-the-loop signals. Temporal's Signals enable workflows to sleep for days waiting for human input, then resume precisely where they stopped. The tradeoff is operational complexity — you need Temporal Server (or Temporal Cloud at ~$200/month) plus PostgreSQL.

```python
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalAgent, PydanticAIPlugin

agent = Agent('openai:gpt-4o', name='researcher')
temporal_agent = TemporalAgent(agent)

# Worker automatically handles crash recovery and replay
worker = Worker(
    client, task_queue="research-queue",
    workflows=[temporal_agent.workflow()],
    activities=temporal_agent.activities(),
    plugins=[PydanticAIPlugin(__pydantic_ai_agents__=[temporal_agent])],
)
```

**DBOS + PydanticAI** offers the simplest path — roughly **7 lines of code** added to an existing PydanticAI app. DBOS runs fully in-process as a library with no separate server. It checkpoints every workflow step to PostgreSQL (or SQLite for development). The `DBOSAgent` wrapper makes any PydanticAI agent durable. The official demo app shows a multi-agent deep research system with a planning agent (Claude Sonnet), search agents (Gemini Flash), and a synthesis agent, all with automatic crash recovery.

**Inngest and Hatchet** are alternatives without native PydanticAI integration. Inngest excels at event-driven workflows with `step.wait_for_event()` for human-in-the-loop, but its AgentKit is TypeScript-only. Hatchet provides durable events and high-throughput task queuing backed by PostgreSQL. Both require manual wrapping of PydanticAI agent calls inside their step functions.

| Capability | Temporal | DBOS | Inngest | Hatchet |
|---|---|---|---|---|
| **PydanticAI integration** | Native `TemporalAgent` | Native `DBOSAgent` | Manual wrapping | Manual wrapping |
| **Human-in-the-loop** | Signals + wait_condition | Notifications (send/recv) | wait_for_event (native) | Durable events (native) |
| **Deployment complexity** | High (Server + DB + Workers) | Very low (pip install + Postgres) | Medium (SaaS or K8s) | Medium (Engine + Postgres) |
| **Crash recovery model** | Deterministic replay | Resume from last checkpoint | Step retry + cached results | Durable task resume |
| **Workflow versioning** | Worker Versioning + Patches | Patching support | Function versioning | Workflow versioning |

For tasks spanning weeks, **Temporal is the recommended choice** when reliability is paramount. **DBOS is ideal** when you want durable execution with minimal infrastructure overhead alongside an existing FastAPI app.

---

## Hierarchical orchestration through coordinator agents with typed delegation

The coordinator-worker pattern is the dominant architecture for complex autonomous tasks. A horizontal coordinator agent decomposes goals into subtasks, delegates to vertical (domain-specific) agents, tracks progress, and synthesizes results. Five frameworks implement this pattern with meaningfully different approaches.

**PydanticAI's delegation model** uses the `@agent.tool` decorator: the coordinator agent calls worker agents as tool functions, each worker runs its own agent loop with its own model and tools, and returns a Pydantic-validated output. This is explicit, type-safe, and composable. Different models can power each agent — GPT-5 for coordination, Gemini Flash for fast retrieval, Claude for analysis — with `ctx.usage` tracking aggregate token costs across the hierarchy.

```python
coordinator = Agent('openai:gpt-5', instructions='Decompose research goals and delegate.')
researcher = Agent('google-gla:gemini-3-flash', output_type=ResearchReport)

@coordinator.tool
async def research_topic(ctx: RunContext[None], topic: str) -> ResearchReport:
    result = await researcher.run(f'Research: {topic}', usage=ctx.usage)
    return result.output
```

**LangGraph's supervisor pattern** (`langgraph-supervisor` package) uses `create_supervisor()` with `create_handoff_tool` for routing between agents. Its strongest feature is **checkpointing** — `PostgresSaver` persists state at every graph node, enabling pause/resume, time-travel debugging, and crash recovery. LangChain now recommends implementing the supervisor pattern directly via tool-calling for more control over context engineering.

**CrewAI's hierarchical process** (`Process.hierarchical`) auto-creates a manager agent that allocates tasks based on agent roles and capabilities. The `planning=True` flag generates execution plans before starting. However, CrewAI **lacks built-in durable execution** — there is no checkpoint/recovery mechanism for multi-day tasks, and community reports indicate reliability issues with the manager looping or failing to find agents.

**AutoGen/AG2's GroupChat** manager uses LLM-based speaker selection to coordinate agents in a shared conversation. The newer AgentChat API (v0.4+) adds `AgentTool` for wrapping agents as tools and `GraphFlow` for directed workflows. AutoGen offers the most flexible conversation model but can be unpredictable — conversations may loop or diverge without careful `max_round` tuning. The framework is currently transitioning to Microsoft Agent Framework.

**OpenAI Agents SDK** provides clean handoff primitives — agents list other agents as `handoffs`, and the LLM generates `transfer_to_<name>` tool calls. Session persistence supports PostgreSQL via `SQLAlchemySession`. However, there is **no built-in durable execution** — sessions handle conversation persistence, not workflow durability.

For long-running autonomous tasks, **PydanticAI + Temporal** is the clear winner: native durable execution means multi-day workflows survive any failure, typed delegation ensures reliable coordinator-worker communication, and Temporal Signals provide robust human-in-the-loop. The recommended architecture:

```
FastAPI → Temporal Workflow (persisted, survives crashes)
  → Coordinator Agent (decomposes goal, manages plan)
    → Worker Agent 1 (domain-specific, runs as Temporal Activity)
    → Worker Agent 2 (different model, different tools)
  → Human-in-the-loop via Temporal Signals
  → Resume after days/weeks with full state intact
```

---

## DAG-based plan management with persistent task tracking

Agents managing multi-step plans over weeks need structured task decomposition, dependency tracking, and failure recovery. The dominant pattern is a **Directed Acyclic Graph** of tasks stored in PostgreSQL.

**The LLMCompiler pattern** (from LangChain/LangGraph research) represents the most mature plan-and-execute implementation. A planner streams a DAG where each task contains a tool, arguments, and dependency references using variable syntax (`search("${1}")`). A Task Fetching Unit schedules tasks as dependencies complete, enabling **parallel execution of independent branches** with a claimed 3.6x speedup. A Joiner component evaluates results and decides whether to respond, replan, or escalate.

The task state machine should track these transitions:

```
pending → ready (all dependencies met)
ready → in_progress (executor picks up)
in_progress → completed | failed | waiting_for_input | waiting_for_approval
waiting_for_input → in_progress (input received)
failed → ready (retry after plan revision)
```

A production PostgreSQL schema needs five core tables: **plans** (top-level goals with versioning), **tasks** (DAG nodes with status, assigned model, input/output data), **task_dependencies** (DAG edges with dependency types), **task_attempts** (audit trail of every execution attempt with token usage and cost), and **plan_decisions** (log of every decision — who decided what and why). The `plan_decisions` table is critical for observability: it records plan creation, task additions, reorderings, revisions, escalations, and human overrides with full reasoning.

```sql
-- Find tasks ready to execute (all dependencies satisfied)
SELECT t.* FROM tasks t
WHERE t.plan_id = :plan_id AND t.status = 'pending'
AND NOT EXISTS (
    SELECT 1 FROM task_dependencies td
    JOIN tasks dep ON dep.id = td.depends_on_task_id
    WHERE td.task_id = t.id AND dep.status != 'completed'
);
```

**Plan revision beats replanning.** When a task fails, modifying the remaining plan (plan repair) outperforms generating an entirely new plan — particularly when downstream dependencies remain valid, other systems have been notified, or completed work would need re-execution. The Deep Agent research (arXiv 2502.07056) introduces Hierarchical Task DAGs where "at each planner invocation, the task DAG is created, modified, or expanded given the available information and context at the moment." Plans are living documents.

**No-progress detection** prevents agents from spinning. Track recent tool invocations and workspace state hashes — if the same call repeats without meaningful change, trigger replanning or human escalation. The Cline agent community documented this pattern extensively.

---

## Human-in-the-loop through Temporal Signals, Queries, and unified responders

Long-running agents need three human interaction modes: **checking in** (read-only progress inspection), **approval gates** (pausing for decisions), and **plan modification** (changing direction mid-execution). Temporal provides the cleanest primitives for all three.

**Temporal Queries** are synchronous, read-only calls that return workflow state without interrupting execution. A FastAPI endpoint calls `handle.query(AgentPlanWorkflow.get_status)` to return current task, progress percentage, completed tasks, and blocked items. This powers dashboards, CLI tools, and monitoring systems.

**Temporal Signals** are asynchronous messages that deliver human input to a waiting workflow. When a task requires approval, the workflow calls `await workflow.wait_condition(lambda: self._approval is not None)` — this can sleep for hours or days, surviving crashes and restarts. When a human clicks "Approve" in Slack or a dashboard, a Signal delivers the decision and the workflow resumes instantly.

```python
@workflow.signal
async def submit_approval(self, decision: ApprovalDecision):
    self._approval = decision

@workflow.signal
async def modify_plan(self, modifications: dict):
    # Add, remove, or reorder tasks mid-execution
    self._plan = apply_modifications(self._plan, modifications)
```

**The unified responder pattern** makes pause-and-ask work identically for humans and AI. The `InputResponse` dataclass includes a `responder_type` field ("human", "ai_agent", or "automated_rule") — the same Signal accepts input from a person clicking a button, an AI triage agent auto-responding to simple clarifications, or an automated rule engine. This enables **AI-in-the-loop escalation**: when a task exceeds the assigned model's capability, escalate through a chain (e.g., Haiku → Sonnet → Opus → human), with each level attempting the task before passing upward.

**Notification mechanisms** work as Temporal Activities. When an agent needs attention, it executes a `send_notification` activity that fires Slack webhooks (with approve/reject buttons linking back to FastAPI endpoints), emails, or generic webhooks. **Durable timers** enable automatic escalation — if no approval arrives within 4 hours, re-notify with higher urgency or escalate to a manager.

For observability platforms, **Langfuse** (22,300 GitHub stars, MIT license, self-hostable) is the recommended default for agent monitoring. **Pydantic Logfire** provides seamless native integration with PydanticAI via OpenTelemetry. Both support multi-agent trace visualization, token usage tracking, and cost monitoring.

---

## Persistent memory across weeks requires layered context assembly

When agents work for weeks, raw conversation history explodes past context window limits. The solution is a **hierarchical memory architecture** that layers compressed history, retrieved memories, and recent verbatim messages.

**PydanticAI's `ModelMessagesTypeAdapter`** handles serialization of conversation history to JSON for database storage. The `history_processors` feature intercepts and transforms message history before each model request — this is the hook for implementing summarization and context management. A cheaper model (GPT-5-mini) can handle summarization while the primary model focuses on reasoning.

**Factory.ai's anchored rolling summary** pattern (published July 2025) is the most effective production compression strategy. It maintains a persistent summary anchored to a specific message index. When compression triggers, only the newly dropped message span gets summarized and merged into the existing summary — **never re-summarizing already-summarized content**. The summary preserves four critical categories: session intent (original goals), high-level play-by-play (sequence of major actions), artifact trail (files created/modified with paths), and breadcrumbs (identifiers needed for re-fetching context). Structured summarization with explicit sections significantly outperforms generic summarization — OpenAI-style compression discards file paths as "low-entropy content," which breaks agent continuity.

**The three memory types** map to different storage strategies, all unifiable in PostgreSQL with pgvector:

- **Episodic memory** (what happened): Events, conversations, outcomes stored as vectors with rich metadata. Agent queries: "Have I encountered similar migration issues?" retrieves relevant past episodes via semantic similarity.
- **Semantic memory** (what was learned): Facts and relationships extracted from episodes. Mem0's architecture (arXiv 2504.19413) implements a two-phase pipeline — extract salient facts, then compare against existing memories to merge duplicates and resolve contradictions. This achieved **26% accuracy improvement** over full-context approaches with **90% token savings**.
- **Procedural memory** (how to do things): Successful strategies and tool usage patterns stored in relational tables with success rates and usage counts.

**The optimal context window assembly** for a week-long task follows this structure: system prompt with agent identity and current task (~2K tokens) → core memory blocks with task status and key decisions (~4K) → rolling summary of all prior work (~8K) → relevant memories retrieved via vector search (~4K) → last 10-20 verbatim messages (remaining budget). PydanticAI's `history_processors` can implement this assembly, using `RunContext` to access the database pool and memory stores.

```python
async def build_context(ctx: RunContext[AgentDeps], messages: list[ModelMessage]):
    summary = await ctx.deps.summary_store.get_latest(ctx.deps.task_id)
    memories = await ctx.deps.memory_store.search(
        query=str(messages[-1]), task_id=ctx.deps.task_id, limit=5
    )
    return [summary_as_message(summary)] + [memories_as_message(memories)] + messages[-20:]

agent = Agent('openai:gpt-5', deps_type=AgentDeps, history_processors=[build_context])
```

**The Letta/MemGPT approach** takes this further: agents actively manage their own memory via tool calls (`archival_memory_insert`, `archival_memory_search`, `memory_replace`), treating the context window like RAM and vector storage like disk. Their "sleep-time compute" addition runs background agents that reorganize and consolidate memory during idle periods.

**The hybrid state architecture rule**: Temporal owns orchestration state (workflow position, retry counts, signal queues). PostgreSQL owns domain state (conversation history, memories, plan/task records, decision logs). Never store large data in Temporal's event history — it bloats replay. Store references and fetch from the database in activities.

---

## Production systems and tools that exist today

Several production-grade implementations demonstrate these patterns in practice. The **PydanticAI + Temporal example repo** (github.com/pydantic/pydantic-ai-temporal-example) shows a complete Slack bot with multi-agent coordination and human-in-the-loop. The **DBOS demo apps** include a multi-agent deep research system with planning, parallel search, and synthesis agents. A third-party extension, `temporal-pydanticai-codeact`, combines PydanticAI's Temporal integration with Docker sandboxing for code-executing agents.

**Julep** (6,617 GitHub stars) is a serverless platform that uses Temporal under the hood for workflow scheduling, with YAML-based task definitions supporting branching, loops, and a "Wait for Input" step for human-in-the-loop. It has real production deployments at companies like Reclaim Protocol and Essentially Sports. **Letta** (formerly MemGPT, backed by $10M from a16z) is the leader in persistent agent memory, with self-editing memory blocks, git-based context repositories, and the Conversations API for shared memory across parallel experiences.

**LangGraph** (16,400 stars) provides the most widely adopted agent orchestration with `langgraph-checkpoint-postgres` (v3.0.4) for production persistence, time-travel debugging, and the LangGraph Platform for managed deployment. Production users include Klarna, Replit, and Elastic. **Prefect** also has native PydanticAI integration via `PrefectAgent`, with transactional semantics in Prefect 3.0 and auto-generated UI forms for approval workflows.

For observability, **Langfuse** (22,300 stars, MIT) provides comprehensive LLM tracing with OpenTelemetry support and a free tier of 50K events/month. **Arize Phoenix** offers open-source tracing with strong evaluation capabilities under Elastic License 2.0. **Pydantic Logfire** integrates natively with PydanticAI, Temporal, DBOS, and Prefect traces.

Anthropic's engineering team published "Effective Harnesses for Long-Running Agents," documenting two key failure modes — agents trying to do too much at once, and agents declaring done prematurely — with the solution being spec-driven development, incremental feature-by-feature progress, and clean state management at session boundaries.

---

## Conclusion: the recommended architecture stack

The production architecture for autonomous agents spanning days or weeks combines five layers. **PydanticAI** provides the agent framework with type-safe delegation, multi-model support, and native durable execution hooks. **Temporal** (or DBOS for simpler deployments) provides crash recovery, long-running waits, and human-in-the-loop via Signals and Queries. **PostgreSQL with pgvector** stores plans, tasks, decision logs, conversation history, and all three memory types in a single queryable database. **FastAPI** exposes REST endpoints for dashboards, approvals, and plan modifications. **Langfuse or Pydantic Logfire** provides end-to-end observability across the entire agent execution.

The most underappreciated insight from this research: **plans must be mutable, versioned documents** — not static blueprints. Every decision (plan creation, task revision, human override, model escalation) should be logged with full reasoning in a `plan_decisions` table. The unified responder pattern — where Signals accept input from humans, AI agents, or automated rules identically — eliminates the artificial boundary between human-in-the-loop and AI-in-the-loop, creating a system where any capable responder can unblock a waiting agent. This architectural choice, more than any individual framework selection, determines whether a long-running agent system succeeds in production.