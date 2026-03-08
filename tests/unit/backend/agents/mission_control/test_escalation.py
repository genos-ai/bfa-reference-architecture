"""Tests for escalation chain logic.

Pure deterministic logic — no mocks, no infrastructure.
"""

import pytest

from modules.backend.agents.mission_control.escalation import (
    ESCALATION_CHAIN,
    evaluate_automated_rules,
    evaluate_risk_matrix,
    get_escalation_level,
    get_next_escalation,
)


class TestEscalationChain:
    def test_four_levels_exist(self):
        assert len(ESCALATION_CHAIN) == 4
        assert ESCALATION_CHAIN[0].level == 1
        assert ESCALATION_CHAIN[-1].level == 4

    def test_no_ai_responders(self):
        """P2: all escalation is deterministic, no AI in the chain."""
        for level in ESCALATION_CHAIN:
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

    def test_level3_has_timeout(self):
        level = get_escalation_level(3)
        assert level is not None
        assert level.timeout_seconds == 14400  # 4 hours

    def test_level4_has_longer_timeout(self):
        level = get_escalation_level(4)
        assert level is not None
        assert level.timeout_seconds == 86400  # 24 hours


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
                "allowed_agents": {"code.qa.agent"},
                "agent_name": "code.qa.agent",
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
