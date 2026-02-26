"""
Startup Security Validation.

Enforces P8 (Secure by Default) by checking security invariants
before the application accepts traffic. If any check fails, the
application refuses to start with a clear error message.

Called during FastAPI lifespan initialization.
"""

from modules.backend.core.config import AppConfig, Settings, get_app_config, get_settings
from modules.backend.core.config_schema import FeaturesSchema, SecuritySchema
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class StartupSecurityError(RuntimeError):
    """Raised when a startup security check fails."""

    pass


def run_startup_checks() -> None:
    """
    Validate all security invariants at startup.

    Raises:
        StartupSecurityError: If any check fails
    """
    app_config = get_app_config()
    settings = get_settings()
    security_config = app_config.security
    features = app_config.features
    environment = app_config.application.environment
    is_production = environment == "production"

    errors: list[str] = []

    _check_secret_strength(settings, security_config, features, errors)
    _check_channel_secrets(settings, features, errors)
    _check_production_safety(app_config, is_production, errors)
    _check_channel_allowlists(app_config, features, errors)

    if errors:
        for error in errors:
            logger.error("Startup security check failed", extra={"check": error})
        raise StartupSecurityError(
            f"Startup blocked — {len(errors)} security check(s) failed:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    logger.info(
        "Startup security checks passed",
        extra={"environment": environment, "checks_run": 4},
    )


def _check_secret_strength(settings: Settings, security_config: SecuritySchema, features: FeaturesSchema, errors: list[str]) -> None:
    """Validate that secrets meet minimum length requirements."""
    validation = security_config.secrets_validation

    jwt_min = validation.jwt_secret_min_length
    if len(settings.jwt_secret) < jwt_min:
        errors.append(
            f"JWT_SECRET is {len(settings.jwt_secret)} chars, "
            f"minimum is {jwt_min}"
        )

    salt_min = validation.api_key_salt_min_length
    if len(settings.api_key_salt) < salt_min:
        errors.append(
            f"API_KEY_SALT is {len(settings.api_key_salt)} chars, "
            f"minimum is {salt_min}"
        )

    webhook_min = validation.webhook_secret_min_length
    if features.channel_telegram_enabled and len(settings.telegram_webhook_secret) < webhook_min:
        errors.append(
            f"TELEGRAM_WEBHOOK_SECRET is {len(settings.telegram_webhook_secret)} chars, "
            f"minimum is {webhook_min}"
        )


def _check_channel_secrets(settings: Settings, features: FeaturesSchema, errors: list[str]) -> None:
    """Validate that enabled channels have required secrets configured."""
    if features.channel_telegram_enabled:
        if not settings.telegram_bot_token:
            errors.append(
                "channel_telegram_enabled is true but TELEGRAM_BOT_TOKEN is empty"
            )
        if not settings.telegram_webhook_secret:
            errors.append(
                "channel_telegram_enabled is true but TELEGRAM_WEBHOOK_SECRET is empty"
            )


def _check_production_safety(app_config: AppConfig, is_production: bool, errors: list[str]) -> None:
    """Validate production environment safety constraints."""
    if not is_production:
        return

    app = app_config.application
    if app.debug:
        errors.append("debug is true in production environment")

    if app_config.features.api_detailed_errors:
        errors.append("api_detailed_errors is true in production environment")

    if app.docs_enabled:
        errors.append("docs_enabled is true in production environment")

    cors_config = app_config.security.cors
    if cors_config.enforce_in_production:
        origins = app.cors.origins
        localhost_origins = [o for o in origins if "localhost" in o]
        if localhost_origins:
            errors.append(
                f"CORS origins contain localhost in production: {localhost_origins}"
            )


def _check_channel_allowlists(app_config: AppConfig, features: FeaturesSchema, errors: list[str]) -> None:
    """Validate that enabled channels with allowlist policy have non-empty allowlists."""
    gateway = app_config.gateway
    policy = gateway.default_policy

    for channel_name, channel_conf in gateway.channels.items():
        feature_key = f"channel_{channel_name}_enabled"
        if not getattr(features, feature_key, False):
            continue

        if policy == "allowlist" and not channel_conf.allowlist:
            errors.append(
                f"Channel '{channel_name}' is enabled with 'allowlist' policy "
                f"but allowlist is empty"
            )
