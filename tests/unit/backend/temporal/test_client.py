"""Tests for Temporal client factory — feature flag gating.

Mocks only get_app_config (config loading, not infra we operate).
Uses real TemporalSchema instances.
"""

import pytest
from unittest.mock import MagicMock, patch

from modules.backend.core.config_schema import TemporalSchema
from modules.backend.temporal.client import get_temporal_config


def _mock_app_config(enabled: bool = False, **overrides) -> MagicMock:
    config = MagicMock()
    config.temporal = TemporalSchema(enabled=enabled, **overrides)
    return config


class TestGetTemporalConfig:
    def test_raises_when_not_enabled(self):
        with patch(
            "modules.backend.temporal.client.get_app_config",
            return_value=_mock_app_config(enabled=False),
        ):
            with pytest.raises(RuntimeError, match="not enabled"):
                get_temporal_config()

    def test_returns_config_when_enabled(self):
        with patch(
            "modules.backend.temporal.client.get_app_config",
            return_value=_mock_app_config(enabled=True),
        ):
            config = get_temporal_config()
            assert config.enabled is True
            assert config.server_url == "localhost:7233"
            assert config.task_queue == "agent-missions"

    def test_custom_config_values(self):
        with patch(
            "modules.backend.temporal.client.get_app_config",
            return_value=_mock_app_config(
                enabled=True,
                task_queue="custom-queue",
                namespace="production",
            ),
        ):
            config = get_temporal_config()
            assert config.task_queue == "custom-queue"
            assert config.namespace == "production"
