"""
Agent-level tests using PydanticAI TestModel.

These tests exercise the full agent chain — LLM -> tool invocation -> structured
output — without making real API calls. TestModel generates deterministic,
schema-valid responses and calls every registered tool.

The ALLOW_MODEL_REQUESTS = False guard in tests/conftest.py ensures that any
test accidentally creating a real model connection fails immediately.
"""

import pytest
from pydantic_ai.models.test import TestModel

from modules.backend.agents.deps.base import FileScope, HealthAgentDeps, QaAgentDeps
from modules.backend.agents.schemas import HealthCheckResult, QaAuditResult
from modules.backend.core.config import find_project_root, get_app_config


@pytest.fixture
def qa_deps():
    """Build QaAgentDeps for testing with a permissive scope."""
    from modules.backend.agents.mission_control.registry import get_registry

    config = get_registry().get("code.qa.agent")
    return QaAgentDeps(
        project_root=find_project_root(),
        scope=FileScope(read_paths=["*"], write_paths=["*"]),
        config=config,
    )


@pytest.fixture
def health_deps():
    """Build HealthAgentDeps for testing."""
    from modules.backend.agents.mission_control.registry import get_registry

    config = get_registry().get("system.health.agent")
    return HealthAgentDeps(
        project_root=find_project_root(),
        scope=FileScope(read_paths=["*"], write_paths=[]),
        config=config,
        app_config=get_app_config(),
    )


@pytest.fixture(autouse=True)
def _reset_agent_instances():
    """Clear registry agent cache before each test so TestModel can be used."""
    from modules.backend.agents.mission_control.registry import get_registry

    get_registry().reset()
    yield
    get_registry().reset()


class TestQaAgentWithTestModel:
    """Tests for code.qa.agent using deterministic TestModel."""

    @pytest.mark.asyncio
    async def test_returns_qa_audit_result_schema(self, qa_deps):
        """TestModel with call_tools='none' validates schema output
        without executing tools (tool tests cover execution separately)."""
        from modules.backend.agents.vertical.code.qa.agent import create_agent

        agent = create_agent(TestModel(call_tools=[]))

        result = await agent.run("run compliance audit", deps=qa_deps)

        assert isinstance(result.output, QaAuditResult)
        assert hasattr(result.output, "summary")
        assert hasattr(result.output, "violations")
        assert hasattr(result.output, "total_violations")
        assert hasattr(result.output, "scanned_files_count")

    @pytest.mark.asyncio
    async def test_usage_is_tracked(self, qa_deps):
        from modules.backend.agents.vertical.code.qa.agent import create_agent

        agent = create_agent(TestModel(call_tools=[]))

        result = await agent.run("check code quality", deps=qa_deps)

        usage = result.usage()
        assert usage.requests >= 1

    @pytest.mark.asyncio
    async def test_run_agent_interface(self, qa_deps):
        """Test the standard run_agent() entry point used by the coordinator."""
        from modules.backend.agents.vertical.code.qa.agent import create_agent, run_agent

        agent = create_agent(TestModel(call_tools=[]))
        result = await run_agent("scan everything", qa_deps, agent)

        assert isinstance(result, QaAuditResult)


class TestHealthAgentWithTestModel:
    """Tests for system.health.agent using deterministic TestModel."""

    @pytest.mark.asyncio
    async def test_returns_health_check_result_schema(self, health_deps):
        """TestModel with call_tools='none' validates schema output."""
        from modules.backend.agents.vertical.system.health.agent import create_agent

        agent = create_agent(TestModel(call_tools=[]))

        result = await agent.run("check system health", deps=health_deps)

        assert isinstance(result.output, HealthCheckResult)
        assert hasattr(result.output, "summary")
        assert hasattr(result.output, "components")
        assert hasattr(result.output, "advice")

    @pytest.mark.asyncio
    async def test_usage_is_tracked(self, health_deps):
        from modules.backend.agents.vertical.system.health.agent import create_agent

        agent = create_agent(TestModel(call_tools=[]))

        result = await agent.run("ping", deps=health_deps)

        usage = result.usage()
        assert usage.requests >= 1

    @pytest.mark.asyncio
    async def test_run_agent_interface(self, health_deps):
        """Test the standard run_agent() entry point used by the coordinator."""
        from modules.backend.agents.vertical.system.health.agent import create_agent, run_agent

        agent = create_agent(TestModel(call_tools=[]))
        result = await run_agent("how is the system", health_deps, agent)

        assert isinstance(result, HealthCheckResult)


class TestAllowModelRequestsGuard:
    """Verify the CI guardrail prevents real LLM calls."""

    def test_guard_is_active(self):
        """ALLOW_MODEL_REQUESTS = False is set in conftest.py."""
        from pydantic_ai import models

        assert models.ALLOW_MODEL_REQUESTS is False
