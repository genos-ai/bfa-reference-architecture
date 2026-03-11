"""Tests for escalation chain logic.

Pure deterministic logic — no mocks needed for rules.
Config mock needed for escalation chain timeouts.
"""

from unittest.mock import MagicMock, patch

import pytest

from modules.backend.agents.mission_control.escalation import (
    evaluate_automated_rules,
    evaluate_risk_matrix,
    get_escalation_chain,
    get_escalation_level,
    get_next_escalation,
)


def _mock_app_config(
    approval_timeout=14400,
    escalation_timeout=86400,
):
    config = MagicMock()
    config.temporal.approval_timeout_seconds = approval_timeout
    config.temporal.escalation_timeout_seconds = escalation_timeout
    return config


@pytest.fixture(autouse=True)
def _patch_config():
    with patch(
        "modules.backend.agents.mission_control.escalation.get_app_config",
        return_value=_mock_app_config(),
    ):
        yield


class TestEscalationChain:
    def test_four_levels_exist(self):
        chain = get_escalation_chain()
        assert len(chain) == 4
        assert chain[0].level == 1
        assert chain[-1].level == 4

    def test_no_ai_responders(self):
        """P2: all escalation is deterministic, no AI in the chain."""
        for level in get_escalation_chain():
            assert "ai_" not in level.responder_type

    def test_get_escalation_level(self):
        level = get_escalation_level(1)
        assert level is not None
        assert level.responder_type == "automated_rule_low_risk"

    def test_get_escalation_level_invalid(self):
        assert get_escalation_level(99) is None

    def test_get_next_escalation(self):
        next_level = get_next_escalation(1)
        assert next_level is not None
        assert next_level.level == 2

    def test_get_next_escalation_at_max(self):
        assert get_next_escalation(4) is None

    def test_level3_timeout_from_config(self):
        level = get_escalation_level(3)
        assert level is not None
        assert level.timeout_seconds == 14400

    def test_level4_timeout_from_config(self):
        level = get_escalation_level(4)
        assert level is not None
        assert level.timeout_seconds == 86400

    def test_custom_timeouts_from_config(self):
        """Verify timeouts are driven by config, not hardcoded."""
        with patch(
            "modules.backend.agents.mission_control.escalation.get_app_config",
            return_value=_mock_app_config(
                approval_timeout=7200,
                escalation_timeout=43200,
            ),
        ):
            level3 = get_escalation_level(3)
            level4 = get_escalation_level(4)
            assert level3 is not None
            assert level3.timeout_seconds == 7200
            assert level4 is not None
            assert level4.timeout_seconds == 43200


class TestAutomatedRules:
    @pytest.mark.asyncio
    async def test_approve_low_risk_action(self):
        result = await evaluate_automated_rules("read_file", {})
        assert result is not None
        assert result["decision"] == "approved"
        assert result["responder_type"] == "automated_rule"

    @pytest.mark.asyncio
    async def test_approve_low_cost(self):
        result = await evaluate_automated_rules(
            "invoke_agent", {"estimated_cost_usd": 0.50},
        )
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_approve_retry(self):
        result = await evaluate_automated_rules(
            "invoke_agent", {"is_retry": True, "retry_count": 1},
        )
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_skip_high_risk(self):
        result = await evaluate_automated_rules(
            "deploy_to_production", {"estimated_cost_usd": 100.0},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_skip_too_many_retries(self):
        result = await evaluate_automated_rules(
            "invoke_agent",
            {"is_retry": True, "retry_count": 10, "estimated_cost_usd": 5.0},
        )
        assert result is None


class TestRiskMatrix:
    @pytest.mark.asyncio
    async def test_approve_medium_risk_known_agent(self):
        result = await evaluate_risk_matrix(
            "invoke_agent",
            {
                "estimated_cost_usd": 5.0,
                "allowed_agents": {"code.quality.agent"},
                "agent_name": "code.quality.agent",
            },
        )
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_escalate_high_cost(self):
        result = await evaluate_risk_matrix(
            "invoke_agent", {"estimated_cost_usd": 50.0},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_approve_safe_error_category(self):
        result = await evaluate_risk_matrix(
            "unknown_action", {"error_category": "timeout"},
        )
        assert result is not None
        assert result["decision"] == "approved"

    @pytest.mark.asyncio
    async def test_approve_rate_limit_error(self):
        result = await evaluate_risk_matrix(
            "invoke_agent", {"error_category": "rate_limit"},
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_escalate_unknown_error(self):
        result = await evaluate_risk_matrix(
            "unknown_action", {"error_category": "data_corruption"},
        )
        assert result is None
