"""
Centralized report renderer and Rich display primitives.

Provides:
    1. Shared Rich primitives — console, tables, panels, status styling.
       All CLI handlers import from here instead of building their own.
    2. Report renderers — summary (AI narrative), detail, json tiers.

All public functions are async. CLI handlers are already async
(called via asyncio.run()), so there is no sync/async duality.
"""

import json as json_mod
import re
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

OUTPUT_FORMATS = ("summary", "detail", "json")

# =============================================================================
# Shared Rich primitives — single source of truth for CLI display
# =============================================================================

_CONSOLE_WIDTH = 140

_STATUS_COLORS: dict[str, str] = {
    "completed": "green",
    "failed": "red",
    "running": "yellow",
    "pending": "yellow",
}


def get_console() -> Console:
    """Return a Console with the standard project width."""
    return Console(width=_CONSOLE_WIDTH)


def status_color(status: Any) -> str:
    """Return the color name for a status value (str or enum)."""
    val = status.value if hasattr(status, "value") else str(status)
    return _STATUS_COLORS.get(val, "white")


def styled_status(status: Any) -> str:
    """Return a Rich-markup-colored status string."""
    val = status.value if hasattr(status, "value") else str(status)
    color = _STATUS_COLORS.get(val, "white")
    return f"[{color}]{val}[/{color}]"


def build_table(
    title: str | None = None,
    *,
    columns: list[tuple[str, dict[str, Any]]],
    show_lines: bool = False,
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
    table = Table(title=title, show_lines=show_lines, expand=True)
    for name, kwargs in columns:
        table.add_column(name, no_wrap=True, **kwargs)
    return table


def status_panel(content: str, status: Any, **kwargs: Any) -> Panel:
    """Panel with border color matching the status."""
    return Panel(content, border_style=status_color(status), **kwargs)


def info_panel(content: str, title: str | None = None) -> Panel:
    """Panel with dim border for secondary/supporting content."""
    return Panel(content, title=title, border_style="dim")


def primary_panel(content: str, title: str | None = None) -> Panel:
    """Panel with cyan border for primary content."""
    return Panel(content, title=title, border_style="cyan")


_SEVERITY_COLORS: dict[str, str] = {
    "error": "red",
    "warning": "yellow",
    "info": "dim",
    "critical": "bold red",
}


def severity_color(severity: str) -> str:
    """Return the Rich color for a finding severity level."""
    return _SEVERITY_COLORS.get(severity.lower(), "white")


# =============================================================================
# Public report API — async only, called from async CLI handlers
# =============================================================================


async def render_mission(mission: Any, output_format: str = "summary") -> None:
    """Render a single mission result."""
    if output_format == "json":
        _emit_json(_mission_to_dict(mission))
    elif output_format == "detail":
        _render_mission_detail(mission)
    else:
        await _render_summary(
            title="Mission Summary",
            status_line=f"  Status: {_styled_status(mission.status)}    Cost: ${mission.total_cost_usd:.4f}",
            data=_mission_to_dict(mission),
        )


async def render_playbook_run(
    run: Any,
    missions: list[Any],
    output_format: str = "summary",
) -> None:
    """Render a playbook run result."""
    if output_format == "json":
        _emit_json(_playbook_run_to_dict(run, missions))
    elif output_format == "detail":
        _render_playbook_detail(run, missions)
    else:
        await _render_summary(
            title="Playbook Run Summary",
            status_line=(
                f"  {run.playbook_name} v{run.playbook_version}    "
                f"Status: {_styled_status(run.status)}    "
                f"Cost: ${run.total_cost_usd:.4f}"
            ),
            data=_playbook_run_to_dict(run, missions),
        )


# =============================================================================
# Summary tier — AI narrative with deterministic fallback
# =============================================================================


async def _render_summary(title: str, status_line: str, data: dict) -> None:
    """Render the summary header and AI-generated narrative."""
    click.echo(click.style(title, fg="cyan", bold=True))
    click.echo(click.style("=" * 60, dim=True))
    click.echo()
    click.echo(status_line)
    click.echo()
    click.echo(await _generate_narrative(data))


async def _generate_narrative(data: dict) -> str:
    """Call the synthesis agent; fall back to deterministic summary on failure."""
    try:
        from modules.backend.agents.horizontal.synthesis.agent import synthesize
        return await synthesize(data)
    except Exception as e:
        logger.warning(
            "Synthesis agent unavailable, using fallback",
            extra={"error": str(e)},
        )
        return _fallback_narrative(data)


def _fallback_narrative(data: dict) -> str:
    """Deterministic fallback when the synthesis agent is unavailable."""
    lines = []

    if "playbook_name" in data:
        lines.append(f"  Playbook '{data['playbook_name']}' {data.get('status', 'unknown')}.")
        steps = data.get("steps", [])
        if steps:
            completed = sum(1 for s in steps if s.get("status") == "completed")
            lines.append(f"  {completed}/{len(steps)} steps completed.")
    else:
        lines.append(f"  Mission {data.get('status', 'unknown')}.")

    lines.append(f"  Total cost: ${data.get('total_cost_usd', 0):.4f}.")

    for finding in _extract_findings(data)[:10]:
        lines.append(f"    - {finding}")

    return "\n".join(lines)


# =============================================================================
# Narrative colorization — keyword-driven, not hardcoded
# =============================================================================

# Maps keyword patterns to Rich markup styles.
# Each key is a regex pattern matched case-insensitively against
# standalone heading lines (short lines with no leading digits).
# Add new entries here to support additional priority levels.
_HEADING_STYLES: list[tuple[str, str]] = [
    (r"critical|error|failure", "bold red"),
    (r"warning|caution|degraded", "bold yellow"),
    (r"info|note|passed|success", "dim"),
]


def colorize_narrative(text: str) -> str:
    """Apply Rich markup to priority headings in a narrative.

    Detects standalone heading lines (short, no leading numbers) and
    applies styles based on keyword matching. This is data-driven —
    new priority levels only require adding to _HEADING_STYLES.
    """
    lines = text.split("\n")
    result = []

    for line in lines:
        stripped = line.strip()
        # A heading line: short, not a numbered item, not empty
        if stripped and len(stripped) <= 40 and not re.match(r"^\d+\.", stripped):
            for pattern, style in _HEADING_STYLES:
                if re.search(pattern, stripped, re.IGNORECASE):
                    line = re.sub(
                        re.escape(stripped),
                        f"[{style}]{stripped}[/{style}]",
                        line,
                        count=1,
                    )
                    break
        result.append(line)

    return "\n".join(result)


# =============================================================================
# JSON tier
# =============================================================================


def _emit_json(data: dict) -> None:
    """Emit data as formatted JSON."""
    click.echo(json_mod.dumps(data, indent=2, default=str))


# =============================================================================
# Detail tier — deterministic per-task breakdown
# =============================================================================


def _render_mission_detail(mission: Any) -> None:
    """Deterministic detailed view of a mission."""
    click.echo(click.style("Mission Report", fg="cyan", bold=True))
    click.echo(click.style("=" * 60, dim=True))
    click.echo()

    click.echo(f"  ID:         {mission.id}")
    click.echo(f"  Status:     {_styled_status(mission.status)}")
    click.echo(f"  Objective:  {mission.objective[:120]}")
    click.echo(f"  Cost:       ${mission.total_cost_usd:.4f}")
    if mission.cost_ceiling_usd:
        pct = (mission.total_cost_usd / mission.cost_ceiling_usd) * 100
        click.echo(f"  Budget:     ${mission.cost_ceiling_usd:.2f} ({pct:.0f}% used)")
    click.echo(f"  Started:    {mission.started_at}")
    click.echo(f"  Completed:  {mission.completed_at}")

    _render_outcome_tasks(mission.mission_outcome)
    _render_errors(mission.error_data)


def _render_playbook_detail(run: Any, missions: list[Any]) -> None:
    """Deterministic detailed view of a playbook run."""
    click.echo(click.style("Playbook Run Report", fg="cyan", bold=True))
    click.echo(click.style("=" * 60, dim=True))
    click.echo()

    click.echo(f"  Playbook:   {run.playbook_name} v{run.playbook_version}")
    click.echo(f"  Run ID:     {run.id}")
    click.echo(f"  Status:     {_styled_status(run.status)}")
    click.echo(f"  Cost:       ${run.total_cost_usd:.4f}")
    if run.budget_usd:
        pct = (run.total_cost_usd / run.budget_usd) * 100
        click.echo(f"  Budget:     ${run.budget_usd:.2f} ({pct:.0f}% used)")
    click.echo(f"  Started:    {run.started_at}")
    click.echo(f"  Completed:  {run.completed_at}")
    click.echo(f"  Triggered:  {run.triggered_by}")

    if missions:
        # Step summary table
        click.echo()
        click.echo(click.style("  Steps:", fg="cyan"))
        click.echo(f"    {'Step':<20} {'Status':<12} {'Cost':>8}  {'Tasks':>5}  Objective")
        click.echo("    " + "-" * 90)

        for m in missions:
            task_count = len(m.mission_outcome.get("task_results", [])) if m.mission_outcome else 0
            click.echo(
                f"    {(m.playbook_step_id or '—'):<20} "
                f"{_styled_status(m.status, pad=12)} "
                f"${m.total_cost_usd:>7.4f}  "
                f"{task_count:>5}  "
                f"{m.objective[:50]}"
            )

        # Expanded task detail per step
        for m in missions:
            if not m.mission_outcome:
                continue
            task_results = m.mission_outcome.get("task_results", [])
            if not task_results:
                continue

            click.echo()
            click.echo(click.style(f"  Step: {m.playbook_step_id or m.id[:12]}", fg="cyan", bold=True))
            _render_task_table(task_results)

    _render_errors(run.error_data)


# =============================================================================
# Shared rendering helpers
# =============================================================================


def _render_outcome_tasks(outcome: dict | None) -> None:
    """Render task results and token usage from a mission outcome."""
    if not outcome:
        return

    task_results = outcome.get("task_results", [])
    if task_results:
        click.echo()
        click.echo(click.style("  Tasks:", fg="cyan"))
        _render_task_table(task_results)

    total_tokens = outcome.get("total_tokens", {})
    if total_tokens:
        click.echo()
        click.echo(click.style("  Token Usage:", fg="cyan"))
        click.echo(f"    Input:    {total_tokens.get('input', 0):,}")
        click.echo(f"    Output:   {total_tokens.get('output', 0):,}")
        click.echo(f"    Thinking: {total_tokens.get('thinking', 0):,}")


def _render_task_table(task_results: list[dict]) -> None:
    """Render task result rows with verification detail."""
    click.echo(f"    {'ID':<12} {'Agent':<28} {'Status':<10} {'Cost':>8}  {'Duration':>8}  Verification")
    click.echo("    " + "-" * 90)

    for t in task_results:
        status = t.get("status", "unknown")
        v = t.get("verification_outcome", {})
        click.echo(
            f"    {t.get('task_id', '—'):<12} "
            f"{t.get('agent_name', '—'):<28} "
            f"{click.style(status, fg='green' if status == 'success' else 'red'):<10} "
            f"${t.get('cost_usd', 0):>7.4f}  "
            f"{t.get('duration_seconds', 0):>7.1f}s  "
            f"T1:{v.get('tier_1', {}).get('status', '—')} "
            f"T2:{v.get('tier_2', {}).get('status', '—')} "
            f"T3:{v.get('tier_3', {}).get('status', '—')}"
        )

    # Expanded verification detail
    for t in task_results:
        _render_verification_detail(t)


def _render_verification_detail(t: dict) -> None:
    """Render expanded verification detail for a task."""
    v = t.get("verification_outcome", {})
    if not v:
        return
    task_id = t.get("task_id", "—")

    tier1 = v.get("tier_1", {})
    if tier1.get("status") not in ("skipped", None):
        details = tier1.get("details", "")
        if details:
            click.echo(f"    {task_id} Tier 1: {details}")

    tier2 = v.get("tier_2", {})
    if tier2.get("status") not in ("skipped", None):
        click.echo(f"    {task_id} Tier 2: {tier2.get('checks_passed', 0)}/{tier2.get('checks_run', 0)} checks passed")
        for fc in tier2.get("failed_checks", []):
            click.echo(f"      FAIL: {fc.get('check', '—')} — {fc.get('reason', '—')}")

    tier3 = v.get("tier_3", {})
    if tier3.get("status") not in ("skipped", None):
        click.echo(f"    {task_id} Tier 3: score {tier3.get('overall_score', 0):.2f} (${tier3.get('cost_usd', 0):.4f})")


def _render_errors(error_data: dict | None) -> None:
    """Render error section if present."""
    if error_data:
        click.echo()
        click.echo(click.style("  Errors:", fg="red"))
        click.echo(f"    {json_mod.dumps(error_data, indent=2, default=str)}")


def _status_str(status: Any) -> str:
    """Get string value from status (handles both str and enum)."""
    return status if isinstance(status, str) else status.value


def _styled_status(status: Any, pad: int = 0) -> str:
    """Return a click-styled status string."""
    val = _status_str(status)
    styled = click.style(val.upper(), fg="green" if val == "completed" else "red", bold=True)
    return f"{styled:<{pad}}" if pad else styled


# =============================================================================
# Data extraction — converts ORM objects to report-friendly dicts
# =============================================================================


def _mission_to_dict(mission: Any) -> dict:
    """Convert a Mission ORM object to a report-friendly dict."""
    data: dict[str, Any] = {
        "type": "mission",
        "id": mission.id,
        "objective": mission.objective,
        "status": _status_str(mission.status),
        "total_cost_usd": mission.total_cost_usd,
        "cost_ceiling_usd": mission.cost_ceiling_usd,
        "started_at": mission.started_at,
        "completed_at": mission.completed_at,
        "roster_ref": getattr(mission, "roster_ref", None),
    }

    if mission.mission_outcome:
        outcome = mission.mission_outcome
        data["task_results"] = _extract_task_summaries(outcome)
        data["total_tokens"] = outcome.get("total_tokens", {})

    if mission.error_data:
        data["errors"] = mission.error_data

    return data


def _playbook_run_to_dict(run: Any, missions: list[Any]) -> dict:
    """Convert a PlaybookRun + its missions to a report-friendly dict."""
    data: dict[str, Any] = {
        "type": "playbook_run",
        "id": run.id,
        "playbook_name": run.playbook_name,
        "playbook_version": run.playbook_version,
        "status": _status_str(run.status),
        "total_cost_usd": run.total_cost_usd,
        "budget_usd": run.budget_usd,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "triggered_by": run.triggered_by,
        "steps": [
            {**_mission_to_dict(m), "step_id": m.playbook_step_id}
            for m in missions
        ],
    }

    if run.error_data:
        data["errors"] = run.error_data

    return data


def _extract_task_summaries(outcome: dict) -> list[dict]:
    """Extract simplified task summaries from a mission outcome."""
    summaries = []
    for t in outcome.get("task_results", []):
        v = t.get("verification_outcome", {})
        summary: dict[str, Any] = {
            "task_id": t.get("task_id"),
            "agent_name": t.get("agent_name"),
            "status": t.get("status"),
            "cost_usd": t.get("cost_usd", 0),
            "duration_seconds": t.get("duration_seconds", 0),
            "verification": {
                "tier_1": v.get("tier_1", {}).get("status", "skipped"),
                "tier_2": v.get("tier_2", {}).get("status", "skipped"),
                "tier_3": v.get("tier_3", {}).get("status", "skipped"),
            },
        }

        output_ref = t.get("output_reference", {})
        if output_ref:
            summary["output"] = output_ref

        summaries.append(summary)
    return summaries


def _extract_findings(data: dict) -> list[str]:
    """Extract key findings from task outputs for fallback rendering."""
    findings = []

    task_sources = data.get("task_results", [])
    if not task_sources:
        for step in data.get("steps", []):
            task_sources.extend(step.get("task_results", []))

    for task in task_sources:
        output = task.get("output", {})
        if not isinstance(output, dict):
            continue

        summary = output.get("summary")
        if summary:
            findings.append(str(summary)[:200])

        violations = output.get("violations")
        if isinstance(violations, list):
            findings.append(f"{len(violations)} violation(s) found")

        findings_list = output.get("findings")
        if isinstance(findings_list, list):
            findings.append(f"{len(findings_list)} finding(s) reported")

    return findings
