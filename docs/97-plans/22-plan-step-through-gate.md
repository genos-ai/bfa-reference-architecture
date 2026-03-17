# Plan 22 — Step-Through Gate (Human/AI-in-the-Loop)

**Status:** Draft
**Created:** 2026-03-17
**Depends on:** Plans 13 (Dispatch), 17 (Playbooks/Missions), 14 (Verification)

## Objective

Add a **gate mechanism** to the agent dispatch pipeline that pauses execution at
key decision points, presents context (plan, inputs, outputs, verification,
cost), and waits for a **reviewer** to approve, reject, modify, skip, or retry
before proceeding.

The reviewer is abstracted behind a protocol — the first implementation is an
interactive CLI (human-in-the-loop), but the same protocol supports a thinking
LLM reviewer (AI-in-the-loop) or a composite (AI proposes, human confirms).

This is primarily a **development/testing tool** for validating agent behavior,
accuracy, and workflow correctness. It is opt-in (`--step` flag) and has zero
impact on autonomous execution when disabled.

## Architecture

### Gate Protocol

```python
# modules/backend/agents/mission_control/gate.py

class GateAction(str, Enum):
    CONTINUE = "continue"   # Proceed to next step
    SKIP = "skip"           # Skip this task/layer, mark SKIPPED
    RETRY = "retry"         # Re-run the task (with optional modified inputs)
    ABORT = "abort"         # Halt the entire mission/playbook
    MODIFY = "modify"       # Proceed but with modified inputs (returns new dict)

@dataclass
class GateContext:
    """Everything the reviewer needs to make a decision."""
    gate_type: str               # "pre_layer", "post_task", "post_layer",
                                 # "pre_dispatch", "verification_failed"
    mission_id: str
    layer_index: int             # Current layer number (0-based)
    total_layers: int
    # Pre-layer context
    pending_tasks: list[dict]    # Tasks about to execute (task_id, agent, inputs)
    # Post-task context
    task_result: TaskResult | None
    task_output: dict | None     # Raw agent output
    verification: dict | None    # Verification outcome if available
    # Aggregates
    completed_tasks: list[TaskResult]
    total_cost_usd: float
    budget_usd: float
    # For retry/modify
    current_instructions: str | None
    current_inputs: dict | None

@dataclass
class GateDecision:
    """Reviewer's decision."""
    action: GateAction
    reason: str | None = None
    modified_inputs: dict | None = None        # For MODIFY action
    modified_instructions: str | None = None   # For RETRY with feedback
    reviewer: str = "human"                    # "human", "ai:claude-sonnet-4-6", etc.


class GateReviewer(Protocol):
    """Abstract reviewer — human, AI, or composite."""

    async def review(self, context: GateContext) -> GateDecision:
        """Present context and return a decision. May block (human) or call LLM (AI)."""
        ...
```

### Gate Points

There are **5 gate points** in the pipeline. Each is opt-in — only fires if a
`GateReviewer` is provided to `dispatch()`.

| # | Gate Point | Location | Fires When | Context Available |
|---|-----------|----------|------------|-------------------|
| 1 | `pre_dispatch` | `dispatch()` entry | Before any execution | Full task plan, roster, budget |
| 2 | `pre_layer` | Before `asyncio.gather()` | Before each layer executes | Pending tasks with resolved inputs |
| 3 | `post_task` | After task completes | After each task (success or fail) | Task output, verification, cost |
| 4 | `verification_failed` | After verification fails | Before retry decision | Verification details, feedback |
| 5 | `post_layer` | After layer results collected | Before proceeding to next layer | All layer results, cumulative cost |

### Reviewer Implementations

#### 1. `CliGateReviewer` (Human-in-the-loop)

Interactive Rich-based CLI reviewer for development/testing.

```
┌─── Gate: pre_layer (Layer 2/3) ──────────────────────────────────┐
│                                                                   │
│  Mission: abc-123   Budget: $0.42 / $2.00                        │
│                                                                   │
│  Tasks about to execute:                                          │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ task-002  code.quality.agent                               │   │
│  │ Instructions: Audit the codebase for compliance...         │   │
│  │ Inputs: {project_context: {...}, scope: "modules/"}        │   │
│  │ Depends on: task-001 (✓ completed)                         │   │
│  ├────────────────────────────────────────────────────────────┤   │
│  │ task-003  system.health.agent                              │   │
│  │ Instructions: Check system health...                       │   │
│  │ Inputs: {project_context: {...}}                           │   │
│  │ Depends on: task-001 (✓ completed)                         │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                   │
│  [c]ontinue  [s]kip  [a]bort  [i]nspect task  [?] help          │
└───────────────────────────────────────────────────────────────────┘
```

Post-task view:

```
┌─── Gate: post_task ──────────────────────────────────────────────┐
│                                                                   │
│  Task: task-002 (code.quality.agent)                             │
│  Status: ✓ SUCCESS  Duration: 34.2s  Cost: $0.18                │
│                                                                   │
│  Verification: Tier 1 ✓  Tier 2 ✓  Tier 3 ✓ (score: 0.92)     │
│                                                                   │
│  Output (summary): Found 21 violations (9 errors, 12 warnings)  │
│  PQI: 67.1/100 (Good)                                           │
│                                                                   │
│  [c]ontinue  [r]etry  [a]bort  [o]utput (full)  [v]erification  │
└───────────────────────────────────────────────────────────────────┘
```

**Inspect mode** (`[o]utput`, `[v]erification`, `[i]nspect`):
- `[o]` — render full agent output using `render_human()` from report.py
- `[v]` — show per-tier verification details
- `[i]` — show resolved inputs, instructions, upstream references
- `[t]` — show token usage breakdown
- These don't consume a gate action — user returns to the decision prompt after

#### 2. `NoOpGate` (Autonomous — default)

```python
class NoOpGate:
    """Pass-through gate that always continues. Zero overhead."""
    async def review(self, context: GateContext) -> GateDecision:
        return GateDecision(action=GateAction.CONTINUE)
```

This is the default when `--step` is not provided. The gate calls are still
made but return instantly. The `if gate:` check pattern is NOT used — instead
the NoOpGate eliminates branching.

#### 3. `LlmGateReviewer` (AI-in-the-loop — future)

Uses a thinking LLM (e.g., Claude Sonnet with extended thinking) to review
each gate point. The LLM receives the same `GateContext` and returns a
`GateDecision`.

```python
class LlmGateReviewer:
    """AI reviewer using a thinking model."""

    def __init__(self, model: str = "claude-sonnet-4-6", thinking_budget: int = 5000):
        self.model = model
        self.thinking_budget = thinking_budget

    async def review(self, context: GateContext) -> GateDecision:
        prompt = self._build_review_prompt(context)
        # Call LLM with structured output → GateDecision
        ...
```

The AI reviewer's prompt would include:
- The task plan and current progress
- The specific output to review
- Quality criteria (verification results, PQI scores, etc.)
- Cost tracking (is the mission on budget?)
- Instructions to flag anything suspicious or low-quality

#### 4. `CompositeGateReviewer` (AI proposes, human confirms — future)

```python
class CompositeGateReviewer:
    """AI makes recommendation, human has final say."""

    def __init__(self, ai: LlmGateReviewer, human: CliGateReviewer):
        self.ai = ai
        self.human = human

    async def review(self, context: GateContext) -> GateDecision:
        ai_decision = await self.ai.review(context)
        # Show AI's recommendation to human
        context.ai_recommendation = ai_decision
        return await self.human.review(context)
```

---

## Implementation Steps

### Step 1: Gate Protocol & Models

**File:** `modules/backend/agents/mission_control/gate.py` (new)

Create the gate module with:
- `GateAction` enum
- `GateContext` dataclass
- `GateDecision` dataclass
- `GateReviewer` protocol
- `NoOpGate` implementation (always continues)

**Constraints:**
- No external dependencies beyond stdlib + pydantic
- All fields in `GateContext` must be serializable (for future AI reviewer)
- `GateDecision` must include `reviewer` field for audit trail

### Step 2: Wire Gate into Dispatch Loop

**File:** `modules/backend/agents/mission_control/dispatch.py`

Modify `dispatch()` signature to accept an optional gate:

```python
async def dispatch(
    plan: TaskPlan,
    roster: Roster,
    execute_agent_fn: ExecuteAgentFn,
    mission_budget_usd: float,
    *,
    gate: GateReviewer | None = None,   # ← NEW
    project_id: str | None = None,
    context_curator: ContextCuratorProtocol | None = None,
    context_assembler: ContextAssemblerProtocol | None = None,
) -> MissionOutcome:
```

If `gate` is None, use `NoOpGate()` internally (no branching needed).

**Gate point 1 — `pre_dispatch`** (after topological sort, before layer loop):
```python
layers = topological_sort(plan)
gate = gate or NoOpGate()

# Gate 1: Review full plan before execution
decision = await gate.review(GateContext(
    gate_type="pre_dispatch",
    mission_id=plan.mission_id,
    layer_index=0,
    total_layers=len(layers),
    pending_tasks=[
        {"task_id": t.task_id, "agent": t.agent, "description": t.description}
        for t in plan.tasks
    ],
    completed_tasks=[],
    total_cost_usd=0.0,
    budget_usd=mission_budget_usd,
))
if decision.action == GateAction.ABORT:
    return _aborted_outcome(plan, decision.reason)
```

**Gate point 2 — `pre_layer`** (after input resolution, before `asyncio.gather`):
```python
for layer_idx, layer in enumerate(layers):
    # ... resolve inputs ...

    decision = await gate.review(GateContext(
        gate_type="pre_layer",
        mission_id=plan.mission_id,
        layer_index=layer_idx,
        total_layers=len(layers),
        pending_tasks=[
            {
                "task_id": t.task_id,
                "agent": t.agent,
                "instructions": t.instructions[:500],
                "inputs": resolved_inputs_map[t.task_id],
            }
            for t in layer_tasks
        ],
        completed_tasks=task_results,
        total_cost_usd=total_cost,
        budget_usd=mission_budget_usd,
    ))
    if decision.action == GateAction.ABORT:
        return _aborted_outcome(plan, decision.reason, task_results)
    if decision.action == GateAction.SKIP:
        # Mark all tasks in layer as SKIPPED
        for t in layer_tasks:
            task_results.append(_skipped_result(t, decision.reason))
        continue
```

**Gate point 5 — `post_layer`** (after results collected, before budget check):
```python
    # After asyncio.gather and result collection...

    decision = await gate.review(GateContext(
        gate_type="post_layer",
        mission_id=plan.mission_id,
        layer_index=layer_idx,
        total_layers=len(layers),
        pending_tasks=[],
        completed_tasks=task_results,
        total_cost_usd=total_cost,
        budget_usd=mission_budget_usd,
    ))
    if decision.action == GateAction.ABORT:
        break
```

**Gate points 3 & 4** — inside `_execute_with_retry()`. Pass gate as parameter:

```python
async def _execute_with_retry(
    task, roster_entry, resolved_inputs, execute_agent_fn, execution_id,
    gate: GateReviewer | None = None,   # ← NEW
) -> TaskResult:
```

**Gate 3 — `post_task`** (after execution + verification, on success):
```python
    # After verification passes...
    decision = await gate.review(GateContext(
        gate_type="post_task",
        task_result=TaskResult(...),  # Preliminary result
        task_output=output,
        verification=build_verification_outcome(verification).model_dump(),
        current_instructions=instructions,
        current_inputs=resolved_inputs,
        ...
    ))
    if decision.action == GateAction.RETRY:
        instructions = decision.modified_instructions or instructions
        continue  # Next attempt
    if decision.action == GateAction.ABORT:
        return _failed_result(task, "Aborted by reviewer")
    if decision.action == GateAction.SKIP:
        return _skipped_result(task, decision.reason)
```

**Gate 4 — `verification_failed`** (before retry decision):
```python
    if not verification.passed:
        feedback = build_retry_feedback(verification, attempt=attempt + 1)

        if attempt < retry_budget:
            decision = await gate.review(GateContext(
                gate_type="verification_failed",
                task_output=output,
                verification=build_verification_outcome(verification).model_dump(),
                current_instructions=instructions,
                ...
            ))
            if decision.action == GateAction.ABORT:
                return _failed_result(task, "Aborted after verification failure")
            if decision.action == GateAction.SKIP:
                return _skipped_result(task, "Skipped after verification failure")
            if decision.action == GateAction.CONTINUE:
                pass  # Accept despite verification failure
            # Default (RETRY): proceed with retry as normal
```

**New helper functions:**

```python
def _aborted_outcome(plan, reason, task_results=None) -> MissionOutcome:
    """Build a MissionOutcome for an aborted mission."""
    ...

def _skipped_result(task, reason) -> TaskResult:
    """Build a TaskResult with SKIPPED status."""
    ...
```

**Note:** Add `SKIPPED` to `TaskStatus` enum if not already present (it is — see
outcome.py line 29).

### Step 3: Wire Gate into Playbook Execution

**File:** `modules/backend/services/playbook_run.py`

The playbook layer sits above the dispatch layer. Since dispatch already has
gate support, the playbook layer gets step-through "for free" at the task
level. However, the playbook layer has its own wave structure that the user
may also want to gate.

Add gate parameter threading:

```python
async def run_playbook(
    self,
    playbook_name: str,
    triggered_by: str = "user:cli",
    context_overrides: dict[str, Any] | None = None,
    on_progress: Any | None = None,
    project_name: str | None = None,
    gate: GateReviewer | None = None,   # ← NEW
) -> PlaybookRun:
```

Thread `gate` through:
- `run_playbook()` → `_execute_steps()` → `_execute_wave()` → `_execute_step()`
- In `_execute_step()`, pass gate to `mission_service.execute_mission()`
- In `mission_service.execute_mission()`, pass gate to the dispatch adapter
- In `dispatch_adapter.execute()`, pass gate to `dispatch()`

**Playbook-level wave gates** are handled by emitting progress events that the
CLI can intercept — no additional gate points needed at this layer since the
dispatch loop handles task-level gating.

### Step 4: Thread Gate Through Mission Service

**File:** `modules/backend/services/mission.py`

Add gate parameter to:

```python
async def execute_mission(
    self, mission_id: str,
    gate: GateReviewer | None = None,   # ← NEW
) -> Mission:
```

Pass to dispatch adapter:

```python
outcome = await self._mission_control_dispatch.execute(
    ...,
    gate=gate,
)
```

**File:** `modules/backend/agents/mission_control/dispatch_adapter.py`

Add gate to the adapter's execute method and thread to `dispatch()`.

**File:** `modules/backend/agents/mission_control/mission_control.py`

Add gate to `handle_mission()` and thread to `dispatch()`.

### Step 5: CLI Interactive Reviewer

**File:** `modules/backend/cli/gate.py` (new)

Implement `CliGateReviewer` using Rich for rendering:

```python
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

class CliGateReviewer:
    """Interactive CLI gate reviewer using Rich."""

    def __init__(self, console: Console | None = None, verbose: bool = False):
        self.console = console or Console()
        self.verbose = verbose

    async def review(self, context: GateContext) -> GateDecision:
        """Render gate context and prompt for decision."""
        self._render_header(context)

        if context.gate_type == "pre_dispatch":
            return await self._review_pre_dispatch(context)
        elif context.gate_type == "pre_layer":
            return await self._review_pre_layer(context)
        elif context.gate_type == "post_task":
            return await self._review_post_task(context)
        elif context.gate_type == "verification_failed":
            return await self._review_verification_failed(context)
        elif context.gate_type == "post_layer":
            return await self._review_post_layer(context)
```

**Rendering helpers** (use Rich panels, tables, syntax highlighting):

- `_render_header()` — gate type, mission ID, progress bar, cost
- `_render_task_preview()` — task details, agent, inputs (truncated)
- `_render_task_result()` — status, duration, cost, output summary
- `_render_verification()` — per-tier pass/fail with details
- `_render_output_full()` — delegate to `report.render_human()` for full output

**Prompt actions per gate type:**

| Gate Type | Actions Available |
|-----------|------------------|
| `pre_dispatch` | `[c]ontinue`, `[a]bort`, `[i]nspect plan` |
| `pre_layer` | `[c]ontinue`, `[s]kip layer`, `[a]bort`, `[i]nspect task N` |
| `post_task` | `[c]ontinue`, `[r]etry`, `[s]kip`, `[a]bort`, `[o]utput`, `[v]erification` |
| `verification_failed` | `[r]etry` (default), `[c]ontinue` (accept anyway), `[a]bort`, `[v]erification` |
| `post_layer` | `[c]ontinue`, `[a]bort` |

**Inspect sub-commands** (non-consuming — return to prompt):
- `[o]` — full output via render_human()
- `[v]` — verification detail panel
- `[i]` — inputs/instructions panel
- `[t]` — token usage table
- `[j]` — raw JSON dump of output

### Step 6: CLI Flag & Wiring

**File:** `modules/backend/cli/playbook.py`

Add `--step` flag to the playbook run command:

```python
# In the CLI group/command definition
@click.option("--step", is_flag=True, help="Step-through mode: pause at each gate point for review")
```

In `_action_run()`:

```python
gate = None
if step:
    from modules.backend.cli.gate import CliGateReviewer
    gate = CliGateReviewer(console=console, verbose=verbose)

# Pass gate to run_playbook
run = await playbook_run_service.run_playbook(
    playbook_name=playbook_name,
    ...,
    gate=gate,
)
```

Also add to mission CLI and test_agents_live.py for single-agent testing.

### Step 7: Gate Decision Logging

All gate decisions should be logged for audit trail:

```python
logger.info(
    "Gate decision",
    extra={
        "gate_type": context.gate_type,
        "mission_id": context.mission_id,
        "action": decision.action.value,
        "reviewer": decision.reviewer,
        "reason": decision.reason,
    },
)
```

Store gate decisions in MissionOutcome for post-run analysis:

```python
# In outcome.py
class GateDecisionRecord(BaseModel):
    gate_type: str
    layer_index: int
    task_id: str | None = None
    action: str
    reason: str | None = None
    reviewer: str

# In MissionOutcome
gate_decisions: list[GateDecisionRecord] = []
```

### Step 8: Tests

**File:** `tests/unit/backend/agents/mission_control/test_gate.py` (new)

Test the gate mechanism:

```python
class TestNoOpGate:
    async def test_always_continues(self):
        gate = NoOpGate()
        ctx = GateContext(gate_type="pre_layer", ...)
        decision = await gate.review(ctx)
        assert decision.action == GateAction.CONTINUE

class TestGateIntegration:
    async def test_abort_stops_dispatch(self):
        """Gate that aborts on pre_dispatch should return empty outcome."""
        gate = AbortGate()  # Test helper that always aborts
        outcome = await dispatch(plan, roster, executor, 10.0, gate=gate)
        assert outcome.status == MissionStatus.FAILED
        assert len(outcome.task_results) == 0

    async def test_skip_layer_marks_tasks_skipped(self):
        """Gate that skips should mark all layer tasks as SKIPPED."""
        gate = SkipLayerGate(skip_layer=1)
        outcome = await dispatch(plan, roster, executor, 10.0, gate=gate)
        skipped = [r for r in outcome.task_results if r.status == TaskStatus.SKIPPED]
        assert len(skipped) > 0

    async def test_retry_replays_task(self):
        """Gate that returns RETRY should re-execute the task."""
        gate = RetryOnceGate()
        outcome = await dispatch(plan, roster, executor, 10.0, gate=gate)
        # Task should have retry_count >= 1

    async def test_gate_not_called_when_none(self):
        """Default dispatch (no gate) should work unchanged."""
        outcome = await dispatch(plan, roster, executor, 10.0)
        assert outcome.status in (MissionStatus.SUCCESS, MissionStatus.PARTIAL)

class TestGateContext:
    def test_context_serializable(self):
        """GateContext must be JSON-serializable for AI reviewer."""
        ctx = GateContext(...)
        json.dumps(asdict(ctx), default=str)  # Should not raise
```

### Step 9: LLM Gate Reviewer (Future — Stub Only)

**File:** `modules/backend/agents/mission_control/gate.py`

Add a stub for the AI reviewer (not fully implemented, but interface ready):

```python
class LlmGateReviewer:
    """AI-in-the-loop reviewer (stub — full implementation in Plan 23)."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model

    async def review(self, context: GateContext) -> GateDecision:
        raise NotImplementedError(
            "LLM gate reviewer not yet implemented. "
            "Use CliGateReviewer for interactive review."
        )
```

---

## File Summary

| File | Action | Description |
|------|--------|-------------|
| `modules/backend/agents/mission_control/gate.py` | **NEW** | Gate protocol, models, NoOpGate, LlmGateReviewer stub |
| `modules/backend/agents/mission_control/dispatch.py` | MODIFY | Add gate parameter, 5 gate points, _aborted_outcome, _skipped_result |
| `modules/backend/agents/mission_control/outcome.py` | MODIFY | Add GateDecisionRecord, gate_decisions to MissionOutcome |
| `modules/backend/agents/mission_control/models.py` | MODIFY | Export GateReviewer protocol (optional) |
| `modules/backend/agents/mission_control/mission_control.py` | MODIFY | Thread gate through handle_mission → dispatch |
| `modules/backend/agents/mission_control/dispatch_adapter.py` | MODIFY | Thread gate through adapter.execute → dispatch |
| `modules/backend/services/mission.py` | MODIFY | Thread gate through execute_mission |
| `modules/backend/services/playbook_run.py` | MODIFY | Thread gate through run_playbook → _execute_steps → _execute_wave |
| `modules/backend/cli/gate.py` | **NEW** | CliGateReviewer with Rich rendering |
| `modules/backend/cli/playbook.py` | MODIFY | Add --step flag, instantiate CliGateReviewer |
| `scripts/test_agents_live.py` | MODIFY | Add --step flag support |
| `tests/unit/backend/agents/mission_control/test_gate.py` | **NEW** | Gate unit and integration tests |

## Key Design Decisions

1. **NoOpGate as default** — no `if gate:` branching; always call gate, NoOpGate returns instantly
2. **Gate at dispatch level, not playbook level** — playbook waves map to missions which run dispatch internally; gating at dispatch covers all execution paths
3. **Non-consuming inspect commands** — `[o]`, `[v]`, `[i]` show detail and return to prompt, don't consume the gate action
4. **GateContext is serializable** — enables AI reviewer to receive the same data as human reviewer
5. **Gate decisions recorded in MissionOutcome** — full audit trail of reviewer decisions
6. **Async protocol** — supports both blocking (human input) and non-blocking (AI call) reviewers
7. **Gate threads through existing parameter chains** — no global state, no monkey-patching, explicit dependency injection

## Sequence Diagram

```
CLI (--step)
  │
  ├─ Creates CliGateReviewer
  ├─ Calls run_playbook(gate=gate)
  │   └─ _execute_steps()
  │       └─ _execute_wave()
  │           └─ _execute_step()
  │               └─ mission_service.execute_mission(gate=gate)
  │                   └─ dispatch_adapter.execute(gate=gate)
  │                       └─ handle_mission(gate=gate)
  │                           └─ dispatch(plan, ..., gate=gate)
  │                               │
  │                               ├─ gate.review(pre_dispatch)     → User sees plan
  │                               │   └─ [c]ontinue
  │                               │
  │                               ├─ Layer 1:
  │                               │   ├─ gate.review(pre_layer)    → User sees tasks
  │                               │   │   └─ [c]ontinue
  │                               │   ├─ execute tasks (parallel)
  │                               │   ├─ gate.review(post_task)    → User sees results
  │                               │   │   └─ [o]utput → show full
  │                               │   │   └─ [c]ontinue
  │                               │   └─ gate.review(post_layer)   → User sees summary
  │                               │       └─ [c]ontinue
  │                               │
  │                               ├─ Layer 2:
  │                               │   ├─ gate.review(pre_layer)
  │                               │   │   └─ [a]bort               → STOP
  │                               │   └─ return _aborted_outcome()
  │                               │
  │                               └─ MissionOutcome (with gate_decisions)
  │
  └─ Render results
```

## Implementation Order

1. Step 1 (gate.py) — protocol and models
2. Step 2 (dispatch.py) — core gate integration
3. Step 8 (tests) — verify dispatch gates work
4. Step 3-4 (threading) — wire through playbook/mission/adapter
5. Step 5-6 (CLI) — interactive reviewer
6. Step 7 (logging) — audit trail
7. Step 9 (LLM stub) — future AI reviewer interface

## Non-Goals (This Plan)

- Full LLM reviewer implementation (future Plan 23)
- Web/API gate reviewer (future — WebSocket-based)
- Gate persistence across process restarts
- Modifying task plan structure at gate points (only inputs/instructions)
