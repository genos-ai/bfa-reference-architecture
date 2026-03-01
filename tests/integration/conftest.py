"""
Integration Test Fixtures.

Fixtures for integration tests - uses real database and services.
These fixtures build on the root conftest.py database fixtures.
"""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.database import get_db_session
from tests.test_config import get_test_database_config


# =============================================================================
# API Client Fixtures
# =============================================================================


@pytest.fixture
async def client(
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Create a test client with database session override.

    The client uses the test database session, ensuring all API
    operations use the same session that gets rolled back after the test.

    Usage:
        async def test_health_endpoint(client: AsyncClient):
            response = await client.get("/health")
            assert response.status_code == 200
    """
    # Override the database session dependency
    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    with patch("modules.backend.core.config.get_settings") as mock_secrets, \
         patch("modules.backend.core.config.get_app_config") as mock_config, \
         patch("modules.backend.core.security.get_settings") as mock_security_settings, \
         patch("modules.backend.core.security.get_app_config") as mock_security_config:
        mock_secrets.return_value = _create_mock_settings()
        mock_security_settings.return_value = _create_mock_settings()
        mock_app_config = _create_mock_app_config()
        mock_config.return_value = mock_app_config
        mock_security_config.return_value = mock_app_config

        from modules.backend.main import create_app

        app = create_app()
        app.dependency_overrides[get_db_session] = override_get_db_session

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client

        app.dependency_overrides.clear()


@pytest.fixture
async def client_no_db() -> AsyncGenerator[AsyncClient, None]:
    """
    Create a test client without database dependency override.

    Use this for testing endpoints that don't require database access
    (e.g., health checks, static responses).

    Note: This requires mocking get_settings since no .env exists.
    """
    with patch("modules.backend.core.config.get_settings") as mock_secrets, \
         patch("modules.backend.core.config.get_app_config") as mock_config, \
         patch("modules.backend.core.security.get_settings") as mock_security_settings, \
         patch("modules.backend.core.security.get_app_config") as mock_security_config:
        mock_secrets.return_value = _create_mock_settings()
        mock_security_settings.return_value = _create_mock_settings()
        mock_app_config = _create_mock_app_config()
        mock_config.return_value = mock_app_config
        mock_security_config.return_value = mock_app_config

        from modules.backend.main import create_app

        app = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client


# =============================================================================
# Mock Settings Helper
# =============================================================================


def _create_mock_settings() -> Any:
    """Create a real Settings-like object for testing with typed fields."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.db_password = "test_pass"
    settings.redis_password = ""
    settings.jwt_secret = "test-secret-key-that-is-long-enough-for-validation"
    settings.api_key_salt = "test-salt-long-enough"
    settings.telegram_bot_token = ""
    settings.telegram_webhook_secret = ""
    settings.anthropic_api_key = ""
    return settings


def _create_mock_app_config() -> Any:
    """
    Create a test AppConfig using real Pydantic schema instances.

    Uses the actual schema classes from config_schema.py so that
    integration tests exercise the same attribute access paths as
    production code.
    """
    from modules.backend.core.config_schema import (
        ApplicationSchema,
        DatabaseSchema,
        FeaturesSchema,
        GatewaySchema,
        LoggingSchema,
        SecuritySchema,
    )

    class TestAppConfig:
        """Test-specific AppConfig with real schema instances."""

        def __init__(self) -> None:
            self.application = ApplicationSchema(
                name="Test Application",
                version="1.0.0",
                description="Test application",
                environment="test",
                debug=True,
                api_prefix="/api",
                docs_enabled=True,
                server={"host": "127.0.0.1", "port": 8000},
                cors={"origins": ["http://localhost:3000"]},
                pagination={"default_limit": 50, "max_limit": 100},
                timeouts={"database": 10, "external_api": 30, "background": 120},
                telegram={"webhook_path": "/webhook/telegram", "authorized_users": []},
            )
            self.database = DatabaseSchema(**get_test_database_config())
            self.logging = LoggingSchema(
                level="WARNING",
                format="console",
                handlers={
                    "console": {"enabled": True},
                    "file": {
                        "enabled": False,
                        "path": "logs/test.jsonl",
                        "max_bytes": 10485760,
                        "backup_count": 5,
                    },
                },
            )
            self.features = FeaturesSchema(
                auth_require_email_verification=False,
                auth_allow_api_key_creation=True,
                auth_rate_limit_enabled=False,
                auth_require_api_authentication=False,
                api_detailed_errors=True,
                api_request_logging=False,
                channel_telegram_enabled=False,
                channel_slack_enabled=False,
                channel_discord_enabled=False,
                channel_whatsapp_enabled=False,
                gateway_enabled=False,
                gateway_websocket_enabled=False,
                gateway_pairing_enabled=False,
                agent_coordinator_enabled=False,
                agent_streaming_enabled=False,
                mcp_enabled=False,
                a2a_enabled=False,
                security_startup_checks_enabled=False,
                security_headers_enabled=False,
                security_cors_enforce_production=False,
                experimental_background_tasks_enabled=False,
            )
            self.security = SecuritySchema(
                jwt={
                    "algorithm": "HS256",
                    "access_token_expire_minutes": 30,
                    "refresh_token_expire_days": 7,
                    "audience": "bff-api",
                },
                rate_limiting={
                    "api": {"requests_per_minute": 60, "requests_per_hour": 1000},
                    "telegram": {"messages_per_minute": 30, "messages_per_hour": 500},
                    "websocket": {"messages_per_minute": 60, "messages_per_hour": 1000},
                },
                request_limits={"max_body_size_bytes": 1048576, "max_header_size_bytes": 8192},
                headers={
                    "x_content_type_options": "nosniff",
                    "x_frame_options": "DENY",
                    "referrer_policy": "strict-origin-when-cross-origin",
                    "hsts_enabled": False,
                    "hsts_max_age": 31536000,
                },
                secrets_validation={
                    "jwt_secret_min_length": 32,
                    "api_key_salt_min_length": 16,
                    "webhook_secret_min_length": 16,
                },
                cors={
                    "enforce_in_production": False,
                    "allow_methods": ["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                    "allow_headers": ["Authorization", "Content-Type"],
                },
            )
            self.gateway = GatewaySchema(
                default_policy="allow_all",
                channels={"telegram": {"allowlist": []}},
            )

    return TestAppConfig()


# =============================================================================
# API Response Assertion Helpers
# =============================================================================


class ApiAssertions:
    """Helper class for API response assertions."""

    @staticmethod
    def assert_success(response: Any, expected_status: int = 200) -> dict[str, Any]:
        """
        Assert API response is successful.

        Args:
            response: httpx Response object
            expected_status: Expected HTTP status code

        Returns:
            Response JSON data

        Raises:
            AssertionError: If response is not successful
        """
        assert response.status_code == expected_status, (
            f"Expected status {expected_status}, got {response.status_code}: "
            f"{response.text}"
        )
        data = response.json()
        assert data.get("success") is True, f"Response not successful: {data}"
        return data

    @staticmethod
    def assert_error(
        response: Any,
        expected_status: int,
        expected_code: str | None = None,
    ) -> dict[str, Any]:
        """
        Assert API response is an error.

        Args:
            response: httpx Response object
            expected_status: Expected HTTP status code
            expected_code: Expected error code (optional)

        Returns:
            Response JSON data

        Raises:
            AssertionError: If response is not an error or codes don't match
        """
        assert response.status_code == expected_status, (
            f"Expected status {expected_status}, got {response.status_code}: "
            f"{response.text}"
        )
        data = response.json()
        assert data.get("success") is False, f"Response should be error: {data}"
        assert data.get("error") is not None, f"Missing error details: {data}"

        if expected_code:
            actual_code = data["error"].get("code")
            assert actual_code == expected_code, (
                f"Expected error code {expected_code}, got {actual_code}"
            )

        return data

    @staticmethod
    def assert_validation_error(
        response: Any,
        field: str | None = None,
    ) -> dict[str, Any]:
        """
        Assert API response is a validation error (422).

        Args:
            response: httpx Response object
            field: Expected field with validation error (optional)

        Returns:
            Response JSON data
        """
        data = ApiAssertions.assert_error(response, 422, "VAL_REQUEST_INVALID")

        if field:
            errors = data["error"].get("details", {}).get("validation_errors", [])
            fields = [e.get("field", "") for e in errors]
            assert any(field in f for f in fields), (
                f"Expected validation error for field '{field}', "
                f"got errors for: {fields}"
            )

        return data


@pytest.fixture
def api() -> ApiAssertions:
    """Provide API assertion helpers."""
    return ApiAssertions()


# =============================================================================
# Authentication Fixtures
# =============================================================================


@pytest.fixture
def auth_headers(test_settings: dict[str, Any]) -> dict[str, str]:
    """
    Provide authentication headers for API requests.

    Creates a valid JWT token for testing authenticated endpoints.

    Usage:
        async def test_protected_endpoint(client: AsyncClient, auth_headers: dict):
            response = await client.get("/api/v1/me", headers=auth_headers)
            assert response.status_code == 200
    """
    from modules.backend.core.security import create_access_token

    # Create a test token with mock user data
    token = create_access_token(
        data={"sub": "test-user-id", "email": "test@example.com"},
    )
    return {"Authorization": f"Bearer {token}"}
