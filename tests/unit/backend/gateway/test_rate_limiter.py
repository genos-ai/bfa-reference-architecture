"""
Unit Tests for gateway rate limiter.

Tests use a real GatewayRateLimiter with mocked config.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from modules.backend.gateway.security.rate_limiter import GatewayRateLimiter, RateLimitResult


@pytest.fixture
def mock_app_config():
    """Mock app config with rate limiting settings."""
    config = MagicMock()
    telegram_limits = MagicMock()
    telegram_limits.model_dump.return_value = {
        "messages_per_minute": 5,
        "messages_per_hour": 100,
    }
    config.security.rate_limiting.telegram = telegram_limits

    slack_limits = MagicMock()
    slack_limits.model_dump.return_value = {
        "messages_per_minute": 10,
        "messages_per_hour": 200,
    }
    config.security.rate_limiting.slack = slack_limits
    config.security.rate_limiting.unknown_channel = None
    return config


@pytest.fixture
def limiter(mock_app_config):
    """Create a rate limiter with mocked config."""
    with patch(
        "modules.backend.gateway.security.rate_limiter.get_app_config",
        return_value=mock_app_config,
    ):
        rl = GatewayRateLimiter()
        yield rl


class TestRateLimitResult:
    """Tests for the RateLimitResult dataclass."""

    def test_allowed_result(self):
        result = RateLimitResult(allowed=True)
        assert result.allowed is True
        assert result.retry_after_seconds == 0

    def test_denied_result(self):
        result = RateLimitResult(allowed=False, retry_after_seconds=30)
        assert result.allowed is False
        assert result.retry_after_seconds == 30


class TestGatewayRateLimiter:
    """Tests for the rate limiter with real sliding window logic."""

    def test_allows_requests_under_limit(self, limiter, mock_app_config):
        with patch(
            "modules.backend.gateway.security.rate_limiter.get_app_config",
            return_value=mock_app_config,
        ):
            for _ in range(5):
                result = limiter.check("telegram", "user_1")
                assert result.allowed is True

    def test_blocks_requests_over_minute_limit(self, limiter, mock_app_config):
        with patch(
            "modules.backend.gateway.security.rate_limiter.get_app_config",
            return_value=mock_app_config,
        ):
            for _ in range(5):
                limiter.check("telegram", "user_1")

            result = limiter.check("telegram", "user_1")
            assert result.allowed is False
            assert result.retry_after_seconds > 0

    def test_separate_limits_per_user(self, limiter, mock_app_config):
        with patch(
            "modules.backend.gateway.security.rate_limiter.get_app_config",
            return_value=mock_app_config,
        ):
            for _ in range(5):
                limiter.check("telegram", "user_1")

            result = limiter.check("telegram", "user_2")
            assert result.allowed is True

    def test_separate_limits_per_channel(self, limiter, mock_app_config):
        with patch(
            "modules.backend.gateway.security.rate_limiter.get_app_config",
            return_value=mock_app_config,
        ):
            for _ in range(5):
                limiter.check("telegram", "user_1")

            result_blocked = limiter.check("telegram", "user_1")
            assert result_blocked.allowed is False

            result_other = limiter.check("slack", "user_1")
            assert result_other.allowed is True

    def test_unknown_channel_allows_all(self, limiter, mock_app_config):
        with patch(
            "modules.backend.gateway.security.rate_limiter.get_app_config",
            return_value=mock_app_config,
        ):
            for _ in range(100):
                result = limiter.check("unknown_channel", "user_1")
                assert result.allowed is True
