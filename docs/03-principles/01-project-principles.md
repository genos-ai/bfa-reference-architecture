# Project Principles

Guiding principles for all architectural decisions, plans, and implementation work in this project. These are non-negotiable — every plan and PR should be evaluated against them.

---

## P1: Infrastructure Before Agents

**Build the platform first. Agents are cheap to add on top of solid infrastructure.**

We invest upfront in sessions, event streaming, the coordinator, plan management, and delegation — so that adding a new agent is a YAML file and a thin Python module, not a refactoring project. The cost of retrofitting infrastructure under existing agents is always higher than building it right once.

This means:
- Plans 10-15 (event bus, sessions, streaming coordinator, delegation, plan management, Temporal) are the foundation. They ship before we build more vertical agents.
- When choosing between "build an agent now and adapt infrastructure later" vs. "build infrastructure now and agents drop in later" — choose infrastructure.
- A new agent should require: one YAML config, one `agent.py` with `create_agent()` / `run_agent()`, and optionally shared tool wrappers. Nothing else.

**Test:** Can a developer add a fully functional agent in under an hour without touching coordinator, session, or infrastructure code? If not, the platform isn't ready.

---

## P2: Deterministic Over Non-Deterministic

**Never use an agent where a tool will do the job faster, cheaper, and better.**

An LLM call is non-deterministic, slow, and expensive. A deterministic tool is predictable, fast, and free. If a task can be solved with a regex, a SQL query, a rule engine, or any deterministic logic — that's a tool, not an agent task. Agents are for reasoning, judgment, and ambiguity. Everything else is a tool.

This means:
- Compliance scanning uses deterministic regex rules (tools), not an LLM reading code and guessing.
- File listing, search, and filtering are tools. An agent decides *what* to search for.
- Routing by keyword match is a tool. An agent handles only the ambiguous cases the rules can't resolve.
- DAG traversal, cycle detection, and ready-task queries are deterministic algorithms, not agent reasoning.
- Cost calculation, budget enforcement, and state machine transitions are pure functions.

**Test:** Before adding an LLM call, ask: "Would a deterministic function produce the same or better result?" If yes, write the function.

---

## P3: Breaking Changes Are Free (During Dev)

**We are in dev mode. We have not shipped to production. We do not carry backward-compatibility debt.**

This means:
- Refactor in-place. No shims, no `_legacy` aliases, no deprecation wrappers.
- Delete what's replaced. Don't comment it out or re-export unused symbols.
- Rename freely when the new name is clearer.
- Tests that break because of interface changes get rewritten, not patched around.

**Expires:** When we ship the first production deployment, this principle is replaced by a versioning and migration strategy.

---

## P4: Scope Is Configuration, Not Code

**What an agent can do is defined in YAML. How it does it is defined in Python.**

Agent capabilities (tools, filesystem access, delegation targets, model selection, budget) are declared in YAML config and injected via dependency injection. Changing an agent's permissions, model, or tool access is a config change, not a code change.

This means:
- `AgentConfigSchema` validates every agent YAML at load time.
- `FileScope` enforces read/write paths from config, not from hardcoded logic.
- Delegation allowlists, budget caps, and model selection come from YAML.
- Adding an agent to a new project with different permissions = different YAML, same Python.

---

## P5: Streaming Is the Default Path

**Every agent interaction produces a typed event stream. Synchronous responses are the degraded case.**

The coordinator's `handle()` returns `AsyncIterator[SessionEvent]`. Every channel (API, TUI, Telegram, MCP, A2A) consumes the same event stream. Callers that need a synchronous result call `collect()` which drains the iterator.

This means:
- There is no separate synchronous execution path. One code path, always.
- Events are both yielded to the caller AND published to the session event bus.
- Error handling yields error events instead of throwing — the stream always terminates cleanly.

---

## P6: The Coordinator Is Infrastructure, Not Intelligence

**The coordinator routes, enforces, tracks, and yields events. It does not reason, plan, or make domain decisions.**

The coordinator is a state machine. It applies middleware (cost tracking, guardrails, budget enforcement), routes to agents, and manages the event stream. Domain intelligence belongs in agents. Strategic intelligence belongs in horizontal agents. The coordinator never calls an LLM.

This means:
- All delegation goes through the coordinator, ensuring middleware always applies.
- Adding a new concern (logging, tracing, rate limiting) happens in coordinator middleware, not in agent code.
- Horizontal agents (like the PM agent) are the ones that reason about which agent to call — but they delegate through the coordinator, never directly.

---

## P7: Separate Implementation from Registration

**Tool implementations are pure functions. Tool registrations are thin wrappers.**

Shared tools (filesystem, compliance scanning, delegation) are implemented as plain Python functions with no PydanticAI dependency. Agent files contain thin `@agent.tool` wrappers that call the shared implementation, passing scope from deps.

This means:
- Tools are testable as plain functions without any agent runtime.
- Multiple agents reuse the same tool implementations with different scopes.
- PydanticAI version changes don't break tool logic.

---

## P8: Plan Revision Over Replanning

**When a task fails, modify the remaining plan. Don't throw away completed work.**

Failed tasks trigger retry → revision → escalation. Revision means adjusting remaining tasks and dependencies while preserving completed work. Full replanning is a last resort.

This means:
- The plan data model supports mutable task graphs with version tracking.
- Completed tasks and their outputs are immutable after completion.
- Every decision (retry, revise, escalate) is logged in an audit trail with reasoning.

---

## P9: Temporal Owns Orchestration, PostgreSQL Owns Domain

**Never mix durable execution state with business data.**

Temporal manages workflow position, retry counts, signal queues, and durable timers. PostgreSQL manages conversations, plans, decisions, and domain entities. Activities bridge between them by reading/writing PostgreSQL and reporting results to Temporal.

This means:
- No large data in Temporal event history — Activities pass IDs, not objects.
- ORM objects never cross the Temporal boundary — serializable dataclasses (DTOs) do.
- The system works without Temporal (Tiers 1-3). Temporal activates only for Tier 4.

---

## P10: Every Phase Is an Expansion, Not a Rewrite

**New capabilities layer on top of existing ones. Existing patterns remain unchanged.**

Stateless CRUD endpoints continue to work without sessions. Simple agent calls work without plan management. Sessions work without Temporal. Each tier of complexity is opt-in.

This means:
- `GET /api/v1/notes` never creates a session or touches the event bus.
- A one-shot agent call can auto-create an ephemeral session transparently.
- The graduated complexity model: Tier 1 (CRUD) → Tier 2 (stateless agent) → Tier 3 (interactive session) → Tier 4 (long-running autonomous).

---

## P11: Test Without LLMs

**CI never makes a real LLM call. Tests use deterministic fixtures.**

PydanticAI's `TestModel` and `ALLOW_MODEL_REQUESTS = False` are enforced globally. Agent tests verify tool wiring, schema validation, and control flow — not LLM quality. Integration tests that need realistic responses use recorded fixtures.

This means:
- Tests are fast, deterministic, and free.
- Every agent test uses `TestModel(call_tools=[...])` to simulate specific tool sequences.
- Flaky tests from LLM variability don't exist.

---

## P12: Test Against Real Infrastructure

**Tests run against the live platform. Mock only what you don't operate.**

A test that mocks the database proves your mock works, not your code. Tests connect to real PostgreSQL, real Redis, real FastStream, and real Temporal. Write operations use transaction rollback so tests don't pollute data, but every query, constraint, and subscription exercises the real system.

This means:
- Service tests call real repositories against real PostgreSQL. No mocked sessions, no mocked repos.
- Event bus tests publish and subscribe on real Redis. No `AsyncMock(return_value=1)`.
- Temporal tests use the real Temporal test server, not mocked workflow execution.
- The only mocks are for external services you don't operate: LLM providers (TestModel per P11), Telegram API, third-party webhooks.
- Tests that pass against mocks but fail against real infrastructure are worthless — they hide bugs instead of catching them.

**Test:** If you remove all mocks from a test and it breaks, was it testing your code or testing your mocks?
