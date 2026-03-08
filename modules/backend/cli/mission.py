"""
CLI handler for --service mission.

Full mission lifecycle: create, execute, list, detail, cost.
All operations go through proper service layers with real DB persistence.
"""

import asyncio
import sys

import click

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class _AbortMission(Exception):
    """Raised by async actions to signal a clean exit (output already printed)."""
    pass


def run_mission(
    cli_logger,
    action: str,
    objective: str | None,
    mission_id: str | None,
    roster: str,
    budget: float | None,
    triggered_by: str,
    output_format: str = "summary",
) -> None:
    """Dispatch mission CLI actions."""
    actions = {
        "create": _action_create,
        "execute": _action_execute,
        "run": _action_run,
        "list": _action_list,
        "detail": _action_detail,
        "cost": _action_cost,
    }

    handler = actions.get(action)
    if not handler:
        click.echo(
            click.style(
                f"Unknown mission action: {action}. "
                f"Valid: {', '.join(actions.keys())}",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    try:
        asyncio.run(handler(
            cli_logger,
            objective=objective,
            mission_id=mission_id,
            roster=roster,
            budget=budget,
            triggered_by=triggered_by,
            output_format=output_format,
        ))
    except _AbortMission:
        # Output already printed by the async action — just exit.
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        cli_logger.error("Mission action failed", extra={"action": action, "error": str(e)})
        sys.exit(1)


# =============================================================================
# Actions
# =============================================================================


async def _action_create(cli_logger, *, objective, mission_id, roster, budget, triggered_by, output_format):
    """Create a mission (PENDING state)."""
    if not objective:
        click.echo(click.style("Error: --objective is required for create.", fg="red"), err=True)
        raise _AbortMission("objective required")

    from modules.backend.core.database import get_async_session
    from modules.backend.services.mission import MissionService

    async with get_async_session() as db:
        service = MissionService(session=db)
        mission = await service.create_adhoc_mission(
            objective=objective,
            triggered_by=triggered_by,
            session_id=_generate_session_id(),
            roster_ref=roster,
            cost_ceiling_usd=budget,
        )
        await db.commit()

    click.echo(click.style("Mission created", fg="green", bold=True))
    click.echo(f"  ID:        {mission.id}")
    click.echo(f"  Status:    {mission.status.value}")
    click.echo(f"  Roster:    {mission.roster_ref}")
    click.echo(f"  Budget:    ${mission.cost_ceiling_usd:.2f}" if mission.cost_ceiling_usd else "  Budget:    default")
    click.echo(f"  Objective: {mission.objective[:100]}")
    click.echo()
    click.echo(f"Execute with: python cli.py --service mission --mission-action execute --mission-id {mission.id}")


async def _action_execute(cli_logger, *, objective, mission_id, roster, budget, triggered_by, output_format):
    """Execute an existing mission (PENDING → RUNNING → COMPLETED)."""
    if not mission_id:
        click.echo(click.style("Error: --mission-id is required for execute.", fg="red"), err=True)
        raise _AbortMission("mission-id required")

    await _preflight_gate(roster)

    from modules.backend.core.database import get_async_session
    from modules.backend.agents.mission_control.dispatch_adapter import (
        MissionControlDispatchAdapter,
    )
    from modules.backend.cli.report import render_mission
    from modules.backend.services.mission import MissionService
    from modules.backend.services.session import SessionService

    click.echo(f"Executing mission {mission_id}...")
    click.echo()

    async with get_async_session() as db:
        session_service = SessionService(db)
        adapter = MissionControlDispatchAdapter(
            session_service=session_service,
            db_session=db,
        )
        service = MissionService(
            session=db,
            mission_control_dispatch=adapter,
            session_service=session_service,
        )

        mission = await service.execute_mission(mission_id)
        await db.commit()

    await render_mission(mission, output_format)


async def _action_run(cli_logger, *, objective, mission_id, roster, budget, triggered_by, output_format):
    """Create + execute in one step (convenience)."""
    if not objective:
        click.echo(click.style("Error: --objective is required for run.", fg="red"), err=True)
        raise _AbortMission("objective required")

    await _preflight_gate(roster)

    from modules.backend.core.database import get_async_session
    from modules.backend.agents.mission_control.dispatch_adapter import (
        MissionControlDispatchAdapter,
    )
    from modules.backend.cli.report import render_mission
    from modules.backend.services.mission import MissionService
    from modules.backend.services.session import SessionService

    click.echo("Creating and executing mission...")
    click.echo()

    async with get_async_session() as db:
        session_service = SessionService(db)
        adapter = MissionControlDispatchAdapter(
            session_service=session_service,
            db_session=db,
        )
        service = MissionService(
            session=db,
            mission_control_dispatch=adapter,
            session_service=session_service,
        )

        mission = await service.create_adhoc_mission(
            objective=objective,
            triggered_by=triggered_by,
            session_id=_generate_session_id(),
            roster_ref=roster,
            cost_ceiling_usd=budget,
        )
        click.echo(f"  Mission ID: {mission.id}")

        mission = await service.execute_mission(mission.id)
        await db.commit()

    await render_mission(mission, output_format)


async def _action_list(cli_logger, *, objective, mission_id, roster, budget, triggered_by, output_format):
    """List missions."""
    from modules.backend.cli.report import get_console, build_table, styled_status
    from modules.backend.core.database import get_async_session
    from modules.backend.services.mission import MissionService

    async with get_async_session() as db:
        service = MissionService(session=db)
        missions, total = await service.list_missions(limit=20)

    if not missions:
        click.echo("No missions found.")
        return

    console = get_console()
    table = build_table(f"Missions ({total} total)", columns=[
        ("Date/Time",  {"style": "dim", "width": 16}),
        ("ID",         {"style": "cyan", "width": 36}),
        ("Status",     {"width": 10}),
        ("Cost",       {"justify": "right", "width": 8}),
        ("Trigger",    {"style": "dim", "width": 12}),
        ("Objective",  {"ratio": 1}),
    ])

    for m in missions:
        obj_preview = m.objective[:60] + "..." if len(m.objective) > 60 else m.objective
        dt_str = m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "—"
        table.add_row(
            dt_str, str(m.id), styled_status(m.status),
            f"${m.total_cost_usd:.4f}", m.triggered_by, obj_preview,
        )

    console.print(table)


async def _action_detail(cli_logger, *, objective, mission_id, roster, budget, triggered_by, output_format):
    """Show mission detail."""
    if not mission_id:
        click.echo(click.style("Error: --mission-id is required for detail.", fg="red"), err=True)
        raise _AbortMission("mission-id required")

    from modules.backend.cli.report import (
        get_console, build_table, styled_status,
        primary_panel, info_panel, severity_color,
    )
    from rich.panel import Panel

    from modules.backend.core.database import get_async_session
    from modules.backend.services.mission import MissionService

    async with get_async_session() as db:
        service = MissionService(session=db)
        try:
            mission = await service.get_mission(mission_id)
        except Exception:
            click.echo(click.style(f"Mission '{mission_id}' not found.", fg="red"), err=True)
            raise _AbortMission("mission not found")

    console = get_console()

    # Header info
    info_lines = [
        f"[bold]ID:[/bold]        {mission.id}",
        f"[bold]Status:[/bold]    {styled_status(mission.status)}",
        f"[bold]Created:[/bold]   {mission.created_at.strftime('%Y-%m-%d %H:%M:%S') if mission.created_at else '—'}",
        f"[bold]Started:[/bold]   {mission.started_at or '—'}",
        f"[bold]Finished:[/bold]  {mission.completed_at or '—'}",
        f"[bold]Roster:[/bold]    {mission.roster_ref}",
        f"[bold]Cost:[/bold]      ${mission.total_cost_usd:.4f}" + (f"  (ceiling: ${mission.cost_ceiling_usd:.2f})" if mission.cost_ceiling_usd else ""),
        f"[bold]Trigger:[/bold]   {mission.triggered_by}",
        f"[bold]Session:[/bold]   {mission.session_id}",
    ]
    console.print(primary_panel("\n".join(info_lines), title="Mission Detail"))

    # Objective
    console.print(info_panel(mission.objective, title="Objective"))

    # Result summary
    if mission.result_summary:
        console.print(Panel(mission.result_summary, title="Result Summary", border_style="green"))

    # Mission outcome (task-level breakdown)
    outcome = mission.mission_outcome
    if outcome and isinstance(outcome, dict):
        tasks = outcome.get("task_results") or outcome.get("task_outcomes") or []
        if tasks:
            table = build_table("Task Outcomes", columns=[
                ("Task",     {"style": "cyan", "width": 12}),
                ("Agent",    {"width": 28}),
                ("Status",   {"width": 10}),
                ("Cost",     {"justify": "right", "width": 8}),
                ("Duration", {"justify": "right", "width": 10}),
                ("Summary",  {"ratio": 1}),
            ], show_lines=True)

            for t in tasks:
                t_status = str(t.get("status", "—"))
                cost = f"${t['cost_usd']:.4f}" if "cost_usd" in t else "—"
                dur = f"{t['duration_seconds']:.1f}s" if "duration_seconds" in t else "—"
                out_ref = t.get("output_reference") or {}
                summary = out_ref.get("summary", "") if isinstance(out_ref, dict) else str(out_ref)
                if not summary:
                    summary = t.get("summary", t.get("result_summary", ""))
                if len(summary) > 120:
                    summary = summary[:120] + "..."
                table.add_row(
                    t.get("task_id", "—"),
                    t.get("agent_name", "—"),
                    styled_status(t_status),
                    cost,
                    dur,
                    summary,
                )
            console.print(table)

    # Full task outputs (when -o detail or -o json)
    if output_format in ("detail", "json") and outcome and isinstance(outcome, dict):
        tasks = outcome.get("task_results") or outcome.get("task_outcomes") or []
        for t in tasks:
            task_id = t.get("task_id", "—")
            agent = t.get("agent_name", "—")
            out_ref = t.get("output_reference") or {}
            if not isinstance(out_ref, dict):
                out_ref = {"raw": str(out_ref)}

            if output_format == "json":
                import json
                console.print(primary_panel(
                    json.dumps(out_ref, indent=2, default=str),
                    title=f"{task_id} / {agent}",
                ))
            else:
                # Render structured findings nicely
                lines: list[str] = []
                summary = out_ref.get("summary", "")
                if summary:
                    lines.append(f"[bold]Summary:[/bold] {summary}")
                    lines.append("")

                findings = out_ref.get("findings") or out_ref.get("violations") or []
                for f in findings:
                    if isinstance(f, dict):
                        sev = f.get("severity", f.get("principle", ""))
                        file_ = f.get("file", "")
                        line_ = f.get("line", "")
                        msg = f.get("message", f.get("details", ""))
                        loc = f"[dim]{file_}:{line_}[/dim]" if file_ else ""
                        sev_color = severity_color(sev)
                        lines.append(f"  [{sev_color}]{sev}[/{sev_color}]  {loc}  {msg}")
                        rec = f.get("recommendation", "")
                        if rec:
                            lines.append(f"         [dim]{rec}[/dim]")
                    else:
                        lines.append(f"  {f}")

                # Stats line
                stats = []
                for key in ("total_findings", "total_violations", "error_count", "warning_count",
                            "scanned_files_count", "files_reviewed", "overall_status", "checks_performed"):
                    val = out_ref.get(key)
                    if val is not None:
                        label = key.replace("_", " ")
                        stats.append(f"{label}: {val}")
                if stats:
                    lines.append("")
                    lines.append("[dim]" + " | ".join(stats) + "[/dim]")

                content = "\n".join(lines) if lines else str(out_ref)
                console.print(primary_panel(content, title=f"{task_id} / {agent}"))

    # Error data
    if mission.error_data:
        console.print(Panel(str(mission.error_data), title="Error", border_style="red"))


async def _action_cost(cli_logger, *, objective, mission_id, roster, budget, triggered_by, output_format):
    """Show mission cost breakdown."""
    if not mission_id:
        click.echo(click.style("Error: --mission-id is required for cost.", fg="red"), err=True)
        raise _AbortMission("mission-id required")

    from modules.backend.core.database import get_async_session
    from modules.backend.services.mission_persistence import MissionPersistenceService

    async with get_async_session() as db:
        service = MissionPersistenceService(db)
        breakdown = await service.get_cost_breakdown(mission_id)

    from modules.backend.cli.report import get_console, build_table, primary_panel

    console = get_console()

    info_lines = [
        f"[bold]Mission:[/bold]       {breakdown.mission_id}",
        f"[bold]Total Cost:[/bold]    ${breakdown.total_cost_usd:.4f}",
        f"[bold]Input Tokens:[/bold]  {breakdown.total_input_tokens:,}",
        f"[bold]Output Tokens:[/bold] {breakdown.total_output_tokens:,}",
    ]
    console.print(primary_panel("\n".join(info_lines), title="Cost Breakdown"))

    if breakdown.task_costs:
        table = build_table("Task Costs", columns=[
            ("Task",     {"style": "cyan", "width": 12}),
            ("Agent",    {"width": 28}),
            ("Cost",     {"justify": "right", "width": 10}),
            ("Tokens",   {"justify": "right", "width": 14}),
            ("Duration", {"justify": "right", "width": 10}),
        ])
        for tc in breakdown.task_costs:
            tokens = f"{(tc.get('input_tokens') or 0) + (tc.get('output_tokens') or 0):,}"
            dur = f"{tc['duration_seconds']:.1f}s" if tc.get('duration_seconds') else "—"
            table.add_row(tc['task_id'], tc['agent_name'], f"${tc['cost_usd']:.4f}", tokens, dur)
        console.print(table)


# =============================================================================
# Helpers
# =============================================================================


def _generate_session_id() -> str:
    """Generate a session ID for CLI missions."""
    from uuid import uuid4
    return str(uuid4())


async def _preflight_gate(roster: str) -> None:
    """Run preflight credit check; abort if any model fails."""
    from modules.backend.agents.preflight import preflight_check

    click.echo("Preflight credit check...")
    result = await preflight_check(roster_name=roster)
    if result.ok:
        click.echo(click.style("  All models OK", fg="green"))
        click.echo()
        return

    for check in result.failed:
        label = "insufficient credits" if check.error_type == "insufficient_credits" else check.error
        click.echo(click.style(f"  ✗ {check.model_name}: {label}", fg="red"))
    click.echo()
    click.echo(click.style("Aborting — fix credit issues before running.", fg="red"), err=True)
    raise _AbortMission("preflight failed")


