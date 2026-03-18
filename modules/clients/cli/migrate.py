"""
CLI handler for --service migrate.

Runs database migrations using Alembic.
"""

import subprocess
import sys

import click

from modules.backend.core.config import find_project_root


def run_migrations(
    logger,
    migrate_action: str,
    revision: str,
    message: str | None,
) -> None:
    """Run database migrations using Alembic."""
    logger.info(
        "Running migrations",
        extra={"action": migrate_action, "revision": revision},
    )

    alembic_ini = find_project_root() / "modules" / "backend" / "migrations" / "alembic.ini"

    if not alembic_ini.exists():
        click.echo(
            click.style("Error: modules/backend/migrations/alembic.ini not found.", fg="red"),
            err=True,
        )
        sys.exit(1)

    cmd = [sys.executable, "-m", "alembic", "-c", str(alembic_ini)]

    if migrate_action == "upgrade":
        cmd.extend(["upgrade", revision])
        click.echo(f"Upgrading database to revision: {revision}")
    elif migrate_action == "downgrade":
        cmd.extend(["downgrade", revision])
        click.echo(f"Downgrading database to revision: {revision}")
    elif migrate_action == "current":
        cmd.append("current")
        click.echo("Showing current database revision...")
    elif migrate_action == "history":
        cmd.extend(["history", "--verbose"])
        click.echo("Showing migration history...")
    elif migrate_action == "autogenerate":
        if not message:
            click.echo(
                click.style("Error: --message/-m required for autogenerate.", fg="red"),
                err=True,
            )
            sys.exit(1)
        cmd.extend(["revision", "--autogenerate", "-m", message])
        click.echo(f"Generating migration: {message}")

    click.echo()

    try:
        result = subprocess.run(cmd, cwd=str(find_project_root()))
        if result.returncode != 0:
            logger.error("Migration failed", extra={"exit_code": result.returncode})
            sys.exit(result.returncode)
        logger.info("Migration completed successfully")
    except FileNotFoundError:
        logger.error("alembic not found. Install with: pip install alembic")
        sys.exit(1)
