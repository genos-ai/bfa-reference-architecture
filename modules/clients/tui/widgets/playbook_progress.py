"""Playbook progress widget — wave-based step visualization.

Shows playbook execution as a series of waves, with each step
displaying its mission status, cost, and agent assignment.
Mounted in the center panel when a playbook is running.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Label, Static

from modules.clients.common.gate_helpers import STATUS_ICONS, cost_color, safe_css_id


class StepNode(Static):
    """A single playbook step in the wave display."""

    DEFAULT_CSS = """
    StepNode {
        height: auto;
        min-height: 1;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        step_id: str,
        *,
        status: str = "pending",
        cost: float = 0.0,
        roster: str = "",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._step_id = step_id
        self._status = status
        self._cost = cost
        self._roster = roster

    def compose(self) -> ComposeResult:
        icon = STATUS_ICONS.get(self._status, STATUS_ICONS["pending"])
        cost_str = f" ${self._cost:.3f}" if self._cost > 0 else ""
        roster_str = f" [{self._roster}]" if self._roster else ""
        yield Label(
            f"  {icon} {self._step_id}{roster_str}{cost_str}",
            markup=True,
        )


class PlaybookProgressWidget(Widget):
    """Wave-based visualization for playbook execution."""

    DEFAULT_CSS = """
    PlaybookProgressWidget {
        height: 1fr;
    }
    #playbook-header {
        height: 3;
        padding: 0 1;
        background: $surface-lighten-1;
    }
    #playbook-header Label {
        height: 3;
        content-align: left middle;
    }
    #wave-scroll {
        height: 1fr;
        padding: 0;
    }
    .wave-heading {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._playbook_name: str = ""
        self._waves: list[list[str]] = []
        self._step_status: dict[str, str] = {}
        self._step_cost: dict[str, float] = {}
        self._step_roster: dict[str, str] = {}
        self._total_cost: float = 0.0
        self._budget: float = 0.0

    def compose(self) -> ComposeResult:
        with Vertical(id="playbook-header"):
            yield Label(
                "[bold]Playbook[/bold]  [dim]No playbook running[/dim]",
                markup=True,
                id="playbook-title",
            )
        yield VerticalScroll(id="wave-scroll")

    def load_playbook(
        self,
        name: str,
        waves: list[list[str]],
        budget: float = 0.0,
    ) -> None:
        """Load a playbook and render the wave layout."""
        self._playbook_name = name
        self._waves = waves
        self._step_status = {s: "pending" for wave in waves for s in wave}
        self._step_cost = {}
        self._step_roster = {}
        self._total_cost = 0.0
        self._budget = budget
        self._render_waves()

    def update_step(
        self,
        step_id: str,
        *,
        status: str | None = None,
        cost: float | None = None,
        roster: str | None = None,
    ) -> None:
        """Update a step's status/cost and refresh its node."""
        if status:
            self._step_status[step_id] = status
        if cost is not None:
            self._step_cost[step_id] = cost
            self._total_cost = sum(self._step_cost.values())
        if roster:
            self._step_roster[step_id] = roster
        self._refresh_step_node(step_id)
        self._update_header()

    def set_completed(self, total_cost: float = 0.0, summary: str = "") -> None:
        """Mark the playbook as completed."""
        self._total_cost = total_cost
        self._update_header(status="complete", summary=summary)

    def set_failed(self, error: str = "", failed_step: str | None = None) -> None:
        """Mark the playbook as failed."""
        if failed_step and failed_step in self._step_status:
            self._step_status[failed_step] = "failed"
            self._refresh_step_node(failed_step)
        self._update_header(status="failed", summary=error)

    def _update_header(
        self, status: str = "running", summary: str = "",
    ) -> None:
        """Update the header with progress info."""
        done = sum(1 for s in self._step_status.values() if s in ("success", "failed", "skipped"))
        total = len(self._step_status)
        cc = cost_color(self._total_cost, self._budget)

        status_str = ""
        if status == "complete":
            status_str = "  [green]✓ Complete[/green]"
        elif status == "failed":
            status_str = "  [red]✗ Failed[/red]"

        title_text = (
            f"[bold]Playbook: {self._playbook_name}[/bold]  "
            f"[dim]{done}/{total} steps  [{cc}]${self._total_cost:.3f}[/{cc}][/dim]"
            f"{status_str}"
        )
        if summary:
            title_text += f"  [dim]{summary[:40]}[/dim]"

        try:
            title = self.query_one("#playbook-title", Label)
            title.update(title_text)
        except NoMatches:
            pass

    def _render_waves(self) -> None:
        """Render the full wave layout — called once on load."""
        scroll = self.query_one("#wave-scroll", VerticalScroll)
        self._update_header()

        for wave_idx, wave_steps in enumerate(self._waves):
            scroll.mount(Label(
                f"  Wave {wave_idx}",
                classes="wave-heading",
            ))
            for step_id in wave_steps:
                safe_id = safe_css_id(step_id)
                node = StepNode(
                    step_id,
                    status=self._step_status.get(step_id, "pending"),
                    cost=self._step_cost.get(step_id, 0.0),
                    roster=self._step_roster.get(step_id, ""),
                    id=f"step-{safe_id}",
                )
                scroll.mount(node)

    def _refresh_step_node(self, step_id: str) -> None:
        """Update a single step node in-place."""
        safe_id = safe_css_id(step_id)
        try:
            node = self.query_one(f"#step-{safe_id}", StepNode)
        except NoMatches:
            return
        status = self._step_status.get(step_id, "pending")
        icon = STATUS_ICONS.get(status, STATUS_ICONS["pending"])
        cost = self._step_cost.get(step_id, 0.0)
        roster = self._step_roster.get(step_id, "")
        cost_str = f" ${cost:.3f}" if cost > 0 else ""
        roster_str = f" [{roster}]" if roster else ""
        node.update(f"  {icon} {step_id}{roster_str}{cost_str}")
