"""
CLI handler for --service config.

Displays the loaded application configuration from YAML files.
"""

import sys

import click


def show_config(logger) -> None:
    """Display loaded configuration."""
    click.echo("Application Configuration:\n")

    try:
        from modules.backend.core.config import get_app_config

        app_config = get_app_config()

        click.echo("Application Settings (from YAML):")
        click.echo("-" * 40)
        for key, value in app_config.application.model_dump().items():
            click.echo(f"  {key}: {value}")

        click.echo("\nDatabase Settings (from YAML):")
        click.echo("-" * 40)
        for key, value in app_config.database.model_dump().items():
            click.echo(f"  {key}: {value}")

        click.echo("\nLogging Settings (from YAML):")
        click.echo("-" * 40)
        for key, value in app_config.logging.model_dump().items():
            if isinstance(value, dict):
                click.echo(f"  {key}:")
                for k, v in value.items():
                    click.echo(f"    {k}: {v}")
            else:
                click.echo(f"  {key}: {value}")

        click.echo("\nFeature Flags (from YAML):")
        click.echo("-" * 40)
        for key, value in app_config.features.model_dump().items():
            click.echo(f"  {key}: {value}")

        logger.info("Configuration displayed successfully")

    except Exception as e:
        logger.error("Failed to load configuration", extra={"error": str(e)})
        click.echo(click.style(f"Error loading configuration: {e}", fg="red"))
        sys.exit(1)
