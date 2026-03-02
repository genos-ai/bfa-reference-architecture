"""
Event Consumer Worker.

Runs the FastStream application with Redis Streams consumers.
Launched via: python cli.py --service event-worker
"""

import subprocess
import sys


def run_event_worker(logger):
    """
    Start the FastStream event consumer worker.

    Uses faststream CLI to run the application factory, which
    sets up the broker, middleware, and registered consumers.

    Args:
        logger: Configured logger instance.
    """
    logger.info("Starting event worker")
    subprocess.run([
        sys.executable, "-m", "faststream",
        "run", "modules.backend.events.broker:create_event_app",
        "--factory",
    ])
