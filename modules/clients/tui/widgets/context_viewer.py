"""Context viewer — inspect PCD, code map, and assembled task context.

Displays structured context data in a scrollable, syntax-highlighted view.
Can be mounted in the center panel when the user wants to inspect context.
"""

from __future__ import annotations

import json

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Label, RichLog, TabbedContent, TabPane

from modules.clients.common.gate_helpers import STATUS_ICONS


class ContextViewer(Widget):
    """Tabbed viewer for PCD, code map, and task context."""

    DEFAULT_CSS = """
    ContextViewer {
        height: 1fr;
    }
    #context-header {
        height: 3;
        padding: 0 1;
        background: $surface-lighten-1;
    }
    #context-header Label {
        height: 3;
        content-align: left middle;
    }
    """

    def __init__(self, title: str = "Context", **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="context-header"):
            yield Label(
                f"[bold]{self._title}[/bold]",
                markup=True,
                id="context-title",
            )
        with TabbedContent():
            with TabPane("Overview", id="context-overview-tab"):
                yield RichLog(id="context-overview", wrap=True, markup=True)
            with TabPane("Raw JSON", id="context-json-tab"):
                yield RichLog(id="context-json", wrap=True)
            with TabPane("Tasks", id="context-tasks-tab"):
                yield RichLog(id="context-tasks", wrap=True, markup=True)

    def load_mission_detail(self, detail: dict) -> None:
        """Load a mission detail dict into the viewer."""
        self._load_overview_tab(detail)
        self._load_json_tab(detail.get("task_plan_json"))
        self._load_tasks_tab(detail.get("task_executions", []))

    def _load_overview_tab(self, detail: dict) -> None:
        try:
            overview = self.query_one("#context-overview", RichLog)
        except NoMatches:
            return
        overview.clear()
        overview.write(f"[bold]Objective:[/bold] {detail.get('objective', '?')}")
        overview.write(f"[bold]Status:[/bold] {detail.get('status', '?')}")
        overview.write(f"[bold]Cost:[/bold] ${detail.get('total_cost_usd', 0):.4f}")
        overview.write(f"[bold]Roster:[/bold] {detail.get('roster_name', '?')}")
        overview.write(f"[bold]Created:[/bold] {detail.get('created_at', '?')}")

    def _load_json_tab(self, plan_json: str | dict | None) -> None:
        try:
            json_log = self.query_one("#context-json", RichLog)
        except NoMatches:
            return
        json_log.clear()
        if plan_json:
            if isinstance(plan_json, str):
                try:
                    parsed = json.loads(plan_json)
                    json_log.write(json.dumps(parsed, indent=2))
                except json.JSONDecodeError:
                    json_log.write(plan_json)
            else:
                json_log.write(json.dumps(plan_json, indent=2, default=str))
        else:
            json_log.write("No task plan available")

    def _load_tasks_tab(self, executions: list[dict]) -> None:
        try:
            tasks_log = self.query_one("#context-tasks", RichLog)
        except NoMatches:
            return
        tasks_log.clear()
        if not executions:
            tasks_log.write("[dim]No task executions recorded[/dim]")
        for t in executions:
            status = t.get("status", "?")
            icon = STATUS_ICONS.get(status, f"[dim]{status}[/dim]")
            tasks_log.write(
                f"{icon} [bold]{t.get('task_id', '?')}[/bold]  "
                f"[{t.get('agent_name', '?')}]  "
                f"${t.get('cost_usd', 0):.4f}  "
                f"{t.get('input_tokens', 0)}in/{t.get('output_tokens', 0)}out"
            )

    def load_json(self, title: str, data: dict | str) -> None:
        """Load arbitrary JSON data into the viewer."""
        try:
            self.query_one("#context-title", Label).update(
                f"[bold]{title}[/bold]"
            )
        except NoMatches:
            pass
        self._load_json_tab(data)

    def clear(self) -> None:
        """Clear all tabs."""
        for log_id in ("#context-overview", "#context-json", "#context-tasks"):
            try:
                self.query_one(log_id, RichLog).clear()
            except NoMatches:
                pass
