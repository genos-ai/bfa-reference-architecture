# Plan 23 — TUI: Interactive Mission Control Dashboard

**Status:** Draft
**Created:** 2026-03-17
**Updated:** 2026-03-18
**Depends on:** Plans 13 (Dispatch), 17 (Playbooks/Missions), 22 (Step-Through Gate), 18 (Project Context), 24 (Client Module Restructure — completed), 25 (Dispatch Streaming Events — completed)

## Objective

Build a production-grade interactive TUI that puts the human at the center of the agentic loop — seeing what agents think, controlling what they do, and deciding when to intervene.

The platform has a sophisticated multi-agent orchestration system (Project → Playbook → Mission → Mission Control → Agents) with real-time event streaming (20+ SessionEvent types via Redis Pub/Sub), a fully-wired gate system for human-in-the-loop review (5 decision points in dispatch), and a rich service layer — but the only human interface is a CLI that runs fire-and-forget. The existing root `tui.py` (363 lines) is a basic Textual prototype that talks to the backend via HTTP, has no project awareness, no gate integration, no mission visualization, and no real-time streaming.

Plan 24 (Client Module Restructure) created the `modules/clients/` namespace with shared infrastructure that this plan builds on:
- `modules/clients/common/display.py` — shared Rich primitives (tables, panels, formatters) with keyword-only APIs
- `modules/clients/common/gate_helpers.py` — shared gate display helpers (`cost_color`, `status_icon`, `ACTION_COLORS`, `gate_header`)
- `modules/clients/tui/` — skeleton package structure (empty `__init__.py`, `screens/`, `widgets/`, `services/`, `styles/`)
- `modules/clients/cli/gate.py` — `CliGateReviewer` reference implementation for `TuiGateReviewer`
- Rule 006 (display centralization) governs all clients — TUI must use shared primitives, not raw Rich `Table()`, `Panel()`, `Console()`

---

## Architecture Decision: In-Process, Not HTTP

The TUI imports services directly via their `factory()` context managers rather than going through the REST API. This is required because:

1. **GateReviewer integration** — the gate protocol is an `await gate.review(context)` call inside the dispatch loop. The TUI must implement `GateReviewer` and resolve decisions synchronously within the same async event loop. HTTP would require polling or WebSockets with complex state synchronization.
2. **Service reuse** — all services (`ProjectService`, `MissionService`, `PlaybookRunService`, `SessionService`, `ContextAssembler`) already have `factory()` context managers designed for exactly this use case.
3. **Event streaming** — the TUI can use `InternalEventBus` (implements `EventBusProtocol`) for direct callback, or subscribe to `SessionEventBus` via Redis Pub/Sub when available.

### Event Gap: RESOLVED (Plan 25 — completed)

Plan 25 resolved the dispatch event gap. The dispatch path now has full event parity with `handle()`:

```
PlanStepStartedEvent          (dispatch.py — per task)
├─ AgentThinkingEvent         (helpers.py — before execution)
├─ AgentResponseChunkEvent*   (helpers.py — live text deltas via run_stream)
├─ AgentToolCallEvent*        (helpers.py — retrospective from stream.new_messages)
├─ AgentToolResultEvent*      (helpers.py — retrospective from stream.new_messages)
├─ AgentResponseCompleteEvent (helpers.py — after execution)
└─ CostUpdateEvent            (helpers.py — cumulative cost tracking)
PlanStepCompletedEvent        (dispatch.py — per task)
```

Key implementation details for TUI integration:
- `dispatch()` accepts `event_bus` and `session_id` keyword args
- `_emit()` helper handles event construction + publish errors (best-effort, never breaks execution)
- `_emit_tool_events()` shared helper extracts tool events from `stream.new_messages()`
- `NoOpEventBus` is the default — no impact on CLI or tests

---

## Screen Layout

```
+-----------------------------------------------------------------------+
| [Project: my-saas ▾]  [Mission | Playbook | History]     BFA Mission  |
+-----------------------------------------------------------------------+
| SIDEBAR-LEFT (22ch) |  CENTER (1fr)               | SIDEBAR-RIGHT(30)|
|                     |                              |                   |
| AGENTS              | +-- Mission / Agent View --+ | EVENT STREAM     |
| ● code.qa    [RUN]  | | TaskPlan DAG             | | 12:01 thinking   |
|   code.arch         | | L0: [plan]  ✓            | | 12:01 tool:scan  |
|   system.health     | | L1: [qa][arch]  ●  ○     | | 12:02 tool:ret   |
|   planning          | | L2: [health]  ○          | | 12:02 cost $0.04 |
|   verification      | | L3: [synth]  ○           | | 12:03 chunk...   |
|   synthesis         | +---------------------------+ | 12:03 gate!      |
|                     | +-- Agent Detail -----------+ |                  |
| ─────────────       | | code.qa  Running  $0.042  | | NOTIFICATIONS    |
| MISSION             | | Tk: 2.1k in / 800 out    | | ▲ Budget 75%     |
| Status: Running     | |                           | | ▲ Verif failed   |
| Budget: ████░ 62%   | | [Think][Out][Tool][Vfy][Rty]| | ● Gate pending   |
| Layer: 2/4          | | Analyzing compliance...   | |                  |
| Tasks: 1/4 done     | |                           | | CONTEXT          |
| Cost: $0.18         | +---------------------------+ | PCD v3 (12KB)    |
|                     | [> type message to agent... ] | Code Map: 42 mod |
+-----------------------------------------------------------------------+
| $0.18 | 4.2k in / 1.1k out | Layer 2/4 | ● 1 gate | connected       |
+-----------------------------------------------------------------------+
```

---

## File Structure

All files under `modules/clients/tui/`. Every file under 500 lines.

```
modules/clients/tui/
├── __init__.py                    # Re-exports BfaTuiApp
├── app.py                         # ~400 lines — App, bindings, lifecycle, event routing
├── messages.py                    # ~80 lines  — Custom Textual Message types
├── screens/
│   ├── __init__.py
│   ├── main.py                    # ~400 lines — MainScreen: 3-column layout
│   ├── project_picker.py          # ~200 lines — Create/select project modal
│   └── mission_history.py         # ~250 lines — Past missions browser
├── widgets/
│   ├── __init__.py
│   ├── agent_sidebar.py           # ~250 lines — Roster list, active highlights, click-to-select
│   ├── mission_panel.py           # ~350 lines — DAG viz, layer progress, task status
│   ├── agent_detail.py            # ~400 lines — Thinking/output/tools/verification/retries tabbed view
│   ├── event_stream.py            # ~250 lines — Real-time event log with type coloring
│   ├── cost_bar.py                # ~200 lines — Bottom bar: budget, tokens, cost
│   ├── gate_modal.py              # ~450 lines — Gate decision modal with per-type views
│   ├── notification.py            # ~150 lines — Alert badges + notification list
│   ├── chat_input.py              # ~150 lines — Message input with agent targeting
│   ├── context_viewer.py          # ~300 lines — PCD, code map, history inspection
│   └── playbook_progress.py       # ~250 lines — Wave/step progress tracker
├── services/
│   ├── __init__.py
│   ├── gate_reviewer.py           # ~200 lines — TuiGateReviewer: GateReviewer protocol impl
│   ├── event_listener.py          # ~150 lines — SessionEventBus subscriber + InternalEventBus
│   ├── state.py                   # ~300 lines — TuiState: centralized state store
│   └── service_bridge.py          # ~300 lines — Async service factory wrappers
└── styles/
    └── tui.tcss                   # ~200 lines — Textual CSS
```

**~20 files, ~4,500 lines estimated. All under 500 lines.**

---

## Core Data Flow

### Mission Execution

```
User clicks "New Mission" (Ctrl+M)
  → App shows input dialog for mission brief
  → App calls ServiceBridge.run_mission() in @work(thread=False)
    → ServiceBridge creates MissionService via factory()
    → Calls handle_mission() directly (in-process)
      → handle_mission calls dispatch() with gate=TuiGateReviewer
        → dispatch awaits gate.review() at 5 decision points
          → TuiGateReviewer posts GateReviewRequested message to App
          → TuiGateReviewer awaits asyncio.Future
          → App opens GateReviewModal
          → User presses decision key (c/s/r/a)
          → Modal resolves the Future with GateDecision
          → dispatch continues with the decision
        → Agent executes, events flow via InternalEventBus
          → InternalEventBus.publish() calls App.post_message()
          → App routes event to widgets (sidebar, detail, stream, cost)
    → MissionOutcome returned
  → App updates state, refreshes widgets
```

### Event Routing

```
SessionEvent arrives (via TuiEventBus or SessionEventBus)
  → App.handle_session_event() routes by event type:

    Agent events:
    AgentThinkingEvent        → mark agent active in sidebar, update thinking tab
    AgentToolCallEvent        → add to agent's tool call table
    AgentToolResultEvent      → update tool call result
    AgentResponseChunkEvent   → append to agent's output stream
    AgentResponseCompleteEvent→ mark agent done, update tokens/cost

    Plan events:
    PlanCreatedEvent          → populate DAG in mission panel
    PlanStepStartedEvent      → highlight task node as running
    PlanStepCompletedEvent    → mark task node as done/failed
    PlanRevisedEvent          → re-render DAG with revised plan

    Playbook events:
    PlaybookRunStartedEvent       → init playbook progress widget
    PlaybookMissionStartedEvent   → highlight active step in wave
    PlaybookMissionCompletedEvent → mark step done, update cost
    PlaybookRunCompletedEvent     → mark playbook complete
    PlaybookRunFailedEvent        → mark playbook failed, show error

    Cost & approval events:
    CostUpdateEvent           → update cost bar, check budget threshold
    ApprovalRequestedEvent    → add notification badge
    ApprovalResponseEvent     → clear notification badge

    User events (outbound, for event log only):
    UserMessageEvent          → append to event stream
    UserApprovalEvent         → append to event stream

  → ALL events append to EventStreamWidget (right sidebar)
```

---

## GateReviewer Implementation (Killer Feature)

### The Bridge Pattern

```python
# modules/clients/tui/services/gate_reviewer.py

class TuiGateReviewer:
    """Implements GateReviewer protocol for the Textual TUI.

    When dispatch() calls `await gate.review(context)`:
    1. Creates an asyncio.Future
    2. Posts GateReviewRequested message to the Textual App
    3. Awaits the Future (does NOT block UI — dispatch runs in @work coroutine)
    4. GateReviewModal resolves the Future when user decides
    5. Returns GateDecision to dispatch
    """

    def __init__(self, app: App):
        self._app = app
        self._pending: asyncio.Future[GateDecision] | None = None

    async def review(self, context: GateContext) -> GateDecision:
        loop = asyncio.get_running_loop()
        self._pending = loop.create_future()
        self._app.post_message(GateReviewRequested(context=context))
        try:
            return await self._pending
        finally:
            self._pending = None  # Clean up even on CancelledError

    def resolve(self, decision: GateDecision) -> None:
        if self._pending and not self._pending.done():
            self._pending.set_result(decision)
```

**Why this works**: Textual's `@work(thread=False)` schedules the mission coroutine on the same asyncio event loop as the UI. When `TuiGateReviewer.review()` awaits the Future, it yields control back to the event loop, allowing the UI to remain responsive and process the user's gate decision.

### Gate Modal (per gate type)

| Gate Type | What the user sees | Available actions |
|---|---|---|
| `pre_dispatch` | Full TaskPlan table (task_id, agent, description, deps). Budget summary. | Continue, Abort |
| `pre_layer` | Tasks about to execute. Resolved input keys. Cost so far vs budget bar. | Continue, Skip layer, Abort |
| `post_task` | Task output summary. Verification badge (T1/T2/T3). Duration, cost, tokens. | Continue, Retry (with editable instructions), Skip, Abort |
| `verification_failed` | Which tier failed. Failure details. Retry feedback preview. Attempt N of M. | Retry (with editable feedback), Modify (accept with edits), Skip, Abort |
| `post_layer` | Layer summary. Cumulative cost. Next layer preview. | Continue, Abort |

### Gate Modal Keyboard Shortcuts

```
c — Continue (proceed)
s — Skip (skip this task/layer)
r — Retry (re-run, optionally edit instructions via TextArea)
m — Modify (accept despite failure, verification_failed only)
a — Abort (halt entire mission)
o — Inspect full output (scrollable view)
v — Inspect verification details
i — Inspect resolved inputs
Esc — Same as Continue (safe default)
```

---

## State Management

```python
# modules/clients/tui/services/state.py

@dataclass
class TuiState:
    """Plain dataclass held by the App. Widgets read from it.
    App updates it on events and triggers widget refreshes."""

    # Project
    current_project_id: str | None = None
    current_project_name: str | None = None

    # Session
    current_session_id: str | None = None

    # Roster
    roster_agents: list[RosterAgentEntry] = field(default_factory=list)

    # Active mission
    mission_id: str | None = None
    mission_status: str = "idle"       # idle|planning|running|completed|failed
    task_plan: TaskPlan | None = None
    task_layers: list[list[str]] = field(default_factory=list)  # from topological_sort
    task_results: dict[str, TaskResult] = field(default_factory=dict)
    current_layer: int = 0

    # Agent tracking (keyed by task_id or agent_name)
    active_agents: set[str] = field(default_factory=set)
    selected_agent: str | None = None
    agent_thinking: dict[str, str] = field(default_factory=dict)
    agent_output: dict[str, str] = field(default_factory=dict)
    agent_tool_calls: dict[str, list[dict]] = field(default_factory=dict)
    agent_context: dict[str, dict] = field(default_factory=dict)        # assembled context per task
    agent_verification: dict[str, dict] = field(default_factory=dict)   # VerificationOutcome per task

    # Cost
    total_cost_usd: float = 0.0
    budget_usd: float = 0.0
    per_task_costs: dict[str, float] = field(default_factory=dict)

    # Events (ring buffer)
    events: deque = field(default_factory=lambda: deque(maxlen=500))

    # Gate
    pending_gate: GateContext | None = None
    gate_history: list[dict] = field(default_factory=list)

    # Notifications
    notifications: deque = field(default_factory=lambda: deque(maxlen=50))

    # Playbook
    playbook_name: str | None = None
    playbook_progress: dict[str, dict] = field(default_factory=dict)
    playbook_waves: list[list[str]] = field(default_factory=list)

    # Planning trace
    planning_trace: str | None = None
```

---

## Widget Details

### AgentSidebar (`widgets/agent_sidebar.py`)

- Lists all agents from `Roster.agents` (uses `RosterAgentEntry` fields: `agent_name`, `description`, `model.name`, `constraints`)
- Each agent is a clickable `AgentCard(Static)` with CSS class `.active` when executing, `.selected` when user-focused
- Clicking an agent posts `AgentSelected(agent_name)` → App switches center panel to `AgentDetailWidget`
- Active agents have a pulsing `●` indicator and `[RUN]` badge
- Completed agents show `status_icon()` from `common/gate_helpers` with per-task cost
- Below agent list: mission summary panel (status, budget bar using `cost_color()`, layer progress, task count)

### MissionPanel (`widgets/mission_panel.py`)

- Text-based DAG rendering using the output of `topological_sort(plan)`
- Each task renders from `TaskDefinition` fields: `task_id`, `agent`, `description`, `dependencies`
- Status icon per task: `○` pending, `●` running, `✓` success, `✗` failed, `⊘` skipped (from `TaskResult.status`)
- Layers displayed as rows with `→` showing dependency flow
- Below the DAG: layer progress bar and cumulative cost
- Uses `TuiState.task_plan` + `TuiState.task_results` to render
- Shows `execution_hints.critical_path` tasks highlighted

### AgentDetailWidget (`widgets/agent_detail.py`)

- Header: agent name, status, model (from `RosterAgentEntry.model.name`), tokens (in/out), cost, duration
- TabbedContent with 6 tabs:
  - **Thinking**: RichLog streaming `AgentThinkingEvent` content as it arrives
  - **Output**: RichLog streaming `AgentResponseChunkEvent` chunks, then final `TaskResult.output_reference`
  - **Tools**: DataTable showing `AgentToolCallEvent` / `AgentToolResultEvent` pairs (name, args summary, result summary, duration)
  - **Context**: ContextViewerWidget showing what `ContextAssembler.build()` produced for this task (PCD layer, code map, history)
  - **Retries**: RichLog showing `RetryHistoryEntry` list (attempt, failure_tier, failure_reason, feedback_provided)
  - **Verification**: Shows `VerificationOutcome` — Tier 1 (schema), Tier 2 (deterministic checks with pass/fail per check), Tier 3 (AI evaluation score)

### EventStreamWidget (`widgets/event_stream.py`)

- Scrolling log of all SessionEvents with timestamp, type icon, and one-line summary
- Color-coded by type: thinking=dim, tool=yellow, cost=green, error=red, gate=cyan
- Click on event to expand details (JSON view)
- Filter toggle: All / Agent / Cost / Gate

### GateReviewModal (`widgets/gate_modal.py`)

- Textual `ModalScreen[GateDecision]`
- Renders context-appropriate view based on `gate_type` (see table above)
- Uses `gate_header()` from `common/gate_helpers` for header formatting
- Uses `cost_color()` for budget bar coloring, `status_icon()` for verification badges
- Uses `ACTION_COLORS` from `common/gate_helpers` for action button styling
- Budget progress bar always visible in header
- Action bar at bottom with available actions for this gate type
- `TextArea` appears when user selects Retry (to edit instructions/feedback)
- Dismisses with `GateDecision` result
- If `ctx.ai_recommendation` is present (ai_assisted mode), renders AI suggestion panel

### CostStatusBar (`widgets/cost_bar.py`)

- Docked to bottom, single line
- Shows: `$cost | Tokens in/out | Layer N/M | gate badge | connection status`
- Budget bar uses `cost_color()` from `common/gate_helpers` for threshold coloring

### PlaybookProgressWidget (`widgets/playbook_progress.py`)

- Shows playbook name, version, wave structure
- Each wave as a row with parallel steps shown side-by-side
- Step status with cost and duration
- Output mapping arrows between steps

---

## Keyboard Shortcuts

| Key | Action | Context |
|-----|--------|---------|
| `Ctrl+P` | Switch project | Global |
| `Ctrl+N` | New project | Global |
| `Ctrl+M` | New mission (prompt for brief) | Global |
| `Ctrl+B` | Run playbook (picker) | Global |
| `Ctrl+K` | Kill/cancel active mission (cancels asyncio Task) | Global |
| `Ctrl+H` | Mission history | Global |
| `Ctrl+E` | Toggle event stream sidebar | Global |
| `Ctrl+/` | Focus chat input | Global |
| `F1` | Show mission DAG view | Center panel |
| `F2` | Show selected agent detail | Center panel |
| `F3` | Show playbook progress | Center panel |
| `Tab` | Next agent in sidebar | Agent nav |
| `Shift+Tab` | Previous agent in sidebar | Agent nav |
| `c` | Continue (approve gate) | Gate modal |
| `s` | Skip | Gate modal |
| `r` | Retry (opens instruction editor) | Gate modal |
| `m` | Modify (accept despite failure) | Gate modal (verification_failed only) |
| `a` | Abort mission | Gate modal |
| `o` | Inspect output | Gate modal |
| `v` | Inspect verification | Gate modal |
| `Ctrl+Q` | Quit | Global |

---

## Key Services to Reuse

### Shared Client Infrastructure (from Plan 24)

| Module | File | Usage in TUI |
|--------|------|-------------|
| `build_table()`, panels, `styled_status()` | `modules/clients/common/display.py` | All table/panel rendering in widgets — **must use instead of raw Rich** (Rule 006) |
| `cost_color()`, `status_icon()`, `ACTION_COLORS` | `modules/clients/common/gate_helpers.py` | Gate modal, cost bar, agent sidebar status icons |
| `gate_header()` | `modules/clients/common/gate_helpers.py` | Gate modal header formatting |
| `get_console()` | `modules/clients/common/display.py` | Console factory (if needed for non-Textual Rich rendering) |
| `CliGateReviewer` | `modules/clients/cli/gate.py` | Reference implementation for TuiGateReviewer pattern |

### Backend Services

| Service | File | Usage in TUI |
|---------|------|-------------|
| `ProjectService.factory()` | `modules/backend/services/project.py` | Project CRUD in ProjectPickerScreen |
| `MissionService.factory()` | `modules/backend/services/mission.py` | Mission creation and execution |
| `handle_mission()` | `modules/backend/agents/mission_control/mission_control.py` | In-process mission dispatch with gate |
| `load_roster()` | `modules/backend/agents/mission_control/roster.py` | Load agent roster for sidebar |
| `topological_sort()` | `modules/backend/agents/mission_control/dispatch.py` | Compute DAG layers for visualization |
| `PlaybookRunService` | `modules/backend/services/playbook_run.py` | Playbook execution with gate |
| `PlaybookService` | `modules/backend/services/playbook.py` | List/load playbooks |
| `SessionEventBus` | `modules/backend/events/bus.py` | Redis Pub/Sub event subscription |
| `EventBusProtocol`, `NoOpEventBus` | `modules/backend/agents/mission_control/models.py` | TuiEventBus implementation |
| `GateReviewer` protocol | `modules/backend/agents/mission_control/gate.py` | TuiGateReviewer must implement `async review(context) -> GateDecision` |
| `GateContext`, `GateDecision`, `GateAction` | `modules/backend/agents/mission_control/gate.py` | Data rendered in gate modal; `GateAction` enum: CONTINUE, SKIP, RETRY, ABORT, MODIFY |
| `ConfigurableGate` | `modules/backend/agents/mission_control/gate.py` | Routes to TuiGateReviewer for interactive gates, LlmGateReviewer for AI-assisted |
| `SessionEvent` hierarchy | `modules/backend/events/types.py` | 20+ event types for routing (see Event Routing section) |
| `MissionOutcome`, `TaskResult`, `TaskStatus` | `modules/backend/agents/mission_control/outcome.py` | Mission results rendering |
| `TaskPlan`, `TaskDefinition` | `modules/backend/schemas/task_plan.py` | DAG visualization, task details |
| `VerificationOutcome` (Tier 1/2/3) | `modules/backend/agents/mission_control/outcome.py` | Verification badge in gate modal and agent detail |
| `RetryHistoryEntry` | `modules/backend/agents/mission_control/outcome.py` | Retry tab in agent detail widget |
| `RosterAgentEntry`, `Roster` | `modules/backend/agents/mission_control/roster.py` | Agent sidebar (name, model, constraints, tools) |
| `ProjectContextManager.factory()` | `modules/backend/services/project_context.py` | PCD inspection in ContextViewer |
| `ContextAssembler` | `modules/backend/services/context_assembler.py` | Show assembled context for tasks |
| `get_async_session()` | `modules/backend/core/database.py` | DB session for service factories |

---

## Design Constraints

1. **Rule 006 compliance**: All TUI widgets must use shared primitives from `modules/clients/common/display.py` and `gate_helpers.py` — no raw `Table()`, `Panel()`, or `Console()` instantiation. This ensures visual consistency across CLI and TUI.
2. **Keyword-only APIs (Rule 006.6)**: Any new display primitives added to `common/` must use keyword-only arguments (after `*`).
3. **500-line rule**: Every file under 500 lines. Split early.
4. **Feature parity with CLI**: Every operation available via CLI (`python cli.py mission run`, `playbook run`, gate review, context inspection) must be available in the TUI. The TUI is not a subset — it is the primary human interface. Conversely, anything an AI agent can do via `handle_mission()` (autonomous dispatch, gate decisions, verification review) must be visible and controllable in the TUI. The human sees everything the AI sees.
5. **In-process, not HTTP**: The TUI calls service factories directly. The root `tui.py` (363-line HTTP prototype) is replaced, not extended.
6. **Mission cancellation**: `Ctrl+K` cancels the mission by cancelling the asyncio Task running `ServiceBridge.run_mission()`. Dispatch has no built-in cancellation token — the `asyncio.CancelledError` propagates up from whichever `await` is active (gate review, agent.run, or asyncio.gather). The service bridge must catch this and mark the mission as failed with `abort_reason="user_cancelled"`.

---

## Implementation Phases

### Phase 1: Foundation — Bootable app with project + roster (~10 files)

Create: `app.py`, `messages.py`, `screens/main.py`, `screens/project_picker.py`, `widgets/agent_sidebar.py`, `widgets/cost_bar.py`, `widgets/chat_input.py`, `services/state.py`, `services/service_bridge.py`, `styles/tui.tcss`

`service_bridge.py` was deferred from Plan 24 to this phase — it wraps `ProjectService.factory()`, `MissionService.factory()`, `PlaybookRunService`, `load_roster()`, etc. as async context managers for the TUI's `@work(thread=False)` coroutines. Critically, `run_mission()` must wire: `session_service` (from factory), `event_bus` (TuiEventBus), `db_session` (from `get_async_session()`), `gate` (TuiGateReviewer), and `project_id` (from TuiState) into `handle_mission()`.

Delivers: Launch TUI → pick/create project → see roster agents in sidebar → bottom status bar. Replace root `tui.py` entry point.

### Phase 2: Event streaming + agent detail (~3 files)

Create: `widgets/event_stream.py`, `widgets/agent_detail.py`, `services/event_listener.py`

`event_listener.py` implements `EventBusProtocol` (from `models.py`) — a `TuiEventBus` that calls `App.post_message()` on publish, bridging backend events to Textual's message loop.

Delivers: Real-time event log in right sidebar. Click agent → see thinking/output/tools tabs streaming live.

### Phase 3: Mission execution + DAG visualization (~2 files)

Create: `widgets/mission_panel.py`. Extend `service_bridge.py` with `run_mission()`.

Delivers: Ctrl+M → enter brief → see TaskPlan DAG → watch tasks execute layer by layer with status updates. Uses `topological_sort()` for layer computation.

### Phase 4: Gate reviewer integration (~2 files)

Create: `services/gate_reviewer.py`, `widgets/gate_modal.py`

`TuiGateReviewer` follows the same `GateReviewer` protocol as `CliGateReviewer` but uses asyncio.Future + Textual messages instead of terminal prompts. Gate modal uses shared `gate_header()`, `cost_color()`, `status_icon()`, `ACTION_COLORS` from `common/gate_helpers.py`.

Delivers: Gates pause execution and show modal. Human approves/rejects/retries with full context visibility. Supports all 5 gate types with per-type views. Shows AI recommendation when in `ai_assisted` mode.

### Phase 5: Playbook + cost + notifications (~3 files)

Create: `widgets/playbook_progress.py`, `widgets/notification.py`. Extend `widgets/cost_bar.py`.

Delivers: Run playbooks with wave visualization. Budget warnings as notifications. Verification failure alerts.

### Phase 6: Context inspection + history (~2 files)

Create: `widgets/context_viewer.py`, `screens/mission_history.py`

Delivers: Inspect PCD, code map, assembled context per task. Browse past missions with cost breakdown.

### Phase 7: Polish

Keyboard UX, focus management, error boundaries, loading states, responsive layout.

---

## Verification Plan

1. **Unit**: Test `TuiGateReviewer` with mock App — verify Future creation, resolution, and message posting
2. **Unit**: Test `TuiState` updates — verify event routing populates correct fields for all 19 event types
3. **Unit**: Test `ServiceBridge` factory wrappers — verify async context manager lifecycle
4. **Integration**: Launch TUI with `--debug`, create project, run a mission with `gate=TuiGateReviewer`, verify gate modal appears and dispatch resumes after decision
5. **Manual**: Run `python tui.py`, select project, Ctrl+M to launch mission, observe DAG, click agents, approve gates, verify cost tracking
6. **Playbook**: Run a multi-step playbook, verify wave visualization and inter-step output mapping display
7. **Rule 006**: `rg "Table\(" modules/clients/tui/ --glob "*.py"` returns zero results (all tables via `build_table()`)
8. **Feature parity**: Every CLI command has a TUI equivalent:
   - `cli.py mission run` → Ctrl+M new mission
   - `cli.py mission list/detail` → mission history screen
   - `cli.py mission plan` → mission panel DAG view
   - `cli.py mission cost` → cost bar + agent detail cost breakdown
   - `cli.py playbook run` → Ctrl+B playbook picker
   - `cli.py playbook list/detail` → playbook picker with detail view
   - `cli.py playbook runs/run-detail/report` → playbook progress widget + mission history
   - `cli.py gate` (interactive review) → gate modal with all 5 gate types + all 5 actions (c/s/r/m/a)
   - `cli.py context show/assembled/codemap` → context viewer widget
   - `cli.py project` CRUD → project picker screen
9. **AI visibility**: Everything `handle_mission()` does internally is visible in the TUI — planning trace, task DAG, per-task thinking/output/tools, verification tiers (T1/T2/T3), retry feedback, cost accumulation, gate decisions (including AI recommendations in `ai_assisted` mode)
10. **Event completeness**: All 19 SessionEvent types are routed and rendered (see Event Routing section)
