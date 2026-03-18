"""
CLI handler for --service scheduler.

Starts the Taskiq task scheduler for cron-based background tasks.
"""

import subprocess
import sys

import click


def run_scheduler(logger) -> None:
    """Start the Taskiq task scheduler for cron-based tasks."""
    logger.info("Starting task scheduler")

    try:
        from modules.backend.core.config import get_redis_url
        redis_url = get_redis_url()
        logger.debug("Redis configured", extra={"redis_url": redis_url.split("@")[-1]})
    except Exception as e:
        logger.error("Failed to load Redis configuration.", extra={"error": str(e)})
        click.echo(
            click.style(f"Error: Redis not configured: {e}", fg="red"),
            err=True,
        )
        sys.exit(1)

    try:
        from modules.backend.tasks.scheduled import register_scheduled_tasks, SCHEDULED_TASKS
        register_scheduled_tasks()

        click.echo("Registered scheduled tasks:")
        for task_name, config in SCHEDULED_TASKS.items():
            schedule = config["schedule"][0]["cron"]
            click.echo(f"  - {task_name}: {schedule}")
        click.echo()
    except Exception as e:
        logger.error("Failed to register scheduled tasks", extra={"error": str(e)})
        click.echo(
            click.style(f"Error registering tasks: {e}", fg="red"),
            err=True,
        )
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "taskiq",
        "scheduler",
        "modules.backend.tasks.scheduler:scheduler",
    ]

    click.echo("Starting Taskiq scheduler")
    click.echo("WARNING: Run only ONE scheduler instance to avoid duplicate task execution")
    click.echo("Press Ctrl+C to stop\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")
    except subprocess.CalledProcessError as e:
        logger.error("Scheduler failed to start", extra={"exit_code": e.returncode})
        sys.exit(e.returncode)
