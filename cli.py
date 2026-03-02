#!/usr/bin/env python3
"""
BFF Application CLI.

Primary entry point for all application operations.
Use --service to select what to run, --action to control lifecycle.

Usage:
    python cli.py --help
    python cli.py --service server --verbose
    python cli.py --service server --action stop
    python cli.py --service health --debug
    python cli.py --service config
    python cli.py --service test --test-type unit
"""

import sys
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.cli.config_display import show_config
from modules.backend.cli.health import check_health
from modules.backend.cli.helpers import get_service_port, service_status, service_stop
from modules.backend.cli.info import show_info
from modules.backend.cli.migrate import run_migrations
from modules.backend.cli.scheduler import run_scheduler
from modules.backend.cli.server import run_server
from modules.backend.cli.telegram import run_telegram_poll
from modules.backend.cli.testing import run_tests
from modules.backend.cli.worker import run_worker
from modules.backend.core.config import validate_project_root
from modules.backend.core.logging import bind_context, get_logger, setup_logging

LONG_RUNNING_SERVICES = frozenset({"server", "worker", "scheduler", "telegram-poll", "event-worker"})


@click.command()
@click.option(
    "--service", "-s",
    type=click.Choice(["server", "worker", "scheduler", "health", "config", "test", "info", "migrate", "telegram-poll", "event-worker"]),
    default="info",
    help="Service or command to run.",
)
@click.option(
    "--action", "-a",
    type=click.Choice(["start", "stop", "restart", "status"]),
    default="start",
    help="Lifecycle action for long-running services (server, worker, scheduler, telegram-poll).",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose output (INFO level logging).",
)
@click.option(
    "--debug", "-d",
    is_flag=True,
    help="Enable debug output (DEBUG level logging).",
)
@click.option(
    "--host",
    default=None,
    help="Server host.",
)
@click.option(
    "--port",
    default=None,
    type=int,
    help="Server port.",
)
@click.option(
    "--reload",
    is_flag=True,
    help="Enable auto-reload (server only).",
)
@click.option(
    "--test-type",
    type=click.Choice(["all", "unit", "integration", "e2e"]),
    default="all",
    help="Test type to run.",
)
@click.option(
    "--coverage",
    is_flag=True,
    help="Run tests with coverage.",
)
@click.option(
    "--migrate-action",
    type=click.Choice(["upgrade", "downgrade", "current", "history", "autogenerate"]),
    default="current",
    help="Migration action.",
)
@click.option(
    "--revision",
    default="head",
    help="Target revision for upgrade/downgrade.",
)
@click.option(
    "-m", "--message",
    default=None,
    help="Migration message (for autogenerate).",
)
@click.option(
    "--workers",
    default=1,
    type=int,
    help="Number of worker processes.",
)
def main(
    service: str,
    action: str,
    verbose: bool,
    debug: bool,
    host: str | None,
    port: int | None,
    reload: bool,
    test_type: str,
    coverage: bool,
    migrate_action: str,
    revision: str,
    message: str | None,
    workers: int,
) -> None:
    """
    BFF Application CLI.

    Use --service to select what to run. For long-running services
    (server, worker, scheduler, telegram-poll), use --action to
    control lifecycle (start/stop/restart/status).

    \b
    Examples:
        python cli.py --service server --verbose
        python cli.py --service server --action stop
        python cli.py --service server --action restart --port 8099
        python cli.py --service server --action status
        python cli.py --service worker --verbose
        python cli.py --service worker --action stop
        python cli.py --service scheduler --verbose
        python cli.py --service health --debug
        python cli.py --service config
        python cli.py --service test --test-type unit --coverage
        python cli.py --service info
        python cli.py --service migrate --migrate-action current
        python cli.py --service migrate --migrate-action upgrade
        python cli.py --service migrate --migrate-action autogenerate -m "add users table"
        python cli.py --service telegram-poll --verbose
        python cli.py --service telegram-poll --action stop
    """
    validate_project_root()

    if debug:
        log_level = "DEBUG"
    elif verbose:
        log_level = "INFO"
    else:
        log_level = "WARNING"

    setup_logging(level=log_level, format_type="console")
    bind_context(source="cli")
    logger = get_logger(__name__)
    logger.debug("CLI invoked", extra={"service": service, "action": action, "log_level": log_level})

    if service in LONG_RUNNING_SERVICES and action != "start":
        service_port = get_service_port(port)

        if action == "stop":
            service_stop(logger, service, service_port)
            return
        elif action == "status":
            service_status(logger, service, service_port)
            return
        elif action == "restart":
            service_stop(logger, service, service_port)
            import time
            time.sleep(2)

    if service == "server":
        run_server(logger, host, port, reload)
    elif service == "worker":
        run_worker(logger, workers)
    elif service == "scheduler":
        run_scheduler(logger)
    elif service == "health":
        check_health(logger)
    elif service == "config":
        show_config(logger)
    elif service == "test":
        run_tests(logger, test_type, coverage)
    elif service == "info":
        show_info(logger)
    elif service == "migrate":
        run_migrations(logger, migrate_action, revision, message)
    elif service == "telegram-poll":
        run_telegram_poll(logger)
    elif service == "event-worker":
        from modules.backend.cli.event_worker import run_event_worker
        run_event_worker(logger)


if __name__ == "__main__":
    main()
