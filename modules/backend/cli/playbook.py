"""
CLI handler for playbook commands.

List available playbooks, execute playbook runs, inspect results,
and render reports in multiple output formats.
"""

import asyncio
import sys

import click

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def run_playbook_cli(
    cli_logger,
    action: str,
    playbook_name: str | None,
    run_id: str | None,
    triggered_by: str,
    output_format: str = "summary",
) -> None:
    """Dispatch playbook CLI actions."""
    actions = {
        "list": _action_list,
        "detail": _action_detail,
        "run": _action_run,
        "runs": _action_runs,
        "run-detail": _action_run_detail,
        "report": _action_report,
    }

    handler = actions.get(action)
    if not handler:
        click.echo(
            click.style(
                f"Unknown playbook action: {action}. "
                f"Valid: {', '.join(actions.keys())}",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    try:
        asyncio.run(handler(
            cli_logger,
            playbook_name=playbook_name,
            run_id=run_id,
            triggered_by=triggered_by,
            output_format=output_format,
        ))
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        cli_logger.error(
            "Playbook action failed",
            extra={"action": action, "error": str(e)},
        )
        sys.exit(1)


# =============================================================================
# Actions
# =============================================================================


async def _action_list(cli_logger, *, playbook_name, run_id, triggered_by, output_format):
    """List available playbooks."""
    from rich.console import Console
    from rich.table import Table

    from modules.backend.services.playbook import PlaybookService

    service = PlaybookService()
    playbooks = service.list_playbooks(enabled_only=False)

    if not playbooks:
        click.echo("No playbooks found.")
        return

    console = Console(width=140)
    table = Table(title=f"Playbooks ({len(playbooks)} available)", show_lines=False, expand=True)
    table.add_column("Name", style="cyan", no_wrap=True, width=36)
    table.add_column("Ver", justify="right", no_wrap=True, width=4)
    table.add_column("Enabled", no_wrap=True, width=8)
    table.add_column("Budget", justify="right", no_wrap=True, width=8)
    table.add_column("Steps", justify="right", no_wrap=True, width=6)
    table.add_column("Description", no_wrap=True, ratio=1)

    for p in playbooks:
        enabled = "[green]yes[/green]" if p.enabled else "[red]no[/red]"
        table.add_row(
            p.playbook_name,
            str(p.version),
            enabled,
            f"${p.budget.max_cost_usd:.2f}",
            str(len(p.steps)),
            p.description[:80],
        )

    console.print(table)


async def _action_detail(cli_logger, *, playbook_name, run_id, triggered_by, output_format):
    """Show playbook detail."""
    if not playbook_name:
        click.echo(click.style("Error: playbook name is required for detail.", fg="red"), err=True)
        sys.exit(1)

    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from modules.backend.services.playbook import PlaybookService

    service = PlaybookService()
    playbook = service.get_playbook(playbook_name)

    if not playbook:
        click.echo(click.style(f"Playbook '{playbook_name}' not found.", fg="red"), err=True)
        sys.exit(1)

    console = Console(width=140)

    # Header panel
    enabled_str = "[green]yes[/green]" if playbook.enabled else "[red]no[/red]"
    info_lines = [
        f"[bold]Name:[/bold]        {playbook.playbook_name}",
        f"[bold]Description:[/bold] {playbook.description}",
        f"[bold]Version:[/bold]     {playbook.version}",
        f"[bold]Enabled:[/bold]     {enabled_str}",
        f"[bold]Trigger:[/bold]     {playbook.trigger.type}",
        f"[bold]Budget:[/bold]      ${playbook.budget.max_cost_usd:.2f}",
    ]
    console.print(Panel("\n".join(info_lines), title="Playbook Detail", border_style="cyan"))

    # Objective panel
    obj_lines = [
        f"[bold]Statement:[/bold] {playbook.objective.statement}",
        f"[bold]Category:[/bold]  {playbook.objective.category}",
        f"[bold]Owner:[/bold]     {playbook.objective.owner}",
        f"[bold]Priority:[/bold]  {playbook.objective.priority}",
    ]
    if playbook.trigger.match_patterns:
        obj_lines.append(f"[bold]Triggers:[/bold]  {', '.join(playbook.trigger.match_patterns)}")
    console.print(Panel("\n".join(obj_lines), title="Objective", border_style="dim"))

    # Context panel
    if playbook.context:
        ctx_lines = [f"[bold]{k}:[/bold] {v}" for k, v in playbook.context.items()]
        console.print(Panel("\n".join(ctx_lines), title="Context", border_style="dim"))

    # Steps table
    table = Table(title="Steps", expand=True, show_lines=True)
    table.add_column("ID", style="cyan", no_wrap=True, width=20)
    table.add_column("Capability", no_wrap=True, width=28)
    table.add_column("Budget", justify="right", no_wrap=True, width=8)
    table.add_column("Env", no_wrap=True, width=10)
    table.add_column("Depends On", style="dim", no_wrap=True, width=20)
    table.add_column("Description", ratio=1)

    for step in playbook.steps:
        ceiling = f"${step.cost_ceiling_usd:.2f}" if step.cost_ceiling_usd else "default"
        deps = ", ".join(step.depends_on) if step.depends_on else ""
        table.add_row(
            step.id,
            step.capability,
            ceiling,
            step.environment,
            deps,
            step.description or "",
        )

    console.print(table)


async def _action_run(cli_logger, *, playbook_name, run_id, triggered_by, output_format):
    """Execute a playbook."""
    if not playbook_name:
        click.echo(click.style("Error: --playbook-name is required for run.", fg="red"), err=True)
        sys.exit(1)

    await _preflight_gate(playbook_name)

    from modules.backend.core.database import get_async_session
    from modules.backend.agents.mission_control.dispatch_adapter import (
        MissionControlDispatchAdapter,
    )
    from modules.backend.cli.report import render_playbook_run
    from modules.backend.services.mission import MissionService
    from modules.backend.services.playbook_run import PlaybookRunService
    from modules.backend.services.session import SessionService

    click.echo(f"Running playbook: {playbook_name}")
    click.echo()

    async with get_async_session() as db:
        session_service = SessionService(db)
        adapter = MissionControlDispatchAdapter(
            session_service=session_service,
            db_session=db,
        )
        mission_service = MissionService(
            session=db,
            mission_control_dispatch=adapter,
            session_service=session_service,
        )
        run_service = PlaybookRunService(
            session=db,
            mission_service=mission_service,
        )

        run = await run_service.run_playbook(
            playbook_name=playbook_name,
            triggered_by=triggered_by,
        )

        # Fetch missions for report rendering
        missions, _ = await mission_service.list_missions(
            playbook_run_id=run.id,
        )
        await db.commit()

    await render_playbook_run(run, missions, output_format)


async def _action_runs(cli_logger, *, playbook_name, run_id, triggered_by, output_format):
    """List playbook runs."""
    from rich.console import Console
    from rich.table import Table

    from modules.backend.core.database import get_async_session
    from modules.backend.services.playbook_run import PlaybookRunService
    from modules.backend.services.mission import MissionService

    async with get_async_session() as db:
        mission_service = MissionService(session=db)
        run_service = PlaybookRunService(
            session=db,
            mission_service=mission_service,
        )
        runs, total = await run_service.list_runs(
            playbook_name=playbook_name,
            limit=20,
        )

    if not runs:
        click.echo("No playbook runs found.")
        return

    console = Console(width=140)
    table = Table(title=f"Playbook Runs ({total} total)", show_lines=False, expand=True)
    table.add_column("Date/Time", style="dim", no_wrap=True, width=16)
    table.add_column("ID", style="cyan", no_wrap=True, width=36)
    table.add_column("Playbook", no_wrap=True, width=24)
    table.add_column("Status", no_wrap=True, width=10)
    table.add_column("Cost", justify="right", no_wrap=True, width=8)
    table.add_column("Trigger", style="dim", no_wrap=True, width=10)
    table.add_column("Summary", no_wrap=True, ratio=1)

    for r in runs:
        status_val = r.status.value if hasattr(r.status, "value") else str(r.status)
        if status_val == "completed":
            status_str = f"[green]{status_val}[/green]"
        elif status_val == "failed":
            status_str = f"[red]{status_val}[/red]"
        elif status_val in ("running", "pending"):
            status_str = f"[yellow]{status_val}[/yellow]"
        else:
            status_str = status_val
        dt_str = r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "—"
        raw_summary = r.result_summary or ""
        summary = raw_summary[:80] + "..." if len(raw_summary) > 80 else raw_summary
        table.add_row(
            dt_str,
            str(r.id),
            r.playbook_name,
            status_str,
            f"${r.total_cost_usd:.4f}",
            r.triggered_by,
            summary,
        )

    console.print(table)


async def _action_run_detail(cli_logger, *, playbook_name, run_id, triggered_by, output_format):
    """Show playbook run detail with missions — uses the report renderer."""
    if not run_id:
        click.echo(click.style("Error: --run-id is required for run-detail.", fg="red"), err=True)
        sys.exit(1)

    run, missions = await _load_run_with_missions(run_id)
    from modules.backend.cli.report import render_playbook_run
    await render_playbook_run_async(run, missions, "detail")


async def _action_report(cli_logger, *, playbook_name, run_id, triggered_by, output_format):
    """Render a report for a past playbook run in the requested format."""
    if not run_id:
        click.echo(click.style("Error: --run-id is required for report.", fg="red"), err=True)
        sys.exit(1)

    run, missions = await _load_run_with_missions(run_id)
    from modules.backend.cli.report import render_playbook_run
    await render_playbook_run(run, missions, output_format)


# =============================================================================
# Helpers
# =============================================================================


async def _preflight_gate(playbook_name: str) -> None:
    """Run preflight credit check using rosters referenced by the playbook."""
    from modules.backend.agents.preflight import preflight_check
    from modules.backend.services.playbook import PlaybookService

    service = PlaybookService()
    playbook = service.get_playbook(playbook_name)
    if not playbook:
        return  # let the run action handle the missing playbook error

    # Collect unique rosters from playbook steps
    rosters = {step.roster for step in playbook.steps if step.roster}
    if not rosters:
        rosters = {"default"}

    click.echo("Preflight credit check...")
    for roster_name in sorted(rosters):
        result = await preflight_check(roster_name=roster_name)
        if result.ok:
            click.echo(click.style(f"  All models OK (roster: {roster_name})", fg="green"))
        else:
            for check in result.failed:
                label = "insufficient credits" if check.error_type == "insufficient_credits" else check.error
                click.echo(click.style(f"  ✗ {check.model_name}: {label}", fg="red"))
            click.echo()
            click.echo(click.style("Aborting — fix credit issues before running.", fg="red"), err=True)
            sys.exit(1)
    click.echo()


async def _load_run_with_missions(run_id: str):
    """Load a playbook run and its missions from the database."""
    from modules.backend.core.database import get_async_session
    from modules.backend.services.mission import MissionService
    from modules.backend.services.playbook_run import PlaybookRunService

    async with get_async_session() as db:
        mission_service = MissionService(session=db)
        run_service = PlaybookRunService(
            session=db,
            mission_service=mission_service,
        )
        run = await run_service.get_run(run_id)
        if not run:
            click.echo(click.style(f"Playbook run '{run_id}' not found.", fg="red"), err=True)
            sys.exit(1)

        missions, _ = await mission_service.list_missions(
            playbook_run_id=run.id,
        )

    return run, missions
