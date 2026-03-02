"""
Unit Test Fixtures.

Per P12: tests run against the live platform. Mock only what you don't operate.
Unit tests connect to real PostgreSQL and Redis. Write operations use
transaction rollback so tests don't pollute data.

TODO: Migrate remaining mock fixtures below to real infrastructure.
Legacy mock_db_session, mock_redis, etc. exist for existing tests that
haven't been migrated yet. New tests MUST use real connections.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.backend.core.config_schema import DatabaseSchema
from tests.test_config import get_test_database_config


# =============================================================================
# Database Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """
    Mock database session for unit tests.

    Provides a fully mocked AsyncSession with common methods.

    Usage:
        def test_repository(mock_db_session: AsyncMock):
            repo = UserRepository(mock_db_session)
            # Test repository methods
    """
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def mock_db_result() -> MagicMock:
    """
    Mock database query result.

    Use this to mock the result of session.execute().

    Usage:
        def test_query(mock_db_session, mock_db_result):
            mock_db_result.scalar_one_or_none.return_value = User(id="123")
            mock_db_session.execute.return_value = mock_db_result
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    result.scalars = MagicMock()
    result.scalars.return_value.all = MagicMock(return_value=[])
    result.scalars.return_value.first = MagicMock(return_value=None)
    return result


# =============================================================================
# Redis Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_redis() -> MagicMock:
    """
    Mock Redis client for unit tests.

    Provides a mocked Redis client with common methods.
    """
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=0)
    redis.expire = AsyncMock(return_value=True)
    redis.ttl = AsyncMock(return_value=-1)
    return redis


# =============================================================================
# Settings Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_settings() -> MagicMock:
    """
    Mock application settings.

    Provides a settings object with test values.

    Usage:
        def test_with_settings(mock_settings):
            with patch("module.get_settings", return_value=mock_settings):
                # Test code that uses settings
    """
    settings = MagicMock()
    settings.db_password = "test_pass"
    settings.redis_password = ""
    settings.jwt_secret = "test-secret-key"
    settings.api_key_salt = "test-salt"
    settings.telegram_bot_token = ""
    settings.telegram_webhook_secret = ""
    return settings


@pytest.fixture
def mock_app_config() -> MagicMock:
    """
    Mock YAML application configuration.

    Usage:
        def test_with_config(mock_app_config):
            with patch("module.get_app_config", return_value=mock_app_config):
                # Test code that uses app config
    """
    config = MagicMock()
    config.application = {
        "name": "Test App",
        "version": "1.0.0",
        "description": "Test application",
        "environment": "test",
        "debug": True,
        "server": {"host": "127.0.0.1", "port": 8000},
        "cors": {"origins": []},
        "telegram": {"webhook_path": "/webhook/telegram", "authorized_users": []},
    }
    config.database = DatabaseSchema(**get_test_database_config())
    config.logging = {
        "level": "DEBUG",
        "format": "console",
        "handlers": {
            "console": {"enabled": True},
            "file": {"enabled": False, "max_bytes": 10485760, "backup_count": 5},
        },
    }
    config.features = {
        "auth_require_email_verification": False,
        "api_detailed_errors": True,
    }
    config.security = {
        "jwt": {
            "algorithm": "HS256",
            "access_token_expire_minutes": 30,
            "refresh_token_expire_days": 7,
        },
    }
    return config


# =============================================================================
# HTTP Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_http_client() -> AsyncMock:
    """
    Mock HTTP client for testing external API calls.

    Usage:
        async def test_external_api(mock_http_client):
            mock_http_client.get.return_value = MockResponse(200, {"data": "value"})
            # Test code that makes HTTP requests
    """
    client = AsyncMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.patch = AsyncMock()
    client.delete = AsyncMock()
    return client


class MockResponse:
    """Mock HTTP response for testing."""

    def __init__(
        self,
        status_code: int,
        json_data: dict[str, Any] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or str(json_data)

    def json(self) -> dict[str, Any]:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


@pytest.fixture
def mock_response() -> type[MockResponse]:
    """Provide MockResponse class for creating mock HTTP responses."""
    return MockResponse


# =============================================================================
# Logging Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_logger() -> MagicMock:
    """
    Mock logger for testing logging calls.

    Usage:
        def test_logging(mock_logger):
            with patch("module.get_logger", return_value=mock_logger):
                # Test code that logs
                mock_logger.info.assert_called_once()
    """
    logger = MagicMock()
    logger.debug = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    logger.exception = MagicMock()
    return logger
