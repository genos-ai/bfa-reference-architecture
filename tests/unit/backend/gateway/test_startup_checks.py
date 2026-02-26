"""
Unit Tests for P8 startup security checks.

Tests validate that the application refuses to start when
security invariants are violated.
"""

from unittest.mock import MagicMock, patch

import pytest

from modules.backend.gateway.security.startup_checks import (
    StartupSecurityError,
    _check_channel_allowlists,
    _check_channel_secrets,
    _check_production_safety,
    _check_secret_strength,
    run_startup_checks,
)


def _mock_settings(
    jwt_secret: str = "a" * 64,
    api_key_salt: str = "b" * 32,
    telegram_bot_token: str = "token",
    telegram_webhook_secret: str = "secret",
):
    """Create a mock Settings object."""
    settings = MagicMock()
    settings.jwt_secret = jwt_secret
    settings.api_key_salt = api_key_salt
    settings.telegram_bot_token = telegram_bot_token
    settings.telegram_webhook_secret = telegram_webhook_secret
    return settings


def _mock_security_config(jwt_min: int = 32, salt_min: int = 16, webhook_min: int = 16):
    """Create a mock SecuritySchema."""
    config = MagicMock()
    config.secrets_validation.jwt_secret_min_length = jwt_min
    config.secrets_validation.api_key_salt_min_length = salt_min
    config.secrets_validation.webhook_secret_min_length = webhook_min
    return config


def _mock_features(telegram_enabled: bool = False):
    """Create a mock FeaturesSchema."""
    features = MagicMock()
    features.channel_telegram_enabled = telegram_enabled
    return features


def _mock_app_config(
    environment: str = "development",
    debug: bool = False,
    docs_enabled: bool = False,
    api_detailed_errors: bool = False,
    cors_origins: list | None = None,
    enforce_cors: bool = True,
    telegram_enabled: bool = False,
    default_policy: str = "deny",
    channels: dict | None = None,
):
    """Create a mock AppConfig."""
    config = MagicMock()
    config.application.environment = environment
    config.application.debug = debug
    config.application.docs_enabled = docs_enabled
    config.application.cors.origins = cors_origins or []
    config.features.api_detailed_errors = api_detailed_errors
    config.features.channel_telegram_enabled = telegram_enabled
    config.security.cors.enforce_in_production = enforce_cors
    config.security.secrets_validation.jwt_secret_min_length = 32
    config.security.secrets_validation.api_key_salt_min_length = 16
    config.gateway.default_policy = default_policy
    config.gateway.channels = channels or {}
    return config


class TestSecretStrength:
    """Tests for JWT and API key salt minimum lengths."""

    def test_passes_with_strong_secrets(self):
        errors: list[str] = []
        settings = _mock_settings(jwt_secret="a" * 64, api_key_salt="b" * 32)
        security = _mock_security_config(jwt_min=32, salt_min=16)
        features = _mock_features(telegram_enabled=False)
        _check_secret_strength(settings, security, features, errors)
        assert len(errors) == 0

    def test_fails_with_short_jwt(self):
        errors: list[str] = []
        settings = _mock_settings(jwt_secret="short")
        security = _mock_security_config(jwt_min=32)
        features = _mock_features(telegram_enabled=False)
        _check_secret_strength(settings, security, features, errors)
        assert len(errors) == 1
        assert "JWT_SECRET" in errors[0]

    def test_fails_with_short_api_salt(self):
        errors: list[str] = []
        settings = _mock_settings(api_key_salt="tiny")
        security = _mock_security_config(salt_min=16)
        features = _mock_features(telegram_enabled=False)
        _check_secret_strength(settings, security, features, errors)
        assert len(errors) == 1
        assert "API_KEY_SALT" in errors[0]

    def test_fails_with_short_webhook_secret(self):
        errors: list[str] = []
        settings = _mock_settings(telegram_webhook_secret="short")
        security = _mock_security_config(webhook_min=16)
        features = _mock_features(telegram_enabled=True)
        _check_secret_strength(settings, security, features, errors)
        assert len(errors) == 1
        assert "TELEGRAM_WEBHOOK_SECRET" in errors[0]

    def test_skips_webhook_check_when_telegram_disabled(self):
        errors: list[str] = []
        settings = _mock_settings(telegram_webhook_secret="short")
        security = _mock_security_config(webhook_min=16)
        features = _mock_features(telegram_enabled=False)
        _check_secret_strength(settings, security, features, errors)
        assert len(errors) == 0


class TestChannelSecrets:
    """Tests for channel-specific secret validation."""

    def test_passes_when_telegram_disabled(self):
        errors: list[str] = []
        settings = _mock_settings(telegram_bot_token="", telegram_webhook_secret="")
        features = _mock_features(telegram_enabled=False)
        _check_channel_secrets(settings, features, errors)
        assert len(errors) == 0

    def test_fails_when_telegram_enabled_without_token(self):
        errors: list[str] = []
        settings = _mock_settings(telegram_bot_token="", telegram_webhook_secret="secret")
        features = _mock_features(telegram_enabled=True)
        _check_channel_secrets(settings, features, errors)
        assert len(errors) == 1
        assert "TELEGRAM_BOT_TOKEN" in errors[0]

    def test_fails_when_telegram_enabled_without_webhook_secret(self):
        errors: list[str] = []
        settings = _mock_settings(telegram_bot_token="token", telegram_webhook_secret="")
        features = _mock_features(telegram_enabled=True)
        _check_channel_secrets(settings, features, errors)
        assert len(errors) == 1
        assert "TELEGRAM_WEBHOOK_SECRET" in errors[0]

    def test_passes_when_telegram_has_all_secrets(self):
        errors: list[str] = []
        settings = _mock_settings(telegram_bot_token="token", telegram_webhook_secret="secret")
        features = _mock_features(telegram_enabled=True)
        _check_channel_secrets(settings, features, errors)
        assert len(errors) == 0


class TestProductionSafety:
    """Tests for production environment constraints."""

    def test_skips_in_development(self):
        errors: list[str] = []
        config = _mock_app_config(environment="development", debug=True, docs_enabled=True)
        _check_production_safety(config, is_production=False, errors=errors)
        assert len(errors) == 0

    def test_fails_with_debug_in_production(self):
        errors: list[str] = []
        config = _mock_app_config(environment="production", debug=True)
        _check_production_safety(config, is_production=True, errors=errors)
        assert any("debug" in e for e in errors)

    def test_fails_with_docs_in_production(self):
        errors: list[str] = []
        config = _mock_app_config(environment="production", docs_enabled=True)
        _check_production_safety(config, is_production=True, errors=errors)
        assert any("docs_enabled" in e for e in errors)

    def test_fails_with_detailed_errors_in_production(self):
        errors: list[str] = []
        config = _mock_app_config(environment="production", api_detailed_errors=True)
        _check_production_safety(config, is_production=True, errors=errors)
        assert any("api_detailed_errors" in e for e in errors)

    def test_fails_with_localhost_cors_in_production(self):
        errors: list[str] = []
        config = _mock_app_config(
            environment="production",
            cors_origins=["http://localhost:3000"],
            enforce_cors=True,
        )
        _check_production_safety(config, is_production=True, errors=errors)
        assert any("localhost" in e for e in errors)


class TestChannelAllowlists:
    """Tests for allowlist policy enforcement."""

    def test_passes_with_deny_policy(self):
        errors: list[str] = []
        config = _mock_app_config(
            default_policy="deny",
            telegram_enabled=True,
            channels={},
        )
        features = config.features
        _check_channel_allowlists(config, features, errors)
        assert len(errors) == 0

    def test_fails_with_empty_allowlist(self):
        errors: list[str] = []
        channel_conf = MagicMock()
        channel_conf.allowlist = []
        config = _mock_app_config(
            default_policy="allowlist",
            telegram_enabled=True,
            channels={"telegram": channel_conf},
        )
        features = config.features
        _check_channel_allowlists(config, features, errors)
        assert len(errors) == 1
        assert "allowlist is empty" in errors[0]

    def test_passes_with_populated_allowlist(self):
        errors: list[str] = []
        channel_conf = MagicMock()
        channel_conf.allowlist = ["user_123"]
        config = _mock_app_config(
            default_policy="allowlist",
            telegram_enabled=True,
            channels={"telegram": channel_conf},
        )
        features = config.features
        _check_channel_allowlists(config, features, errors)
        assert len(errors) == 0


class TestRunStartupChecks:
    """Integration test for the full startup check sequence."""

    def test_passes_in_development_with_valid_config(self):
        config = _mock_app_config(environment="development")
        settings = _mock_settings()
        with patch(
            "modules.backend.gateway.security.startup_checks.get_app_config",
            return_value=config,
        ), patch(
            "modules.backend.gateway.security.startup_checks.get_settings",
            return_value=settings,
        ):
            run_startup_checks()

    def test_raises_with_short_jwt_secret(self):
        config = _mock_app_config()
        settings = _mock_settings(jwt_secret="short")
        with patch(
            "modules.backend.gateway.security.startup_checks.get_app_config",
            return_value=config,
        ), patch(
            "modules.backend.gateway.security.startup_checks.get_settings",
            return_value=settings,
        ):
            with pytest.raises(StartupSecurityError, match="security check"):
                run_startup_checks()
