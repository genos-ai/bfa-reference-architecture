"""
CLI handler for project commands.

Thin renderer over ProjectService. Handles create, list, detail, archive.
"""

import asyncio
import sys

from modules.clients.cli.report import get_console, build_table, DOTTED_ROWS, styled_status


def run_project(
    cli_logger,
    action: str,
    *,
    name: str | None = None,
    project_id: str | None = None,
    description: str | None = None,
    owner_id: str = "user:cli",
    roster: str = "default",
    budget: float | None = None,
    repo_url: str | None = None,
    repo_root: str | None = None,
    output_format: str = "human",
) -> None:
    """Dispatch project CLI actions."""
    actions = {
        "create": _action_create,
        "list": _action_list,
        "detail": _action_detail,
        "archive": _action_archive,
        "context-show": _action_context_show,
        "context-history": _action_context_history,
        "summarize": _action_summarize,
    }
    fn = actions.get(action)
    if not fn:
        get_console().print(f"[red]Unknown action: {action}[/red]")
        sys.exit(1)

    asyncio.run(fn(
        cli_logger,
        name=name,
        project_id=project_id,
        description=description,
        owner_id=owner_id,
        roster=roster,
        budget=budget,
        repo_url=repo_url,
        repo_root=repo_root,
        output_format=output_format,
    ))


async def _action_create(cli_logger, *, name, description, owner_id, roster, budget, repo_url, repo_root, **_):
    """Create a new project."""
    from modules.backend.services.project import ProjectService

    console = get_console()
    if not name:
        console.print("[red]--name is required[/red]")
        sys.exit(1)
    if not description:
        console.print("[red]--description is required[/red]")
        sys.exit(1)

    async with ProjectService.factory() as svc:
        project = await svc.create_project(
            name=name,
            description=description,
            owner_id=owner_id,
            default_roster=roster,
            budget_ceiling_usd=budget,
            repo_url=repo_url,
            repo_root=repo_root,
        )
    console.print(f"[green]Project created:[/green] {project.id}")
    console.print(f"  Name: {project.name}")
    console.print(f"  Owner: {project.owner_id}")


async def _action_list(cli_logger, *, output_format, **_):
    """List all active projects."""
    from modules.backend.services.project import ProjectService

    console = get_console()
    async with ProjectService.factory() as svc:
        projects = await svc.list_projects()

    if not projects:
        console.print("[dim]No projects found.[/dim]")
        return

    table = build_table("Projects", columns=[
        ("Status", {"width": 10}),
        ("Name", {"style": "cyan", "width": 30}),
        ("ID", {"width": 38}),
        ("Roster", {"width": 15}),
        ("Description", {"ratio": 1}),
    ], show_lines=True, table_box=DOTTED_ROWS)
    for p in projects:
        desc = p.description[:60] + "..." if len(p.description or "") > 60 else (p.description or "")
        table.add_row(styled_status(p.status), p.name, p.id, p.default_roster, desc)

    console.print(table)


async def _action_detail(cli_logger, *, project_id, name, output_format, **_):
    """Show project details."""
    from modules.backend.services.project import ProjectService

    console = get_console()
    if not project_id and not name:
        console.print("[red]--project or --name is required[/red]")
        sys.exit(1)

    async with ProjectService.factory() as svc:
        if project_id:
            project = await svc.get_project(project_id)
        else:
            project = await svc.get_project_by_name(name)
            if not project:
                console.print(f"[red]Project not found: {name}[/red]")
                sys.exit(1)

    console.print(f"[bold]{project.name}[/bold]  ({project.status})")
    console.print(f"  ID:          {project.id}")
    console.print(f"  Description: {project.description}")
    console.print(f"  Owner:       {project.owner_id}")
    console.print(f"  Roster:      {project.default_roster}")
    if project.budget_ceiling_usd:
        console.print(f"  Budget:      ${project.budget_ceiling_usd:.2f}")
    if project.repo_url:
        console.print(f"  Repo:        {project.repo_url}")

    # Show roster and agents
    from modules.backend.agents.mission_control.roster import load_roster
    try:
        roster = load_roster(project.default_roster or "default")
        roster_name = project.default_roster or "default"
        # Filter out auto-included horizontal agents for cleaner display
        vertical_agents = [
            a for a in roster.agents if not a.agent_name.startswith("horizontal.")
        ]
        console.print(f"\n  [bold]Roster:[/bold] {roster_name}  ({len(vertical_agents)} agents)")
        for agent in vertical_agents:
            desc = agent.description.strip()[:60]
            if len(agent.description.strip()) > 60:
                desc += "..."
            console.print(f"    [cyan]{agent.agent_name}[/cyan]  v{agent.agent_version}")
            console.print(f"      {desc}")
    except FileNotFoundError:
        console.print(f"\n  [dim]Roster '{project.default_roster}' not found.[/dim]")

    # Show playbooks mapped to this project
    from modules.backend.services.playbook import PlaybookService
    playbook_svc = PlaybookService()
    try:
        playbook_svc.load_playbooks()
    except Exception:
        pass  # Playbook loading may fail if agents not registered
    mapped = [
        pb for pb in playbook_svc.list_playbooks(enabled_only=False)
        if pb.project_id == project.id
    ]
    if mapped:
        console.print(f"\n  [bold]Playbooks ({len(mapped)}):[/bold]")
        for pb in mapped:
            status = "[green]enabled[/green]" if pb.enabled else "[dim]disabled[/dim]"
            console.print(f"    {pb.playbook_name}  {status}")
    else:
        console.print(f"\n  [dim]No playbooks mapped to this project.[/dim]")


async def _action_archive(cli_logger, *, project_id, **_):
    """Archive a project."""
    from modules.backend.services.project import ProjectService

    console = get_console()
    if not project_id:
        console.print("[red]PROJECT_ID is required[/red]")
        sys.exit(1)

    async with ProjectService.factory() as svc:
        project = await svc.archive_project(project_id)

    console.print(f"[yellow]Project archived:[/yellow] {project.name} ({project.id})")


async def _action_context_show(cli_logger, *, project_id, output_format, **_):
    """Show the PCD for a project."""
    import json as _json
    from modules.backend.services.project_context import ProjectContextManager

    console = get_console()
    if not project_id:
        console.print("[red]PROJECT_ID is required[/red]")
        sys.exit(1)

    async with ProjectContextManager.factory() as mgr:
        data = await mgr.get_context(project_id)
        size = await mgr.get_context_size(project_id)

    if not data:
        console.print("[dim]No PCD found for this project.[/dim]")
        return

    console.print(f"[bold]Project Context Document[/bold]  (v{size['version']}, "
                  f"{size['size_characters']} chars, {size['pct_of_max']:.0f}% of cap)")
    console.print()
    console.print(_json.dumps(data, indent=2, ensure_ascii=False))


async def _action_context_history(cli_logger, *, project_id, output_format, **_):
    """Show PCD change history."""
    from modules.backend.services.project_context import ProjectContextManager

    console = get_console()
    if not project_id:
        console.print("[red]PROJECT_ID is required[/red]")
        sys.exit(1)

    async with ProjectContextManager.factory() as mgr:
        changes = await mgr.get_history(project_id, limit=20)

    if not changes:
        console.print("[dim]No changes recorded.[/dim]")
        return

    table = build_table("PCD Changes", columns=[
        ("Version", {"width": 8}),
        ("Type", {"width": 10}),
        ("Path", {"style": "cyan", "width": 40}),
        ("Agent", {"width": 25}),
        ("Reason", {"ratio": 1}),
    ])
    for c in changes:
        table.add_row(str(c.version), c.change_type, c.path,
                      c.agent_id or "—", c.reason[:60])

    console.print(table)


async def _action_summarize(cli_logger, *, project_id, **_):
    """Run the summarization pipeline."""
    from modules.backend.services.summarization import SummarizationService

    console = get_console()
    if not project_id:
        console.print("[red]PROJECT_ID is required[/red]")
        sys.exit(1)

    async with SummarizationService.factory() as svc:
        results = await svc.run_full_pipeline(project_id)

    console.print("[bold]Summarization complete[/bold]")
    console.print(f"  Decisions archived:    {results['decisions_archived']}")
    console.print(f"  Missions summarized:   {results['missions_summarized']}")
    console.print(f"  Milestones archived:   {results['milestones_archived']}")
