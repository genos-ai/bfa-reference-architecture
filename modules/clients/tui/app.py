"""BFA Mission Control TUI — main Textual application.

Lifecycle:
    1. on_mount: load projects → show picker if no project selected
    2. User picks project → load roster → populate sidebar
    3. User enters mission brief (Ctrl+M or chat input) → run_mission worker
    4. Events stream in via TuiEventBus → routed to widgets

All heavy work runs via @work(thread=False) so it shares the Textual
event loop and can interact with gate Futures.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Input, Label, Static
from textual.worker import Worker

from modules.backend.core.logging import get_logger
from modules.clients.tui.messages import (
    AgentSelected,
    GateReviewCompleted,
    GateReviewRequested,
    MissionStartRequested,
    ProjectCreated,
    ProjectSelected,
    SessionEventReceived,
)
from modules.clients.tui.screens.main import MainScreen
from modules.clients.tui.screens.project_picker import ProjectPickerScreen
from modules.clients.tui.services.event_listener import TuiEventBus
from modules.clients.tui.services.service_bridge import ServiceBridge
from modules.clients.tui.services.state import TuiState
from modules.backend.agents.mission_control.dispatch import topological_sort
from modules.backend.agents.mission_control.outcome import TaskResult, TaskStatus
from modules.backend.schemas.task_plan import TaskPlan
from modules.clients.tui.widgets.agent_detail import AgentDetailWidget
from modules.clients.tui.widgets.agent_sidebar import AgentSidebar, MissionSummary
from modules.clients.tui.widgets.cost_bar import CostBar
from modules.clients.tui.widgets.event_stream import EventStreamWidget
from modules.clients.tui.services.gate_reviewer import TuiGateReviewer
from modules.clients.tui.widgets.gate_modal import GateReviewModal
from modules.clients.tui.widgets.mission_panel import MissionPanel
from modules.clients.tui.widgets.notification import NotificationStack
from modules.clients.tui.widgets.playbook_progress import PlaybookProgressWidget
from modules.clients.tui.screens.mission_history import MissionHistoryScreen

logger = get_logger(__name__)

CSS_PATH = Path(__file__).parent / "styles" / "tui.tcss"


class BfaTuiApp(App):
    """BFA Mission Control — interactive agent dashboard."""

    TITLE = "BFA Mission Control"
    CSS_PATH = str(CSS_PATH)

    BINDINGS = [
        Binding("ctrl+p", "switch_project", "Switch Project"),
        Binding("ctrl+m", "new_mission", "New Mission"),
        Binding("ctrl+k", "cancel_mission", "Cancel Mission"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+slash", "focus_input", "Focus Input"),
        Binding("f1", "show_overview", "Overview"),
        Binding("f2", "show_history", "History"),
        Binding("tab", "focus_next", "Next", show=False),
        Binding("shift+tab", "focus_previous", "Prev", show=False),
    ]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.state = TuiState()
        self._event_bus = TuiEventBus(self)
        self.bridge = ServiceBridge(event_bus=self._event_bus)
        self._gate_reviewer = TuiGateReviewer(self)
        self._mission_worker: Worker | None = None
        self._agent_detail: AgentDetailWidget | None = None
        self._mission_panel: MissionPanel | None = None
        self._playbook_panel: PlaybookProgressWidget | None = None
        self._budget_warned_75 = False
        self._budget_warned_90 = False

    async def on_mount(self) -> None:
        """Install the main screen and show project picker on startup."""
        self.push_screen(MainScreen())
        self.run_worker(self._startup(), thread=False)

    async def _startup(self) -> None:
        """Load projects and prompt for selection."""
        try:
            projects = await self.bridge.list_projects()
        except Exception:
            logger.warning("Could not load projects (DB may be unavailable)", exc_info=True)
            projects = []

        if projects:
            self.push_screen(ProjectPickerScreen(projects))
        else:
            # No projects yet — show picker with empty list for creation
            self.push_screen(ProjectPickerScreen([]))

    # ── Project handling ─────────────────────────────────────────────

    async def on_project_selected(self, event: ProjectSelected) -> None:
        """User selected an existing project."""
        self.state.current_project_id = event.project_id
        self.state.current_project_name = event.project_name
        self._update_project_header()
        self._load_roster()

    async def on_project_created(self, event: ProjectCreated) -> None:
        """User created a new project — create via bridge then select."""
        try:
            result = await self.bridge.create_project(
                name=event.project_name,
                description=event.description or "Created from TUI",
            )
            self.state.current_project_id = result["id"]
            self.state.current_project_name = result["name"]
            self._update_project_header()
            self._load_roster()
        except Exception as exc:
            logger.error("Failed to create project", exc_info=True)
            self.notify(f"Failed to create project: {exc}", severity="error")

    def _update_project_header(self) -> None:
        """Update the project name in the header bar."""
        try:
            label = self.screen.query_one("#project-name", Label)
            name = self.state.current_project_name or "No Project"
            label.update(f"[bold]{name}[/bold]")
        except NoMatches:
            pass

    def _load_roster(self) -> None:
        """Load the agent roster and populate the sidebar."""
        try:
            roster = self.bridge.load_roster()
            self.state.roster_agents = roster.agents
            sidebar = self.screen.query_one("#agent-sidebar", AgentSidebar)
            sidebar.load_roster(roster.agents)
        except Exception as exc:
            logger.error("Failed to load roster", exc_info=True)
            self.notify(f"Roster error: {exc}", severity="error")

    # ── Mission execution ────────────────────────────────────────────

    def action_new_mission(self) -> None:
        """Focus the mission input (Ctrl+M)."""
        try:
            self.screen.query_one("#mission-input", Input).focus()
        except NoMatches:
            pass

    async def on_mission_start_requested(
        self, event: MissionStartRequested
    ) -> None:
        """Start a mission from the chat input."""
        if not self.state.current_project_id:
            self.notify("Select a project first (Ctrl+P)", severity="warning")
            return

        if self.state.mission_status == "running":
            self.notify("A mission is already running", severity="warning")
            return

        self.state.reset_mission()
        self.state.mission_status = "planning"
        self.state.current_session_id = str(uuid.uuid4())
        self._mission_panel = None
        self._playbook_panel = None
        self._budget_warned_75 = False
        self._budget_warned_90 = False
        self._update_mission_summary()

        self._mission_worker = self.run_worker(
            self._execute_mission(event.brief),
            thread=False,
        )

    async def _execute_mission(self, brief: str) -> None:
        """Run handle_mission() in the Textual event loop."""
        try:
            self.state.mission_status = "running"
            self._update_mission_summary()

            outcome = await self.bridge.run_mission(
                brief=brief,
                project_id=self.state.current_project_id,
                session_id=self.state.current_session_id,
                budget_usd=self.state.budget_usd or 10.0,
                gate=self._gate_reviewer,
            )

            self.state.mission_outcome = outcome
            self.state.mission_status = outcome.status.value
            self.state.total_cost_usd = outcome.total_cost_usd
            self._update_mission_summary()
            self.notify(
                f"Mission {outcome.status}: ${outcome.total_cost_usd:.4f}",
                severity="information",
            )
        except asyncio.CancelledError:
            self.state.mission_status = "failed"
            self._update_mission_summary()
            self.notify("Mission cancelled", severity="warning")
        except Exception as exc:
            self.state.mission_status = "failed"
            self._update_mission_summary()
            logger.error("Mission execution failed", exc_info=True)
            self.notify(f"Mission failed: {exc}", severity="error")

    def action_cancel_mission(self) -> None:
        """Cancel the active mission (Ctrl+K)."""
        if self._mission_worker and self._mission_worker.is_running:
            self._mission_worker.cancel()
            self.notify("Cancelling mission...", severity="warning")

    # ── Event routing ────────────────────────────────────────────────

    async def on_session_event_received(
        self, message: SessionEventReceived,
    ) -> None:
        """Route a SessionEvent to the appropriate state update + widget."""
        event = message.event
        self.state.events.append(event)
        try:
            self._route_event(event)
        except Exception:
            logger.warning("Error routing event %s", getattr(event, "event_type", "?"), exc_info=True)

    def _route_event(self, event: object) -> None:
        """Dispatch event to state updates and widgets. Wrapped in error boundary."""

        # Push to event stream widget
        self._push_to_event_stream(event)

        # Update state based on event type
        event_type = event.event_type

        if event_type == "agent.thinking.started":
            agent_id = getattr(event, "agent_id", "")
            self.state.active_agents.add(agent_id)
            self._sidebar_set_active(agent_id, True)
            self._push_to_agent_detail_thinking(agent_id)

        elif event_type == "agent.response.complete":
            agent_id = getattr(event, "agent_id", "")
            self.state.active_agents.discard(agent_id)
            cost = getattr(event, "cost_usd", 0.0)
            input_tokens = getattr(event, "input_tokens", 0)
            output_tokens = getattr(event, "output_tokens", 0)
            self._sidebar_set_active(agent_id, False)
            self._sidebar_set_status(agent_id, "success", cost)
            self.state.total_input_tokens += input_tokens
            self.state.total_output_tokens += output_tokens
            # Update agent detail if viewing this agent
            self._push_to_agent_detail_complete(
                agent_id, cost=cost,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        elif event_type == "agent.response.chunk":
            agent_id = getattr(event, "agent_id", "")
            content = getattr(event, "content", "")
            self.state.agent_output.setdefault(agent_id, "")
            self.state.agent_output[agent_id] += content
            self._push_to_agent_detail_chunk(agent_id, content)

        elif event_type == "agent.tool.called":
            agent_id = getattr(event, "agent_id", "")
            tool_name = getattr(event, "tool_name", "?")
            tool_args = getattr(event, "tool_args", {})
            tool_call_id = getattr(event, "tool_call_id", "")
            self.state.agent_tool_calls.setdefault(agent_id, [])
            self.state.agent_tool_calls[agent_id].append({
                "tool_name": tool_name,
                "tool_args": tool_args,
                "tool_call_id": tool_call_id,
            })
            self._push_to_agent_detail_tool_call(
                agent_id, tool_name=tool_name,
                tool_args=tool_args, tool_call_id=tool_call_id,
            )

        elif event_type == "agent.tool.returned":
            agent_id = getattr(event, "agent_id", "")
            self._push_to_agent_detail_tool_result(
                agent_id,
                tool_name=getattr(event, "tool_name", "?"),
                status=getattr(event, "status", "success"),
                result=getattr(event, "result", None),
            )

        elif event_type == "session.cost.updated":
            self.state.total_cost_usd = getattr(event, "cumulative_cost_usd", 0.0)
            # Budget warnings
            if self.state.budget_usd > 0:
                ratio = self.state.total_cost_usd / self.state.budget_usd
                if ratio >= 0.9 and not self._budget_warned_90:
                    self._budget_warned_90 = True
                    self._notify("warning", f"Budget 90% used: ${self.state.total_cost_usd:.3f} / ${self.state.budget_usd:.2f}")
                elif ratio >= 0.75 and not self._budget_warned_75:
                    self._budget_warned_75 = True
                    self._notify("warning", f"Budget 75% used: ${self.state.total_cost_usd:.3f} / ${self.state.budget_usd:.2f}")

        elif event_type == "plan.created":
            self.state.mission_status = "running"
            self._handle_plan_created(event)

        elif event_type == "plan.step.started":
            step_id = getattr(event, "step_id", "")
            agent = getattr(event, "assigned_agent", "")
            self.state.active_agents.add(agent)
            self._sidebar_set_active(agent, True)
            if self._mission_panel:
                self._mission_panel.set_active_task(step_id)

        elif event_type == "plan.step.completed":
            step_id = getattr(event, "step_id", "")
            agent = getattr(event, "assigned_agent", "")
            self.state.active_agents.discard(agent)
            self._sidebar_set_active(agent, False)
            status = getattr(event, "status", "success")
            self._sidebar_set_status(agent, status)
            # Build a minimal TaskResult for the panel
            result = TaskResult(
                task_id=step_id,
                agent_name=agent,
                status=TaskStatus(status) if status in TaskStatus.__members__.values() else TaskStatus.SUCCESS,
            )
            self.state.task_results[step_id] = result
            if self._mission_panel:
                self._mission_panel.update_task_status(step_id, result=result)

        elif event_type == "playbook.run.started":
            pb_name = getattr(event, "playbook_name", "")
            step_count = getattr(event, "step_count", 0)
            self.state.playbook_name = pb_name
            self._notify("info", f"Playbook started: {pb_name} ({step_count} steps)")

        elif event_type == "playbook.mission.started":
            step_id = getattr(event, "step_id", "")
            roster = getattr(event, "roster_ref", "")
            self.state.playbook_progress[step_id] = {"status": "running", "roster": roster}
            self._update_playbook_panel(step_id, status="running", roster=roster)

        elif event_type == "playbook.mission.completed":
            step_id = getattr(event, "step_id", "")
            success = getattr(event, "success", True)
            cost = getattr(event, "cost_usd", 0.0)
            status = "success" if success else "failed"
            self.state.playbook_progress[step_id] = {"status": status, "cost": cost}
            self._update_playbook_panel(step_id, status=status, cost=cost)
            if not success:
                self._notify("warning", f"Playbook step failed: {step_id}")

        elif event_type == "playbook.run.completed":
            total_cost = getattr(event, "total_cost_usd", 0.0)
            summary = getattr(event, "result_summary", "") or ""
            self._notify("success", f"Playbook complete: ${total_cost:.3f}")
            if self._playbook_panel:
                self._playbook_panel.set_completed(total_cost, summary)

        elif event_type == "playbook.run.failed":
            error = getattr(event, "error", "")
            failed_step = getattr(event, "failed_step", None)
            self._notify("error", f"Playbook failed: {error[:60]}")
            if self._playbook_panel:
                self._playbook_panel.set_failed(error, failed_step)

        self._update_cost_bar()
        self._update_mission_summary()

    # ── Widget update helpers ────────────────────────────────────────

    def _push_to_event_stream(self, event: object) -> None:
        """Forward an event to the EventStreamWidget."""
        try:
            stream = self.screen.query_one("#event-stream", EventStreamWidget)
            stream.add_event(event)
        except NoMatches:
            pass

    def _active_detail_for(self, agent_id: str) -> AgentDetailWidget | None:
        """Return the agent detail widget if it's showing this agent."""
        if self._agent_detail and self._agent_detail.agent_name == agent_id:
            return self._agent_detail
        return None

    def _push_to_agent_detail_thinking(self, agent_id: str) -> None:
        if detail := self._active_detail_for(agent_id):
            detail.set_thinking(agent_id)
            detail.update_header(status="running")

    def _push_to_agent_detail_chunk(self, agent_id: str, content: str) -> None:
        if detail := self._active_detail_for(agent_id):
            detail.append_output(content)

    def _push_to_agent_detail_complete(
        self, agent_id: str, *, cost: float,
        input_tokens: int, output_tokens: int,
    ) -> None:
        if detail := self._active_detail_for(agent_id):
            detail.update_header(
                status="success", cost=cost,
                input_tokens=input_tokens, output_tokens=output_tokens,
            )

    def _push_to_agent_detail_tool_call(
        self, agent_id: str, *,
        tool_name: str, tool_args: dict, tool_call_id: str,
    ) -> None:
        if detail := self._active_detail_for(agent_id):
            detail.add_tool_call(
                tool_name=tool_name, tool_args=tool_args,
                tool_call_id=tool_call_id,
            )

    def _push_to_agent_detail_tool_result(
        self, agent_id: str, *,
        tool_name: str, status: str, result: str | None,
    ) -> None:
        if detail := self._active_detail_for(agent_id):
            detail.add_tool_result(
                tool_name=tool_name, status=status, result=result,
            )

    def _sidebar_set_active(self, agent_name: str, active: bool) -> None:
        try:
            sidebar = self.screen.query_one("#agent-sidebar", AgentSidebar)
            sidebar.set_active(agent_name, active)
        except NoMatches:
            pass

    def _sidebar_set_status(
        self, agent_name: str, status: str, cost: float = 0.0
    ) -> None:
        try:
            sidebar = self.screen.query_one("#agent-sidebar", AgentSidebar)
            sidebar.set_agent_status(agent_name, status, cost)
        except NoMatches:
            pass

    def _update_cost_bar(self) -> None:
        try:
            bar = self.screen.query_one("#cost-bar", CostBar)
            bar.cost_usd = self.state.total_cost_usd
            bar.budget_usd = self.state.budget_usd
            bar.input_tokens = self.state.total_input_tokens
            bar.output_tokens = self.state.total_output_tokens
            bar.current_layer = self.state.current_layer
            bar.total_layers = len(self.state.task_layers) if self.state.task_layers else 0
            bar.pending_gates = 1 if self.state.pending_gate else 0
            bar.playbook_name = self.state.playbook_name or ""
            done_steps = sum(
                1 for p in self.state.playbook_progress.values()
                if p.get("status") in ("success", "failed", "skipped")
            )
            bar.playbook_step = done_steps
            bar.playbook_total_steps = len(self.state.playbook_progress) if self.state.playbook_progress else 0
        except NoMatches:
            pass

    def _notify(self, severity: str, message: str) -> None:
        """Push a notification to the NotificationStack if mounted."""
        self.state.notifications.append({"severity": severity, "message": message})
        try:
            stack = self.screen.query_one("#notification-stack", NotificationStack)
            stack.add_notification(message, severity=severity)
        except NoMatches:
            pass

    def _update_playbook_panel(
        self, step_id: str, *,
        status: str | None = None,
        cost: float | None = None,
        roster: str | None = None,
    ) -> None:
        """Forward step update to the PlaybookProgressWidget if mounted."""
        if self._playbook_panel:
            self._playbook_panel.update_step(
                step_id, status=status, cost=cost, roster=roster,
            )

    def _update_mission_summary(self) -> None:
        try:
            summary = self.screen.query_one("#mission-summary", MissionSummary)
            summary.update_from_state(
                status=self.state.mission_status,
                budget_usd=self.state.budget_usd,
                total_cost=self.state.total_cost_usd,
                tasks_done=self.state.tasks_completed,
                tasks_total=self.state.tasks_total,
                current_layer=self.state.current_layer,
                total_layers=len(self.state.task_layers),
            )
        except NoMatches:
            pass

    # ── Plan handling ──────────────────────────────────────────────────

    def _handle_plan_created(self, event: object) -> None:
        """Parse the TaskPlan from PlanCreatedEvent metadata and show the DAG."""
        metadata = getattr(event, "metadata", {}) or {}
        plan_json = metadata.get("task_plan_json")
        if not plan_json:
            return
        try:
            plan = TaskPlan.model_validate_json(plan_json)
            layers = topological_sort(plan)
            self.state.task_plan = plan
            self.state.task_layers = layers
            self._show_mission_panel(plan, layers)
        except Exception:
            logger.warning("Failed to parse TaskPlan from event metadata", exc_info=True)

    def _show_mission_panel(self, plan: TaskPlan, layers: list[list[str]]) -> None:
        """Mount the MissionPanel in the center panel with the plan DAG."""
        try:
            container = self.screen.query_one("#center-content", VerticalScroll)
        except NoMatches:
            return
        container.remove_children()
        self._agent_detail = None
        self.state.selected_agent = None

        panel = MissionPanel(id="mission-panel")
        self._mission_panel = panel
        container.mount(panel)
        # load_plan must be called after mount so widgets exist
        panel.load_plan(plan, layers)

    # ── Gate review ────────────────────────────────────────────────────

    async def on_gate_review_requested(
        self, message: GateReviewRequested,
    ) -> None:
        """Dispatch is waiting — show the gate modal for human review."""
        self.state.pending_gate = message.context
        self._update_cost_bar()
        self.push_screen(GateReviewModal(message.context))

    async def on_gate_review_completed(
        self, message: GateReviewCompleted,
    ) -> None:
        """User resolved the gate — forward decision to the gate reviewer."""
        self.state.pending_gate = None
        self._update_cost_bar()
        self._gate_reviewer.resolve(message.decision)

    # ── Agent selection + center panel swap ───────────────────────────

    async def on_agent_selected(self, event: AgentSelected) -> None:
        """User clicked an agent in the sidebar — swap center panel."""
        self.state.selected_agent = event.agent_name
        try:
            sidebar = self.screen.query_one("#agent-sidebar", AgentSidebar)
            sidebar.set_selected(event.agent_name)
        except NoMatches:
            pass
        self._show_agent_detail(event.agent_name)

    def _show_agent_detail(self, agent_name: str) -> None:
        """Replace center-content with AgentDetailWidget for the given agent."""
        try:
            container = self.screen.query_one("#center-content", VerticalScroll)
        except NoMatches:
            return

        # Remove existing children (placeholder or previous detail)
        container.remove_children()

        # Create and mount the agent detail widget
        detail = AgentDetailWidget(agent_name, id="agent-detail")
        self._agent_detail = detail
        container.mount(detail)

        # Backfill any existing state for this agent
        if agent_name in self.state.agent_output:
            detail.set_full_output(self.state.agent_output[agent_name])
        if agent_name in self.state.agent_tool_calls:
            for tc in self.state.agent_tool_calls[agent_name]:
                detail.add_tool_call(
                    tool_name=tc["tool_name"],
                    tool_args=tc.get("tool_args", {}),
                    tool_call_id=tc.get("tool_call_id", ""),
                )
        if agent_name in self.state.active_agents:
            detail.update_header(status="running")

    def action_show_overview(self) -> None:
        """Switch center panel back to overview — MissionPanel if plan exists, else placeholder (F1)."""
        try:
            container = self.screen.query_one("#center-content", VerticalScroll)
        except NoMatches:
            return
        container.remove_children()
        self._agent_detail = None
        self.state.selected_agent = None

        if self.state.task_plan and self.state.task_layers:
            panel = MissionPanel(id="mission-panel")
            self._mission_panel = panel
            container.mount(panel)
            panel.load_plan(self.state.task_plan, self.state.task_layers)
            # Re-apply completed task results
            for task_id, result in self.state.task_results.items():
                panel.update_task_status(task_id, result=result)
        else:
            container.mount(
                Static(
                    "Press [bold]Ctrl+M[/bold] to start a mission\n"
                    "Press [bold]Ctrl+P[/bold] to switch project",
                    classes="placeholder-panel",
                )
            )

    # ── Navigation ───────────────────────────────────────────────────

    def action_switch_project(self) -> None:
        """Show project picker (Ctrl+P)."""
        self.run_worker(self._show_project_picker(), thread=False)

    async def _show_project_picker(self) -> None:
        try:
            projects = await self.bridge.list_projects()
        except Exception:
            logger.warning("Could not load projects for picker", exc_info=True)
            projects = []
        self.push_screen(ProjectPickerScreen(projects))

    def action_show_history(self) -> None:
        """Show mission history screen (F2)."""
        self.run_worker(self._show_history(), thread=False)

    async def _show_history(self) -> None:
        self._set_loading(True)
        try:
            missions = await self.bridge.list_missions(limit=50)
        except Exception:
            logger.warning("Could not load mission history", exc_info=True)
            missions = []
        finally:
            self._set_loading(False)
        self.push_screen(MissionHistoryScreen(missions))

    def _set_loading(self, loading: bool) -> None:
        """Toggle .loading class on center panel for visual feedback."""
        try:
            panel = self.screen.query_one("#center-panel")
            if loading:
                panel.add_class("loading")
            else:
                panel.remove_class("loading")
        except NoMatches:
            pass

    def action_focus_input(self) -> None:
        """Focus the chat input (Ctrl+/)."""
        try:
            self.screen.query_one("#mission-input", Input).focus()
        except NoMatches:
            pass
