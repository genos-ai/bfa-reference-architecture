"""
Shared Rich display primitives for all BFA client surfaces.

Provides console, tables, panels, and formatting helpers used by
CLI, TUI, and any future client. Extracted from the CLI report module
to avoid duplication and keep each client surface thin.

All functions are synchronous — they build Rich renderables, not
business logic.
"""

from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


OUTPUT_FORMATS = ("human", "json", "jsonl")

# Solid outer border with dotted row dividers — used for tables with
# multi-line cells or dense rows where visual separation helps scanning.
DOTTED_ROWS = box.Box(
    "┌─┬┐\n"
    "│ ││\n"
    "├─┼┤\n"
    "│ ││\n"
    "│-││\n"
    "│-││\n"
    "│ ││\n"
    "└─┴┘\n"
)

# ── Status & severity ──────────────────────────────────────────────────

_STATUS_COLORS: dict[str, str] = {
    "completed": "green",
    "failed": "red",
    "running": "yellow",
    "pending": "yellow",
}


def status_color(status: Any) -> str:
    """Return the color name for a status value (str or enum)."""
    val = status.value if hasattr(status, "value") else str(status)
    return _STATUS_COLORS.get(val, "white")


def styled_status(status: Any) -> str:
    """Return a Rich-markup-colored status string."""
    val = status.value if hasattr(status, "value") else str(status)
    color = _STATUS_COLORS.get(val, "white")
    return f"[{color}]{val}[/{color}]"


_SEVERITY_COLORS: dict[str, str] = {
    "critical": "bold red",
    "error": "red",
    "warning": "yellow",
    "info": "dim",
}

# Sort priority — lower number = higher priority.
SEVERITY_ORDER: dict[str, int] = {
    "critical": 0, "error": 1, "warning": 2, "info": 3,
}


def severity_color(severity: str) -> str:
    """Return the Rich color for a finding severity level."""
    return _SEVERITY_COLORS.get(severity.lower(), "white")


# ── Console ────────────────────────────────────────────────────────────


def get_console() -> Console:
    """Return a Console with width from application config."""
    from modules.backend.core.config import get_app_config
    width = get_app_config().application.cli.console_width
    return Console(width=width)


# ── Tables ─────────────────────────────────────────────────────────────


def build_table(
    title: str | None = None,
    *,
    columns: list[tuple[str, dict[str, Any]]],
    show_lines: bool = False,
    table_box: box.Box | None = None,
) -> Table:
    """Build a Rich Table from declarative column specs.

    Each column is a (name, kwargs) tuple. ``no_wrap=True`` and
    ``expand=True`` are applied by default — callers only declare
    what differs.

    Example::

        build_table("Missions", columns=[
            ("ID",     {"style": "cyan", "width": 36}),
            ("Status", {"width": 10}),
            ("Cost",   {"justify": "right", "width": 8}),
            ("Desc",   {"ratio": 1}),
        ])
    """
    table = Table(title=title, show_lines=show_lines, expand=True, box=table_box)
    for name, kwargs in columns:
        col_kwargs = {"no_wrap": True, **kwargs}
        table.add_column(name, **col_kwargs)
    return table


# ── Panels ─────────────────────────────────────────────────────────────


def status_panel(*, content: str, status: Any, **kwargs: Any) -> Panel:
    """Panel with border color matching the status."""
    return Panel(content, border_style=status_color(status), **kwargs)


def info_panel(*, content: str, title: str | None = None) -> Panel:
    """Panel with dim border for secondary/supporting content."""
    return Panel(content, title=title, border_style="dim")


def primary_panel(*, content: str, title: str | None = None) -> Panel:
    """Panel with cyan border for primary content."""
    return Panel(content, title=title, border_style="cyan")


def thinking_panel(*, content: str) -> Panel:
    """Panel for model thinking/reasoning traces (dim border, italic text)."""
    from rich.text import Text

    return Panel(
        Text(content, style="italic"),
        title="[dim]Thinking[/dim]",
        border_style="dim",
        padding=(1, 2),
    )


def output_panel(
    body: Any,
    *,
    title: str,
    subtitle: str | None = None,
) -> Panel:
    """Panel for primary agent/task output (cyan border)."""
    return Panel(
        body,
        title=f"[cyan bold]{title}[/cyan bold]",
        subtitle=f"[dim]{subtitle}[/dim]" if subtitle else None,
        border_style="cyan",
        padding=(1, 2),
    )


# ── Formatters ─────────────────────────────────────────────────────────


def format_json_body(raw: str) -> Any:
    """Parse a JSON string into a Rich Syntax object, or fall back to Text."""
    import json
    from rich.syntax import Syntax
    from rich.text import Text

    try:
        parsed = json.loads(raw)
        return Syntax(
            json.dumps(parsed, indent=2), "json",
            theme="monokai", word_wrap=True, background_color="default",
        )
    except (json.JSONDecodeError, TypeError):
        return Text(str(raw))


def cost_line(
    *,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> str:
    """Formatted dim cost/token summary string (Rich markup)."""
    return (
        f"  [dim]Tokens: {input_tokens:,} in / {output_tokens:,} out  "
        f"Cost: ${cost_usd:.4f}[/dim]"
    )


def summary_table(
    *,
    agent_name: str,
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> Table:
    """Compact key-value stats table for agent run results."""
    table = Table(
        show_header=False,
        box=box.SIMPLE,
        padding=(0, 2),
        expand=False,
    )
    table.add_column("Key", style="dim", no_wrap=True)
    table.add_column("Value", no_wrap=True)

    table.add_row("Agent", f"[cyan]{agent_name}[/cyan]")
    table.add_row("Session", f"[dim]{session_id}[/dim]")
    table.add_row("Tokens", f"{input_tokens:,} in / {output_tokens:,} out")
    table.add_row("Cost", f"${cost_usd:.4f}")

    return table
