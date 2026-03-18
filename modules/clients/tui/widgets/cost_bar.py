"""Bottom status bar — cost, tokens, layer progress, connection status.

Docked to the bottom of the screen. Always visible.
Uses cost_color() from common/gate_helpers for budget threshold coloring.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

from modules.clients.common.gate_helpers import cost_color


def _fmt_tokens(n: int) -> str:
    """Format a token count compactly (e.g. 2.1k)."""
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


class CostBar(Widget):
    """Single-line bottom status bar."""

    DEFAULT_CSS = """
    CostBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        layout: horizontal;
        padding: 0 1;
    }
    CostBar > Label {
        width: auto;
        margin: 0 2 0 0;
    }
    """

    cost_usd: reactive[float] = reactive(0.0)
    budget_usd: reactive[float] = reactive(0.0)
    input_tokens: reactive[int] = reactive(0)
    output_tokens: reactive[int] = reactive(0)
    current_layer: reactive[int] = reactive(0)
    total_layers: reactive[int] = reactive(0)
    pending_gates: reactive[int] = reactive(0)
    connected: reactive[bool] = reactive(True)

    def compose(self) -> ComposeResult:
        yield Label("$0.0000", id="cost-label")
        yield Label("0 in / 0 out", id="token-label")
        yield Label("Layer 0/0", id="layer-label")
        yield Label("", id="gate-label")
        yield Label("ready", id="status-label")

    def watch_cost_usd(self, cost: float) -> None:
        color = cost_color(cost, self.budget_usd)
        try:
            self.query_one("#cost-label", Label).update(
                f"[{color}]${cost:.4f}[/{color}]"
            )
        except NoMatches:
            pass

    def watch_input_tokens(self, tokens: int) -> None:
        self._update_tokens()

    def watch_output_tokens(self, tokens: int) -> None:
        self._update_tokens()

    def _update_tokens(self) -> None:
        try:
            self.query_one("#token-label", Label).update(
                f"{_fmt_tokens(self.input_tokens)} in / {_fmt_tokens(self.output_tokens)} out"
            )
        except NoMatches:
            pass

    def watch_current_layer(self, layer: int) -> None:
        try:
            self.query_one("#layer-label", Label).update(
                f"Layer {layer}/{self.total_layers}"
            )
        except NoMatches:
            pass

    def watch_pending_gates(self, count: int) -> None:
        try:
            label = self.query_one("#gate-label", Label)
            if count > 0:
                label.update(f"[bold cyan]● {count} gate[/bold cyan]")
            else:
                label.update("")
        except NoMatches:
            pass

    def watch_connected(self, connected: bool) -> None:
        try:
            label = self.query_one("#status-label", Label)
            if connected:
                label.update("[green]ready[/green]")
            else:
                label.update("[red]disconnected[/red]")
        except NoMatches:
            pass
