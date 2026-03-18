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
from textual.css.query import NoMatches
from textual.widgets import Input, Label
from textual.worker import Worker

from modules.backend.core.logging import get_logger
from modules.clients.tui.messages import (
    AgentSelected,
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
from modules.clients.tui.widgets.agent_sidebar import AgentSidebar, MissionSummary
from modules.clients.tui.widgets.cost_bar import CostBar

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
    ]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.state = TuiState()
        self._event_bus = TuiEventBus(self)
        self.bridge = ServiceBridge(event_bus=self._event_bus)
        self._mission_worker: Worker | None = None

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
                gate=None,  # Phase 4: TuiGateReviewer
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

        # Update state based on event type
        event_type = event.event_type

        if event_type == "agent.thinking.started":
            agent_id = getattr(event, "agent_id", "")
            self.state.active_agents.add(agent_id)
            self._sidebar_set_active(agent_id, True)

        elif event_type == "agent.response.complete":
            agent_id = getattr(event, "agent_id", "")
            self.state.active_agents.discard(agent_id)
            cost = getattr(event, "cost_usd", 0.0)
            self._sidebar_set_active(agent_id, False)
            self._sidebar_set_status(agent_id, "success", cost)
            # Update token counts
            self.state.total_input_tokens += getattr(event, "input_tokens", 0)
            self.state.total_output_tokens += getattr(event, "output_tokens", 0)

        elif event_type == "agent.response.chunk":
            agent_id = getattr(event, "agent_id", "")
            content = getattr(event, "content", "")
            self.state.agent_output.setdefault(agent_id, "")
            self.state.agent_output[agent_id] += content

        elif event_type == "session.cost.updated":
            self.state.total_cost_usd = getattr(event, "cumulative_cost_usd", 0.0)

        elif event_type == "plan.created":
            self.state.mission_status = "running"

        elif event_type == "plan.step.started":
            agent = getattr(event, "assigned_agent", "")
            self.state.active_agents.add(agent)
            self._sidebar_set_active(agent, True)

        elif event_type == "plan.step.completed":
            step_id = getattr(event, "step_id", "")
            status = getattr(event, "status", "success")
            # Phase 3 will update task_results here

        self._update_cost_bar()
        self._update_mission_summary()

    # ── Widget update helpers ────────────────────────────────────────

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
        except NoMatches:
            pass

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

    # ── Agent selection ──────────────────────────────────────────────

    async def on_agent_selected(self, event: AgentSelected) -> None:
        """User clicked an agent in the sidebar."""
        self.state.selected_agent = event.agent_name
        try:
            sidebar = self.screen.query_one("#agent-sidebar", AgentSidebar)
            sidebar.set_selected(event.agent_name)
        except NoMatches:
            pass
        # Phase 2 will switch center panel to AgentDetailWidget

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

    def action_focus_input(self) -> None:
        """Focus the chat input (Ctrl+/)."""
        try:
            self.screen.query_one("#mission-input", Input).focus()
        except NoMatches:
            pass
