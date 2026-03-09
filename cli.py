#!/usr/bin/env python3
"""
BFA Platform CLI.

Usage:
    python cli.py --help
    python cli.py server --verbose
    python cli.py server stop
    python cli.py health
    python cli.py test unit --coverage
    python cli.py agent "run a health check"
    python cli.py mission run "audit the platform"
    python cli.py mission list
    python cli.py mission cost <id>
    python cli.py db stats
    python cli.py db query missions --limit 5
    python cli.py db clear --yes
    python cli.py playbook list
    python cli.py playbook run ops.platform-audit
    python cli.py credits
"""

import sys
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.core.config import validate_project_root
from modules.backend.core.logging import bind_context, get_logger, setup_logging

# Unified output format for all commands — single source of truth.
OUTPUT_FORMATS = click.Choice(["human", "json", "jsonl"])


# =============================================================================
# Root group — global options propagate to all subcommands
# =============================================================================


class CliContext:
    """Shared context passed to all subcommands."""

    def __init__(self, verbose: bool, debug: bool, output_format: str = "human"):
        if debug:
            log_level = "DEBUG"
        elif verbose:
            log_level = "INFO"
        else:
            log_level = "WARNING"

        validate_project_root()
        setup_logging(level=log_level, format_type="console")
        bind_context(source="cli")
        self.logger = get_logger("cli")
        self.output_format = output_format


class ShowHelpOnMissingArgs(click.Group):
    """Show full help instead of terse error when required args are missing."""

    def resolve_command(self, ctx, args):
        cmd_name, cmd, remaining = super().resolve_command(ctx, args)
        if cmd is not None and not isinstance(cmd, click.Group):
            # Count required arguments
            required_args = [p for p in cmd.params if isinstance(p, click.Argument) and p.required]
            if required_args and len(remaining) < len(required_args):
                # Not enough positional args — show help instead of cryptic error
                with click.Context(cmd, info_name=cmd_name, parent=ctx) as sub_ctx:
                    click.echo(cmd.get_help(sub_ctx))
                ctx.exit(0)
        return cmd_name, cmd, remaining


@click.group(cls=ShowHelpOnMissingArgs, invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Enable INFO-level logging.")
@click.option("--debug", "-d", is_flag=True, help="Enable DEBUG-level logging.")
@click.option("-o", "--output", "output_format", default="human",
              type=OUTPUT_FORMATS, help="Output format (human, json, jsonl).")
@click.pass_context
def cli(ctx, verbose: bool, debug: bool, output_format: str):
    """BFA Platform CLI.

    \b
    Infrastructure:  server, worker, scheduler, telegram, event-worker
    Diagnostics:     health, config, info, credits
    Development:     test, migrate, db
    Agents:          agent, mission, playbook
    """
    ctx.ensure_object(dict)
    ctx.obj = CliContext(verbose, debug, output_format)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# =============================================================================
# Simple commands — no subcommands
# =============================================================================


@cli.command()
@click.pass_obj
def health(ctx):
    """Run local health checks."""
    from modules.backend.cli.health import check_health
    check_health(ctx.logger, output_format=ctx.output_format)


@cli.command()
@click.pass_obj
def config(ctx):
    """Display loaded YAML configuration."""
    from modules.backend.cli.config_display import show_config
    show_config(ctx.logger, output_format=ctx.output_format)


@cli.command()
@click.pass_obj
def info(ctx):
    """Show application metadata and version."""
    from modules.backend.cli.info import show_info
    show_info(ctx.logger, output_format=ctx.output_format)


@cli.command()
@click.option("--roster", default="default", help="Roster to check models from.")
@click.pass_obj
def credits(ctx, roster: str):
    """Preflight credit check — verify all roster models have available credits."""
    from modules.backend.cli.credits import check_credits
    check_credits(ctx.logger, roster=roster, output_format=ctx.output_format)


# =============================================================================
# Agent dispatch
# =============================================================================


@cli.command()
@click.argument("message", required=False, default=None)
@click.option("--name", default=None, help="Target a specific agent, bypassing routing.")
@click.option("--list", "list_agents", is_flag=True, help="List available agents.")
@click.pass_context
def agent(ctx, message: str | None, name: str | None, list_agents: bool):
    """Send a message to an agent.

    \b
    Examples:
        python cli.py agent "run a health check"
        python cli.py agent "scan code quality" --name code.qa.agent
        python cli.py -o jsonl agent "check health"
        python cli.py agent --list
    """
    if list_agents:
        from modules.backend.cli.agent import show_agents
        show_agents(ctx.obj.logger)
        return
    if not message:
        click.echo(ctx.get_help())
        return
    from modules.backend.cli.agent import run_agent
    run_agent(ctx.obj.logger, message, name, ctx.obj.output_format)


# =============================================================================
# Server (with lifecycle actions)
# =============================================================================


@cli.group(cls=ShowHelpOnMissingArgs, invoke_without_command=True)
@click.pass_context
def server(ctx):
    """Manage the API server lifecycle.

    \b
    Examples:
        python cli.py server start --reload --port 8099
        python cli.py server stop
        python cli.py server status
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@server.command()
@click.option("--host", default=None, help="Server host.")
@click.option("--port", default=None, type=int, help="Server port.")
@click.option("--reload", is_flag=True, help="Enable auto-reload.")
@click.pass_obj
def start(ctx, host, port, reload):
    """Start the API server."""
    from modules.backend.cli.server import run_server
    run_server(ctx.logger, host, port, reload)


@server.command()
@click.option("--port", default=None, type=int, help="Port to stop.")
@click.pass_obj
def stop(ctx, port):
    """Stop a running server."""
    from modules.backend.cli.helpers import get_service_port, service_stop
    service_stop(ctx.logger, "server", get_service_port(port))


@server.command()
@click.option("--port", default=None, type=int, help="Port to check.")
@click.pass_obj
def status(ctx, port):
    """Check if the server is running."""
    from modules.backend.cli.helpers import get_service_port, service_status
    service_status(ctx.logger, "server", get_service_port(port))


@server.command()
@click.option("--host", default=None, help="Server host.")
@click.option("--port", default=None, type=int, help="Server port.")
@click.option("--reload", is_flag=True, help="Enable auto-reload.")
@click.pass_obj
def restart(ctx, host, port, reload):
    """Restart the server (stop then start)."""
    import time
    from modules.backend.cli.helpers import get_service_port, service_stop
    from modules.backend.cli.server import run_server
    service_stop(ctx.logger, "server", get_service_port(port))
    time.sleep(2)
    run_server(ctx.logger, host, port, reload)


# =============================================================================
# Worker
# =============================================================================


@cli.command()
@click.option("--workers", default=1, type=int, help="Number of worker processes.")
@click.pass_obj
def worker(ctx, workers: int):
    """Start the background task worker."""
    from modules.backend.cli.worker import run_worker
    run_worker(ctx.logger, workers)


# =============================================================================
# Scheduler
# =============================================================================


@cli.command()
@click.pass_obj
def scheduler(ctx):
    """Start the cron-based task scheduler."""
    from modules.backend.cli.scheduler import run_scheduler
    run_scheduler(ctx.logger)


# =============================================================================
# Telegram
# =============================================================================


@cli.command()
@click.pass_obj
def telegram(ctx):
    """Start the Telegram bot in polling mode."""
    from modules.backend.cli.telegram import run_telegram_poll
    run_telegram_poll(ctx.logger)


# =============================================================================
# Event worker
# =============================================================================


@cli.command("event-worker")
@click.pass_obj
def event_worker(ctx):
    """Start the event bus consumer worker."""
    from modules.backend.cli.event_worker import run_event_worker
    run_event_worker(ctx.logger)


# =============================================================================
# Test
# =============================================================================


@cli.command()
@click.argument("type", default="all", type=click.Choice(["all", "unit", "integration", "e2e"]))
@click.option("--coverage", is_flag=True, help="Run with coverage reporting.")
@click.pass_obj
def test(ctx, type: str, coverage: bool):
    """Run the test suite.

    \b
    Examples:
        python cli.py test unit
        python cli.py test unit --coverage
        python cli.py test integration
    """
    from modules.backend.cli.testing import run_tests
    run_tests(ctx.logger, type, coverage)


# =============================================================================
# Migrate
# =============================================================================


@cli.group(cls=ShowHelpOnMissingArgs, invoke_without_command=True)
@click.pass_context
def migrate(ctx):
    """Database migrations (Alembic).

    \b
    Examples:
        python cli.py migrate current
        python cli.py migrate upgrade head
        python cli.py migrate autogenerate -m "add table"
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@migrate.command()
@click.argument("revision", default="head")
@click.pass_obj
def upgrade(ctx, revision: str):
    """Upgrade database to a revision (default: head)."""
    from modules.backend.cli.migrate import run_migrations
    run_migrations(ctx.logger, "upgrade", revision, None)


@migrate.command()
@click.argument("revision")
@click.pass_obj
def downgrade(ctx, revision: str):
    """Downgrade database to a revision."""
    from modules.backend.cli.migrate import run_migrations
    run_migrations(ctx.logger, "downgrade", revision, None)


@migrate.command()
@click.pass_obj
def current(ctx):
    """Show current database revision."""
    from modules.backend.cli.migrate import run_migrations
    run_migrations(ctx.logger, "current", "head", None)


@migrate.command()
@click.pass_obj
def history(ctx):
    """Show migration history."""
    from modules.backend.cli.migrate import run_migrations
    run_migrations(ctx.logger, "history", "head", None)


@migrate.command()
@click.option("-m", "--message", required=True, help="Migration message.")
@click.pass_obj
def autogenerate(ctx, message: str):
    """Auto-generate migration from model changes."""
    from modules.backend.cli.migrate import run_migrations
    run_migrations(ctx.logger, "autogenerate", "head", message)


# =============================================================================
# Mission group
# =============================================================================


@cli.group(cls=ShowHelpOnMissingArgs, invoke_without_command=True)
@click.pass_context
def mission(ctx):
    """Create, execute, and inspect missions.

    \b
    Examples:
        python cli.py mission run "audit the platform" --budget 2.00
        python cli.py mission list
        python cli.py mission detail <id>
        python cli.py mission cost <id>
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@mission.command("run")
@click.argument("objective")
@click.option("--roster", default="default", help="Agent roster to use.")
@click.option("--budget", default=None, type=float, help="Cost ceiling in USD.")
@click.option("--triggered-by", default="user:cli", help="Trigger origin.")
@click.pass_obj
def mission_run(ctx, objective, roster, budget, triggered_by):
    """Create and execute a mission in one step."""
    from modules.backend.cli.mission import run_mission
    run_mission(ctx.logger, action="run", objective=objective, mission_id=None,
                roster=roster, budget=budget, triggered_by=triggered_by,
                output_format=ctx.output_format)


@mission.command("create")
@click.argument("objective")
@click.option("--roster", default="default", help="Agent roster to use.")
@click.option("--budget", default=None, type=float, help="Cost ceiling in USD.")
@click.option("--triggered-by", default="user:cli", help="Trigger origin.")
@click.pass_obj
def mission_create(ctx, objective, roster, budget, triggered_by):
    """Create a mission (PENDING state, not yet executed)."""
    from modules.backend.cli.mission import run_mission
    run_mission(ctx.logger, action="create", objective=objective, mission_id=None,
                roster=roster, budget=budget, triggered_by=triggered_by,
                output_format=ctx.output_format)


@mission.command("execute")
@click.argument("mission_id")
@click.option("--roster", default="default", help="Agent roster to use.")
@click.pass_obj
def mission_execute(ctx, mission_id, roster):
    """Execute an existing PENDING mission."""
    from modules.backend.cli.mission import run_mission
    run_mission(ctx.logger, action="execute", objective=None, mission_id=mission_id,
                roster=roster, budget=None, triggered_by="user:cli",
                output_format=ctx.output_format)


@mission.command("list")
@click.pass_obj
def mission_list(ctx):
    """List recent missions."""
    from modules.backend.cli.mission import run_mission
    run_mission(ctx.logger, action="list", objective=None, mission_id=None,
                roster="default", budget=None, triggered_by="user:cli",
                output_format=ctx.output_format)


@mission.command("detail")
@click.argument("mission_id")
@click.pass_obj
def mission_detail(ctx, mission_id):
    """Show mission detail with task executions."""
    from modules.backend.cli.mission import run_mission
    run_mission(ctx.logger, action="detail", objective=None, mission_id=mission_id,
                roster="default", budget=None, triggered_by="user:cli",
                output_format=ctx.output_format)


@mission.command("cost")
@click.argument("mission_id")
@click.pass_obj
def mission_cost(ctx, mission_id):
    """Show mission cost breakdown."""
    from modules.backend.cli.mission import run_mission
    run_mission(ctx.logger, action="cost", objective=None, mission_id=mission_id,
                roster="default", budget=None, triggered_by="user:cli",
                output_format=ctx.output_format)


# =============================================================================
# Playbook group
# =============================================================================


@cli.group(cls=ShowHelpOnMissingArgs, invoke_without_command=True)
@click.pass_context
def playbook(ctx):
    """List, run, and inspect playbooks.

    \b
    Examples:
        python cli.py playbook list
        python cli.py playbook run ops.platform-audit
        python cli.py playbook detail ops.platform-audit
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@playbook.command("list")
@click.pass_obj
def playbook_list(ctx):
    """List available playbooks."""
    from modules.backend.cli.playbook import run_playbook_cli
    run_playbook_cli(ctx.logger, action="list", playbook_name=None, run_id=None,
                     triggered_by="user:cli", output_format=ctx.output_format)


@playbook.command("detail")
@click.argument("name")
@click.pass_obj
def playbook_detail(ctx, name):
    """Show playbook configuration and steps."""
    from modules.backend.cli.playbook import run_playbook_cli
    run_playbook_cli(ctx.logger, action="detail", playbook_name=name, run_id=None,
                     triggered_by="user:cli", output_format=ctx.output_format)


@playbook.command("run")
@click.argument("name")
@click.option("--triggered-by", default="user:cli", help="Trigger origin.")
@click.pass_obj
def playbook_run(ctx, name, triggered_by):
    """Execute a playbook."""
    from modules.backend.cli.playbook import run_playbook_cli
    run_playbook_cli(ctx.logger, action="run", playbook_name=name, run_id=None,
                     triggered_by=triggered_by, output_format=ctx.output_format)


@playbook.command("runs")
@click.option("--name", default=None, help="Filter by playbook name.")
@click.pass_obj
def playbook_runs(ctx, name):
    """List playbook runs."""
    from modules.backend.cli.playbook import run_playbook_cli
    run_playbook_cli(ctx.logger, action="runs", playbook_name=name, run_id=None,
                     triggered_by="user:cli", output_format=ctx.output_format)


@playbook.command("run-detail")
@click.argument("run_id")
@click.pass_obj
def playbook_run_detail(ctx, run_id):
    """Show details for a specific playbook run."""
    from modules.backend.cli.playbook import run_playbook_cli
    run_playbook_cli(ctx.logger, action="run-detail", playbook_name=None,
                     run_id=run_id, triggered_by="user:cli", output_format=ctx.output_format)


@playbook.command("report")
@click.argument("run_id")
@click.pass_obj
def playbook_report(ctx, run_id):
    """Render a report for a past playbook run."""
    from modules.backend.cli.playbook import run_playbook_cli
    run_playbook_cli(ctx.logger, action="report", playbook_name=None,
                     run_id=run_id, triggered_by="user:cli", output_format=ctx.output_format)


# =============================================================================
# DB group
# =============================================================================


@cli.group(cls=ShowHelpOnMissingArgs, invoke_without_command=True)
@click.pass_context
def db(ctx):
    """Database inspection and management.

    \b
    Examples:
        python cli.py db stats
        python cli.py db query missions --limit 5
        python cli.py db clear --yes
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@db.command("stats")
@click.pass_obj
def db_stats(ctx):
    """Show row counts for all tables."""
    from modules.backend.cli.db import run_db
    run_db(ctx.logger, action="stats", table=None, limit=10, confirm=False)


@db.command("tables")
@click.pass_obj
def db_tables(ctx):
    """Show table schemas (columns, types, nullability)."""
    from modules.backend.cli.db import run_db
    run_db(ctx.logger, action="tables", table=None, limit=10, confirm=False)


@db.command("query")
@click.argument("table")
@click.option("--limit", default=10, type=int, help="Number of rows to show.")
@click.pass_obj
def db_query(ctx, table, limit):
    """Query recent rows from a table."""
    from modules.backend.cli.db import run_db
    run_db(ctx.logger, action="query", table=table, limit=limit, confirm=False)


@db.command("clear")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.pass_obj
def db_clear(ctx, yes):
    """Clear ALL application data (full reset)."""
    from modules.backend.cli.db import run_db
    run_db(ctx.logger, action="clear", table=None, limit=10, confirm=yes)


@db.command("clear-missions")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.pass_obj
def db_clear_missions(ctx, yes):
    """Clear mission data only."""
    from modules.backend.cli.db import run_db
    run_db(ctx.logger, action="clear-missions", table=None, limit=10, confirm=yes)


@db.command("clear-sessions")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.pass_obj
def db_clear_sessions(ctx, yes):
    """Clear session data only."""
    from modules.backend.cli.db import run_db
    run_db(ctx.logger, action="clear-sessions", table=None, limit=10, confirm=yes)


# =============================================================================
# Tree — show full command hierarchy
# =============================================================================


def _format_tree(group: click.Group, prefix: str = "", is_last: bool = True) -> list[str]:
    """Recursively build a tree representation of a Click group."""
    lines: list[str] = []
    commands = sorted(group.list_commands(click.Context(group)))

    for i, name in enumerate(commands):
        cmd = group.get_command(click.Context(group), name)
        if cmd is None:
            continue

        last = i == len(commands) - 1
        connector = "└── " if last else "├── "
        child_prefix = prefix + ("    " if last else "│   ")

        # Build the label: name + params + options
        parts = [name]
        if hasattr(cmd, "params"):
            for param in cmd.params:
                if isinstance(param, click.Argument):
                    parts.append(param.human_readable_name.upper())
                elif isinstance(param, click.Option) and param.name not in ("help", "verbose", "debug"):
                    flag = param.opts[-1]
                    parts.append(f"[{flag}]")

        label = " ".join(parts)
        help_text = cmd.get_short_help_str(limit=60) if cmd.help else ""
        if help_text:
            label = f"{label}  — {help_text}"

        lines.append(f"{prefix}{connector}{label}")

        if isinstance(cmd, click.Group):
            lines.extend(_format_tree(cmd, child_prefix, last))

    return lines


@cli.command("tree")
def tree_cmd():
    """Show the full command tree with all options."""
    click.echo("cli")
    lines = _format_tree(cli)
    click.echo("\n".join(lines))


# =============================================================================
# Entry point
# =============================================================================


if __name__ == "__main__":
    cli()
