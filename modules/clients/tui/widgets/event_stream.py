"""Event stream — scrolling log of SessionEvents in the right sidebar.

Color-coded by event type with timestamp and one-line summary.
The App posts events here via add_event(); the widget auto-scrolls.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Label, Static

from modules.backend.events.types import SessionEvent

# ── Event type → display config ──────────────────────────────────────

_EVENT_STYLES: dict[str, tuple[str, str]] = {
    # event_type → (icon, Rich color)
    "agent.thinking.started": ("🧠", "dim cyan"),
    "agent.response.chunk": ("·", "dim"),
    "agent.response.complete": ("✓", "green"),
    "agent.tool.called": ("🔧", "yellow"),
    "agent.tool.returned": ("📎", "dim yellow"),
    "session.cost.updated": ("$", "green"),
    "plan.created": ("📋", "bold blue"),
    "plan.step.started": ("▶", "cyan"),
    "plan.step.completed": ("■", "green"),
    "plan.revised": ("↻", "magenta"),
    "agent.approval.requested": ("⏸", "bold yellow"),
    "approval.response.received": ("▶", "bold green"),
    "playbook.run.started": ("🎬", "bold blue"),
    "playbook.mission.started": ("▶", "blue"),
    "playbook.mission.completed": ("■", "blue"),
    "playbook.run.completed": ("✓", "bold green"),
    "playbook.run.failed": ("✗", "bold red"),
    "user.message.sent": ("💬", "white"),
    "user.approval.granted": ("👍", "green"),
}

_DEFAULT_STYLE: tuple[str, str] = ("·", "dim")


def _summarize_event(event: SessionEvent) -> str:
    """Build a one-line summary for the event stream."""
    etype = event.event_type

    if etype == "agent.thinking.started":
        return f"{getattr(event, 'agent_id', '?')} thinking"

    if etype == "agent.response.chunk":
        content = getattr(event, "content", "")
        preview = content[:30].replace("\n", " ")
        return preview or "..."

    if etype == "agent.response.complete":
        agent = getattr(event, "agent_id", "?")
        cost = getattr(event, "cost_usd", 0.0)
        return f"{agent} done ${cost:.3f}"

    if etype == "agent.tool.called":
        return f"{getattr(event, 'tool_name', '?')}"

    if etype == "agent.tool.returned":
        status = getattr(event, "status", "ok")
        return f"{getattr(event, 'tool_name', '?')} → {status}"

    if etype == "session.cost.updated":
        return f"${getattr(event, 'cumulative_cost_usd', 0.0):.4f}"

    if etype == "plan.created":
        return f"{getattr(event, 'step_count', '?')} tasks planned"

    if etype == "plan.step.started":
        return f"{getattr(event, 'assigned_agent', '?')}: {getattr(event, 'step_name', '')[:25]}"

    if etype == "plan.step.completed":
        return f"{getattr(event, 'step_id', '?')} {getattr(event, 'status', '')}"

    if etype == "plan.revised":
        return getattr(event, "revision_reason", "revised")[:30]

    if etype == "agent.approval.requested":
        return f"gate: {getattr(event, 'action', '?')}"

    if etype in ("playbook.run.started", "playbook.run.completed", "playbook.run.failed"):
        return getattr(event, "playbook_name", "?")

    # Fallback: use last segment of event_type
    return etype.rsplit(".", 1)[-1]


class EventEntry(Static):
    """A single event row in the stream."""

    DEFAULT_CSS = """
    EventEntry {
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(self, event: SessionEvent, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._event = event

    def compose(self) -> ComposeResult:
        icon, color = _EVENT_STYLES.get(self._event.event_type, _DEFAULT_STYLE)
        ts = self._event.timestamp.strftime("%H:%M:%S")
        summary = _summarize_event(self._event)
        yield Label(
            f"[dim]{ts}[/dim] {icon} [{color}]{summary}[/{color}]",
            markup=True,
        )


class EventStreamWidget(Widget):
    """Scrolling event log for the right sidebar."""

    DEFAULT_CSS = """
    EventStreamWidget {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("  EVENTS", classes="sidebar-heading")
        yield VerticalScroll(id="event-scroll")

    def add_event(self, event: SessionEvent) -> None:
        """Append an event to the stream and auto-scroll."""
        scroll = self.query_one("#event-scroll", VerticalScroll)
        # Skip noisy chunk events — they'd flood the stream
        if event.event_type == "agent.response.chunk":
            return
        entry = EventEntry(event)
        scroll.mount(entry)
        entry.scroll_visible()
