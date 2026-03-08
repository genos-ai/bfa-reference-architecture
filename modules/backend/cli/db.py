"""
CLI handler for --service db.

Database inspection, cleanup, and management commands for development.
All operations use real async DB sessions via get_async_session().
"""

import asyncio
import sys

import click

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

# Tables in dependency order (children first for safe truncation)
ALL_TABLES = [
    "mission_decisions",
    "task_attempts",
    "task_executions",
    "mission_records",
    "session_messages",
    "session_channels",
    "missions",
    "playbook_runs",
    "sessions",
    "notes",
]


def run_db(
    cli_logger,
    action: str,
    table: str | None,
    limit: int,
    confirm: bool,
) -> None:
    """Dispatch db CLI actions."""
    actions = {
        "stats": _action_stats,
        "tables": _action_tables,
        "query": _action_query,
        "clear": _action_clear,
        "clear-missions": _action_clear_missions,
        "clear-sessions": _action_clear_sessions,
    }

    handler = actions.get(action)
    if not handler:
        click.echo(
            click.style(
                f"Unknown db action: {action}. "
                f"Valid: {', '.join(actions.keys())}",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    try:
        asyncio.run(handler(
            cli_logger,
            table=table,
            limit=limit,
            confirm=confirm,
        ))
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        cli_logger.error("DB action failed", extra={"action": action, "error": str(e)})
        sys.exit(1)


# =============================================================================
# Actions
# =============================================================================


async def _action_stats(cli_logger, *, table, limit, confirm):
    """Show row counts for all tables."""
    from sqlalchemy import text

    from modules.backend.core.database import get_async_session

    async with get_async_session() as db:
        click.echo(click.style("Database Statistics", fg="cyan", bold=True))
        click.echo(f"  {'Table':<24} {'Rows':>8}")
        click.echo("  " + "-" * 34)

        total = 0
        for tbl in ALL_TABLES:
            result = await db.execute(text(f"SELECT COUNT(*) FROM {tbl}"))  # noqa: S608
            count = result.scalar()
            total += count
            color = "white" if count == 0 else "green"
            click.echo(f"  {tbl:<24} {click.style(str(count), fg=color):>8}")

        click.echo("  " + "-" * 34)
        click.echo(f"  {'TOTAL':<24} {total:>8}")


async def _action_tables(cli_logger, *, table, limit, confirm):
    """List all application tables with column info."""
    from sqlalchemy import text

    from modules.backend.core.database import get_async_session

    async with get_async_session() as db:
        click.echo(click.style("Application Tables", fg="cyan", bold=True))
        click.echo()

        for tbl in ALL_TABLES:
            result = await db.execute(text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = :table "
                "ORDER BY ordinal_position"
            ), {"table": tbl})
            columns = result.fetchall()

            result = await db.execute(text(f"SELECT COUNT(*) FROM {tbl}"))  # noqa: S608
            count = result.scalar()

            click.echo(click.style(f"  {tbl}", fg="cyan", bold=True) + f"  ({count} rows)")
            for col_name, data_type, nullable in columns:
                null_str = "" if nullable == "YES" else " NOT NULL"
                click.echo(f"    {col_name:<28} {data_type:<20}{null_str}")
            click.echo()


async def _action_query(cli_logger, *, table, limit, confirm):
    """Query recent rows from a table."""
    if not table:
        click.echo(click.style("Error: --table is required for query.", fg="red"), err=True)
        click.echo(f"Available tables: {', '.join(ALL_TABLES)}")
        sys.exit(1)

    if table not in ALL_TABLES:
        click.echo(click.style(f"Error: unknown table '{table}'.", fg="red"), err=True)
        click.echo(f"Available tables: {', '.join(ALL_TABLES)}")
        sys.exit(1)

    from sqlalchemy import text

    from modules.backend.core.database import get_async_session

    async with get_async_session() as db:
        # Get column names
        col_result = await db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :table ORDER BY ordinal_position"
        ), {"table": table})
        columns = [row[0] for row in col_result.fetchall()]

        # Determine order column
        order_col = "created_at" if "created_at" in columns else columns[0]

        result = await db.execute(text(
            f"SELECT * FROM {table} ORDER BY {order_col} DESC LIMIT :limit"  # noqa: S608
        ), {"limit": limit})
        rows = result.fetchall()

        if not rows:
            click.echo(f"No rows in {table}.")
            return

        click.echo(click.style(f"{table}", fg="cyan", bold=True) + f"  ({len(rows)} rows shown)")
        click.echo()

        for i, row in enumerate(rows):
            click.echo(click.style(f"  --- Row {i + 1} ---", dim=True))
            for col, val in zip(columns, row):
                val_str = _format_value(val)
                click.echo(f"    {col:<28} {val_str}")
            click.echo()


async def _action_clear(cli_logger, *, table, limit, confirm):
    """Clear ALL application data (full reset for testing)."""
    if not confirm:
        click.echo(click.style("This will DELETE ALL DATA from all application tables.", fg="red", bold=True))
        click.echo(f"Tables: {', '.join(ALL_TABLES)}")
        click.echo()
        if not click.confirm("Are you sure?"):
            click.echo("Aborted.")
            return

    from sqlalchemy import text

    from modules.backend.core.database import get_async_session

    async with get_async_session() as db:
        for tbl in ALL_TABLES:
            await db.execute(text(f"TRUNCATE TABLE {tbl} CASCADE"))  # noqa: S608
        await db.commit()

    click.echo(click.style("All application data cleared.", fg="green"))


async def _action_clear_missions(cli_logger, *, table, limit, confirm):
    """Clear mission-related data only (missions, records, executions, decisions)."""
    mission_tables = [
        "mission_decisions",
        "task_attempts",
        "task_executions",
        "mission_records",
        "missions",
        "playbook_runs",
    ]

    if not confirm:
        click.echo(click.style("This will DELETE all mission data.", fg="red", bold=True))
        click.echo(f"Tables: {', '.join(mission_tables)}")
        click.echo()
        if not click.confirm("Are you sure?"):
            click.echo("Aborted.")
            return

    from sqlalchemy import text

    from modules.backend.core.database import get_async_session

    async with get_async_session() as db:
        for tbl in mission_tables:
            await db.execute(text(f"TRUNCATE TABLE {tbl} CASCADE"))  # noqa: S608
        await db.commit()

    click.echo(click.style("Mission data cleared.", fg="green"))


async def _action_clear_sessions(cli_logger, *, table, limit, confirm):
    """Clear session-related data only (sessions, channels, messages)."""
    session_tables = [
        "session_messages",
        "session_channels",
        "sessions",
    ]

    if not confirm:
        click.echo(click.style("This will DELETE all session data.", fg="red", bold=True))
        click.echo(f"Tables: {', '.join(session_tables)}")
        click.echo()
        if not click.confirm("Are you sure?"):
            click.echo("Aborted.")
            return

    from sqlalchemy import text

    from modules.backend.core.database import get_async_session

    async with get_async_session() as db:
        for tbl in session_tables:
            await db.execute(text(f"TRUNCATE TABLE {tbl} CASCADE"))  # noqa: S608
        await db.commit()

    click.echo(click.style("Session data cleared.", fg="green"))


# =============================================================================
# Helpers
# =============================================================================


def _format_value(val) -> str:
    """Format a DB value for display, truncating long strings."""
    if val is None:
        return click.style("NULL", dim=True)
    s = str(val)
    if len(s) > 120:
        return s[:117] + "..."
    return s
