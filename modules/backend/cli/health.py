"""
CLI handler for --service health.

Runs diagnostic checks against core application components.
"""

import click


def check_health(logger) -> None:
    """Check application health by testing imports and configuration."""
    click.echo("Checking application health...\n")

    checks = []

    try:
        from modules.backend.core.config import get_settings, get_app_config
        from modules.backend.core.logging import get_logger
        from modules.backend.core.exceptions import ApplicationError
        checks.append(("Core imports", True, None))
        logger.debug("Core imports successful")
    except Exception as e:
        checks.append(("Core imports", False, str(e)))
        logger.error("Core imports failed", extra={"error": str(e)})

    try:
        app_config = get_app_config()
        app_name = app_config.application.name
        checks.append(("YAML configuration", True, f"App: {app_name}"))
        logger.debug("Configuration loaded", extra={"app_name": app_name})
    except Exception as e:
        checks.append(("YAML configuration", False, str(e)))
        logger.error("Configuration failed", extra={"error": str(e)})

    try:
        app_env = get_app_config().application.environment
        checks.append(("Environment settings", True, f"Env: {app_env}"))
        logger.debug("Settings loaded", extra={"env": app_env})
    except Exception as e:
        checks.append(("Environment settings", False, str(e)))
        logger.warning("Environment settings not configured (expected for skeleton)")

    try:
        from modules.backend.main import get_app
        app = get_app()
        checks.append(("FastAPI application", True, f"Title: {app.title}"))
        logger.debug("FastAPI app loaded", extra={"title": app.title})
    except Exception as e:
        checks.append(("FastAPI application", False, str(e)))
        logger.error("FastAPI app failed", extra={"error": str(e)})

    try:
        from modules.backend.models.base import Base, TimestampMixin, UUIDMixin
        checks.append(("Database models", True, None))
        logger.debug("Database models loaded")
    except Exception as e:
        checks.append(("Database models", False, str(e)))
        logger.error("Database models failed", extra={"error": str(e)})

    try:
        from modules.backend.schemas.base import ApiResponse, ErrorResponse
        checks.append(("API schemas", True, None))
        logger.debug("Schemas loaded")
    except Exception as e:
        checks.append(("API schemas", False, str(e)))
        logger.error("Schemas failed", extra={"error": str(e)})

    click.echo("Health Check Results:")
    click.echo("-" * 50)

    all_passed = True
    for name, passed, detail in checks:
        status = click.style("✓ PASS", fg="green") if passed else click.style("✗ FAIL", fg="red")
        detail_str = f" ({detail})" if detail else ""
        click.echo(f"  {status}  {name}{detail_str}")
        if not passed:
            all_passed = False

    click.echo("-" * 50)

    if all_passed:
        click.echo(click.style("\nAll checks passed!", fg="green"))
    else:
        click.echo(click.style("\nSome checks failed. See details above.", fg="yellow"))
        click.echo("Note: Environment settings require config/.env to be configured.")
