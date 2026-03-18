"""Agent detail — tabbed view of a selected agent's activity.

Shows Thinking, Output, and Tools tabs with live-streaming content.
Mounted in the center panel when a user clicks an agent in the sidebar.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, RichLog, Static, TabbedContent, TabPane


class AgentDetailWidget(Widget):
    """Tabbed detail view for a single agent's execution state."""

    DEFAULT_CSS = """
    AgentDetailWidget {
        height: 1fr;
    }
    #agent-detail-header {
        height: 3;
        padding: 0 1;
        background: $surface-lighten-1;
    }
    #agent-detail-header Label {
        height: 3;
        content-align: left middle;
    }
    AgentDetailWidget TabbedContent {
        height: 1fr;
    }
    AgentDetailWidget TabPane {
        padding: 0;
    }
    AgentDetailWidget RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-gutter: stable;
    }
    #tool-log {
        height: 1fr;
        padding: 0 1;
    }
    """

    def __init__(self, agent_name: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.agent_name = agent_name
        self._display_name = (
            agent_name.split(".")[-2] if "." in agent_name else agent_name
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="agent-detail-header"):
            yield Label(
                f"[bold]{self._display_name}[/bold]  [dim]{self.agent_name}[/dim]",
                markup=True,
                id="agent-header-label",
            )

        with TabbedContent():
            with TabPane("Output", id="tab-output"):
                yield RichLog(
                    id="output-log",
                    highlight=True,
                    markup=True,
                    wrap=True,
                )
            with TabPane("Thinking", id="tab-thinking"):
                yield RichLog(
                    id="thinking-log",
                    highlight=False,
                    markup=True,
                    wrap=True,
                )
            with TabPane("Tools", id="tab-tools"):
                yield RichLog(
                    id="tool-log",
                    highlight=True,
                    markup=True,
                    wrap=True,
                )

    # ── Public API for the App to push content ───────────────────────

    def append_output(self, content: str) -> None:
        """Append streamed response content to the Output tab."""
        log = self.query_one("#output-log", RichLog)
        log.write(content)

    def set_full_output(self, content: str) -> None:
        """Replace output with the final complete response."""
        log = self.query_one("#output-log", RichLog)
        log.clear()
        log.write(content)

    def set_thinking(self, agent_id: str) -> None:
        """Show that the agent has started thinking."""
        log = self.query_one("#thinking-log", RichLog)
        log.write(f"[dim cyan]{agent_id} is thinking...[/dim cyan]")

    def add_tool_call(
        self,
        *,
        tool_name: str,
        tool_args: dict | None = None,
        tool_call_id: str = "",
    ) -> None:
        """Record a tool invocation in the Tools tab."""
        log = self.query_one("#tool-log", RichLog)
        args_preview = ""
        if tool_args:
            # Show first 80 chars of stringified args
            args_str = str(tool_args)
            args_preview = f"  [dim]{args_str[:80]}[/dim]"
        log.write(f"[yellow]🔧 {tool_name}[/yellow]{args_preview}")

    def add_tool_result(
        self,
        *,
        tool_name: str,
        status: str = "success",
        result: str | None = None,
    ) -> None:
        """Record a tool result in the Tools tab."""
        log = self.query_one("#tool-log", RichLog)
        color = "green" if status == "success" else "red"
        preview = ""
        if result:
            preview = f"  [dim]{result[:60]}[/dim]"
        log.write(f"  [{color}]→ {status}[/{color}]{preview}")

    def update_header(
        self,
        *,
        status: str = "",
        cost: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Update the header bar with agent status info."""
        from modules.clients.tui.widgets.cost_bar import _fmt_tokens

        parts = [f"[bold]{self._display_name}[/bold]"]
        if status:
            color = {"running": "cyan", "success": "green", "failed": "red"}.get(
                status, "dim"
            )
            parts.append(f"[{color}]{status}[/{color}]")
        if cost > 0:
            parts.append(f"[green]${cost:.3f}[/green]")
        if input_tokens or output_tokens:
            parts.append(
                f"[dim]{_fmt_tokens(input_tokens)} in / "
                f"{_fmt_tokens(output_tokens)} out[/dim]"
            )

        label = self.query_one("#agent-header-label", Label)
        label.update("  ".join(parts))

    def clear(self) -> None:
        """Reset all tabs for a new agent or mission."""
        self.query_one("#output-log", RichLog).clear()
        self.query_one("#thinking-log", RichLog).clear()
        self.query_one("#tool-log", RichLog).clear()
