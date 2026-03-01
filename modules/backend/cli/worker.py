"""
CLI handler for --service worker.

Starts the Taskiq background task worker as a subprocess.
"""

import subprocess
import sys

import click


def run_worker(logger, workers: int) -> None:
    """Start the Taskiq background task worker."""
    logger.info("Starting background task worker", extra={"workers": workers})

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

    cmd = [
        sys.executable, "-m", "taskiq",
        "worker",
        "modules.backend.tasks.broker:broker",
        "--workers", str(workers),
    ]

    click.echo(f"Starting Taskiq worker with {workers} worker(s)")
    click.echo("Press Ctrl+C to stop\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        logger.info("Worker stopped")
    except subprocess.CalledProcessError as e:
        logger.error("Worker failed to start", extra={"exit_code": e.returncode})
        sys.exit(e.returncode)
