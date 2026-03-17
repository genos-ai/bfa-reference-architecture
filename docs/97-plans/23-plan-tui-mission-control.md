# Plan 23 — TUI: Interactive Mission Control Dashboard

**Status:** Draft
**Created:** 2026-03-17
**Depends on:** Plans 13 (Dispatch), 17 (Playbooks/Missions), 22 (Step-Through Gate), 18 (Project Context)

## Objective

Build a production-grade interactive TUI that puts the human at the center of the agentic loop — seeing what agents think, controlling what they do, and deciding when to intervene.

The platform has a sophisticated multi-agent orchestration system (Project → Playbook → Mission → Mission Control → Agents) with real-time event streaming (20+ SessionEvent types via Redis Pub/Sub), a fully-wired gate system for human-in-the-loop review (5 decision points in dispatch), and a rich service layer — but the only human interface is a CLI that runs fire-and-forget. The existing `tui.py` (362 lines) is a basic Textual prototype that talks to the backend via HTTP, has no project awareness, no gate integration, no mission visualization, and no real-time streaming.

---

## Architecture Decision: In-Process, Not HTTP

The TUI imports services directly via their `factory()` context managers rather than going through the REST API. This is required because:

1. **GateReviewer integration** — the gate protocol is an `await gate.review(context)` call inside the dispatch loop. The TUI must implement `GateReviewer` and resolve decisions synchronously within the same async event loop. HTTP would require polling or WebSockets with complex state synchronization.
2. **Service reuse** — all services (`ProjectService`, `MissionService`, `PlaybookRunService`, `SessionService`, `ContextAssembler`) already have `factory()` context managers designed for exactly this use case.
3. **Event streaming** — the TUI can use `InternalEventBus` (implements `EventBusProtocol`) for direct callback, or subscribe to `SessionEventBus` via Redis Pub/Sub when available.

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
| Budget: ████░ 62%   | | [Think] [Output] [Tools]  | | ● Gate pending   |
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

All files under `modules/tui/`. Every file under 500 lines.

```
modules/tui/
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
│   ├── agent_detail.py            # ~350 lines — Thinking/output/tools/retries tabbed view
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
SessionEvent arrives (via InternalEventBus or SessionEventBus)
  → App.handle_session_event() routes by event type:
    AgentThinkingEvent   → mark agent active in sidebar, clear thinking log
    AgentToolCallEvent   → add to agent's tool call table
    AgentToolResultEvent → update tool call result
    AgentResponseChunk   → append to agent's output stream
    AgentResponseComplete→ mark agent done, update tokens/cost
    CostUpdateEvent      → update cost bar, check budget threshold
    PlanCreatedEvent     → populate DAG in mission panel
    PlanStepStarted      → highlight task node as running
    PlanStepCompleted    → mark task node as done/failed
    ApprovalRequested    → add notification badge
  → ALL events append to EventStreamWidget (right sidebar)
```

---

## GateReviewer Implementation (Killer Feature)

### The Bridge Pattern

```python
# modules/tui/services/gate_reviewer.py

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
        decision = await self._pending
        self._pending = None
        return decision

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
| `verification_failed` | Which tier failed. Failure details. Retry feedback preview. Attempt N of M. | Retry (with editable feedback), Continue (accept anyway), Abort |
| `post_layer` | Layer summary. Cumulative cost. Next layer preview. | Continue, Abort |

### Gate Modal Keyboard Shortcuts

```
c — Continue (proceed)
s — Skip (skip this task/layer)
r — Retry (re-run, optionally edit instructions via TextArea)
a — Abort (halt entire mission)
o — Inspect full output (scrollable view)
v — Inspect verification details
i — Inspect resolved inputs
Esc — Same as Continue (safe default)
```

---

## State Management

```python
# modules/tui/services/state.py

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

    # Agent tracking
    active_agents: set[str] = field(default_factory=set)
    selected_agent: str | None = None
    agent_thinking: dict[str, str] = field(default_factory=dict)
    agent_output: dict[str, str] = field(default_factory=dict)
    agent_tool_calls: dict[str, list[dict]] = field(default_factory=dict)

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

- Lists all agents from `Roster.agents`
- Each agent is a clickable `AgentCard(Static)` with CSS class `.active` when executing, `.selected` when user-focused
- Clicking an agent posts `AgentSelected(agent_name)` → App switches center panel to `AgentDetailWidget`
- Active agents have a pulsing `●` indicator and `[RUN]` badge
- Completed agents show `✓` or `✗` with cost

### MissionPanel (`widgets/mission_panel.py`)

- Text-based DAG rendering using the output of `topological_sort(plan)`
- Each task is a box with status icon: `○` pending, `●` running, `✓` success, `✗` failed, `⊘` skipped
- Layers displayed as rows with `→` showing dependency flow
- Below the DAG: layer progress bar and cumulative cost
- Uses `TuiState.task_plan` + `TuiState.task_results` to render

### AgentDetailWidget (`widgets/agent_detail.py`)

- Header: agent name, status, model, tokens (in/out), cost, duration
- TabbedContent with 5 tabs:
  - **Thinking**: RichLog streaming thinking content as it arrives
  - **Output**: RichLog streaming response chunks, then final formatted output
  - **Tools**: DataTable showing tool calls (name, args summary, result summary, duration)
  - **Context**: ContextViewerWidget showing what context was assembled for this task
  - **Retries**: RichLog showing RetryHistoryEntry list if task was retried

### EventStreamWidget (`widgets/event_stream.py`)

- Scrolling log of all SessionEvents with timestamp, type icon, and one-line summary
- Color-coded by type: thinking=dim, tool=yellow, cost=green, error=red, gate=cyan
- Click on event to expand details (JSON view)
- Filter toggle: All / Agent / Cost / Gate

### GateReviewModal (`widgets/gate_modal.py`)

- Textual `ModalScreen[GateDecision]`
- Renders context-appropriate view based on `gate_type` (see table above)
- Budget progress bar always visible in header
- Action bar at bottom with available actions for this gate type
- `TextArea` appears when user selects Retry (to edit instructions/feedback)
- Dismisses with `GateDecision` result

### CostStatusBar (`widgets/cost_bar.py`)

- Docked to bottom, single line
- Shows: `$cost | Tokens in/out | Layer N/M | gate badge | connection status`
- Budget bar changes color: green (<50%), yellow (50-75%), red (>75%)

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
| `Ctrl+K` | Kill/cancel active mission | Global |
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
| `a` | Abort mission | Gate modal |
| `o` | Inspect output | Gate modal |
| `v` | Inspect verification | Gate modal |
| `Ctrl+Q` | Quit | Global |

---

## Key Services to Reuse

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
| `EventBusProtocol` | `modules/backend/agents/mission_control/models.py` | InternalEventBus implementation |
| `GateReviewer` protocol | `modules/backend/agents/mission_control/gate.py` | TuiGateReviewer must implement this |
| `GateContext`, `GateDecision` | `modules/backend/agents/mission_control/gate.py` | Data rendered in gate modal |
| `SessionEvent` hierarchy | `modules/backend/events/types.py` | All 20+ event types for routing |
| `ProjectContextManager.factory()` | `modules/backend/services/project_context.py` | PCD inspection in ContextViewer |
| `ContextAssembler` | `modules/backend/services/context_assembler.py` | Show assembled context for tasks |
| `get_async_session()` | `modules/backend/core/database.py` | DB session for service factories |

---

## Implementation Phases

### Phase 1: Foundation — Bootable app with project + roster (~8 files)

Create: `app.py`, `messages.py`, `screens/main.py`, `screens/project_picker.py`, `widgets/agent_sidebar.py`, `widgets/cost_bar.py`, `widgets/chat_input.py`, `services/state.py`, `services/service_bridge.py`, `styles/tui.tcss`

Delivers: Launch TUI → pick/create project → see roster agents in sidebar → bottom status bar. Replace root `tui.py` entry point.

### Phase 2: Event streaming + agent detail (~3 files)

Create: `widgets/event_stream.py`, `widgets/agent_detail.py`, `services/event_listener.py`

Delivers: Real-time event log in right sidebar. Click agent → see thinking/output/tools tabs streaming live.

### Phase 3: Mission execution + DAG visualization (~2 files)

Create: `widgets/mission_panel.py`. Extend `service_bridge.py`.

Delivers: Ctrl+M → enter brief → see TaskPlan DAG → watch tasks execute layer by layer with status updates.

### Phase 4: Gate reviewer integration (~2 files)

Create: `services/gate_reviewer.py`, `widgets/gate_modal.py`

Delivers: When `--step` equivalent is active, gates pause execution and show modal. Human approves/rejects/retries. This is the differentiating feature.

### Phase 5: Playbook + cost + notifications (~3 files)

Create: `widgets/playbook_progress.py`, `widgets/notification.py`. Extend `widgets/cost_bar.py`.

Delivers: Run playbooks with wave visualization. Budget warnings as notifications. Verification failure alerts.

### Phase 6: Context inspection + history (~2 files)

Create: `widgets/context_viewer.py`, `screens/mission_history.py`

Delivers: Inspect PCD, code map, assembled context per task. Browse past missions.

### Phase 7: Polish

Keyboard UX, focus management, error boundaries, loading states, responsive layout.

---

## Verification Plan

1. **Unit**: Test `TuiGateReviewer` with mock App — verify Future creation, resolution, and message posting
2. **Unit**: Test `TuiState` updates — verify event routing populates correct fields
3. **Integration**: Launch TUI with `--debug`, create project, run a mission with `gate=TuiGateReviewer`, verify gate modal appears and dispatch resumes after decision
4. **Manual**: Run `python tui.py`, select project, Ctrl+M to launch mission, observe DAG, click agents, approve gates, verify cost tracking
5. **Playbook**: Run a multi-step playbook, verify wave visualization and inter-step output mapping display
