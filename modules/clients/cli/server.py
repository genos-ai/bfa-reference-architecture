"""
CLI handler for --service server.

Starts the FastAPI development server via uvicorn subprocess.
"""

import subprocess
import sys

import click

from modules.backend.core.config import get_app_config


def run_server(logger, host: str | None, port: int | None, reload: bool) -> None:
    """Start the FastAPI development server."""
    try:
        server_config = get_app_config().application.server
    except Exception as e:
        logger.error("Failed to load configuration.", extra={"error": str(e)})
        click.echo(
            click.style("Error: Could not load config/settings/application.yaml.", fg="red"),
            err=True,
        )
        sys.exit(1)

    server_host = host or server_config.host
    server_port = port or server_config.port

    logger.info(
        "Starting server",
        extra={"host": server_host, "port": server_port, "reload": reload},
    )

    cmd = [
        sys.executable, "-m", "uvicorn",
        "modules.backend.main:app",
        "--host", server_host,
        "--port", str(server_port),
    ]

    if reload:
        cmd.append("--reload")

    click.echo(f"Starting server at http://{server_host}:{server_port}")
    click.echo("Press Ctrl+C to stop\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        logger.info("Server stopped")
    except subprocess.CalledProcessError as e:
        logger.error("Server failed to start", extra={"exit_code": e.returncode})
        sys.exit(e.returncode)
