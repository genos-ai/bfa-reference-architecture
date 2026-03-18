"""
CLI report renderer — AI narrative, dynamic table rendering, detail views.

Display primitives (console, tables, panels, status styling) live in
``modules.clients.common.display`` and are re-exported here for backwards
compatibility with existing CLI handlers.

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

# Re-export display primitives so existing CLI files don't need changes yet.
from modules.clients.common.display import (
    DOTTED_ROWS,
    OUTPUT_FORMATS,
    build_table,
    cost_line,
    format_json_body,
    get_console,
    info_panel,
    output_panel,
    primary_panel,
    severity_color,
    status_color,
    status_panel,
    styled_status,
    summary_table,
    thinking_panel,
)

# Re-export severity internals used by _build_dynamic_table
from modules.clients.common.display import (
    SEVERITY_ORDER,
)

logger = get_logger(__name__)


# =============================================================================
# Human-friendly output — dynamic shape-detected rendering
# =============================================================================

# Known field styles — applied automatically when a field name matches.
_FIELD_STYLES: dict[str, dict[str, Any]] = {
    "severity":    {"width": 8},
    "status":      {"width": 10},
    "category":    {"style": "cyan", "width": 20},
    "type":        {"style": "cyan", "width": 16},
    "rule_id":     {"style": "cyan", "width": 24},
    "rule":        {"style": "cyan", "width": 24},
    "file":        {"style": "dim", "width": 44},
    "path":        {"style": "dim", "width": 44},
    "line":        {"justify": "right", "width": 5},
    "line_number": {"justify": "right", "width": 5},
    "name":        {"style": "cyan", "width": 30},
    "check":       {"style": "cyan", "width": 30},
}

_SKIP_FIELDS: set[str] = {"type", "id", "uuid"}

_FLEX_FIELDS: set[str] = {
    "message", "description", "detail", "details",
    "finding", "summary", "output", "value",
}


def render_task_outputs(
    console: Console,
    tasks: list[dict],
    *,
    title_prefix: str = "",
) -> None:
    """Render task output_reference dicts through the dynamic shape-detected renderer."""
    import json as _json

    for t in tasks:
        task_id = t.get("task_id", "—")
        agent = t.get("agent_name", "—")
        out_ref = t.get("output_reference") or {}
        if not isinstance(out_ref, dict):
            out_ref = {"raw": str(out_ref)}

        title_parts = [p for p in (title_prefix, task_id, agent) if p]
        title = " / ".join(title_parts)

        raw_json = _json.dumps(out_ref, indent=2, default=str)
        for renderable in render_human(raw_json, title=title):
            console.print(renderable)


def render_mission_outcomes(console: Console, missions: list[Any]) -> None:
    """Render per-mission task outputs."""
    if not missions:
        return

    for m in missions:
        prefix = getattr(m, "playbook_step_id", None) or str(m.id)[:12]
        outcome = m.mission_outcome if hasattr(m, "mission_outcome") else None
        if not outcome or not isinstance(outcome, dict):
            continue
        tasks = outcome.get("task_results") or outcome.get("task_outcomes") or []
        if not tasks:
            continue
        render_task_outputs(console, tasks, title_prefix=prefix)


def render_human(
    raw: str,
    *,
    title: str,
    subtitle: str | None = None,
    show_scalars: bool = False,
) -> list[Any]:
    """Parse agent output and return human-friendly Rich renderables."""
    import json as _json
    from rich.text import Text

    try:
        parsed = _json.loads(raw)
    except (_json.JSONDecodeError, TypeError):
        return [output_panel(Text(str(raw)), title=title, subtitle=subtitle)]

    if not isinstance(parsed, dict):
        return [output_panel(format_json_body(raw), title=title, subtitle=subtitle)]

    renderables: list[Any] = []

    summary_text = parsed.get("summary")
    if summary_text:
        renderables.append(info_panel(content=str(summary_text), title=title))

    list_key, items = _find_list_field(parsed)

    if items:
        table = _build_dynamic_table(items, list_key=list_key)
        renderables.append(table)
    elif not summary_text:
        return [output_panel(format_json_body(raw), title=title, subtitle=subtitle)]

    pqi = parsed.get("pqi")
    if isinstance(pqi, dict) and "composite" in pqi:
        renderables.append(_build_pqi_panel(pqi))

    if show_scalars:
        scalars = _extract_scalars(parsed)
        if scalars:
            renderables.append(_build_scalars_table(scalars))

    return renderables


def _find_list_field(parsed: dict) -> tuple[str, list[dict]]:
    """Find the first top-level field containing a non-empty list of dicts."""
    for key, val in parsed.items():
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return key, val
    return "", []


def _build_dynamic_table(items: list[dict], *, list_key: str) -> Table:
    """Build a Rich table by discovering columns from the data itself."""
    field_order: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in item:
            if key not in seen:
                seen.add(key)
                field_order.append(key)

    styled = [f for f in field_order if f in _FIELD_STYLES and f not in _SKIP_FIELDS and f not in _FLEX_FIELDS]
    plain = [f for f in field_order if f not in _FIELD_STYLES and f not in _SKIP_FIELDS and f not in _FLEX_FIELDS]
    flex = [f for f in field_order if f in _FLEX_FIELDS]

    def _has_data(field: str) -> bool:
        return any(
            item.get(field) not in (None, "", [])
            for item in items
            if isinstance(item, dict)
        )

    ordered = [f for f in styled + plain + flex if _has_data(f)]

    if not ordered:
        ordered = field_order[:5]

    columns: list[tuple[str, dict[str, Any]]] = [
        ("#", {"style": "dim", "width": 3, "justify": "right"}),
    ]
    for i, field in enumerate(ordered):
        header = field.replace("_", " ").title()
        kwargs: dict[str, Any] = {}

        if field in _FIELD_STYLES:
            kwargs = dict(_FIELD_STYLES[field])
        elif field in _FLEX_FIELDS or i == len(ordered) - 1:
            kwargs = {"ratio": 1, "no_wrap": False}
        else:
            kwargs = {"width": 24}

        columns.append((header, kwargs))

    table = build_table(
        f"{len(items)} {list_key}",
        columns=columns,
        show_lines=True,
        table_box=DOTTED_ROWS,
    )

    sort_field = next((f for f in ordered if f in ("severity", "priority", "status")), None)
    if sort_field:
        items = sorted(
            items,
            key=lambda x: SEVERITY_ORDER.get(str(x.get(sort_field, "")).lower(), 99),
        )

    row_num = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        row_num += 1
        row: list[str] = [str(row_num)]
        for field in ordered:
            val = item.get(field)
            if val is None:
                row.append("")
                continue
            val = str(val)
            if field == "severity" and val:
                color = severity_color(val)
                val = f"[{color}]{val.upper()}[/{color}]"
            elif field == "status" and val:
                val = styled_status(val)
            row.append(val)
        table.add_row(*row)

    return table


def _build_pqi_panel(pqi: dict) -> Panel:
    """Build a Rich panel showing the PQI composite score and per-dimension breakdown."""
    composite = pqi.get("composite", 0)
    band = pqi.get("quality_band", "?")
    file_count = pqi.get("file_count", 0)
    line_count = pqi.get("line_count", 0)

    band_colors = {
        "Excellent": "green", "Good": "cyan", "Adequate": "yellow",
        "Acceptable": "yellow", "Poor": "red",
    }
    color = band_colors.get(band, "white")

    bar_len = int(composite / 2.5)
    bar = "█" * bar_len + "░" * (40 - bar_len)

    lines: list[str] = []
    lines.append(f"  Composite Score:  [{color} bold]{composite:.1f} / 100[/{color} bold]  [{color}][{band}][/{color}]")
    lines.append(f"    [{color}]{bar}[/{color}] {composite:.1f}%")
    lines.append("")
    lines.append(f"  Files: {file_count}    Lines: {line_count:,}")

    dims = pqi.get("dimensions", {})
    if dims:
        lines.append("")
        lines.append("  ─" * 30)
        lines.append(f"  {'Dimension':<22s} {'Score':>5s}  Bar")
        lines.append("  ─" * 30)

        for name, dim in sorted(dims.items(), key=lambda x: -x[1].get("score", 0)):
            score = dim.get("score", 0)
            confidence = dim.get("confidence", 1.0)
            dim_bar_len = int(score / 5)
            dim_bar = "█" * dim_bar_len + "░" * (20 - dim_bar_len)
            conf_note = f" [dim](confidence: {confidence:.0%})[/dim]" if confidence < 0.8 else ""
            lines.append(f"  {name:<22s} {score:5.1f}  {dim_bar}{conf_note}")

            sub_scores = dim.get("sub_scores", {})
            for sub_name, sub_val in sub_scores.items():
                lines.append(f"    [dim]{sub_name:<20s} {sub_val:5.1f}[/dim]")

    body = "\n".join(lines)
    return Panel(
        body,
        title="[cyan bold]PyQuality Index (PQI)[/cyan bold]",
        border_style="cyan",
        padding=(1, 2),
    )


def _extract_scalars(parsed: dict) -> list[tuple[str, str]]:
    """Extract scalar summary fields as (label, value) pairs."""
    pairs: list[tuple[str, str]] = []
    for key, val in parsed.items():
        if isinstance(val, (list, dict)):
            continue
        if key == "summary":
            continue
        label = key.replace("_", " ").title()
        pairs.append((label, str(val)))
    return pairs


def _build_scalars_table(scalars: list[tuple[str, str]]) -> Table:
    """Horizontal stats table from scalar key-value pairs."""
    table = Table(
        show_header=True,
        box=DOTTED_ROWS,
        padding=(0, 2),
        expand=False,
    )
    for label, _val in scalars:
        table.add_column(label, style="dim", no_wrap=True)
    table.add_row(*(val for _label, val in scalars))
    return table


# =============================================================================
# Public report API — async only, called from async CLI handlers
# =============================================================================


async def render_mission(mission: Any, output_format: str = "human") -> None:
    """Render a single mission result."""
    if output_format == "jsonl":
        _emit_json(_mission_to_dict(mission))
    elif output_format == "human":
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
    output_format: str = "human",
) -> None:
    """Render a playbook run result."""
    if output_format == "jsonl":
        _emit_json(playbook_run_to_dict(run, missions))
    elif output_format == "human":
        _render_playbook_detail(run, missions)
    else:
        await _render_summary(
            title="Playbook Run Summary",
            status_line=(
                f"  {run.playbook_name} v{run.playbook_version}    "
                f"Status: {_styled_status(run.status)}    "
                f"Cost: ${run.total_cost_usd:.4f}"
            ),
            data=playbook_run_to_dict(run, missions),
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
    click.echo(await generate_narrative(data))


async def generate_narrative(data: dict) -> str:
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

_HEADING_STYLES: list[tuple[str, str]] = [
    (r"critical|error|failure", "bold red"),
    (r"warning|caution|degraded", "bold yellow"),
    (r"info|note|passed|success", "dim"),
]


def colorize_narrative(text: str) -> str:
    """Apply Rich markup to priority headings in a narrative."""
    lines = text.split("\n")
    result = []

    for line in lines:
        stripped = line.strip()
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
    console = get_console()

    info_lines = [
        f"[bold]ID:[/bold]        {mission.id}",
        f"[bold]Status:[/bold]    {styled_status(mission.status)}",
        f"[bold]Objective:[/bold] {mission.objective[:120]}",
        f"[bold]Cost:[/bold]      ${mission.total_cost_usd:.4f}"
        + (f"  (ceiling: ${mission.cost_ceiling_usd:.2f})" if mission.cost_ceiling_usd else ""),
        f"[bold]Started:[/bold]   {mission.started_at or '—'}",
        f"[bold]Completed:[/bold] {mission.completed_at or '—'}",
    ]
    console.print(primary_panel(content="\n".join(info_lines), title="Mission Report"))

    outcome = mission.mission_outcome
    if outcome and isinstance(outcome, dict):
        tasks = outcome.get("task_results") or outcome.get("task_outcomes") or []
        if tasks:
            render_task_outputs(console, tasks)

    _render_errors(mission.error_data)


def _render_playbook_detail(run: Any, missions: list[Any]) -> None:
    """Deterministic detailed view of a playbook run."""
    console = get_console()

    info_lines = [
        f"[bold]Playbook:[/bold]  {run.playbook_name} v{run.playbook_version}",
        f"[bold]Run ID:[/bold]    {run.id}",
        f"[bold]Status:[/bold]    {styled_status(run.status)}",
        f"[bold]Cost:[/bold]      ${run.total_cost_usd:.4f}"
        + (f"  ({(run.total_cost_usd / run.budget_usd) * 100:.0f}% of ${run.budget_usd:.2f} budget)" if run.budget_usd else ""),
        f"[bold]Started:[/bold]   {run.started_at or '—'}",
        f"[bold]Completed:[/bold] {run.completed_at or '—'}",
        f"[bold]Triggered:[/bold] {run.triggered_by}",
    ]
    console.print(primary_panel(content="\n".join(info_lines), title="Playbook Run Report"))

    render_mission_outcomes(console, missions)
    _render_errors(run.error_data)


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


def playbook_run_to_dict(run: Any, missions: list[Any]) -> dict:
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
