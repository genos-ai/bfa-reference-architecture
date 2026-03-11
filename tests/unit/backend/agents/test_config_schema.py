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


class TestAgentConfigMalformed:
    """Tests for malformed agent config data."""

    def test_wrong_type_for_enabled(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentConfigSchema(
                agent_name="test.agent",
                agent_type="vertical",
                description="test",
                enabled="not_a_bool",
                model="anthropic:test",
                max_input_length=1000,
                max_budget_usd=1.0,
                execution={"mode": "local"},
            )

    def test_wrong_type_for_max_input_length(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentConfigSchema(
                agent_name="test.agent",
                agent_type="vertical",
                description="test",
                enabled=True,
                model="anthropic:test",
                max_input_length="not_an_int",
                max_budget_usd=1.0,
                execution={"mode": "local"},
            )


class TestFeaturesSchemaValidation:
    """Tests for features.yaml schema validation."""

    def test_rejects_unknown_feature_flag(self):
        from pydantic import ValidationError

        from modules.backend.core.config_schema import FeaturesSchema

        with pytest.raises(ValidationError, match="extra"):
            FeaturesSchema(
                auth_require_email_verification=True,
                auth_allow_api_key_creation=True,
                auth_rate_limit_enabled=True,
                auth_require_api_authentication=True,
                api_detailed_errors=False,
                api_request_logging=True,
                channel_telegram_enabled=False,
                channel_slack_enabled=False,
                channel_discord_enabled=False,
                channel_whatsapp_enabled=False,
                gateway_enabled=True,
                gateway_websocket_enabled=True,
                gateway_pairing_enabled=True,
                agent_coordinator_enabled=True,
                agent_streaming_enabled=True,
                mcp_enabled=False,
                a2a_enabled=False,
                security_startup_checks_enabled=True,
                security_headers_enabled=True,
                security_cors_enforce_production=False,
                experimental_background_tasks_enabled=False,
                events_publish_enabled=True,
                typo_feature_flag=True,
            )

    def test_rejects_missing_feature_flag(self):
        from pydantic import ValidationError

        from modules.backend.core.config_schema import FeaturesSchema

        with pytest.raises(ValidationError):
            FeaturesSchema(
                auth_require_email_verification=True,
                # Missing all other required fields
            )


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
