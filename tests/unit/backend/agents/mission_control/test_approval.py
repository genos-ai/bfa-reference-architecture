"""Tests for the approval module.

Mocks only get_app_config (config loading).
Uses real TemporalSchema for accurate feature flag testing.
"""

import pytest
from unittest.mock import MagicMock, patch

from modules.backend.core.config_schema import TemporalSchema


def _mock_app_config(temporal_enabled: bool) -> MagicMock:
    config = MagicMock()
    kwargs = {}
    if temporal_enabled:
        kwargs["server_url"] = "temporal.test:7233"
    config.temporal = TemporalSchema(enabled=temporal_enabled, **kwargs)
    return config


class TestRequestApproval:
    @pytest.mark.asyncio
    async def test_tier3_auto_approves_in_dev_mode(self):
        from modules.backend.agents.mission_control.approval import (
            request_approval,
        )

        with patch(
            "modules.backend.agents.mission_control.approval.get_app_config",
            return_value=_mock_app_config(temporal_enabled=False),
        ):
            result = await request_approval(
                mission_id="test-mission",
                task_id="test-task",
                action="read_file",
                context={},
            )
            assert result["decision"] == "approved"
            assert result["responder_type"] == "automated_rule"

    @pytest.mark.asyncio
    async def test_raises_in_tier4(self):
        from modules.backend.agents.mission_control.approval import (
            request_approval,
        )

        with patch(
            "modules.backend.agents.mission_control.approval.get_app_config",
            return_value=_mock_app_config(temporal_enabled=True),
        ):
            with pytest.raises(RuntimeError, match="Tier 4"):
                await request_approval(
                    mission_id="m", task_id="t", action="a", context={},
                )
