#!/usr/bin/env python3
"""
Tachikoma Platform CLI.

Primary entry point for all application operations.
Use --service to select what to run, --action to control lifecycle.

Usage:
    python cli.py --help
    python cli.py --service server --verbose
    python cli.py --service server --action stop
    python cli.py --service health --debug
    python cli.py --service config
    python cli.py --service test --test-type unit
    python cli.py --service agent --agent-message "run a health check"
    python cli.py --service mission --mission-action run --objective "audit the platform"
    python cli.py --service mission --mission-action list
    python cli.py --service mission --mission-action cost --mission-id <id>
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

ALL_SERVICES = [
    "server", "worker", "scheduler", "health", "config", "test", "info",
    "migrate", "telegram-poll", "event-worker", "agent", "mission",
]


@click.command()
@click.option(
    "--service", "-s",
    type=click.Choice(ALL_SERVICES),
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
# ---- Agent options ----
@click.option(
    "--agent-message",
    default=None,
    help="Message to send to an agent (--service agent).",
)
@click.option(
    "--agent-name",
    default=None,
    help="Target a specific agent by name, bypassing routing (--service agent).",
)
# ---- Mission options ----
@click.option(
    "--mission-action",
    type=click.Choice(["create", "execute", "run", "list", "detail", "cost"]),
    default="list",
    help="Mission action (--service mission).",
)
@click.option(
    "--objective",
    default=None,
    help="Mission objective text (--service mission --mission-action create/run).",
)
@click.option(
    "--mission-id",
    default=None,
    help="Mission ID for execute/detail/cost actions (--service mission).",
)
@click.option(
    "--roster",
    default="default",
    help="Agent roster to use (--service mission).",
)
@click.option(
    "--budget",
    default=None,
    type=float,
    help="Cost ceiling in USD (--service mission).",
)
@click.option(
    "--triggered-by",
    default="user:cli",
    help="Who triggered this mission (--service mission).",
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
    agent_message: str | None,
    agent_name: str | None,
    mission_action: str,
    objective: str | None,
    mission_id: str | None,
    roster: str,
    budget: float | None,
    triggered_by: str,
) -> None:
    """
    Tachikoma Platform CLI.

    Use --service to select what to run. For long-running services
    (server, worker, scheduler, telegram-poll), use --action to
    control lifecycle (start/stop/restart/status).

    \b
    Services:
        server          Start the API server
        worker          Start the task worker
        scheduler       Start the scheduler
        health          Run local health checks
        config          Display configuration
        test            Run tests
        info            Show application info
        migrate         Run database migrations
        telegram-poll   Start Telegram polling
        event-worker    Start event worker
        agent           Send a message to an agent
        mission         Create, execute, and inspect missions

    \b
    Agent examples:
        python cli.py --service agent --agent-message "run a health check" --verbose
        python cli.py --service agent --agent-message "scan code quality" --agent-name code.qa.agent

    \b
    Mission examples:
        python cli.py --service mission --mission-action run --objective "audit the platform" --verbose
        python cli.py --service mission --mission-action create --objective "scan for violations"
        python cli.py --service mission --mission-action execute --mission-id <id>
        python cli.py --service mission --mission-action list
        python cli.py --service mission --mission-action detail --mission-id <id>
        python cli.py --service mission --mission-action cost --mission-id <id>

    \b
    Server examples:
        python cli.py --service server --verbose
        python cli.py --service server --action stop
        python cli.py --service server --action restart --port 8099
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
    elif service == "agent":
        from modules.backend.cli.agent import run_agent
        if not agent_message:
            click.echo(
                click.style("Error: --agent-message is required for --service agent.", fg="red"),
                err=True,
            )
            sys.exit(1)
        run_agent(logger, agent_message, agent_name)
    elif service == "mission":
        from modules.backend.cli.mission import run_mission
        run_mission(
            logger,
            action=mission_action,
            objective=objective,
            mission_id=mission_id,
            roster=roster,
            budget=budget,
            triggered_by=triggered_by,
        )


if __name__ == "__main__":
    main()
