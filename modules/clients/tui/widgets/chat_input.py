"""Chat input — message entry with mission dispatch.

A simple input field at the bottom of the center panel.
Pressing Enter with a non-empty message posts MissionStartRequested.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Input, Label

from modules.clients.tui.messages import MissionStartRequested


class ChatInput(Widget):
    """Message input bar with a prompt indicator."""

    DEFAULT_CSS = """
    ChatInput {
        dock: bottom;
        height: 3;
        padding: 0 1;
    }
    ChatInput > Horizontal {
        height: 3;
    }
    ChatInput Label {
        width: 2;
        height: 3;
        content-align: center middle;
    }
    ChatInput Input {
        width: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(">")
            yield Input(
                placeholder="Enter mission brief...",
                id="mission-input",
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Dispatch mission when user presses Enter."""
        text = event.value.strip()
        if text:
            event.input.clear()
            self.post_message(MissionStartRequested(brief=text))
