"""Unit tests for session config schema."""

import pytest
from pydantic import ValidationError

from modules.backend.core.config_schema import SessionsSchema


class TestSessionsSchema:
    """Tests for SessionsSchema config."""

    def test_defaults(self):
        """Default values should match expectations."""
        config = SessionsSchema()
        assert config.default_ttl_hours == 24
        assert config.max_ttl_hours == 168
        assert config.default_cost_budget_usd == 50.00
        assert config.max_cost_budget_usd == 500.00
        assert config.cleanup_interval_minutes == 60
        assert config.budget_warning_threshold == 0.80

    def test_custom_values(self):
        """Should accept custom values."""
        config = SessionsSchema(
            default_ttl_hours=12,
            max_ttl_hours=72,
            default_cost_budget_usd=100.00,
            max_cost_budget_usd=1000.00,
            cleanup_interval_minutes=30,
            budget_warning_threshold=0.90,
        )
        assert config.default_ttl_hours == 12
        assert config.max_cost_budget_usd == 1000.00

    def test_strict_mode_rejects_unknown_keys(self):
        """Unknown keys should be rejected (extra=forbid)."""
        with pytest.raises(ValidationError):
            SessionsSchema(unknown_field="value")
