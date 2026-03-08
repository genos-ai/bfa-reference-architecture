"""
CLI handler for --service playbook.

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
    from modules.backend.services.playbook import PlaybookService

    service = PlaybookService()
    playbooks = service.list_playbooks(enabled_only=False)

    if not playbooks:
        click.echo("No playbooks found.")
        return

    click.echo(click.style("Available Playbooks:", fg="cyan", bold=True))
    click.echo(f"  {'Name':<36} {'Ver':>3}  {'Enabled':<8} {'Budget':>8}  {'Steps':>5}  Description")
    click.echo("  " + "-" * 110)

    for p in playbooks:
        enabled_str = click.style("yes", fg="green") if p.enabled else click.style("no", fg="red")
        click.echo(
            f"  {p.playbook_name:<36} {p.version:>3}  {enabled_str:<8} "
            f"${p.budget.max_cost_usd:>7.2f}  {len(p.steps):>5}  "
            f"{p.description[:50]}"
        )


async def _action_detail(cli_logger, *, playbook_name, run_id, triggered_by, output_format):
    """Show playbook detail."""
    if not playbook_name:
        click.echo(click.style("Error: --playbook-name is required for detail.", fg="red"), err=True)
        sys.exit(1)

    from modules.backend.services.playbook import PlaybookService

    service = PlaybookService()
    playbook = service.get_playbook(playbook_name)

    if not playbook:
        click.echo(click.style(f"Playbook '{playbook_name}' not found.", fg="red"), err=True)
        sys.exit(1)

    click.echo(click.style(f"Playbook: {playbook.playbook_name}", fg="cyan", bold=True))
    click.echo(f"  Description: {playbook.description}")
    click.echo(f"  Version:     {playbook.version}")
    click.echo(f"  Enabled:     {playbook.enabled}")
    click.echo(f"  Trigger:     {playbook.trigger.type}")
    click.echo(f"  Budget:      ${playbook.budget.max_cost_usd:.2f}")
    click.echo()

    click.echo(click.style("  Objective:", fg="cyan"))
    click.echo(f"    Statement: {playbook.objective.statement}")
    click.echo(f"    Category:  {playbook.objective.category}")
    click.echo(f"    Owner:     {playbook.objective.owner}")
    click.echo(f"    Priority:  {playbook.objective.priority}")
    click.echo()

    if playbook.trigger.match_patterns:
        click.echo(click.style("  Trigger Patterns:", fg="cyan"))
        for pattern in playbook.trigger.match_patterns:
            click.echo(f"    - {pattern}")
        click.echo()

    if playbook.context:
        click.echo(click.style("  Context:", fg="cyan"))
        for key, value in playbook.context.items():
            click.echo(f"    {key}: {value}")
        click.echo()

    click.echo(click.style("  Steps:", fg="cyan"))
    for step in playbook.steps:
        deps = f" (depends_on: {', '.join(step.depends_on)})" if step.depends_on else ""
        ceiling = f"${step.cost_ceiling_usd:.2f}" if step.cost_ceiling_usd else "default"
        click.echo(
            f"    {step.id:<20} {step.capability:<24} "
            f"budget: {ceiling:<10} {step.environment}{deps}"
        )
        if step.description:
            click.echo(f"      {click.style(step.description, dim=True)}")


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

    click.echo(f"Playbook Runs ({total} total):")
    click.echo(f"  {'ID':<38} {'Status':<12} {'Cost':>8}  {'Playbook':<36} Trigger")
    click.echo("  " + "-" * 110)

    for r in runs:
        status_val = r.status if isinstance(r.status, str) else r.status.value
        cost_str = f"${r.total_cost_usd:.4f}"
        click.echo(
            f"  {r.id:<38} {status_val:<12} {cost_str:>8}  "
            f"{r.playbook_name:<36} {r.triggered_by}"
        )


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
