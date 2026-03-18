"""Notification widget — toast-style alerts for budget warnings and failures.

Displays a stack of dismissible notifications at the top of the event stream
panel. Notifications auto-expire or can be dismissed with a click.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Label, Static


# ── Severity levels ──────────────────────────────────────────────────

_SEVERITY_STYLES: dict[str, tuple[str, str]] = {
    "info": ("ℹ", "cyan"),
    "warning": ("⚠", "yellow"),
    "error": ("✗", "red"),
    "success": ("✓", "green"),
}


class NotificationEntry(Static):
    """A single notification in the stack."""

    DEFAULT_CSS = """
    NotificationEntry {
        height: auto;
        min-height: 1;
        padding: 0 1;
        margin: 0 0 0 0;
    }
    NotificationEntry.severity-warning {
        background: $warning 10%;
    }
    NotificationEntry.severity-error {
        background: $error 10%;
    }
    """

    def __init__(
        self,
        message: str,
        severity: str = "info",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._message = message
        self._severity = severity

    def compose(self) -> ComposeResult:
        icon, color = _SEVERITY_STYLES.get(
            self._severity, _SEVERITY_STYLES["info"]
        )
        yield Label(
            f"[{color}]{icon}[/{color}] {self._message}",
            markup=True,
        )

    def on_click(self) -> None:
        """Dismiss on click."""
        self.remove()


class NotificationStack(Widget):
    """Stack of toast-style notifications. Most recent on top."""

    DEFAULT_CSS = """
    NotificationStack {
        height: auto;
        max-height: 6;
        overflow-y: auto;
    }
    """

    MAX_VISIBLE = 5

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._count = 0
        self._dismiss_timers: dict[str, Timer] = {}

    def compose(self) -> ComposeResult:
        yield Vertical(id="notification-container")

    def add_notification(
        self,
        message: str,
        severity: str = "info",
        timeout_seconds: float = 10.0,
    ) -> None:
        """Add a notification to the stack."""
        self._count += 1
        entry_id = f"notif-{self._count}"
        entry = NotificationEntry(
            message,
            severity=severity,
            id=entry_id,
        )
        entry.add_class(f"severity-{severity}")

        try:
            container = self.query_one("#notification-container", Vertical)
        except NoMatches:
            return

        container.mount(entry)

        # Trim old notifications
        children = list(container.children)
        while len(children) > self.MAX_VISIBLE:
            oldest = children.pop(0)
            oldest.remove()

        # Auto-dismiss after timeout
        if timeout_seconds > 0:
            timer = self.set_timer(
                timeout_seconds,
                lambda eid=entry_id: self._dismiss(eid),
            )
            self._dismiss_timers[entry_id] = timer

    def _dismiss(self, entry_id: str) -> None:
        """Remove a notification by ID."""
        try:
            entry = self.query_one(f"#{entry_id}", NotificationEntry)
            entry.remove()
        except NoMatches:
            pass
        self._dismiss_timers.pop(entry_id, None)

    def clear_all(self) -> None:
        """Remove all notifications."""
        try:
            container = self.query_one("#notification-container", Vertical)
            container.remove_children()
        except NoMatches:
            pass
        for timer in self._dismiss_timers.values():
            timer.stop()
        self._dismiss_timers.clear()
