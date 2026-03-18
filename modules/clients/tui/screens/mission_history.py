"""Mission history screen — browse past missions with cost breakdown.

Shows a scrollable list of past missions. Selecting a mission shows
its detail in a ContextViewer.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.message import Message
from textual.widgets import Label, Static

from modules.clients.common.gate_helpers import STATUS_ICONS, safe_css_id
from modules.clients.tui.widgets.context_viewer import ContextViewer


class MissionRow(Static):
    """A single mission in the history list."""

    DEFAULT_CSS = """
    MissionRow {
        height: 3;
        padding: 0 1;
    }
    MissionRow:hover {
        background: $primary-background;
    }
    MissionRow.selected {
        background: $primary-background-darken-1;
    }
    """

    def __init__(
        self,
        mission: dict,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.mission_data = mission

    def compose(self) -> ComposeResult:
        m = self.mission_data
        icon = STATUS_ICONS.get(str(m.get("status", "")), "[dim]?[/dim]")
        objective = str(m.get("objective", ""))[:45]
        cost = m.get("total_cost_usd", 0.0)
        roster = m.get("roster_name", "")
        created = str(m.get("created_at", ""))[:16]
        yield Label(
            f"{icon} [bold]{objective}[/bold]  "
            f"[dim]{roster}  ${cost:.4f}  {created}[/dim]",
            markup=True,
        )

    def on_click(self) -> None:
        self.post_message(MissionSelected(self.mission_data))


class MissionSelected(Message):
    """User selected a mission from the history list."""

    def __init__(self, mission: dict) -> None:
        super().__init__()
        self.mission = mission


class MissionHistoryScreen(ModalScreen[None]):
    """Modal screen for browsing mission history."""

    DEFAULT_CSS = """
    MissionHistoryScreen {
        align: center middle;
    }
    #history-dialog {
        width: 90%;
        height: 85%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #history-header {
        height: 3;
        padding: 0 1;
        background: $surface-lighten-1;
        content-align: left middle;
    }
    #history-columns {
        height: 1fr;
    }
    #mission-list-panel {
        width: 1fr;
        min-width: 30;
    }
    #mission-list-scroll {
        height: 1fr;
    }
    #mission-detail-panel {
        width: 2fr;
    }
    .history-hint {
        height: 1;
        content-align: center middle;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    def __init__(
        self,
        missions: list[dict],
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._missions = missions
        self._selected_id: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="history-dialog"):
            yield Label(
                f"[bold]Mission History[/bold]  "
                f"[dim]{len(self._missions)} missions[/dim]",
                markup=True,
                id="history-header",
            )

            with Horizontal(id="history-columns"):
                with Vertical(id="mission-list-panel"):
                    with VerticalScroll(id="mission-list-scroll"):
                        if self._missions:
                            for m in self._missions:
                                safe_id = safe_css_id(str(m.get("id", "")))
                                yield MissionRow(m, id=f"mrow-{safe_id}")
                        else:
                            yield Static(
                                "[dim]No missions found[/dim]",
                                markup=True,
                            )

                with Vertical(id="mission-detail-panel"):
                    yield ContextViewer(
                        title="Select a mission",
                        id="history-context-viewer",
                    )

            yield Label(
                "[dim]Click a mission to view details  |  Esc to close[/dim]",
                markup=True,
                classes="history-hint",
            )

    def on_mission_selected(self, event: MissionSelected) -> None:
        """Load mission detail into the context viewer."""
        mission = event.mission
        self._selected_id = mission.get("id")

        # Highlight selected row
        for row in self.query(MissionRow):
            row.remove_class("selected")
            if row.mission_data.get("id") == self._selected_id:
                row.add_class("selected")

        # Load into context viewer
        try:
            viewer = self.query_one("#history-context-viewer", ContextViewer)
        except NoMatches:
            return
        viewer.load_mission_detail(mission)
