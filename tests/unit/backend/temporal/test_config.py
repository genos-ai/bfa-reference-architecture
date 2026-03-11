"""Tests for TemporalSchema configuration.

Pure Pydantic schema tests — no mocks, no infrastructure.
"""

import pytest

from modules.backend.core.config_schema import TemporalSchema


class TestTemporalSchema:
    def test_defaults(self):
        config = TemporalSchema()
        assert config.enabled is False
        assert config.server_url == "localhost:7233"
        assert config.namespace == "default"
        assert config.task_queue == "agent-missions"
        assert config.workflow_execution_timeout_days == 30
        assert config.activity_start_to_close_seconds == 600
        assert config.activity_retry_max_attempts == 3
        assert config.approval_timeout_seconds == 14400
        assert config.escalation_timeout_seconds == 86400
        assert config.notification_timeout_seconds == 30

    def test_strict_rejects_unknown_fields(self):
        with pytest.raises(Exception):
            TemporalSchema(unknown_field="oops")

    def test_enabled_requires_explicit_server_url(self):
        with pytest.raises(ValueError, match="server_url must be explicitly configured"):
            TemporalSchema(enabled=True)

    def test_disabled_allows_default_server_url(self):
        config = TemporalSchema(enabled=False)
        assert config.server_url == "localhost:7233"

    def test_custom_values(self):
        config = TemporalSchema(
            enabled=True,
            server_url="temporal.prod:7233",
            task_queue="production-missions",
        )
        assert config.enabled is True
        assert config.server_url == "temporal.prod:7233"
        assert config.task_queue == "production-missions"
