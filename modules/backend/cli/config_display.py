"""
CLI handler for --service config.

Displays the loaded application configuration from YAML files.
"""

import sys

import click


def show_config(logger, output_format: str = "human") -> None:
    """Display loaded configuration."""
    try:
        from modules.backend.cli.report import get_console, primary_panel
        from modules.backend.core.config import get_app_config

        app_config = get_app_config()
        console = get_console()

        sections = [
            ("Application Settings", app_config.application.model_dump()),
            ("Database Settings", app_config.database.model_dump()),
            ("Logging Settings", app_config.logging.model_dump()),
            ("Feature Flags", app_config.features.model_dump()),
        ]

        for title, data in sections:
            lines = []
            for key, value in data.items():
                if isinstance(value, dict):
                    lines.append(f"[bold]{key}:[/bold]")
                    for k, v in value.items():
                        lines.append(f"  {k}: {v}")
                else:
                    lines.append(f"[bold]{key}:[/bold] {value}")
            console.print(primary_panel("\n".join(lines), title=title))

        logger.info("Configuration displayed successfully")

    except Exception as e:
        logger.error("Failed to load configuration", extra={"error": str(e)})
        click.echo(click.style(f"Error loading configuration: {e}", fg="red"))
        sys.exit(1)
