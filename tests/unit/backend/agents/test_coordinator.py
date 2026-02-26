"""
Unit Tests for coordinator, registry, router, and middleware.

Tests exercise real config loading, registry discovery, keyword routing,
and guardrail enforcement.
"""

import pytest

from modules.backend.agents.coordinator.middleware import (
    _load_coordinator_config,
    compute_cost_usd,
)
from modules.backend.agents.coordinator.models import CoordinatorRequest, CoordinatorResponse
from modules.backend.agents.coordinator.registry import AgentRegistry, get_registry
from modules.backend.agents.coordinator.router import RuleBasedRouter


class TestAgentRegistry:
    """Tests for agent registry discovery from YAML."""

    def test_discovers_agents_from_config(self):
        registry = get_registry()
        agents = registry.list_all()
        names = [a["agent_name"] for a in agents]
        assert "code.qa.agent" in names
        assert "system.health.agent" in names

    def test_get_returns_config(self):
        from modules.backend.agents.config_schema import AgentConfigSchema

        registry = get_registry()
        config = registry.get("code.qa.agent")
        assert isinstance(config, AgentConfigSchema)
        assert config.agent_name == "code.qa.agent"
        assert config.enabled is True
        assert config.model is not None

    def test_get_raises_for_unknown(self):
        registry = get_registry()
        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent.agent")

    def test_has_returns_true_for_known(self):
        registry = get_registry()
        assert registry.has("code.qa.agent") is True

    def test_has_returns_false_for_unknown(self):
        registry = get_registry()
        assert registry.has("nonexistent.agent") is False

    def test_get_by_keyword_matches(self):
        registry = get_registry()
        assert registry.get_by_keyword("run compliance audit") == "code.qa.agent"
        assert registry.get_by_keyword("check system health") == "system.health.agent"

    def test_get_by_keyword_returns_none_for_no_match(self):
        registry = get_registry()
        assert registry.get_by_keyword("bake a cake") is None

    def test_resolve_module_path_vertical(self):
        registry = get_registry()
        path = registry.resolve_module_path("code.qa.agent")
        assert path == "modules.backend.agents.vertical.code.qa.agent"

    def test_resolve_module_path_system(self):
        registry = get_registry()
        path = registry.resolve_module_path("system.health.agent")
        assert path == "modules.backend.agents.vertical.system.health.agent"


class TestRuleBasedRouter:
    """Tests for keyword-based routing."""

    def test_routes_by_keyword(self):
        registry = get_registry()
        router = RuleBasedRouter(registry)
        request = CoordinatorRequest(user_input="run compliance audit")
        assert router.route(request) == "code.qa.agent"

    def test_routes_health_keywords(self):
        registry = get_registry()
        router = RuleBasedRouter(registry)
        request = CoordinatorRequest(user_input="check system health status")
        assert router.route(request) == "system.health.agent"

    def test_returns_none_for_no_match(self):
        registry = get_registry()
        router = RuleBasedRouter(registry)
        request = CoordinatorRequest(user_input="make me a sandwich")
        assert router.route(request) is None

    def test_direct_agent_takes_priority(self):
        registry = get_registry()
        router = RuleBasedRouter(registry)
        request = CoordinatorRequest(
            user_input="check health",
            agent="code.qa.agent",
        )
        assert router.route(request) == "code.qa.agent"


class TestCoordinatorModels:
    """Tests for typed request/response models."""

    def test_request_defaults(self):
        req = CoordinatorRequest(user_input="hello")
        assert req.agent is None
        assert req.conversation_id is None
        assert req.channel == "api"

    def test_response_structure(self):
        resp = CoordinatorResponse(
            agent_name="code.qa.agent",
            output="Found 3 violations",
            metadata={"total_violations": 3},
        )
        assert resp.agent_name == "code.qa.agent"
        assert resp.metadata["total_violations"] == 3


class TestMiddleware:
    """Tests for middleware configuration and cost computation."""

    def test_coordinator_config_loads(self):
        from modules.backend.agents.config_schema import CoordinatorConfigSchema

        config = _load_coordinator_config()
        assert isinstance(config, CoordinatorConfigSchema)
        assert config.routing is not None
        assert config.limits is not None
        assert config.guardrails is not None

    def test_compute_cost_zero_tokens(self):
        cost = compute_cost_usd(0, 0, "anthropic:claude-haiku-4-5-20251001")
        assert cost == 0.0

    def test_compute_cost_known_model(self):
        cost = compute_cost_usd(1_000_000, 1_000_000, "anthropic:claude-haiku-4-5-20251001")
        assert cost > 0

    def test_compute_cost_unknown_model_uses_default(self):
        cost = compute_cost_usd(1_000_000, 1_000_000, "unknown:model")
        assert cost > 0
