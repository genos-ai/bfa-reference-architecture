"""Agent sidebar — roster list with active/selected highlights.

Displays all agents from the loaded Roster. Active agents pulse,
completed agents show status icons. Clicking selects an agent
for detail inspection in the center panel.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, Static

from modules.backend.agents.mission_control.roster import RosterAgentEntry
from modules.clients.common.gate_helpers import status_icon
from modules.clients.tui.messages import AgentSelected


class AgentCard(Static):
    """A single agent entry in the sidebar."""

    DEFAULT_CSS = """
    AgentCard {
        height: 3;
        padding: 0 1;
        margin: 0 0 0 0;
    }
    AgentCard:hover {
        background: $surface-lighten-1;
    }
    AgentCard.active {
        background: $primary-background;
    }
    AgentCard.selected {
        background: $accent-darken-1;
    }
    """

    is_active: reactive[bool] = reactive(False)
    is_selected: reactive[bool] = reactive(False)
    status_text: reactive[str] = reactive("")

    def __init__(self, entry: RosterAgentEntry, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.entry = entry

    def compose(self) -> ComposeResult:
        name = self.entry.agent_name.split(".")[-2] if "." in self.entry.agent_name else self.entry.agent_name
        model_short = self.entry.model.name.split(":")[-1][:12] if self.entry.model else "?"
        yield Label(f"{name}  [dim]{model_short}[/dim]", markup=True)

    def on_click(self) -> None:
        self.post_message(AgentSelected(agent_name=self.entry.agent_name))

    def watch_is_active(self, active: bool) -> None:
        self.set_class(active, "active")

    def watch_is_selected(self, selected: bool) -> None:
        self.set_class(selected, "selected")

    def update_status(self, status: str | None, cost: float = 0.0) -> None:
        """Update the agent's display status."""
        if status is None:
            self.status_text = ""
            return
        icon = status_icon(status=status)
        cost_str = f" ${cost:.3f}" if cost > 0 else ""
        self.status_text = f"{icon}{cost_str}"


class MissionSummary(Static):
    """Compact mission status panel below the agent list."""

    DEFAULT_CSS = """
    MissionSummary {
        height: auto;
        min-height: 5;
        padding: 1;
        border-top: solid $surface-lighten-2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("MISSION", classes="sidebar-heading")
        yield Label("Status: idle", id="mission-status")
        yield Label("Budget: —", id="mission-budget")
        yield Label("Tasks: 0/0", id="mission-tasks")
        yield Label("Cost: $0.00", id="mission-cost")

    def update_from_state(
        self,
        *,
        status: str,
        budget_usd: float,
        total_cost: float,
        tasks_done: int,
        tasks_total: int,
        current_layer: int,
        total_layers: int,
    ) -> None:
        """Refresh mission summary labels from TUI state."""
        try:
            self.query_one("#mission-status", Label).update(f"Status: {status}")
            budget_str = f"${budget_usd:.2f}" if budget_usd > 0 else "—"
            self.query_one("#mission-budget", Label).update(f"Budget: {budget_str}")
            self.query_one("#mission-tasks", Label).update(
                f"Tasks: {tasks_done}/{tasks_total}  Layer {current_layer}/{total_layers}"
            )
            self.query_one("#mission-cost", Label).update(f"Cost: ${total_cost:.4f}")
        except NoMatches:
            pass  # Widget not yet mounted


class AgentSidebar(Widget):
    """Left sidebar showing roster agents and mission summary."""

    DEFAULT_CSS = """
    AgentSidebar {
        width: 26;
        dock: left;
        border-right: solid $surface-lighten-2;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._cards: dict[str, AgentCard] = {}

    def compose(self) -> ComposeResult:
        yield Label("  AGENTS", classes="sidebar-heading")
        yield VerticalScroll(id="agent-list")
        yield MissionSummary(id="mission-summary")

    def load_roster(self, agents: list[RosterAgentEntry]) -> None:
        """Populate the sidebar with roster agents."""
        container = self.query_one("#agent-list", VerticalScroll)
        container.remove_children()
        self._cards.clear()
        for entry in agents:
            safe_id = entry.agent_name.replace(".", "-")
            card = AgentCard(entry, id=f"card-{safe_id}")
            self._cards[entry.agent_name] = card
            container.mount(card)

    def set_active(self, agent_name: str, active: bool) -> None:
        """Mark an agent as active/inactive."""
        if card := self._cards.get(agent_name):
            card.is_active = active

    def set_selected(self, agent_name: str) -> None:
        """Highlight the selected agent, clearing others."""
        for name, card in self._cards.items():
            card.is_selected = name == agent_name

    def set_agent_status(
        self, agent_name: str, status: str, cost: float = 0.0
    ) -> None:
        """Update status icon on an agent card."""
        if card := self._cards.get(agent_name):
            card.update_status(status, cost)
