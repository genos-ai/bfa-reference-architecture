# Change Specification: Integrating Doc 31 (Event-Driven Session Architecture)

> **Historical note (v3.0.0):** Doc numbers in this spec were written against the pre-3.0.0 numbering scheme. All references have been mechanically updated to current numbers. See `00-overview.md` for the authoritative document index.

*Spec Version: 1.0.0*
*Date: 2026-02-26*
*Triggered by: Addition of `46-event-session-architecture.md` to the reference architecture*

---

## Summary

Doc 31 introduces an event-driven session model that unifies all interactive and agent-driven operations under a single architecture. Sessions replace requests as the primitive for any operation involving conversation, streaming, agent plans, or multi-step workflows. This document specifies exactly what must change in every affected document, why, and what the resulting text should look like. Documents not listed here require zero changes.

The new doc is located at `docs/99-reference-architecture/46-event-session-architecture.md` and is already complete (1,522 lines, v1.0.0). This spec covers only the ripple effects into existing documents.

---

## Priority Classification

| Priority | Documents | Rationale |
|----------|-----------|-----------|
| **Must change** (structural — doc 31 is invisible without these) | `00-overview.md`, `21-event-architecture.md`, `41-agentic-pydanticai.md`, `44-multi-channel-gateway.md`, `AGENTS.md` | These documents either register doc 31 in the architecture index, or contain patterns that doc 31 supersedes for interactive operations. Without these changes, an AI reading the architecture will not know doc 31 exists or will generate conflicting patterns. |
| **Should change** (alignment — reduces confusion) | `03-backend-architecture.md`, `40-agentic-architecture.md`, `27-tui-architecture.md`, `43-ai-first-interface-design.md` | These documents describe patterns that doc 31 extends. Cross-references prevent an AI from implementing the older pattern when the session-aware version should be used. |
| **No change needed** | All other docs (01, 02, 04, 05, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 27) | These documents either cover concerns orthogonal to the session model (security, testing, deployment, frontend, coding standards) or already define patterns that doc 31 consumes without modification (doc 27 — MCP/A2A are event producers, unchanged). |

---

## Change 1: `00-overview.md` — Register Doc 31 and Update Metadata

### Why

Doc 31 does not appear in the overview's Optional Modules table, the dependency tree, the decision criteria table, or the scope section. An AI reading only `00-overview.md` (which is the entry point for the entire architecture) will not know doc 31 exists. This is the highest-priority change.

### Change 1.1: Bump Version

**Location**: Line 3 (the `*Version:` line)

**Current**:
```
*Version: 2.3.0*
```

**Replace with**:
```
*Version: 2.4.0*
```

### Change 1.2: Add Changelog Entry

**Location**: Immediately after the line `## Changelog` and before the first `- 2.3.0` entry.

**Insert**:
```markdown
- 2.4.0 (2026-02-26): Added 46-event-session-architecture.md for event-driven sessions, streaming coordinator, plan management, memory architecture, approval gates; updated dependency tree
```

### Change 1.3: Add to Optional Modules Table

**Location**: The table under `### Optional Modules` — after the row for `44-multi-channel-gateway.md`.

**Insert new row**:
```markdown
| 43-ai-first-interface-design.md | AI-first interface design — adapter registry, self-describing APIs, intent/planning APIs, service factory, CLI AI patterns. Requires 03, 04, 14, 27. |
| 46-event-session-architecture.md | Event-driven session architecture — session model, event bus, streaming coordinator, plan management as mutable DAGs, memory architecture (episodic/semantic/procedural), approval and escalation with unified responder pattern, cost tracking, observability. Requires 03, 06, 25, 26. |
```

**Note**: Doc 30 may already be in the table if it was added earlier in this session. If so, only add the doc 31 row.

### Change 1.4: Add to Decision Criteria Table

**Location**: The table under `### Decision Criteria` — after the row for `44-multi-channel-gateway.md`.

**Insert new rows**:
```markdown
| 43-ai-first-interface-design.md | Making services consumable by AI agents (Cursor, Claude Code, external orchestrators) alongside human clients |
| 46-event-session-architecture.md | Interactive conversations, streaming agent responses, multi-step plans with approval gates, long-running autonomous tasks, multi-channel sessions |
```

**Note**: Same caveat as above — doc 30 row may already exist.

### Change 1.5: Update Context Paragraph

**Location**: The paragraph in the `## Context` section that lists optional modules. It currently reads:

```
Optional modules — Data Layer (05), Events (06), Frontend (07), LLM (08), Telegram (20, 23), Agentic AI (25, 26), Agent-First Infrastructure (27), TUI (28), Multi-Channel Gateway (29) — extend the core when projects need those capabilities.
```

**Replace with**:
```
Optional modules — Data Layer (05), Events (06), Frontend (07), LLM (08), Telegram (20, 23), Agentic AI (25, 26), Agent-First Infrastructure (27), TUI (28), Multi-Channel Gateway (29), AI-First Interface Design (30), Event-Driven Sessions (31) — extend the core when projects need those capabilities.
```

### Change 1.6: Update Optional Scope Section

**Location**: The `### Optional Scope (via modules)` bullet list.

**Append**:
```markdown
- Event-driven session architecture (persistent sessions, streaming coordinators, plan management, agent memory)
```

### Change 1.7: Update Dependency Tree

**Location**: The ASCII dependency tree under `### Module Dependencies`.

**Add a new block** for doc 31 after the existing blocks. The positioning should be after the doc 29 block:

```
┌─────────────────────────────────────┐
│  46-event-session-architecture.md   │
│  (optional — interactive sessions,  │
│   streaming, plans, memory, HITL)   │
└──────────┬──┬──────────┬──┬────────┘
           │  │          │  │
    ┌──────┘  │   ┌──────┘  └──────┐
    │         │   │                │
    ▼         ▼   ▼                ▼
┌──────────┐ ┌──────────┐  ┌──────────────────┐
│03-backend│ │21-events │  │25+26 agentic     │
│  (core)  │ │(optional)│  │    (optional)     │
└──────────┘ └──────────┘  └──────────────────┘
```

### Change 1.8: Add Adoption Rule

**Location**: After the existing adoption rules (e.g., "If adopting 44-multi-channel-gateway.md...").

**Insert**:
```markdown
If adopting 46-event-session-architecture.md, also adopt 03-backend-architecture.md (core, always present), 21-event-architecture.md (event primitives), 40-agentic-architecture.md (agent concepts), and 41-agentic-pydanticai.md (PydanticAI implementation). Doc 31 composes with 29 (channels become event subscribers) and 30 (service factory accepts optional Session context) but does not require them.
```

---

## Change 2: `21-event-architecture.md` — Extend with Session Events

### Why

Doc 06 defines the event primitives (Redis pub/sub, event envelope format, naming conventions). Doc 31 introduces 15+ session-specific event types (`session.message.user`, `session.agent.thinking`, `session.agent.tool_call`, `session.agent.response.chunk`, `session.approval.requested`, `session.plan.created`, `session.cost.updated`, etc.) that follow doc 06's conventions but extend them significantly. Without updating doc 06, an AI implementing events will use the base patterns and miss the session event superset.

### Change 2.1: Add Cross-Reference Section

**Location**: At the end of the document, before any `## Related Documentation` section (or at the very end if none exists).

**Insert**:
```markdown
---

## Session Events (Extended by Doc 31)

When the project adopts `46-event-session-architecture.md`, the event system defined in this document becomes the transport layer for session events. Session events are a superset of the module events defined above — they follow the same envelope format, naming conventions, and Redis pub/sub transport, but add:

- **Session-scoped channels**: Events are published to `session:{session_id}` channels in addition to module-level channels. Channel adapters (Telegram, TUI, WebSocket) subscribe to session channels.
- **Typed event classes**: Doc 31 defines `SessionEvent` as the base class with 15+ typed subclasses (`UserMessageEvent`, `AgentThinkingEvent`, `AgentToolCallEvent`, `AgentResponseChunkEvent`, `ApprovalRequestedEvent`, `PlanCreatedEvent`, `CostUpdateEvent`, etc.). All extend the event envelope defined in this document.
- **Event deserialization registry**: A type-discriminated registry maps `event_type` strings to Pydantic event classes for safe deserialization from Redis.
- **Dual transport**: Redis pub/sub for real-time delivery (same as this document); Temporal event history for durable replay in Tier 4 long-running workflows.

The module-level event patterns in this document remain unchanged for non-session inter-module communication (e.g., `users.user.created`, `orders.order.completed`). Session events are for interactive operations only.

See `46-event-session-architecture.md`, Section 2 (Event Bus) for the complete event type hierarchy, deserialization registry, and transport configuration.
```

### Change 2.2: Add to Related Documentation (if section exists)

**Insert**:
```markdown
- [46-event-session-architecture.md](46-event-session-architecture.md) — Session-scoped events, typed event classes, streaming coordinator
```

---

## Change 3: `41-agentic-pydanticai.md` — Add Session-Aware Patterns

### Why

Doc 26 defines how PydanticAI agents are structured: `Agent()` instances, `@agent.tool` decorators, `RunContext[AgentDeps]`, and the `run()` method. Doc 31 introduces three changes that affect how agents are invoked:

1. **`run_stream()` replaces `run()` as the primary invocation** — the coordinator calls `agent.run_stream()` and yields events from the stream. `run()` is still valid for background/batch operations but is no longer the default interactive path.
2. **`handle()` is the universal entry point** — all interactive operations go through `coordinator.handle(session_id, message)` which returns `AsyncIterator[Event]`. Direct `agent.run()` calls bypass session tracking, cost enforcement, and event emission.
3. **Session context in `AgentDeps`** — the dependency injection container should optionally carry a `Session` reference so tools can access session metadata (cost budget remaining, conversation history pointer, active plan).

### Change 3.1: Add Session Integration Section

**Location**: After the main agent patterns section (after the section on agent tools and before the testing section, or at a logical break point).

**Insert**:
```markdown
---

## Session-Aware Agent Invocation (Doc 31)

When the project adopts `46-event-session-architecture.md`, agent invocation changes from direct `run()` calls to coordinator-mediated streaming.

### Primary Path: `run_stream()` via Coordinator

All interactive agent invocations go through the streaming coordinator, which calls `agent.run_stream()` internally:

```python
# modules/backend/agents/coordinator/handle.py
from pydantic_ai import Agent

async def handle(session_id: str, message: str) -> AsyncIterator[Event]:
    session = await session_service.get(session_id)
    agent = agent_router.resolve(message, session)
    deps = AgentDeps(session=session, db=session.db)

    async with agent.run_stream(message, deps=deps) as stream:
        async for chunk in stream.stream_text(delta=True):
            yield AgentResponseChunkEvent(session_id=session_id, content=chunk)

    yield AgentResponseCompleteEvent(session_id=session_id, content=stream.result.data)
```

### When to Use Direct `run()`

Direct `agent.run()` is still appropriate for:
- Background tasks that do not have an interactive session (Taskiq jobs)
- Batch processing where streaming is irrelevant
- Unit tests where you need a synchronous result

Direct `run()` bypasses session cost tracking, event emission, and approval gates. Use it only when these features are not needed.

### Extended AgentDeps

Add an optional `Session` field to the dependency container:

```python
# modules/backend/agents/dependencies.py
from dataclasses import dataclass
from modules.backend.services.base import BaseService

@dataclass
class AgentDeps:
    db: AsyncSession
    session: Session | None = None  # Present for interactive, None for batch

    @property
    def note_service(self) -> NoteService:
        return NoteService(self.db)

    @property
    def cost_remaining(self) -> float | None:
        return self.session.cost_budget_remaining if self.session else None
```

Tools that need session context access it through `ctx.deps.session`. Tools that don't need it are unaffected — `session` defaults to `None`.

See `46-event-session-architecture.md`, Section 3 (Streaming Coordinator) for the complete `handle()` implementation and agent routing.
```

### Change 3.2: Add to Related Documentation

**Insert**:
```markdown
- [46-event-session-architecture.md](46-event-session-architecture.md) — Session-aware agent invocation, streaming coordinator, event-driven interaction model
```

---

## Change 4: `44-multi-channel-gateway.md` — Channels Become Event Subscribers

### Why

Doc 29 currently defines channel adapters (Telegram, WebSocket, TUI) as independent consumers that each manage their own session state and call backend services directly. Doc 31 unifies this: channels become **event subscribers** on the session event bus. The channel adapter's job changes from "call service, format response" to "subscribe to session events, render events in channel-native format." Session state is managed centrally by the session service, not per-channel.

This is the most significant conceptual shift. Without this update, an AI implementing a new channel adapter will build it the old way (direct service calls) instead of subscribing to the event bus.

### Change 4.1: Add Event-Driven Channel Section

**Location**: After the existing channel adapter patterns, or in a new section before the Related Documentation.

**Insert**:
```markdown
---

## Event-Driven Channel Adapters (Doc 31)

When the project adopts `46-event-session-architecture.md`, channel adapters become event subscribers rather than direct service callers.

### Architectural Shift

| Concern | Without Doc 31 | With Doc 31 |
|---------|---------------|-------------|
| Session state | Per-channel tracking | Centralized `SessionService` — channels bind to sessions via `session.bind_channel()` |
| Message handling | Channel calls service layer directly | Channel publishes `UserMessageEvent` → coordinator handles → channel subscribes to response events |
| Response delivery | Service returns response, adapter formats it | Adapter subscribes to `session:{id}` event channel, renders events in channel-native format |
| Streaming | Channel-specific streaming implementation | Universal — coordinator yields `AsyncIterator[Event]`, each adapter renders events differently |
| Multi-channel | Separate session per channel | Single session, multiple channel bindings — user can start in Telegram, continue in TUI |

### Channel Adapter Pattern (Event-Driven)

Each channel adapter performs three operations:

1. **Ingest**: Convert channel-native input (Telegram message, WebSocket frame, TUI keypress) into a `UserMessageEvent` and publish to the event bus.
2. **Subscribe**: Subscribe to `session:{session_id}` channel on Redis pub/sub.
3. **Render**: Convert session events into channel-native output.

```python
# Conceptual pattern — each channel implements this differently
class ChannelAdapter:
    async def on_user_input(self, channel_input) -> None:
        session = await self.resolve_session(channel_input)
        event = UserMessageEvent(session_id=session.id, content=channel_input.text)
        await event_bus.publish(event)

    async def subscribe(self, session_id: str) -> None:
        async for event in event_bus.subscribe(f"session:{session_id}"):
            await self.render(event)

    async def render(self, event: SessionEvent) -> None:
        # Channel-specific rendering
        raise NotImplementedError
```

### Channel-Specific Rendering

| Event Type | REST/SSE | Telegram | TUI | WebSocket |
|-----------|----------|----------|-----|-----------|
| `AgentThinkingEvent` | SSE `event: thinking` | Edit message with "⏳ Thinking..." | Update thinking panel | JSON frame `{type: "thinking"}` |
| `AgentResponseChunkEvent` | SSE `event: chunk` | Buffer chunks, edit message every 500ms | Append to response panel | JSON frame `{type: "chunk", content: "..."}` |
| `AgentToolCallEvent` | SSE `event: tool_call` | Inline "🔧 Searching..." | Tool call panel | JSON frame `{type: "tool_call"}` |
| `ApprovalRequestedEvent` | SSE `event: approval` + poll endpoint | Inline keyboard buttons | Modal dialog | JSON frame `{type: "approval"}` |

### Session-Channel Binding

Sessions support multiple channel bindings. A user can start a conversation in Telegram and continue it in the TUI — same session, same history, same plan state.

```python
await session_service.bind_channel(session_id, channel_type="telegram", channel_id="chat_12345")
await session_service.bind_channel(session_id, channel_type="tui", channel_id="tui_session_abc")
```

The session service maintains a `session_channels` table mapping session IDs to channel bindings.

### Migration Path

Existing channel adapters can be migrated incrementally:
1. Add event bus subscription alongside existing direct service calls
2. Route new features through events, keep existing features on direct calls
3. Once all features use events, remove direct service calls

The existing per-channel session tracking in doc 29 remains valid for projects that do not adopt doc 31.

See `46-event-session-architecture.md`, Section 3 (Streaming Coordinator — Channel Adapters) for the complete adapter implementations.
```

### Change 4.2: Add to Related Documentation

**Insert**:
```markdown
- [46-event-session-architecture.md](46-event-session-architecture.md) — Channels as event subscribers, session-channel binding, unified session state
```

---

## Change 5: `AGENTS.md` — Add Doc 31 to Reference Table

### Why

`AGENTS.md` is the entry point for AI coding assistants (Cursor, Claude Code, Copilot). If doc 31 is not listed, these tools will not know to consult it when implementing session-related features.

### Change 5.1: Add Doc 31 Reference

**Location**: The reference architecture document table (wherever docs 25-30 are listed).

**Insert row**:
```markdown
| 46-event-session-architecture.md | Event-driven session architecture — session model, event bus, streaming coordinator, plan management (mutable DAGs), memory architecture (episodic/semantic/procedural with anchored rolling summaries), approval and escalation (unified responder pattern, Temporal Signals), cost tracking, observability. Adopt for interactive/agent-driven operations. |
```

---

## Change 6: `03-backend-architecture.md` — Cross-Reference for Interactive Operations

### Why

Doc 03 defines the request/response model as the universal interaction pattern. This remains true for stateless CRUD. However, an AI reading only doc 03 may assume request/response is always correct, even for streaming agent interactions. A single paragraph noting the session model alternative prevents this.

### Change 6.1: Add Session Model Note

**Location**: At the end of the `## API Design` section, after the pagination subsection, or at the end of the document before health checks.

**Insert**:
```markdown
### Interactive and Streaming Operations

The request/response patterns above apply to stateless CRUD operations — the majority of API endpoints. For interactive operations involving conversations, agent streaming, multi-step plans, or approval gates, see `46-event-session-architecture.md`. That module introduces a session-and-event model where the coordinator returns `AsyncIterator[Event]` instead of a response object, and channels subscribe to session event streams. The service layer defined in this document remains the single source of business logic — the session model layers on top, it does not replace anything here.
```

---

## Change 7: `40-agentic-architecture.md` — Cross-Reference for Concrete Implementation

### Why

Doc 25 is the conceptual agentic architecture (framework-agnostic). It defines agent phases, orchestration patterns, and the `AgentTask` primitive. Doc 31 provides the concrete implementation of several concepts doc 25 introduces abstractly: plan management as mutable DAGs, approval gates via Temporal Signals, memory architecture with rolling summaries. Without a cross-reference, an AI may attempt to implement these from doc 25's abstract descriptions instead of using doc 31's concrete patterns.

### Change 7.1: Add Implementation Reference

**Location**: In the Related Documentation section at the end of the document.

**Insert**:
```markdown
- [46-event-session-architecture.md](46-event-session-architecture.md) — Concrete implementation of session model, plan management (mutable DAGs with dependency tracking), memory architecture (episodic/semantic/procedural with anchored rolling summaries), and approval gates (unified responder pattern with Temporal Signals). Read this for implementation; read doc 25 for concepts.
```

### Change 7.2: Add Cross-References in Body (Optional)

If the following sections exist in doc 25, add a one-line cross-reference at the end of each:

- **Plan management / orchestration section**: "For the concrete DAG-based implementation with PostgreSQL schema, ready-task queries, and plan revision patterns, see `46-event-session-architecture.md`, Section 4."
- **Memory / context management section**: "For the concrete three-tier memory architecture (episodic, semantic, procedural) with anchored rolling summaries and context window assembly, see `46-event-session-architecture.md`, Section 5."
- **Human-in-the-loop / approval section**: "For the concrete unified responder pattern with Temporal Signals, escalation chains, and durable approval workflows, see `46-event-session-architecture.md`, Section 6."

---

## Change 8: `27-tui-architecture.md` — Reference Event Rendering

### Why

Doc 28 defines the TUI (Textual) interface. With doc 31, the TUI becomes an event subscriber that renders session events in real-time panels. A cross-reference ensures an AI implementing TUI features uses the event-driven pattern.

### Change 8.1: Add Event-Driven Note

**Location**: In the Related Documentation section, or at the end of the section describing how the TUI displays agent responses.

**Insert**:
```markdown
- [46-event-session-architecture.md](46-event-session-architecture.md) — When adopted, the TUI becomes an event subscriber. Agent thinking, tool calls, and response chunks arrive as typed events on the session bus. The TUI renders these in dedicated panels (thinking panel, tool call panel, response panel) rather than polling for updates.
```

---

## Change 9: `43-ai-first-interface-design.md` — Service Factory Accepts Optional Session

### Why

Doc 30 defines the service factory pattern (`get_note_service()` context manager). When doc 31 is adopted, the factory should optionally accept a `Session` parameter so that service calls within a session context can access session metadata (cost tracking, conversation pointer).

### Change 9.1: Add Session-Aware Factory Note

**Location**: In the Service Layer Factory section, after the existing factory pattern.

**Insert**:
```markdown
### Session-Aware Factory (Doc 31)

When the project adopts `46-event-session-architecture.md`, the service factory can optionally accept a session context:

```python
@asynccontextmanager
async def get_note_service(session: Session | None = None) -> AsyncGenerator[NoteService, None]:
    async for db_session in get_db_session():
        service = NoteService(db_session)
        if session:
            service.set_session_context(session)  # Enables cost tracking, audit trail
        yield service
```

The `session` parameter is optional. Non-session callers (CLI, background tasks) pass `None` and the factory behaves identically to the base pattern. Session-aware callers (coordinator, channel adapters) pass the active session for cost tracking and audit trail integration.

See `46-event-session-architecture.md`, Section 1 (Session Model — SessionService) for the `Session` entity and lifecycle management.
```

### Change 9.2: Add to Related Documentation

**Insert**:
```markdown
- [46-event-session-architecture.md](46-event-session-architecture.md) — Session context for service factory, event-driven interaction model
```

---

## Documents Requiring No Changes

| Document | Reason |
|----------|--------|
| `01-core-principles.md` | Doc 31 reinforces P1 (backend owns logic) and P3 (single database of record). No new principles needed. |
| `02-primitive-identification.md` | Session is a new primitive but is domain-specific to doc 31, not a universal identification process. |
| `04-module-structure.md` | Doc 31 introduces new modules (`events/`, `agents/coordinator/`) that follow doc 04's existing patterns. No changes to the patterns themselves. |
| `20-data-layer.md` | PostgreSQL schemas in doc 31 follow existing data layer patterns. |
| `22-frontend-architecture.md` | Frontend is out of scope for session architecture. |
| `24-llm-integration.md` | LLM provider interface unchanged. Doc 31 uses PydanticAI which wraps LLM calls. |
| `05-authentication.md` | Auth patterns unchanged. Sessions use existing user identity. |
| `08-python-coding-standards.md` | Coding standards unchanged. |
| `23-typescript-coding-standards.md` | Not applicable. |
| `10-observability.md` | Doc 31 adds session-specific observability (Pydantic Logfire / Langfuse) but this is self-contained in doc 31, Section 7. No changes to base observability patterns. |
| `12-development-workflow.md` | Workflow unchanged. |
| `09-error-codes.md` | Error code patterns unchanged. Doc 31 uses existing error hierarchy. |
| `13-project-template.md` | Doc 31's module structure is an extension, described in doc 31 itself. |
| `11-testing-standards.md` | Testing patterns unchanged. Doc 31 defines its own test approach (unit, integration, e2e) internally. |
| `06-security-standards.md` | Security patterns unchanged. |
| `07-data-protection.md` | Data protection unchanged. Session data follows existing PII/GDPR patterns. |
| `14-background-tasks.md` | Taskiq patterns unchanged. Doc 31 uses Temporal for durable workflows (Tier 4) but does not replace Taskiq for fire-and-forget jobs. |
| `25-telegram-bot-integration.md` | Telegram bot patterns unchanged. Doc 29 handles the channel adapter; doc 31 makes it event-driven. |
| `15-deployment-bare-metal.md` | Deployment unchanged. |
| `16-deployment-azure.md` | Deployment unchanged. |
| `26-telegram-client-integration.md` | MTProto patterns unchanged. |
| `42-agent-first-infrastructure.md` | MCP and A2A patterns unchanged. MCP tools and A2A executors become event producers under doc 31, but the tool/executor code itself is unchanged — they still call service methods. The event emission happens in the coordinator, not in the tool. |

---

## Execution Order

Execute changes in this order to maintain consistency:

1. **`00-overview.md`** — Makes doc 31 visible in the architecture index. All subsequent changes reference doc 31; it must be registered first.
2. **`AGENTS.md`** — Makes doc 31 visible to AI coding assistants. Quick change, high impact.
3. **`21-event-architecture.md`** — Establishes session events as a superset of module events. Other changes reference "session events on the event bus" which requires doc 06 to acknowledge them.
4. **`41-agentic-pydanticai.md`** — Adds `run_stream()` and `handle()` patterns. This is the most code-heavy change.
5. **`44-multi-channel-gateway.md`** — Converts channels to event subscribers. Conceptually the biggest shift.
6. **`03-backend-architecture.md`** — Small cross-reference. Low risk.
7. **`40-agentic-architecture.md`** — Cross-references to concrete implementations. Low risk.
8. **`27-tui-architecture.md`** — Cross-reference. Low risk.
9. **`43-ai-first-interface-design.md`** — Session-aware factory extension. Low risk.

---

## Validation Checklist

After all changes are applied, verify:

- [ ] `00-overview.md` version is `2.4.0`
- [ ] `00-overview.md` changelog has a `2.4.0` entry
- [ ] `00-overview.md` Optional Modules table includes doc 31
- [ ] `00-overview.md` Decision Criteria table includes doc 31
- [ ] `00-overview.md` dependency tree includes doc 31 block
- [ ] `00-overview.md` adoption rule for doc 31 exists
- [ ] `00-overview.md` Context paragraph lists "Event-Driven Sessions (31)"
- [ ] `00-overview.md` Optional Scope includes event-driven session line
- [x] `21-event-architecture.md` has Session Events section referencing doc 46 (was doc 31)
- [ ] `41-agentic-pydanticai.md` has Session-Aware Agent Invocation section with `run_stream()` and `handle()` patterns
- [ ] `44-multi-channel-gateway.md` has Event-Driven Channel Adapters section with the architectural shift table
- [x] `AGENTS.md` has doc 46 row in reference table (was doc 31, already present)
- [ ] `03-backend-architecture.md` has Interactive and Streaming Operations paragraph
- [ ] `40-agentic-architecture.md` Related Documentation includes doc 31
- [ ] `27-tui-architecture.md` Related Documentation includes doc 31
- [ ] `43-ai-first-interface-design.md` has Session-Aware Factory subsection
- [ ] No document introduces patterns that conflict with doc 31's axioms (A1-A5)
- [ ] All cross-references use the exact filename `46-event-session-architecture.md`

---

## Glossary

| Term | Definition |
|------|-----------|
| **Session** | A persistent, bidirectional context carrying conversation history, active agents, cost tracking, and channel bindings. Introduced in doc 31. |
| **Event Bus** | Redis pub/sub transport for real-time session events. Extends the module event system in doc 06. |
| **Coordinator** | Infrastructure component that routes messages to agents, enforces cost budgets, manages approval gates, and yields `AsyncIterator[Event]`. Not an agent — contains no LLM calls or domain logic. |
| **Unified Responder** | Pattern where approvals can be responded to by humans, AI agents, or automated rules through the same mechanism (Temporal Signals). |
| **Anchored Rolling Summary** | Memory compression technique where only new conversation spans are summarized, preserving intent, artifacts, and breadcrumbs from previous summaries. |
| **Channel Adapter** | A transport-specific subscriber that converts session events into channel-native output (Telegram message edits, WebSocket frames, TUI panel updates, SSE events). |
| **Mutable DAG** | Plan representation as a directed acyclic graph of tasks with dependencies. Plans are revised (remaining tasks modified) rather than replanned from scratch on failure. |
