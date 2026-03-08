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
        sys.exit(1)

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
        sys.exit(1)

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
        sys.exit(1)

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
    from modules.backend.core.database import get_async_session
    from modules.backend.services.mission import MissionService

    async with get_async_session() as db:
        service = MissionService(session=db)
        missions, total = await service.list_missions(limit=20)

    if not missions:
        click.echo("No missions found.")
        return

    click.echo(f"Missions ({total} total):")
    click.echo(f"{'ID':<38} {'Status':<12} {'Cost':>8}  {'Trigger':<16} Objective")
    click.echo("-" * 110)

    for m in missions:
        obj_preview = m.objective[:40] + "..." if len(m.objective) > 40 else m.objective
        cost_str = f"${m.total_cost_usd:.4f}"
        click.echo(f"{m.id:<38} {m.status.value:<12} {cost_str:>8}  {m.triggered_by:<16} {obj_preview}")


async def _action_detail(cli_logger, *, objective, mission_id, roster, budget, triggered_by, output_format):
    """Show mission detail."""
    if not mission_id:
        click.echo(click.style("Error: --mission-id is required for detail.", fg="red"), err=True)
        sys.exit(1)

    from modules.backend.core.database import get_async_session
    from modules.backend.services.mission_persistence import MissionPersistenceService

    async with get_async_session() as db:
        service = MissionPersistenceService(db)
        record = await service.get_mission(mission_id)

        if not record:
            click.echo(click.style(f"Mission record '{mission_id}' not found.", fg="red"), err=True)
            sys.exit(1)

        # Also get task executions
        executions = await service.get_task_executions(mission_id)

    click.echo(click.style("Mission Record", fg="cyan", bold=True))
    click.echo(f"  ID:       {record.id}")
    click.echo(f"  Session:  {record.session_id}")
    click.echo(f"  Status:   {record.status.value}")
    click.echo(f"  Roster:   {record.roster_name}")
    click.echo(f"  Cost:     ${record.total_cost_usd:.4f}")
    click.echo(f"  Started:  {record.started_at}")
    click.echo(f"  Finished: {record.completed_at}")

    if executions:
        click.echo()
        click.echo(click.style("Task Executions:", fg="cyan"))
        for ex in executions:
            status_color = "green" if ex.status.value == "COMPLETED" else "red"
            click.echo(
                f"  {ex.task_id:<12} "
                f"{click.style(ex.agent_name, fg='cyan'):<40} "
                f"{click.style(ex.status.value, fg=status_color):<14} "
                f"${ex.cost_usd:.4f}  "
                f"{ex.duration_seconds:.1f}s"
            )


async def _action_cost(cli_logger, *, objective, mission_id, roster, budget, triggered_by, output_format):
    """Show mission cost breakdown."""
    if not mission_id:
        click.echo(click.style("Error: --mission-id is required for cost.", fg="red"), err=True)
        sys.exit(1)

    from modules.backend.core.database import get_async_session
    from modules.backend.services.mission_persistence import MissionPersistenceService

    async with get_async_session() as db:
        service = MissionPersistenceService(db)
        breakdown = await service.get_cost_breakdown(mission_id)

    click.echo(click.style("Cost Breakdown", fg="cyan", bold=True))
    click.echo(f"  Mission:       {breakdown.mission_id}")
    click.echo(f"  Total Cost:    ${breakdown.total_cost_usd:.4f}")
    click.echo(f"  Input Tokens:  {breakdown.total_input_tokens:,}")
    click.echo(f"  Output Tokens: {breakdown.total_output_tokens:,}")
    click.echo()

    if breakdown.task_costs:
        click.echo(f"  {'Task':<12} {'Agent':<28} {'Cost':>8}  {'Tokens':>12}  {'Duration':>8}")
        click.echo("  " + "-" * 80)
        for tc in breakdown.task_costs:
            tokens = f"{(tc.get('input_tokens') or 0) + (tc.get('output_tokens') or 0):,}"
            dur = f"{tc['duration_seconds']:.1f}s" if tc.get('duration_seconds') else "—"
            click.echo(f"  {tc['task_id']:<12} {tc['agent_name']:<28} ${tc['cost_usd']:>7.4f}  {tokens:>12}  {dur:>8}")


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
    sys.exit(1)


