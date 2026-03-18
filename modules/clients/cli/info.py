"""
CLI handler for info command.

Displays application metadata and available CLI commands.
"""

import sys

import click


def show_info(logger, output_format: str = "human") -> None:
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
    click.echo("Commands (run 'python cli.py <command> --help' for details):")
    click.echo("  server          Start the API server (stop, status, restart)")
    click.echo("  worker          Start the task worker")
    click.echo("  scheduler       Start the scheduler")
    click.echo("  telegram        Start Telegram polling bot")
    click.echo("  event-worker    Start event worker")
    click.echo("  health          Run local health checks")
    click.echo("  config          Display configuration")
    click.echo("  credits         Preflight credit check")
    click.echo("  test            Run test suite")
    click.echo("  migrate         Database migrations")
    click.echo("  agent           Send a message to an agent")
    click.echo("  mission         Create, execute, and inspect missions")
    click.echo("  playbook        List, run, and inspect playbooks")
    click.echo("  project         Create, list, and manage projects")
    click.echo("  db              Database inspection and management")
    click.echo()
    click.echo("Examples:")
    click.echo("  python cli.py server --reload --verbose")
    click.echo("  python cli.py server stop")
    click.echo("  python cli.py test unit --coverage")
    click.echo("  python cli.py agent \"run a health check\"")
    click.echo("  python cli.py mission run \"audit the platform\" --budget 2.00")
    click.echo("  python cli.py playbook run ops.platform-audit")
    click.echo("  python cli.py db stats")
    click.echo("  python cli.py credits")

    logger.debug("Info displayed")
