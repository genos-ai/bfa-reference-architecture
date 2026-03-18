"""Main screen — three-column layout with project header.

Left: AgentSidebar (roster + mission summary)
Center: Mission/agent view + chat input
Right: Event stream (Phase 2 placeholder)
Bottom: CostBar (always visible)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Label, Static

from modules.clients.tui.widgets.agent_sidebar import AgentSidebar
from modules.clients.tui.widgets.chat_input import ChatInput
from modules.clients.tui.widgets.cost_bar import CostBar


class MainScreen(Screen):
    """Primary three-column layout."""

    def compose(self) -> ComposeResult:
        # ── Top bar ──────────────────────────────────────────────
        with Horizontal(id="project-header"):
            yield Label("[bold]No Project[/bold]", id="project-name", markup=True)
            yield Label("BFA Mission Control", id="app-title")

        # ── Three columns ────────────────────────────────────────
        with Horizontal(id="main-container"):
            yield AgentSidebar(id="agent-sidebar")

            with Vertical(id="center-panel"):
                yield VerticalScroll(
                    Static(
                        "Press [bold]Ctrl+M[/bold] to start a mission\n"
                        "Press [bold]Ctrl+P[/bold] to switch project",
                        classes="placeholder-panel",
                    ),
                    id="center-content",
                )
                yield ChatInput(id="chat-input")

            with Vertical(id="right-sidebar"):
                yield Label("  EVENTS", classes="sidebar-heading")
                with VerticalScroll(id="event-stream-placeholder"):
                    yield Label(
                        "[dim]Events will appear here during missions[/dim]",
                        markup=True,
                    )

        # ── Bottom bar ───────────────────────────────────────────
        yield CostBar(id="cost-bar")
