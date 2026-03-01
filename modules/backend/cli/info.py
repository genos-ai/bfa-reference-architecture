"""
CLI handler for --service info.

Displays application metadata and available CLI services.
"""

import sys

import click


def show_info(logger) -> None:
    """Display application information."""
    click.echo("BFF Python Web Application")
    click.echo("=" * 40)

    try:
        from modules.backend.core.config import get_app_config
        app_config = get_app_config()
        click.echo(f"Name: {app_config.application.name}")
        click.echo(f"Version: {app_config.application.version}")
        click.echo(f"Description: {app_config.application.description}")
    except Exception as e:
        logger.error(
            "Failed to load application configuration",
            extra={"error": str(e)},
        )
        click.echo(
            click.style(
                "Error: Could not load application.yaml configuration.",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    click.echo()
    click.echo("Services (--service):")
    click.echo("  server         FastAPI development server")
    click.echo("  worker         Background task worker")
    click.echo("  scheduler      Task scheduler (cron-based)")
    click.echo("  telegram-poll  Telegram bot (polling, local dev)")
    click.echo("  health         Check application health")
    click.echo("  config         Display configuration")
    click.echo("  test           Run test suite")
    click.echo("  migrate        Database migrations")
    click.echo("  info           Show this information")
    click.echo()
    click.echo("Lifecycle actions (--action, for long-running services):")
    click.echo("  start          Start the service (default)")
    click.echo("  stop           Stop a running service")
    click.echo("  restart        Stop then start")
    click.echo("  status         Check if running")
    click.echo()
    click.echo("Options:")
    click.echo("  --verbose, -v  Enable INFO level logging")
    click.echo("  --debug, -d    Enable DEBUG level logging")
    click.echo()
    click.echo("Examples:")
    click.echo("  python cli.py --service server --reload --verbose")
    click.echo("  python cli.py --service server --action stop")
    click.echo("  python cli.py --service server --action restart --port 8099")
    click.echo("  python cli.py --service server --action status")
    click.echo("  python cli.py --service worker --workers 2 --verbose")
    click.echo("  python cli.py --service health --debug")
    click.echo("  python cli.py --service test --test-type unit --coverage")
    click.echo("  python cli.py --service migrate --migrate-action current")
    click.echo("  python cli.py --service telegram-poll --verbose")

    logger.debug("Info displayed")
