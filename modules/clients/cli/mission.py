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
    output_format: str = "human",
) -> None:
    """Dispatch mission CLI actions."""
    actions = {
        "create": _action_create,
        "execute": _action_execute,
        "run": _action_run,
        "list": _action_list,
        "detail": _action_detail,
        "plan": _action_plan,
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
    from modules.clients.cli.report import render_mission
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
    from modules.clients.cli.report import render_mission
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
    from modules.clients.cli.report import get_console, build_table, styled_status
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

    from modules.clients.cli.report import (
        get_console, styled_status,
        primary_panel, info_panel, status_panel,
        render_task_outputs,
    )

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
    console.print(primary_panel(content="\n".join(info_lines), title="Mission Detail"))

    # Objective
    console.print(info_panel(content=mission.objective, title="Objective"))

    # Result summary
    if mission.result_summary:
        console.print(status_panel(content=mission.result_summary, status="completed", title="Result Summary"))

    # Task outputs — centralized renderer
    outcome = mission.mission_outcome
    if outcome and isinstance(outcome, dict):
        tasks = outcome.get("task_results") or outcome.get("task_outcomes") or []
        if tasks:
            render_task_outputs(console, tasks)

    # Error data
    if mission.error_data:
        console.print(status_panel(content=str(mission.error_data), status="failed", title="Error"))


async def _action_plan(cli_logger, *, objective, mission_id, roster, budget, triggered_by, output_format):
    """Show the TaskPlan DAG for a mission."""
    if not mission_id:
        click.echo(click.style("Error: --mission-id is required for plan.", fg="red"), err=True)
        raise _AbortMission("mission-id required")

    import json as _json

    from modules.clients.cli.report import (
        get_console, build_table, primary_panel, info_panel, styled_status,
    )
    from modules.backend.core.database import get_async_session
    from modules.backend.services.mission import MissionService

    async with get_async_session() as db:
        service = MissionService(session=db)
        try:
            mission = await service.get_mission(mission_id)
        except Exception:
            click.echo(click.style(f"Mission '{mission_id}' not found.", fg="red"), err=True)
            raise _AbortMission("mission not found")

    # Extract task_plan_reference from mission_outcome
    outcome = mission.mission_outcome
    if not outcome or not isinstance(outcome, dict):
        click.echo(click.style("No plan data — mission may not have been executed.", fg="yellow"))
        return

    plan_ref = outcome.get("task_plan_reference")
    if not plan_ref:
        click.echo(click.style("No task plan stored for this mission.", fg="yellow"))
        return

    # plan_ref is a JSON string — parse it
    plan = _json.loads(plan_ref) if isinstance(plan_ref, str) else plan_ref

    # Build lookup of execution results by task_id
    task_results = outcome.get("task_results") or outcome.get("task_outcomes") or []
    results_by_id = {r.get("task_id"): r for r in task_results if isinstance(r, dict)}

    console = get_console()

    # Header panel
    actual_cost = outcome.get("total_cost_usd", 0)
    actual_duration = outcome.get("total_duration_seconds", 0)
    info_lines = [
        f"[bold]Mission:[/bold]      {mission_id}",
        f"[bold]Status:[/bold]       {styled_status(outcome.get('status', '—'))}",
        f"[bold]Summary:[/bold]      {plan.get('summary', '—')}",
        f"[bold]Est. Cost:[/bold]    ${plan.get('estimated_cost_usd', 0):.4f}    [bold]Actual:[/bold] ${actual_cost:.4f}",
        f"[bold]Est. Duration:[/bold] {plan.get('estimated_duration_seconds', 0)}s      [bold]Actual:[/bold] {actual_duration:.1f}s",
        f"[bold]Version:[/bold]      {plan.get('version', '—')}",
    ]
    hints = plan.get("execution_hints", {})
    if hints.get("critical_path"):
        info_lines.append(f"[bold]Critical Path:[/bold] {', '.join(hints['critical_path'])}")
    if hints.get("min_success_threshold"):
        info_lines.append(f"[bold]Min Success:[/bold]  {hints['min_success_threshold']:.0%}")

    console.print(primary_panel(content="\n".join(info_lines), title="Task Plan"))

    # Tasks table — DAG view joined with execution results
    tasks = plan.get("tasks", [])
    if tasks:
        def _tier_icon(verification_outcome: dict, tier: str) -> str:
            tier_data = verification_outcome.get(tier, {})
            status = tier_data.get("status", "skipped")
            if status == "pass":
                return "[green]✓[/green]"
            elif status == "fail":
                return "[red]✗[/red]"
            return "[dim]—[/dim]"

        table = build_table(f"Tasks ({len(tasks)})", columns=[
            ("Task ID",      {"style": "cyan", "width": 20}),
            ("Agent",        {"width": 28}),
            ("Status",       {"width": 10}),
            ("Cost",         {"justify": "right", "width": 10}),
            ("Duration",     {"justify": "right", "width": 10}),
            ("Retries",      {"justify": "right", "width": 8}),
            ("T1",           {"justify": "center", "width": 4}),
            ("T2",           {"justify": "center", "width": 4}),
            ("T3",           {"justify": "center", "width": 4}),
            ("Dependencies", {"style": "dim", "width": 20}),
        ], show_lines=True)

        for t in tasks:
            tid = t.get("task_id", "—")
            deps = ", ".join(t.get("dependencies", []))
            result = results_by_id.get(tid, {})
            verification = result.get("verification_outcome", {})

            table.add_row(
                tid,
                t.get("agent", "—"),
                styled_status(result.get("status", "—")),
                f"${result.get('cost_usd', 0):.4f}" if result else "—",
                f"{result.get('duration_seconds', 0):.1f}s" if result else "—",
                str(result.get("retry_count", 0)) if result else "—",
                _tier_icon(verification, "tier_1"),
                _tier_icon(verification, "tier_2"),
                _tier_icon(verification, "tier_3"),
                deps or "—",
            )
        console.print(table)

    # Per-task detail panels
    for t in tasks:
        tid = t.get("task_id", "—")
        plan_verification = t.get("verification", {})
        inputs = t.get("inputs", {})
        result = results_by_id.get(tid, {})

        detail_lines = [
            f"[bold]Agent:[/bold]    {t.get('agent', '—')} v{t.get('agent_version', '?')}",
        ]

        # Static inputs
        static = inputs.get("static", {})
        if static:
            detail_lines.append(f"[bold]Inputs:[/bold]   {_json.dumps(static, default=str)[:120]}")

        # Upstream references
        upstream = inputs.get("from_upstream", {})
        if upstream:
            refs = [f"{k} ← {v.get('source_task', '?')}.{v.get('source_field', '?')}" for k, v in upstream.items()]
            detail_lines.append(f"[bold]Upstream:[/bold] {', '.join(refs)}")

        # Planned verification tiers
        t1 = plan_verification.get("tier_1", {})
        t2 = plan_verification.get("tier_2", {})
        t3 = plan_verification.get("tier_3", {})
        if t1.get("required_output_fields"):
            detail_lines.append(f"[bold]T1 Fields:[/bold] {', '.join(t1['required_output_fields'])}")
        if t2.get("deterministic_checks"):
            checks = [c.get("check") for c in t2["deterministic_checks"]]
            detail_lines.append(f"[bold]T2 Checks:[/bold] {', '.join(checks)}")
        if t3.get("requires_ai_evaluation"):
            detail_lines.append(f"[bold]T3 Eval:[/bold]  {t3.get('evaluator_agent', '—')} (min: {t3.get('min_evaluation_score', '—')})")

        # Retry history from execution
        retry_history = result.get("retry_history", [])
        if retry_history:
            detail_lines.append("")
            detail_lines.append("[bold]Retry History:[/bold]")
            for entry in retry_history:
                tier = entry.get("failure_tier", "?")
                reason = entry.get("failure_reason", "")[:80]
                detail_lines.append(f"  Attempt {entry.get('attempt', '?')} — Tier {tier}: {reason}")

        console.print(info_panel(content="\n".join(detail_lines), title=tid))

    console.print()


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

    from modules.clients.cli.report import get_console, build_table, primary_panel

    console = get_console()

    info_lines = [
        f"[bold]Mission:[/bold]       {breakdown.mission_id}",
        f"[bold]Total Cost:[/bold]    ${breakdown.total_cost_usd:.4f}",
        f"[bold]Input Tokens:[/bold]  {breakdown.total_input_tokens:,}",
        f"[bold]Output Tokens:[/bold] {breakdown.total_output_tokens:,}",
    ]
    console.print(primary_panel(content="\n".join(info_lines), title="Cost Breakdown"))

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


