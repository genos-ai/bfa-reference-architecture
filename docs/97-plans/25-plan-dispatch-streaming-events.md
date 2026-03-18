# Plan 25 — Dispatch Streaming Events

**Status:** Completed
**Created:** 2026-03-18
**Depends on:** Plan 13 (dispatch loop), Plan 23 (TUI — primary consumer)
**Blocks:** Plan 23 Phase 2 (event streaming + agent detail)

## Objective

Switch `_make_agent_executor()` from `agent.run()` to `agent.run_stream()` so that dispatch emits real-time `AgentResponseChunkEvent`, `AgentToolCallEvent`, and `AgentToolResultEvent` during agent execution. The executor still returns a complete `dict` — the streaming is internal, solely for event emission.

Without this change, the TUI's agent detail panel (thinking tab, tools tab, output tab) shows nothing during dispatch tasks. Users see `PlanStepStartedEvent` → long silence → `PlanStepCompletedEvent`. With it, they see live tool calls, streaming output, and thinking activity.

---

## Problem

The `handle()` interactive path (Plan 12) uses `agent.run_stream()` and emits 5 event types during execution:

```
AgentThinkingEvent → AgentResponseChunkEvent* → AgentToolCallEvent* → AgentToolResultEvent* → AgentResponseCompleteEvent
```

The `_make_agent_executor()` dispatch path (Plan 13) uses `agent.run()` and emits only:

```
AgentThinkingEvent → [silence during execution] → AgentResponseCompleteEvent
```

Three event types are missing from the dispatch path:

| Event | What it enables in TUI |
|-------|----------------------|
| `AgentResponseChunkEvent` | Live text streaming in agent output tab |
| `AgentToolCallEvent` | Tool call entries in agent tools tab |
| `AgentToolResultEvent` | Tool result display in agent tools tab |

---

## Solution

Replace `agent.run()` with `agent.run_stream()` inside `_make_agent_executor()`. The streaming is consumed internally to emit events, then the complete output is extracted via `stream.get_output()`. The function signature and return type (`dict`) do not change — callers (dispatch, verification) are unaffected.

---

## Current Code (Before)

**File:** `modules/backend/agents/mission_control/helpers.py`, lines 352–449

```python
def _make_agent_executor(
    event_bus: EventBusProtocol,
    *,
    session_id: str,
    mission_id: str,
) -> ExecuteAgentFn:
    cumulative_cost_usd = 0.0

    async def execute_agent(
        agent_name: str,
        instructions: str,
        inputs: dict,
        usage_limits: UsageLimits,
    ) -> dict:
        nonlocal cumulative_cost_usd

        # ... agent setup, PQI pre-computation ...

        await _emit(event_bus, AgentThinkingEvent, ...)

        # ── THE GAP ──────────────────────────────────────
        # Blocks until agent finishes. No events emitted.
        run_result = await agent.run(
            user_message, deps=deps, usage_limits=usage_limits,
        )
        # ─────────────────────────────────────────────────

        output = run_result.output
        # ... PQI injection, serialization, usage extraction ...

        await _emit(event_bus, AgentResponseCompleteEvent, ...)
        await _emit(event_bus, CostUpdateEvent, ...)
        return output_dict

    return execute_agent
```

---

## Target Code (After)

**File:** `modules/backend/agents/mission_control/helpers.py`

```python
def _make_agent_executor(
    event_bus: EventBusProtocol,
    *,
    session_id: str,
    mission_id: str,
) -> ExecuteAgentFn:
    cumulative_cost_usd = 0.0

    async def execute_agent(
        agent_name: str,
        instructions: str,
        inputs: dict,
        usage_limits: UsageLimits,
    ) -> dict:
        nonlocal cumulative_cost_usd

        # ... agent setup, PQI pre-computation (UNCHANGED) ...

        await _emit(event_bus, AgentThinkingEvent, ...)

        # ── STREAMING EXECUTION ──────────────────────────
        source = f"dispatch:{mission_id}"
        full_content = ""

        async with agent.run_stream(
            user_message, deps=deps, usage_limits=usage_limits,
        ) as stream:
            # Stream text deltas for live output.
            # Structured-output agents raise UserError — fall back
            # to get_output() (same pattern as handle()).
            try:
                async for text in stream.stream_text(delta=True):
                    full_content += text
                    await _emit(event_bus, AgentResponseChunkEvent,
                        session_id=session_id,
                        source=source,
                        agent_id=agent_name,
                        content=text,
                    )
            except UserError:
                # Structured output — no text stream available.
                # Output will be extracted via get_output() below.
                pass

            # Extract complete output (works for both text and structured)
            output = await stream.get_output()

            # Extract tool calls and results retrospectively
            _emit_tool_events(
                event_bus, stream, session_id=session_id,
                source=source, agent_id=agent_name,
            )

            # Usage is available after stream completes
            usage = stream.usage()
        # ─────────────────────────────────────────────────

        # ... PQI injection, serialization (UNCHANGED) ...
        # ... cost computation, _meta, events (UNCHANGED) ...

        return output_dict

    return execute_agent
```

---

## Detailed Changes

### Change 1: New imports in `helpers.py`

```python
# Add to existing imports from pydantic_ai
from pydantic_ai import UserError
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)

# Add to existing event imports
from modules.backend.events.types import (
    AgentResponseChunkEvent,    # NEW
    AgentResponseCompleteEvent,
    AgentThinkingEvent,
    AgentToolCallEvent,         # NEW
    AgentToolResultEvent,       # NEW
    CostUpdateEvent,
    SessionEvent,
)
```

### Change 2: Extract tool event emission helper

Add a new helper function after `_emit()` in `helpers.py`:

```python
async def _emit_tool_events(
    event_bus: EventBusProtocol,
    stream,
    *,
    session_id: str,
    source: str,
    agent_id: str,
) -> None:
    """Extract and emit tool call/result events from a completed stream.

    Reads stream.new_messages() retrospectively (after streaming ends)
    to find ToolCallPart and ToolReturnPart entries. This is the same
    pattern used by handle() in mission_control.py lines 244-278.

    Best-effort — errors are logged and swallowed.
    """
    try:
        for msg in stream.new_messages():
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart):
                        await _emit(event_bus, AgentToolCallEvent,
                            session_id=session_id,
                            source=source,
                            agent_id=agent_id,
                            tool_name=part.tool_name,
                            tool_args={
                                "raw": part.args if isinstance(part.args, str) else str(part.args),
                            },
                            tool_call_id=part.tool_call_id or str(uuid.uuid4()),
                        )
            elif isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, ToolReturnPart):
                        await _emit(event_bus, AgentToolResultEvent,
                            session_id=session_id,
                            source=source,
                            agent_id=agent_id,
                            tool_name=part.tool_name,
                            tool_call_id=part.tool_call_id or "",
                            result=(
                                part.content
                                if isinstance(part.content, str)
                                else str(part.content)
                            ),
                        )
    except (AttributeError, TypeError, KeyError, ValueError):
        logger.debug("Failed to extract tool events", exc_info=True)
```

**Why a separate helper:**
- `handle()` in mission_control.py has nearly identical logic (lines 244-278) but also `yield`s events. Extracting to a shared helper avoids duplication — `handle()` can be updated to call this too (optional follow-up).
- Keeps `execute_agent()` focused on the execution flow, not message parsing.

### Change 3: Replace `agent.run()` with `agent.run_stream()` in `execute_agent()`

The full replacement of the execution block in `_make_agent_executor()`:

**Remove:**
```python
        # Call agent.run() directly to retain usage metadata
        run_result = await agent.run(
            user_message, deps=deps, usage_limits=usage_limits,
        )

        # Extract output
        output = run_result.output
```

**Replace with:**
```python
        # Stream agent execution for real-time event emission.
        # The executor still returns a complete dict — streaming is
        # internal, solely for emitting chunk/tool events to the bus.
        source = f"dispatch:{mission_id}"

        async with agent.run_stream(
            user_message, deps=deps, usage_limits=usage_limits,
        ) as stream:
            try:
                async for text in stream.stream_text(delta=True):
                    await _emit(event_bus, AgentResponseChunkEvent,
                        session_id=session_id,
                        source=source,
                        agent_id=agent_name,
                        content=text,
                    )
            except UserError:
                pass  # Structured output agent — no text stream

            output = await stream.get_output()
            await _emit_tool_events(
                event_bus, stream,
                session_id=session_id,
                source=source,
                agent_id=agent_name,
            )
            usage = stream.usage()
```

**Then update the usage extraction block — remove:**
```python
        # Extract usage from the AgentRunResult
        usage = run_result.usage()
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
```

**Replace with:**
```python
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
```

(`usage` is already assigned inside the `async with` block.)

### Change 4: Add `uuid` import to `helpers.py`

```python
import uuid  # Add to existing imports at top of file
```

Required by `_emit_tool_events` for fallback `tool_call_id`.

---

## What Does NOT Change

These elements remain exactly as they are:

1. **Function signature** — `execute_agent(agent_name, instructions, inputs, usage_limits) -> dict` is unchanged. The `ExecuteAgentFn` protocol still matches.

2. **Return value** — still returns `output_dict` with `_meta` key. Dispatch, verification, retry — all callers are unaffected.

3. **PQI pre-computation** (lines 406-419) — happens before streaming starts, injects into `user_message`. No change needed.

4. **PQI post-injection** (lines 429-431) — `output = await stream.get_output()` returns the same typed output object as `run_result.output`. The `hasattr(output, "pqi")` check and mutation work identically.

5. **Output serialization** (lines 433-438) — `model_dump()` / `dict` / `str` fallback. Input is the same `output` object.

6. **Cost computation** — `stream.usage()` returns the same `RunUsage` object as `run_result.usage()`. Fields are identical.

7. **`_meta` dict construction** (lines 448-453) — uses `input_tokens`, `output_tokens`, `cost_usd`. All computed the same way.

8. **`AgentResponseCompleteEvent` and `CostUpdateEvent` emission** — still emitted after streaming completes. No change.

9. **`cumulative_cost_usd` tracking** — unchanged.

10. **`dispatch()`, `_execute_with_retry()`, `_execute_with_step_events()`** — zero changes.

---

## Event Flow After Implementation

```
_execute_with_step_events()
  ├─ PlanStepStartedEvent
  ├─ _execute_with_retry()
  │   └─ execute_agent()
  │       ├─ AgentThinkingEvent
  │       ├─ agent.run_stream()
  │       │   ├─ AgentResponseChunkEvent*    ← NEW (live text deltas)
  │       │   └─ (stream completes)
  │       ├─ AgentToolCallEvent*             ← NEW (retrospective)
  │       ├─ AgentToolResultEvent*           ← NEW (retrospective)
  │       ├─ AgentResponseCompleteEvent
  │       └─ CostUpdateEvent
  └─ PlanStepCompletedEvent
```

Now matches the `handle()` event coverage exactly.

---

## Edge Cases

### Structured output agents (most dispatch agents)

Most agents in the roster return structured Pydantic models, not text. For these:
- `stream.stream_text(delta=True)` raises `UserError`
- The `except UserError: pass` branch executes
- No `AgentResponseChunkEvent`s are emitted (expected — no text to stream)
- `stream.get_output()` returns the structured model
- Tool events and completion event still emit normally

This is correct behavior — the TUI's output tab falls back to showing the complete JSON when no chunks arrive.

### Agents with no tools

- `stream.new_messages()` returns messages with no `ToolCallPart`/`ToolReturnPart`
- `_emit_tool_events()` iterates but emits nothing
- No error — clean no-op

### NoOpEventBus (default)

When no TUI/consumer is connected, `event_bus` is `NoOpEventBus`. All `_emit()` calls resolve instantly (async no-op). The streaming overhead is the `async for` loop over text deltas that no one reads — minimal cost.

### Event construction failures

All emission goes through `_emit()` which catches `Exception` during both construction and publish. A malformed `session_id` (non-UUID string) is logged at debug level and swallowed. Execution continues normally.

### Timeout enforcement

`asyncio.wait_for()` in `execute_task()` wraps the entire `execute_agent()` call. If the timeout fires during streaming, `asyncio.TimeoutError` propagates up and the `async with` block cleans up the stream context manager. No resource leak.

### `UsageLimitExceeded`

PydanticAI raises this during streaming when token limits are hit. It propagates out of the `async with` block, through `execute_task()`, and is caught by `_execute_with_retry()` which fails-fast (no retry on token limit errors). Same behavior as `agent.run()`.

---

## Performance Impact

| Aspect | `agent.run()` | `agent.run_stream()` |
|--------|--------------|---------------------|
| API call | Single request | Same single request |
| Token usage | Identical | Identical |
| Network | Waits for complete response | Receives SSE chunks |
| CPU overhead | None | `async for` loop + event construction |
| Latency to first event | After full completion | After first token |

The performance difference is negligible. `run_stream()` uses the same API call but receives the response incrementally. The main cost is constructing `AgentResponseChunkEvent` objects per chunk, which `_emit()` handles as fire-and-forget.

For `NoOpEventBus` (no consumer), the overhead is near-zero: the `async for` loop iterates over chunks, calls `_emit()` which constructs the event and calls `NoOpEventBus.publish()` (a no-op coroutine).

---

## Verification Plan

### Unit Tests

1. **Test streaming event emission** — Mock `agent.run_stream()` to yield text chunks. Verify `AgentResponseChunkEvent`s are emitted with correct `content` and `agent_id`.

2. **Test structured output fallback** — Mock `stream.stream_text()` to raise `UserError`. Verify no chunk events emitted, but `AgentResponseCompleteEvent` still emits with complete output.

3. **Test tool event extraction** — Mock `stream.new_messages()` to return messages with `ToolCallPart` and `ToolReturnPart`. Verify `AgentToolCallEvent` and `AgentToolResultEvent` emitted with correct fields.

4. **Test output dict unchanged** — Verify `execute_agent()` returns identical `output_dict` (including `_meta`) as before the change.

5. **Test PQI injection still works** — Mock QA agent with PQI. Verify `output.pqi` is overwritten after `stream.get_output()`.

6. **Test `_emit_tool_events` with empty messages** — Verify no events emitted, no errors.

7. **Test `_emit_tool_events` with malformed messages** — Verify errors logged and swallowed.

### Integration Tests

8. **Run existing dispatch test suite** — All 42 dispatch tests must pass unchanged. The switch from `run()` to `run_stream()` is internal to the executor.

9. **Full test suite** — All 1227 tests pass with zero warnings.

### Manual Verification

10. **`python -c "from modules.backend.agents.mission_control.helpers import _make_agent_executor"`** — imports cleanly.

11. **Run a live mission with event capture** — Connect an event listener, run a mission, verify the event stream shows chunk/tool/result events between `PlanStepStarted` and `PlanStepCompleted`.

---

## Execution Steps

1. Add `uuid` import and new PydanticAI imports (`UserError`, message types) to `helpers.py`
2. Add `AgentResponseChunkEvent`, `AgentToolCallEvent`, `AgentToolResultEvent` to event imports in `helpers.py`
3. Add `_emit_tool_events()` helper function after `_emit()` in `helpers.py`
4. Replace `agent.run()` block with `agent.run_stream()` block in `execute_agent()`
5. Update `usage` extraction (move inside `async with` block)
6. Run `python -m pytest tests/unit/backend/mission_control/ -x -q` — all pass
7. Run `python -m pytest tests/ -x -q -W error::RuntimeWarning` — all 1227 pass, zero warnings
8. Verify import: `python -c "from modules.backend.agents.mission_control.helpers import _make_agent_executor"`

---

## Optional Follow-up: DRY `handle()` Tool Extraction

After this plan lands, `handle()` in `mission_control.py` (lines 244-278) has near-identical tool extraction logic. A follow-up can replace it with a call to `_emit_tool_events()` plus yielding the events. This is cosmetic — not blocking.

---

## Risk Assessment

**Low risk:**
- `agent.run_stream()` is the same API call as `agent.run()` — PydanticAI uses the same model endpoint
- `stream.get_output()` returns the same typed object as `run_result.output`
- `stream.usage()` returns the same `RunUsage` as `run_result.usage()`
- All event emission is best-effort via `_emit()` — failures are swallowed
- Function signature and return type unchanged — zero caller impact
- `handle()` already uses this exact pattern in production

**Only risk:** If a custom agent's `create_agent()` returns an agent type that doesn't support `run_stream()`. This would be caught immediately by a `TypeError` or `AttributeError`. Mitigation: all agents are PydanticAI `Agent` instances, which always support `run_stream()`.
