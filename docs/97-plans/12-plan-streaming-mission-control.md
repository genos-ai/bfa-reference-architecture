# Implementation Plan: Streaming Mission Control

*Created: 2026-03-02*
*Updated: 2026-03-04 — Renamed coordinator → mission control per research doc 11*
*Status: Done*
*Phase: 3 of 8 (AI-First Platform Build)*
*Depends on: Phase 1 (Event Bus), Phase 2 (Session Model)*
*Blocked by: Phase 2*

---

## Summary

Rename `coordinator` to `mission_control` throughout the codebase. Replace mission control's entry point so that `handle()` returns `AsyncIterator[SessionEvent]`. Streaming is the default and only path. Every channel (REST/SSE, WebSocket, Telegram, TUI, CLI) consumes the same event stream and renders in its native format. Synchronous callers collect the iterator to completion via `collect()`.

Additionally, introduce the agent contract schema (`AgentInterfaceSchema`, `AgentModelSchema`) as the foundation for typed agent I/O contracts and model pinning — prerequisites for the Mission Control dispatch loop in Plan 13.

Mission control is infrastructure, not intelligence (P6). It routes messages to agents, enforces cost budgets, manages approval gates, and yields events. It does not have a personality, make domain decisions, or call LLMs. It is a state machine.

**Dev mode: breaking changes allowed.** The old `handle()`, `handle_direct()`, and `handle_direct_stream()` are replaced. The entire `mission_control/` directory is renamed to `mission_control/`. All agent interactions go through sessions. The `/agents/chat` endpoint auto-creates an ephemeral session when no `session_id` is provided. No backward-compatibility shims.

## Context

- Reference architecture: BFF doc 35 (Section 3: Streaming Coordinator)
- Research doc: `docs/98-research/11-bfa-workflow-architecture-specification.md` — Mission Control execution model, agent contracts, model pinning
- Local doc: `docs/99-reference-architecture/46-event-session-architecture.md` (Section 3)
- Project principles: `docs/03-principles/01-project-principles.md` — P6 (Mission Control Is Infrastructure), P3 (Breaking Changes Are Free), P5 (Streaming Is Default)
- Current state: `modules/backend/agents/coordinator/coordinator.py` — returns `dict`, no sessions, no events (to be renamed to `mission_control/mission_control.py`)
- Current middleware: `middleware.py` has `with_guardrails()`, `with_cost_tracking()`, `compute_cost_usd()`
- Current router: `RuleBasedRouter` matches keywords, returns agent_name or None
- Current registry: `AgentRegistry` discovers YAML configs, resolves module paths, caches agent instances
- Current agent execution: `_execute_agent()` imports module, builds deps, calls `run_agent()`
- Tier 4: `handle()` will be called from inside Temporal Activities — accepts service objects as parameters, not global state

## What to Build

- **Rename `coordinator` → `mission_control`** — directory, files, classes, configs, imports, tests, docs
- **Agent contract schema** — `AgentInterfaceSchema` (typed I/O), `AgentModelSchema` (pinned model config), `version` field on `AgentConfigSchema`
- Refactor `modules/backend/agents/mission_control/mission_control.py` — replace `handle()` signature to yield `AsyncIterator[SessionEvent]`, remove old `handle_direct()` and `handle_direct_stream()`
- `modules/backend/agents/mission_control/cost.py` — extract cost calculation from middleware
- `modules/backend/agents/mission_control/history.py` — convert session_messages ↔ PydanticAI ModelMessage format
- Refactor `modules/backend/agents/mission_control/middleware.py` — remove `compute_cost_usd` (moved to cost.py), remove `with_cost_tracking` (cost tracking now in handle() via SessionService)
- Update `modules/backend/api/v1/endpoints/sessions.py` — SSE message endpoint (`POST /{id}/messages`), SSE live event feed (`GET /{id}/events`)
- Refactor `modules/backend/api/v1/endpoints/agents.py` — all chat goes through sessions, auto-create ephemeral session when no session_id
- Update `modules/backend/agents/deps/base.py` — add `on_event` callback
- Update all existing tests to use new mission control signatures

## Key Design Decisions

- **Rename coordinator → mission_control.** Per research doc 11, the coordinator evolves into mission control. This is the natural break point — Plan 12 already rewrites the `handle()` interface. Directory, files, classes, configs, imports, and tests all rename. P3 (Breaking Changes Are Free) applies.
- **Agent contracts (typed I/O).** `AgentInterfaceSchema` defines typed input/output fields per agent. `AgentModelSchema` pins model name, temperature, and max_tokens as immutable properties. These are optional on existing agents (backward-compatible) but required for agents participating in Mission Control dispatch (Plan 13). Model upgrades are agent version bumps.
- **Sessions are mandatory.** Every agent interaction happens within a session. For quick one-off calls, the API auto-creates an ephemeral session.
- `handle()` is the only entry point — `handle_direct()` and `handle_direct_stream()` are removed
- The function yields events as the agent works: `UserMessageEvent` → `AgentThinkingEvent` → `AgentToolCallEvent` → `AgentToolResultEvent` → `AgentResponseChunkEvent` → `AgentResponseCompleteEvent` → `CostUpdateEvent`
- Every event is published to the session event bus (Redis Pub/Sub) AND yielded to the caller
- Budget enforcement happens BEFORE any LLM call via `SessionService.enforce_budget()`
- Cost tracking updates the session AFTER agent response via `SessionService.update_cost()` — replaces the old `with_cost_tracking` decorator
- Messages (user input and agent response) are persisted to `session_messages` (Phase 2 model)
- Session-based routing: if `session.agent_id` is set, use that agent. Otherwise, use keyword routing with fallback.
- Tool call events extracted from PydanticAI's `stream.new_messages()` after tool execution (retrospective)
- `collect()` helper converts the event stream to a simple response dict for callers that don't need streaming
- `handle()` accepts service objects as parameters, not global state — Temporal ready
- `event_bus` is optional — `handle()` works without it (events are still yielded, just not published to Redis)
- Error handling yields events instead of throwing — the stream always terminates cleanly

## Success Criteria

- [ ] `mission_control/` directory renamed to `mission_control/` with all references updated
- [ ] `CoordinatorRequest/Response` renamed to `MissionControlRequest/Response`
- [ ] `config/agents/mission_control.yaml` renamed to `config/agents/mission_control.yaml`
- [ ] All import paths updated (~15 locations across 8+ source files)
- [ ] `AgentInterfaceSchema` and `AgentModelSchema` added to `config_schema.py`
- [ ] Existing agent YAMLs work with optional `interface` field
- [ ] `handle()` returns an async iterator of typed `SessionEvent` objects
- [ ] Old `handle_direct()` and `handle_direct_stream()` are removed
- [ ] SSE endpoint streams events for a session message
- [ ] Agent thinking, tool calls, and response chunks are all visible as events
- [ ] Cost tracking updates the session after every agent response (replaces `with_cost_tracking`)
- [ ] Budget enforcement blocks execution when session budget exceeded
- [ ] Messages (user + agent) are persisted to `session_messages`
- [ ] Conversation history is loaded and passed to PydanticAI as `message_history`
- [ ] Session `last_activity_at` is updated on each interaction
- [ ] `/api/v1/agents/chat` auto-creates ephemeral session when no session_id provided
- [ ] `/api/v1/sessions/{id}/messages` streams SSE events
- [ ] `collect()` helper returns full response text from the event stream
- [ ] Error events are yielded (not thrown) — the stream always terminates cleanly
- [ ] All 65+ existing tests still pass
- [ ] Docs updated: P6 title, doc 46 Section 3, doc 47 glossary

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Commit any uncommitted work | `git status`, then commit if needed |
| 0.2 | Create feature branch | `git checkout -b feature/streaming-mission-control` |

---

### Step 0.5: Rename coordinator → mission_control

**This is a mechanical rename. Do it first, commit, then proceed with functional changes.**

**Directory rename:**
- `modules/backend/agents/mission_control/` → `modules/backend/agents/mission_control/`

**File renames within the directory:**
- `coordinator.py` → `mission_control.py`
- All other files (`middleware.py`, `router.py`, `registry.py`, `models.py`, `__init__.py`) keep their names

**Config file rename:**
- `config/agents/mission_control.yaml` → `config/agents/mission_control.yaml`

**Class renames:**
- `CoordinatorRequest` → `MissionControlRequest` (in `models.py`)
- `CoordinatorResponse` → `MissionControlResponse` (in `models.py`)
- `CoordinatorConfigSchema` → `MissionControlConfigSchema` (in `config_schema.py`)
- `CoordinatorLimitsSchema` → `MissionControlLimitsSchema` (in `config_schema.py`)

**Function renames:**
- `_load_mission_control_config()` → `_load_mission_control_config()` (in `middleware.py`)

**Import path updates (all files importing from `agents.mission_control`):**
- `modules/backend/agents/mission_control/mission_control.py` — internal imports
- `modules/backend/agents/mission_control/middleware.py` — config path string
- `modules/backend/agents/mission_control/router.py` — internal imports
- `modules/backend/agents/mission_control/__init__.py` — exports
- `modules/backend/agents/__init__.py` — comment update
- `modules/backend/agents/deps/base.py` — comment update
- `modules/backend/agents/config_schema.py` — class renames
- `modules/backend/agents/vertical/code/qa/agent.py` — `assemble_instructions` import
- `modules/backend/agents/vertical/system/health/agent.py` — `assemble_instructions` import
- `modules/backend/api/v1/endpoints/agents.py` — all coordinator imports
- `scripts/compliance_checker.py` — `get_registry` import
- `chat.py` — comments only
- `tui.py` — comments only

**Test file renames:**
- `tests/unit/backend/agents/test_coordinator.py` → `tests/unit/backend/agents/test_mission_control.py`
- Update imports in `test_config_schema.py`, `test_agent_testmodel.py`, `test_compliance.py`

**Config path update in middleware.py:**
```python
config_path = find_project_root() / "config" / "agents" / "mission_control.yaml"
```

**Verification:** `python -m pytest tests/` — all 65+ existing tests must pass after rename.

---

### Step 0.5b: Agent Contract Schema

**File:** `modules/backend/agents/config_schema.py` (MODIFY)

Add typed I/O contracts and structured model configuration:

```python
class AgentInterfaceSchema(_StrictBase):
    """Typed input/output contract for an agent.

    Defines the fields an agent expects as input and produces as output.
    Used by Mission Control for Tier 1 structural validation (Plan 14)
    and by the Planning Agent for input compatibility checks (Plan 13).
    """

    input: dict[str, str] = Field(
        default_factory=dict,
        description="Input fields: field_name → type_name",
    )
    output: dict[str, str] = Field(
        default_factory=dict,
        description="Output fields: field_name → type_name",
    )


class AgentModelSchema(_StrictBase):
    """Pinned model configuration. Immutable at runtime.

    Models are pinned to agents as non-overridable properties (research doc 11).
    Model upgrades are agent version bumps: create agent_v2 with new model,
    validate, then update roster. No runtime model override path exists.
    """

    name: str = Field(
        ...,
        description="Model identifier, e.g. 'anthropic:claude-sonnet-4-20250514'",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature. Pinned, non-overridable.",
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        description="Max output tokens. Pinned, non-overridable.",
    )
```

Update `AgentConfigSchema`:

```python
class AgentConfigSchema(_StrictBase):
    # ... existing fields ...
    model: str | AgentModelSchema  # Accept both flat string and structured schema
    interface: AgentInterfaceSchema | None = None  # Optional until Plan 13 makes it required for roster agents
    version: str = "1.0.0"  # Semantic versioning, used by roster validation
```

**Migration note:** Existing agent YAMLs use `model: "anthropic:claude-sonnet-4-20250514"` (flat string). This continues to work. New agents and roster agents should use the structured `AgentModelSchema` format. Add a validator that normalizes flat strings to `AgentModelSchema(name=value)`.

**Verification:** Existing agent YAML configs load without changes. New `interface` and `version` fields have sensible defaults.

---

### Step 0.5c: Documentation Alignment

Update reference docs to reflect the rename:

- `docs/99-reference-architecture/46-agentic-event-session-architecture.md` — Section 3 heading: "Streaming Mission Control"
- `docs/99-reference-architecture/47-agentic-module-organization.md` — Glossary: "Mission Control" entry, directory references `agents/mission_control/`
- `docs/03-principles/01-project-principles.md` — Already updated (P6 title)

**Note:** Doc 40 (Agentic Architecture) uses "orchestrator" generically and does not need updating.

---

### Step 1: Create `mission_control/cost.py`

**File:** `modules/backend/agents/mission_control/cost.py` (NEW, ~60 lines)

Extract cost calculation from `middleware.py` into its own module.

```python
"""Cost calculation for agent executions.

Pricing comes from mission_control.yaml model_pricing config.
Budget enforcement lives in SessionService — this module only computes costs.
"""

from modules.backend.agents.mission_control.middleware import _load_mission_control_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def compute_cost_usd(
    input_tokens: int,
    output_tokens: int,
    model: str | None = None,
) -> float:
    """Compute dollar cost from token counts and model pricing config."""
    config = _load_mission_control_config()
    default_rates = config.model_pricing.get("default")
    rates = config.model_pricing.get(model or "", default_rates)
    if rates is None:
        rates = default_rates
    if rates is None:
        logger.warning("No pricing config found", extra={"model": model})
        return 0.0
    input_cost = (input_tokens / 1_000_000) * rates.input
    output_cost = (output_tokens / 1_000_000) * rates.output
    return round(input_cost + output_cost, 6)


def estimate_cost(
    estimated_input_tokens: int,
    model: str | None = None,
) -> float:
    """Estimate cost before execution. Assumes output ~= input."""
    return compute_cost_usd(estimated_input_tokens, estimated_input_tokens, model)
```

---

### Step 2: Refactor `mission_control/middleware.py`

**File:** `modules/backend/agents/mission_control/middleware.py` (MODIFY)

Remove `compute_cost_usd` (moved to `cost.py`). Remove `with_cost_tracking` decorator (cost tracking now happens in `handle()` via `SessionService.update_cost()`).

**Keep:**
- `_load_mission_control_config()` — still needed by cost.py, handler, and guardrails
- `with_guardrails()` — still used by `handle()` for input validation

**Remove:**
- `compute_cost_usd()` function body — replaced by `cost.py`
- `with_cost_tracking()` decorator — replaced by session-based cost tracking in `handle()`

Update all callers of `compute_cost_usd` to import from `modules.backend.agents.mission_control.cost`.

---

### Step 3: Create `mission_control/history.py`

**File:** `modules/backend/agents/mission_control/history.py` (NEW, ~120 lines)

Converts between session_messages (our persistence format) and PydanticAI's ModelMessage format.

**Two functions:**

`session_messages_to_model_history(messages: list) -> list[ModelMessage]`
- Converts session_message rows to PydanticAI's `ModelMessage` list
- Maps roles: `user` → `ModelRequest`+`UserPromptPart`, `assistant` → `ModelResponse`+`TextPart`, `system` → `ModelRequest`+`SystemPromptPart`, `tool_call` → `ModelResponse`+`ToolCallPart`, `tool_result` → `ModelRequest`+`ToolReturnPart`
- Messages are ordered by `created_at` ascending
- Unknown roles are logged and skipped

`model_messages_to_session_creates(messages, session_id, agent_id, model, input_tokens, output_tokens, cost_usd) -> list[SessionMessageCreate]`
- Converts PydanticAI's `new_messages()` output to `SessionMessageCreate` schemas for persistence
- Cost fields attached to the last assistant message only

**Note on PydanticAI imports:** Check `pydantic_ai.messages` for exact types at implementation time. The pattern is stable; class names may vary by version.

---

### Step 4: Rewrite `mission_control/mission_control.py`

**File:** `modules/backend/agents/mission_control/mission_control.py` (REWRITE, ~300 lines)

This is the core change. Replace the entire public interface. Keep the reusable internals (`_build_model`, `assemble_instructions`, `build_deps_from_config`, `_build_agent_deps`).

**Remove:**
- `handle(user_input: str) -> dict` — old non-streaming entry point
- `handle_direct(agent_name, user_input) -> dict` — direct invocation without sessions
- `handle_direct_stream(agent_name, user_input, conversation_id) -> AsyncGenerator[dict, None]` — old streaming with untyped dict events
- `_execute_agent()` — replaced by streaming execution inside `handle()`
- `_format_response()` — no longer needed (events replace formatted responses)
- `route()` — folded into `_resolve_agent()` inside `handle()`

**Keep (refactored):**
- `_build_model(config_model) -> Model` — unchanged
- `assemble_instructions(category, name) -> str` — unchanged
- `build_deps_from_config(agent_config) -> dict` — unchanged
- `_build_agent_deps(agent_name, agent_config, session_id) -> BaseAgentDeps` — add session_id parameter
- `_get_usage_limits() -> UsageLimits` — unchanged
- `_import_agent_module(agent_name)` — unchanged
- `list_agents() -> list[dict]` — unchanged

**New public interface:**

```python
async def handle(
    session_id: str,
    message: str,
    *,
    session_service: SessionService,
    event_bus: SessionEventBus | None = None,
    channel: str = "api",
    sender_id: str | None = None,
) -> AsyncIterator[SessionEvent]:
    """Universal streaming mission control entry point.

    All channels call this function:
    - REST/SSE: stream events directly
    - WebSocket: forward events to socket
    - Telegram: buffer chunks, edit message
    - TUI: render events in panels
    - CLI: print events to terminal
    - Temporal Activity: collect events, persist state
    """


async def collect(session_id: str, message: str, **kwargs) -> dict:
    """Collect all events from handle(), return a dict.

    Returns: {"agent_name": str, "output": str, "cost_usd": float}
    """
```

**Event flow within `handle()`:**

```
1. Validate session exists (get_session)
2. Enforce budget: estimate cost → SessionService.enforce_budget()
   → If exceeded: yield CostUpdateEvent with budget.exceeded, return
3. Create and yield UserMessageEvent (+ publish to event bus)
4. Resolve agent: session.agent_id > keyword routing > fallback
5. Apply guardrails (input length, injection patterns from mission_control.yaml)
6. Yield AgentThinkingEvent (+ publish)
7. Build agent deps with session_id, load model, get agent instance
8. Load conversation history: get_messages() → session_messages_to_model_history()
9. Execute agent with streaming:
   async with agent.run_stream(message, message_history, deps, usage_limits):
     a. Extract tool events from stream (retrospective)
        → Yield AgentToolCallEvent + AgentToolResultEvent (+ publish)
     b. Iterate stream.stream_text(delta=True):
        → Yield AgentResponseChunkEvent for each chunk (+ publish)
     c. On completion:
        → compute_cost_usd() for dollar cost
        → Yield AgentResponseCompleteEvent (+ publish)
        → SessionService.update_cost()
        → Yield CostUpdateEvent (+ publish)
     d. Persist messages to session_messages
     e. SessionService.touch_activity()
10. Error handling: catch exceptions, yield partial result, log, don't crash stream
```

**Private helper functions (new):**

- `_resolve_agent(session, message) -> str` — session.agent_id > keyword routing > fallback
- `_extract_tool_events(stream, session_id, agent_name) -> list[SessionEvent]` — reads `stream.new_messages()` for tool parts, returns typed events. Defensive.
- `_persist_messages(session_service, session_id, ...) -> None` — saves user message and agent response to session_messages. Non-critical (try/except).
- `_publish(event_bus, event) -> None` — publishes to event bus if available. Non-critical (try/except).

**Key patterns:**
- `handle()` accepts service objects as parameters — Temporal ready
- `event_bus` is optional — works without Redis
- Error handling yields events instead of throwing
- `_build_agent_deps()` updated to include `session_id`
- `with_cost_tracking` decorator is gone — cost tracking is inline via SessionService

---

### Step 5: Update `agents/deps/base.py`

**File:** `modules/backend/agents/deps/base.py` (MODIFY)

Add `on_event` callback to `BaseAgentDeps`:

```python
@dataclass
class BaseAgentDeps:
    """Common dependencies injected into every agent at runtime."""

    project_root: Path
    scope: FileScope
    config: AgentConfigSchema | None = None
    session_id: str | None = None       # Set when running within a session
    on_event: Any = None                # Callable[[SessionEvent], Awaitable[None]] | None
```

Update all call sites that construct `BaseAgentDeps` or subclasses to pass `session_id` (already added in Phase 2).

---

### Step 6: Refactor agents API endpoint

**File:** `modules/backend/api/v1/endpoints/agents.py` (REWRITE, ~100 lines)

All chat now goes through sessions. When no `session_id` is provided, auto-create an ephemeral session.

```python
class ChatRequest(BaseModel):
    """Request body for agent chat."""
    message: str = Field(..., min_length=1, description="User message")
    agent: str | None = Field(default=None, description="Target agent name")
    session_id: str | None = Field(default=None, description="Session ID. Auto-created if omitted.")


@router.post("/chat", response_model=ApiResponse[ChatResponse], summary="Chat with an agent")
async def agent_chat(
    data: ChatRequest,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[ChatResponse]:
    """Send a message to an agent. Auto-creates a session if none provided."""
    from modules.backend.agents.mission_control.mission_control import collect
    from modules.backend.services.session import SessionService
    from modules.backend.schemas.session import SessionCreate

    service = SessionService(db)

    # Auto-create ephemeral session if not provided
    session_id = data.session_id
    if not session_id:
        session = await service.create_session(
            SessionCreate(agent_id=data.agent, goal=data.message[:200]),
        )
        session_id = session.id

    result = await collect(
        session_id,
        data.message,
        session_service=service,
    )

    return ApiResponse(
        data=ChatResponse(
            agent_name=result.get("agent_name", ""),
            output=result.get("output", ""),
            session_id=session_id,
        ),
    )


@router.post("/chat/stream", summary="Chat with an agent (streaming SSE)")
async def agent_chat_stream(
    data: ChatRequest,
    db: DbSession,
) -> StreamingResponse:
    """Stream agent progress events as SSE."""
    from modules.backend.agents.mission_control.mission_control import handle
    from modules.backend.services.session import SessionService
    from modules.backend.schemas.session import SessionCreate

    service = SessionService(db)

    session_id = data.session_id
    if not session_id:
        session = await service.create_session(
            SessionCreate(agent_id=data.agent, goal=data.message[:200]),
        )
        session_id = session.id

    async def generate():
        async for event in handle(session_id, data.message, session_service=service):
            yield f"event: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

**Update `ChatResponse`** to include `session_id`:

```python
class ChatResponse(BaseModel):
    agent_name: str
    output: str
    session_id: str | None = None
```

**Keep** the `/registry` endpoint unchanged.

---

### Step 7: Update session API endpoints for SSE

**File:** `modules/backend/api/v1/endpoints/sessions.py` (MODIFY, +80 lines)

Add two new endpoints to the sessions router (Phase 2):

**`POST /{session_id}/messages`** — Send message, stream events as SSE:
- Accepts `SessionMessageCreate` body
- Creates handler with `SessionService(db)` and optional `SessionEventBus`
- Calls `handle()` and streams events
- SSE format: `event: {event_type}\ndata: {json}\n\n` (W3C spec)
- Final: `event: done\ndata: {}\n\n`
- Headers: `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`

**`GET /{session_id}/events`** — Live event feed:
- Subscribes to the session's Redis Pub/Sub channel via `SessionEventBus`
- Streams events as SSE (for dashboards, monitoring)

---

### Step 8: Update `mission_control/__init__.py`

**File:** `modules/backend/agents/mission_control/__init__.py` (MODIFY)

Clean exports — no aliased imports needed since there's only one `handle` now:

```python
"""Mission control — routes, executes, and streams agent interactions."""

from modules.backend.agents.mission_control.mission_control import (
    handle,
    collect,
    list_agents,
)

__all__ = ["handle", "collect", "list_agents"]
```

---

### Step 9: Update existing mission control tests

**File:** `tests/unit/backend/agents/mission_control/` (MODIFY existing tests)

Existing mission control tests reference the old `handle()` signature (`handle(user_input) -> dict`). These must be rewritten to use the new signature.

**Strategy (P12):** Replace all existing mission control test calls with the new pattern using real infrastructure:
- Use real `SessionService` backed by real PostgreSQL (via `db_session` fixture with transaction rollback)
- Use real `SessionEventBus` backed by real Redis (via `redis` fixture)
- Use real agent registry loaded from real config YAML
- Use `TestModel` (PydanticAI) for LLM calls — the only acceptable mock per P12 (we don't operate LLM providers)
- Call `handle(session_id, message, session_service=real_service, event_bus=real_bus)`
- Collect events and assert on them instead of asserting on dict keys

If existing tests are tightly coupled to the old interface, delete and rewrite them. We're in dev mode.

---

### Step 10: Write new tests

**File:** `tests/unit/backend/mission_control/test_handler.py` (NEW, ~200 lines)

Test the streaming handler:

- `test_handle_yields_user_message_event` — first event is UserMessageEvent with correct content
- `test_handle_yields_thinking_event` — AgentThinkingEvent follows user message
- `test_handle_yields_response_chunks` — AgentResponseChunkEvent for each text chunk
- `test_handle_yields_complete_event` — AgentResponseCompleteEvent with full content and cost
- `test_handle_yields_cost_update_event` — CostUpdateEvent with cumulative cost and budget remaining
- `test_handle_event_order` — events arrive in correct order: user → thinking → [tool events] → chunks → complete → cost
- `test_handle_budget_exceeded` — yields CostUpdateEvent with budget.exceeded and returns
- `test_handle_session_agent_routing` — uses session.agent_id when set
- `test_handle_keyword_routing_fallback` — falls back to keyword routing when no session agent
- `test_handle_persists_user_message` — user message saved via add_message()
- `test_handle_persists_agent_response` — agent response saved
- `test_handle_updates_session_cost` — update_cost() called with correct values
- `test_handle_touches_activity` — touch_activity() called
- `test_handle_loads_conversation_history` — history passed as message_history
- `test_handle_error_does_not_crash_stream` — exception yields partial result
- `test_handle_without_event_bus` — works when event_bus is None

**Testing strategy (P12 — test against real infrastructure, mock only what you don't operate):**
- Use `TestModel` (PydanticAI) for agent execution — the only mock (we don't operate LLM providers per P11)
- Use real `SessionService` with real PostgreSQL (via `db_session` fixture with transaction rollback)
- Use real `SessionEventBus` with real Redis (via `redis` fixture) — subscribe to verify published events
- Use real agent registry loaded from real config YAML files
- Create a real session in the database before each test, assert events and session state after

**File:** `tests/unit/backend/mission_control/test_cost.py` (NEW, ~40 lines)

- `test_compute_cost_usd_known_model`
- `test_compute_cost_usd_unknown_model_uses_default`
- `test_compute_cost_usd_no_pricing`
- `test_estimate_cost`

**File:** `tests/unit/backend/mission_control/test_history.py` (NEW, ~100 lines)

- `test_user_message_to_model_request`
- `test_assistant_message_to_model_response`
- `test_tool_call_to_model_response`
- `test_tool_result_to_model_request`
- `test_system_message_to_model_request`
- `test_unknown_role_skipped`
- `test_roundtrip_conversion`
- `test_cost_attached_to_last_assistant`
- `test_empty_messages`

**File:** `tests/unit/backend/mission_control/test_collect.py` (NEW, ~40 lines)

- `test_collect_returns_full_response`
- `test_collect_returns_agent_name`
- `test_collect_returns_cost`
- `test_collect_empty_stream`

**File:** `tests/integration/backend/mission_control/test_session_chat.py` (NEW, ~100 lines)

- `test_send_message_sse_stream` — POST /sessions/{id}/messages returns SSE
- `test_sse_events_have_correct_format`
- `test_chat_auto_creates_session` — POST /agents/chat without session_id creates one
- `test_chat_with_session_id` — POST /agents/chat with session_id uses it
- `test_session_cost_updated_after_chat`

---

### Step 11: Cleanup and review

- Verify old `handle_direct()`, `handle_direct_stream()`, `_execute_agent()`, `_format_response()` are fully removed
- Verify `with_cost_tracking` decorator is removed from middleware.py
- Verify all callers of `compute_cost_usd` import from `cost.py`
- Verify SSE format follows W3C spec (`event:` + `data:` + double newline)
- Verify all logging uses `get_logger(__name__)`
- Verify all datetimes use `utc_now()`
- Verify event bus publishing is non-critical (try/except)
- Verify message persistence is non-critical (try/except)
- Verify `handle()` accepts service objects as parameters (Temporal ready)
- Verify no file exceeds 500 lines

---

## Files Summary

| Category | File | Action | Est. Lines |
|----------|------|--------|-----------|
| Cost | `modules/backend/agents/mission_control/cost.py` | New | ~60 |
| History | `modules/backend/agents/mission_control/history.py` | New | ~120 |
| Mission Control | `modules/backend/agents/mission_control/mission_control.py` | Rewrite | ~300 (was ~330) |
| Middleware | `modules/backend/agents/mission_control/middleware.py` | Modify | ~50 (was ~130, remove cost tracking) |
| Coordinator init | `modules/backend/agents/mission_control/__init__.py` | Modify | ~10 |
| Agent deps | `modules/backend/agents/deps/base.py` | Modify | +2 |
| Sessions API | `modules/backend/api/v1/endpoints/sessions.py` | Modify | +80 |
| Agents API | `modules/backend/api/v1/endpoints/agents.py` | Rewrite | ~100 (was ~124) |
| Tests - existing | `tests/unit/backend/agents/mission_control/` | Rewrite | varies |
| Tests - handler | `tests/unit/backend/mission_control/test_handler.py` | New | ~200 |
| Tests - cost | `tests/unit/backend/mission_control/test_cost.py` | New | ~40 |
| Tests - history | `tests/unit/backend/mission_control/test_history.py` | New | ~100 |
| Tests - collect | `tests/unit/backend/mission_control/test_collect.py` | New | ~40 |
| Tests - integration | `tests/integration/backend/mission_control/test_session_chat.py` | New | ~100 |
| **Total** | **14 files** | **5 new, 9 modified/rewritten** | **~1,200** |

---

## Anti-Patterns (Do NOT)

- Do not put business logic in mission control. Mission control routes and yields events. Domain decisions live in agents and services.
- Do not call `agent.run()` (non-streaming). Always use `agent.run_stream()`. Synchronous callers use `collect()`.
- Do not let channels call agents directly, bypassing mission control. All operations go through `handle()`.
- Do not use global state in `handle()`. Accept services as parameters — Temporal ready.
- Do not make event publishing or message persistence critical. Both are wrapped in try/except.
- Do not keep dead code. Remove `handle_direct()`, `handle_direct_stream()`, `with_cost_tracking`, `_execute_agent()`, `_format_response()` completely.
- Do not import `logging` directly. Use `from modules.backend.core.logging import get_logger`.
- Do not use `datetime.utcnow()`. Use `from modules.backend.core.utils import utc_now`.
- Do not hardcode model pricing, token limits, or timeouts. All from config.

---
