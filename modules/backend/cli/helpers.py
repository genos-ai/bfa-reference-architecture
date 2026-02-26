"""
Shared CLI helper functions.

Process management utilities used by lifecycle actions (stop, status, restart)
for long-running services.
"""

import os
import signal
import subprocess

import click


def find_process_on_port(port: int) -> list[int]:
    """Find PIDs listening on a port."""
    result = subprocess.run(
        ["lsof", "-ti", f":{port}"],
        capture_output=True, text=True,
    )
    pids = result.stdout.strip().split("\n")
    return [int(p) for p in pids if p.strip()]


def service_stop(logger, service: str, port: int) -> None:
    """Stop a running service by finding its process on the port."""
    pids = find_process_on_port(port)
    if not pids:
        click.echo(f"No {service} running on port {port}.")
        return

    for pid in pids:
        os.kill(pid, signal.SIGINT)
        logger.info("Sent SIGINT", extra={"service": service, "pid": pid, "port": port})

    click.echo(f"{service.title()} on port {port} stopped (PID: {', '.join(str(p) for p in pids)}).")


def service_status(logger, service: str, port: int) -> None:
    """Check if a service is running on a port."""
    pids = find_process_on_port(port)
    if pids:
        click.echo(f"{service.title()} is running on port {port} (PID: {', '.join(str(p) for p in pids)}).")
    else:
        click.echo(f"{service.title()} is not running on port {port}.")


def get_service_port(port: int | None) -> int:
    """Get the port from argument or config."""
    if port is not None:
        return port
    from modules.backend.core.config import get_app_config
    return get_app_config().application.server.port
