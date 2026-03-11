"""
CLI handler for project commands.

Thin renderer over ProjectService. Handles create, list, detail, archive.
"""

import asyncio
import sys

from modules.backend.cli.report import get_console, build_table


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
    ])
    for p in projects:
        status_display = (
            "[green]active[/green]" if p.status == "active"
            else f"[yellow]{p.status}[/yellow]"
        )
        desc = p.description[:60] + "..." if len(p.description) > 60 else p.description
        table.add_row(status_display, p.name, p.id, p.default_roster, desc)

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
