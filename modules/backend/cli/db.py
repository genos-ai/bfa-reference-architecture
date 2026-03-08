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

    from modules.backend.cli.report import get_console, build_table
    from modules.backend.core.database import get_async_session

    console = get_console()

    async with get_async_session() as db:
        tbl_table = build_table("Database Statistics", columns=[
            ("Table", {"style": "cyan", "width": 28}),
            ("Rows",  {"justify": "right", "width": 10}),
        ])

        total = 0
        for tbl in ALL_TABLES:
            result = await db.execute(text(f"SELECT COUNT(*) FROM {tbl}"))  # noqa: S608
            count = result.scalar()
            total += count
            count_str = f"[green]{count}[/green]" if count else str(count)
            tbl_table.add_row(tbl, count_str)

        tbl_table.add_row("[bold]TOTAL[/bold]", f"[bold]{total}[/bold]", end_section=True)

    console.print(tbl_table)


async def _action_tables(cli_logger, *, table, limit, confirm):
    """List all application tables with column info."""
    from sqlalchemy import text

    from modules.backend.cli.report import get_console, build_table
    from modules.backend.core.database import get_async_session

    console = get_console()

    async with get_async_session() as db:
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

            col_table = build_table(f"{tbl}  ({count} rows)", columns=[
                ("Column",   {"style": "cyan", "width": 30}),
                ("Type",     {"width": 22}),
                ("Nullable", {"width": 10}),
            ])
            for col_name, data_type, nullable in columns:
                null_str = "yes" if nullable == "YES" else "[dim]NOT NULL[/dim]"
                col_table.add_row(col_name, data_type, null_str)
            console.print(col_table)


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

        from modules.backend.cli.report import get_console, build_table

        console = get_console()
        row_table = build_table(f"{table}  ({len(rows)} rows shown)", columns=[
            ("Column", {"style": "cyan", "width": 30}),
            ("Value",  {"ratio": 1}),
        ], show_lines=True)

        for i, row in enumerate(rows):
            row_table.add_row(f"[dim]--- Row {i + 1} ---[/dim]", "", end_section=True)
            for col, val in zip(columns, row):
                val_str = _format_value(val)
                row_table.add_row(col, val_str)

        console.print(row_table)


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
