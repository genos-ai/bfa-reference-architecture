"""
Unit tests for agent configuration schemas.

Validates that real YAML config files pass schema validation, and that
malformed configs are caught with clear errors.
"""

import pytest
import yaml

from modules.backend.agents.config_schema import (
    AgentConfigSchema,
    MissionControlConfigSchema,
)
from modules.backend.core.config import find_project_root


class TestAgentConfigSchema:
    """Tests for agent YAML schema validation."""

    def test_qa_agent_config_validates(self):
        path = find_project_root() / "config" / "agents" / "code" / "qa" / "agent.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = AgentConfigSchema(**raw)
        assert config.agent_name == "code.qa.agent"
        assert config.agent_type == "vertical"
        assert config.enabled is True
        assert len(config.rules) > 0
        assert config.exclusions is not None

    def test_health_agent_config_validates(self):
        path = find_project_root() / "config" / "agents" / "system" / "health" / "agent.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = AgentConfigSchema(**raw)
        assert config.agent_name == "system.health.agent"
        assert config.rules is None
        assert config.exclusions is None

    def test_rejects_unknown_field(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="extra"):
            AgentConfigSchema(
                agent_name="test.agent",
                agent_type="vertical",
                description="test",
                enabled=True,
                model="anthropic:test",
                max_input_length=1000,
                max_budget_usd=1.0,
                execution={"mode": "local"},
                unknown_field="should fail",
            )

    def test_rejects_missing_required_field(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentConfigSchema(
                agent_name="test.agent",
            )

    def test_model_dump_produces_dict(self):
        path = find_project_root() / "config" / "agents" / "code" / "qa" / "agent.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = AgentConfigSchema(**raw)
        dumped = config.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["agent_name"] == "code.qa.agent"


class TestMissionControlConfigSchema:
    """Tests for mission control YAML schema validation."""

    def test_mission_control_config_validates(self):
        path = find_project_root() / "config" / "agents" / "mission_control.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = MissionControlConfigSchema(**raw)
        assert config.routing.strategy == "hybrid"
        assert config.limits.max_requests_per_task > 0
        assert config.guardrails.max_input_length > 0
        assert len(config.model_pricing) > 0

    def test_pricing_rates_accessible(self):
        path = find_project_root() / "config" / "agents" / "mission_control.yaml"
        with open(path) as f:
            raw = yaml.safe_load(f)
        config = MissionControlConfigSchema(**raw)
        default_rates = config.model_pricing.get("default")
        assert default_rates is not None
        assert default_rates.input > 0
        assert default_rates.output > 0

    def test_rejects_unknown_field(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="extra"):
            MissionControlConfigSchema(
                model_pricing={},
                routing={
                    "strategy": "rule",
                    "llm_model": "test",
                    "complex_request_agent": "test",
                    "fallback_agent": "test",
                    "max_routing_depth": 1,
                },
                limits={
                    "max_requests_per_task": 1,
                    "max_tool_calls_per_task": 1,
                    "max_tokens_per_task": 1,
                    "max_cost_per_plan": 1.0,
                    "max_cost_per_user_daily": 1.0,
                    "task_timeout_seconds": 1,
                    "plan_timeout_seconds": 1,
                },
                guardrails={"max_input_length": 1, "injection_patterns": []},
                redis_ttl={"session": 1, "approval": 1, "lock": 1, "result": 1},
                approval={"poll_interval_seconds": 1, "timeout_seconds": 1},
                rogue_key="should fail",
            )
