"""
TUI Client — Agent-First Terminal Interface.

Interactive terminal interface for the agentic AI platform.
All messages are routed through the backend agent coordinator API.

Usage:
    python tui.py
    python tui.py --verbose
    python tui.py --debug
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import click
import httpx

from modules.backend.core.config import get_server_base_url, validate_project_root
from modules.backend.core.logging import bind_context, get_logger, setup_logging
from modules.backend.core.utils import utc_now

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    Footer,
    Header,
    Input,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)


@dataclass
class AgentMessage:
    role: str
    content: str
    agent_name: str | None = None
    timestamp: str = field(default_factory=lambda: utc_now().strftime("%H:%M:%S"))


class StatusBar(Static):
    """Persistent status bar showing session metrics."""

    session_cost: reactive[float] = reactive(0.0)
    session_tokens: reactive[int] = reactive(0)
    plans_running: reactive[int] = reactive(0)
    approvals_pending: reactive[int] = reactive(0)
    connected: reactive[bool] = reactive(True)

    def render(self) -> Text:
        conn = "[green]connected[/]" if self.connected else "[red]reconnecting[/]"
        approval_str = f" | [bold yellow]Approvals: {self.approvals_pending}[/]" if self.approvals_pending > 0 else ""
        return Text.from_markup(
            f" Session: [bold]${self.session_cost:.3f}[/] | "
            f"Tokens: [bold]{self.session_tokens:,}[/] | "
            f"Plans: [bold]{self.plans_running}[/] running"
            f"{approval_str} | "
            f"{conn}"
        )


class ChatLog(RichLog):
    """Chat message display with rich formatting."""


class CostDashboard(Static):
    """Cost breakdown display — placeholder until cost tracking is implemented."""

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Cost Dashboard[/]\n"
            "─────────────────────────────────────\n"
            "[dim]No cost tracking backend available.\n"
            "Cost data will appear here when the cost tracking service is implemented.[/]",
            id="cost-content",
        )


class AgentTUI(App):
    """MVP TUI Client for the Agentic AI Platform."""

    TITLE = "Agent TUI"
    SUB_TITLE = "AI-First Terminal Interface"

    CSS = """
    Screen {
        layout: vertical;
    }

    #chat-container {
        height: 1fr;
    }

    ChatLog {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    #chat-input {
        dock: bottom;
        margin: 0 0;
    }

    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
    }

    #registry-container {
        height: 1fr;
        padding: 1;
    }

    .agent-card {
        height: auto;
        margin: 0 0 1 0;
        padding: 1;
        border: solid $primary;
    }

    CostDashboard {
        height: 1fr;
        padding: 1 2;
    }

    #plan-monitor {
        height: 1fr;
        padding: 1 2;
    }

    TabbedContent {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+t", "new_chat", "New Chat"),
        Binding("ctrl+k", "kill_plan", "Kill Plan"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("f1", "show_tab('chat')", "Chat", show=True),
        Binding("f2", "show_tab('registry')", "Registry", show=True),
        Binding("f3", "show_tab('costs')", "Costs", show=True),
        Binding("f4", "show_tab('plans')", "Plans", show=True),
    ]

    def __init__(self, debug: bool = False) -> None:
        super().__init__()
        self._debug = debug
        self._messages: list[AgentMessage] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Chat", id="chat"):
                with Vertical(id="chat-container"):
                    yield ChatLog(id="chat-log", highlight=True, markup=True)
                    yield Input(placeholder="Type a message... (Enter to send)", id="chat-input")
            with TabPane("Registry", id="registry"):
                with VerticalScroll(id="registry-container"):
                    yield Static("[dim]Loading agent registry...[/]", id="registry-loading")
            with TabPane("Costs", id="costs"):
                yield CostDashboard()
            with TabPane("Plans", id="plans"):
                yield Static(
                    "[bold]Plan Monitor[/]\n"
                    "─────────────────────────────────────────\n"
                    "[dim]No active plans.\n"
                    "Plan execution status will appear here when multi-step plans are running.[/]",
                    id="plan-monitor",
                )
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.write(Text.from_markup(
            "[bold]Welcome to Agent TUI[/]\n"
            "Type a message to interact with agents.\n"
            "Messages are routed to the appropriate agent via the coordinator.\n"
            "─────────────────────────────────────────\n"
        ))
        self._load_registry()

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_new_chat(self) -> None:
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.clear()
        self._messages.clear()
        chat_log.write(Text.from_markup("[dim]── New chat session ──[/]\n"))

    def action_kill_plan(self) -> None:
        chat_log = self.query_one("#chat-log", ChatLog)
        chat_log.write(Text.from_markup("\n[bold red]⚡ Plan killed by user (Ctrl+K)[/]\n"))
        status = self.query_one(StatusBar)
        status.plans_running = max(0, status.plans_running - 1)

    @on(Input.Submitted, "#chat-input")
    def on_chat_submit(self, event: Input.Submitted) -> None:
        if not event.value.strip():
            return
        user_input = event.value.strip()
        event.input.value = ""
        self._handle_user_message(user_input)

    @work(thread=False)
    async def _handle_user_message(self, user_input: str) -> None:
        """Send user message to the agent coordinator via API."""
        chat_log = self.query_one("#chat-log", ChatLog)

        chat_log.write(Text.from_markup(f"\n[bold cyan]You:[/] {user_input}\n"))
        self._messages.append(AgentMessage(role="user", content=user_input))

        await self._send_to_agent(chat_log, user_input)

    async def _send_to_agent(self, chat_log: ChatLog, message: str) -> None:
        """Send a message to the agent coordinator and display the response."""
        chat_log.write(Text.from_markup("[dim]→ Sending to agent coordinator...[/]\n"))

        try:
            base_url, timeout = get_server_base_url()

            async with httpx.AsyncClient(
                base_url=base_url,
                timeout=timeout,
                headers={"X-Frontend-ID": "tui"},
            ) as client:
                response = await client.post(
                    "/api/v1/agents/chat",
                    json={"message": message},
                )

            if response.status_code == 200:
                data = response.json()
                agent_data = data.get("data", {})
                agent_name = agent_data.get("agent_name", "agent")
                output = agent_data.get("output", "No response")
                advice = agent_data.get("advice")
                components = agent_data.get("components", {})

                chat_log.write(Text.from_markup(
                    f"\n[bold green]{agent_name}:[/] {output}\n"
                ))

                if components:
                    for comp, comp_status in components.items():
                        color = "green" if "healthy" in comp_status.lower() else "red" if "unhealthy" in comp_status.lower() else "yellow"
                        chat_log.write(Text.from_markup(
                            f"  [{color}]●[/{color}] {comp}: {comp_status}\n"
                        ))

                if advice:
                    chat_log.write(Text.from_markup(
                        f"\n[dim]Advice: {advice}[/]\n"
                    ))

                self._messages.append(AgentMessage(
                    role="assistant",
                    content=output,
                    agent_name=agent_name,
                ))
            else:
                error = response.json().get("error", {}).get("message", response.text)
                chat_log.write(Text.from_markup(f"[red]Agent error: {error}[/]\n"))

        except httpx.ConnectError:
            chat_log.write(Text.from_markup(
                "[red]Backend is not reachable. Start with: python cli.py --service server[/]\n"
            ))
        except Exception as e:
            chat_log.write(Text.from_markup(f"[red]Error: {e}[/]\n"))

    @work(thread=False)
    async def _load_registry(self) -> None:
        """Load agent registry from the backend API."""
        container = self.query_one("#registry-container")
        loading = self.query_one("#registry-loading", Static)

        try:
            base_url, timeout = get_server_base_url()

            async with httpx.AsyncClient(
                base_url=base_url,
                timeout=timeout,
                headers={"X-Frontend-ID": "tui"},
            ) as client:
                response = await client.get("/api/v1/agents/registry")

            if response.status_code == 200:
                agents = response.json().get("data", [])
                await loading.remove()

                if not agents:
                    await container.mount(Static("[dim]No agents registered[/]"))
                    return

                for agent in agents:
                    name = agent["agent_name"]
                    desc = agent.get("description", "")
                    keywords = ", ".join(agent.get("keywords", []))
                    tools = ", ".join(agent.get("tools", []))
                    await container.mount(Static(
                        f"[bold]{name}[/]\n"
                        f"  {desc}\n"
                        f"  Keywords: {keywords} | Tools: {tools or 'none'}",
                        classes="agent-card",
                    ))
            else:
                loading.update("[red]Failed to load agent registry[/]")

        except httpx.ConnectError:
            loading.update(
                "[dim]Backend not reachable — start with: python cli.py --service server[/]"
            )
        except Exception as e:
            loading.update(f"[red]Error loading registry: {e}[/]")


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output (INFO level logging).")
@click.option("--debug", "-d", is_flag=True, help="Enable debug output (DEBUG level logging).")
def main(verbose: bool, debug: bool) -> None:
    """MVP TUI Client — Agent-First Terminal Interface."""
    validate_project_root()

    if debug:
        setup_logging(level="DEBUG", format_type="console")
    elif verbose:
        setup_logging(level="INFO", format_type="console")
    else:
        setup_logging(level="WARNING", format_type="console")

    bind_context(source="tui")

    logger = get_logger(__name__)
    logger.debug("Starting TUI", extra={"debug": debug, "verbose": verbose})

    tui_app = AgentTUI(debug=debug)
    tui_app.run()


if __name__ == "__main__":
    main()
