"""
Configuration Management.

Loads secrets from config/.env and settings from config/settings/*.yaml.
No hardcoded values in code — all configuration comes from these sources.

Secrets (.env):
    DB_PASSWORD, REDIS_PASSWORD, JWT_SECRET, API_KEY_SALT,
    TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET

Settings (YAML):
    application.yaml - App identity, server, cors, telegram, pagination
    database.yaml    - Database and Redis connection settings
    logging.yaml     - Logging configuration
    features.yaml    - Feature flags
    security.yaml    - JWT settings
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from modules.backend.core.config_schema import (
    ApplicationSchema,
    DatabaseSchema,
    EventsSchema,
    FeaturesSchema,
    GatewaySchema,
    LoggingSchema,
    SecuritySchema,
    SessionsSchema,
)


def find_project_root() -> Path:
    """Find project root by looking for .project_root marker file."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".project_root").exists():
            return current
        current = current.parent
    raise RuntimeError("Project root not found. Ensure .project_root file exists.")


def validate_project_root() -> Path:
    """
    Validate that the project root can be found.

    Raises SystemExit with a clear message if .project_root is not found.
    Use this in entry scripts before any configuration loading.
    """
    try:
        return find_project_root()
    except RuntimeError as e:
        raise SystemExit(f"Error: {e}") from e


def load_yaml_config(filename: str) -> dict[str, Any]:
    """Load a YAML configuration file from config/settings/."""
    project_root = find_project_root()
    config_path = project_root / "config" / "settings" / filename

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f) or {}


class Settings(BaseSettings):
    """Secrets loaded from config/.env. Only passwords, tokens, and keys."""

    db_password: str
    redis_password: str
    jwt_secret: str
    api_key_salt: str
    telegram_bot_token: str
    telegram_webhook_secret: str
    anthropic_api_key: str

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


def _load_validated(schema_cls: type, filename: str) -> Any:
    """Load YAML and validate against schema. Returns typed model instance."""
    raw = load_yaml_config(filename)
    try:
        return schema_cls(**raw)
    except ValidationError as e:
        raise ValueError(
            f"Invalid configuration in {filename}:\n{e}"
        ) from e


def _load_validated_optional(schema_cls: type, filename: str) -> Any:
    """Load YAML if it exists, otherwise return schema defaults."""
    try:
        return _load_validated(schema_cls, filename)
    except FileNotFoundError:
        return schema_cls()


class AppConfig:
    """
    Application configuration loaded from YAML files.

    Each YAML file is validated against its Pydantic schema at load time.
    Missing keys, wrong types, or unknown fields raise a clear error
    immediately instead of causing cryptic KeyErrors later.

    Properties return typed Pydantic model instances with attribute access.
    """

    def __init__(self) -> None:
        self._application = _load_validated(ApplicationSchema, "application.yaml")
        self._database = _load_validated(DatabaseSchema, "database.yaml")
        self._logging = _load_validated(LoggingSchema, "logging.yaml")
        self._features = _load_validated(FeaturesSchema, "features.yaml")
        self._security = _load_validated(SecuritySchema, "security.yaml")
        self._gateway = _load_validated(GatewaySchema, "gateway.yaml")
        self._events = _load_validated_optional(EventsSchema, "events.yaml")
        self._sessions = _load_validated_optional(SessionsSchema, "sessions.yaml")

    @property
    def application(self) -> ApplicationSchema:
        """Application settings."""
        return self._application

    @property
    def database(self) -> DatabaseSchema:
        """Database settings."""
        return self._database

    @property
    def logging(self) -> LoggingSchema:
        """Logging settings."""
        return self._logging

    @property
    def features(self) -> FeaturesSchema:
        """Feature flags."""
        return self._features

    @property
    def security(self) -> SecuritySchema:
        """Security settings."""
        return self._security

    @property
    def gateway(self) -> GatewaySchema:
        """Gateway settings."""
        return self._gateway

    @property
    def events(self) -> EventsSchema:
        """Event bus settings."""
        return self._events

    @property
    def sessions(self) -> SessionsSchema:
        """Session settings."""
        return self._sessions


@lru_cache
def get_settings() -> Settings:
    """Get cached secrets instance. Resolves .env path from project root."""
    env_path = find_project_root() / "config" / ".env"
    return Settings(_env_file=str(env_path))


@lru_cache
def get_app_config() -> AppConfig:
    """Get cached application configuration."""
    return AppConfig()


def get_database_url(async_driver: bool = True) -> str:
    """
    Construct database URL from YAML config and secrets.

    Args:
        async_driver: Use asyncpg driver if True, psycopg2 if False.

    Returns:
        Database connection URL string.
    """
    db = get_app_config().database
    password = get_settings().db_password
    driver = "postgresql+asyncpg" if async_driver else "postgresql"
    return f"{driver}://{db.user}:{password}@{db.host}:{db.port}/{db.name}"


def get_redis_url() -> str:
    """
    Construct Redis URL from YAML config and secrets.

    Returns:
        Redis connection URL string.
    """
    redis = get_app_config().database.redis
    password = get_settings().redis_password
    return f"redis://:{password}@{redis.host}:{redis.port}/{redis.db}"


def get_server_base_url() -> tuple[str, float]:
    """
    Get the backend server base URL and timeout from application.yaml.

    Returns:
        Tuple of (base_url, timeout_seconds).
    """
    app = get_app_config().application
    server = app.server
    base_url = f"http://{server.host}:{server.port}"
    timeout = float(app.timeouts.external_api)
    return base_url, timeout
