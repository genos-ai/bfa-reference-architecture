"""
Shared gate display helpers for CLI, TUI, and any future client.

These functions render gate-related information (cost colors, status
icons, headers) and are used by both CliGateReviewer and TuiGateReviewer.
"""

from modules.backend.agents.mission_control.gate import GateContext


def cost_color(cost: float, budget: float) -> str:
    """Return Rich color name based on cost-to-budget ratio."""
    if budget <= 0:
        return "white"
    ratio = cost / budget
    if ratio > 0.9:
        return "red"
    if ratio > 0.6:
        return "yellow"
    return "green"


def status_icon(status: str) -> str:
    """Return Rich-markup status icon for verification/task status."""
    return {
        "success": "[green]\u2713[/green]",
        "failed": "[red]\u2717[/red]",
        "timeout": "[yellow]\u23f1[/yellow]",
        "skipped": "[dim]\u2014[/dim]",
    }.get(status, f"[dim]{status}[/dim]")


# Action label colors — shared by CLI and TUI gate reviewers.
ACTION_COLORS: dict[str, str] = {
    "continue": "green",
    "skip": "yellow",
    "retry": "cyan",
    "abort": "red",
    "modify": "magenta",
}


def safe_css_id(raw: str) -> str:
    """Sanitise a string for use as a Textual CSS ID fragment."""
    return raw.replace(".", "-").replace("_", "-")


# ── Status icons (shared by mission panel, playbook, history) ─────

STATUS_ICONS: dict[str, str] = {
    "pending": "[dim]○[/dim]",
    "running": "[bold cyan]●[/bold cyan]",
    "success": "[green]✓[/green]",
    "completed": "[green]✓[/green]",
    "failed": "[red]✗[/red]",
    "timeout": "[yellow]⏱[/yellow]",
    "timed_out": "[yellow]⏱[/yellow]",
    "skipped": "[dim]⊘[/dim]",
    "cancelled": "[yellow]⊘[/yellow]",
}


def gate_header(ctx: GateContext, title: str) -> str:
    """Format a gate panel header with title, mission ID, and cost."""
    cc = cost_color(ctx.total_cost_usd, ctx.budget_usd)
    return (
        f"[bold]{title}[/bold]  |  "
        f"Mission: {ctx.mission_id[:16]}  |  "
        f"Cost: [{cc}]${ctx.total_cost_usd:.4f}[/{cc}]"
        f" / ${ctx.budget_usd:.2f}"
    )
