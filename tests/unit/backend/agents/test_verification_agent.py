"""Verification Agent tests using PydanticAI TestModel.

Tests the agent's structured output schema and interface.
No real API calls — TestModel generates deterministic, schema-valid responses.
"""

import pytest
from pydantic_ai.models.test import TestModel

from modules.backend.agents.deps.base import BaseAgentDeps, FileScope
from modules.backend.agents.horizontal.verification.agent import (
    VerificationEvaluation,
    create_agent,
    run_agent,
)
from modules.backend.core.config import find_project_root


@pytest.fixture
def verification_deps():
    """Build BaseAgentDeps for Verification Agent testing."""
    return BaseAgentDeps(
        project_root=find_project_root(),
        scope=FileScope(read_paths=[], write_paths=[]),
    )


class TestVerificationAgentWithTestModel:
    """Tests for horizontal.verification.agent using TestModel."""

    @pytest.mark.asyncio
    async def test_returns_verification_evaluation(self, verification_deps):
        agent = create_agent(TestModel(call_tools=[]))
        result = await agent.run(
            "Evaluate this output against the criteria.", deps=verification_deps,
        )

        assert isinstance(result.output, VerificationEvaluation)
        assert hasattr(result.output, "overall_score")
        assert hasattr(result.output, "passed")
        assert hasattr(result.output, "criteria_results")
        assert hasattr(result.output, "blocking_issues")
        assert hasattr(result.output, "recommendations")

    @pytest.mark.asyncio
    async def test_score_range(self, verification_deps):
        agent = create_agent(TestModel(call_tools=[]))
        result = await agent.run(
            "Evaluate this output.", deps=verification_deps,
        )
        assert 0.0 <= result.output.overall_score <= 1.0

    @pytest.mark.asyncio
    async def test_run_agent_interface(self, verification_deps):
        agent = create_agent(TestModel(call_tools=[]))
        result = await run_agent("Evaluate output.", verification_deps, agent)

        assert isinstance(result, VerificationEvaluation)

    @pytest.mark.asyncio
    async def test_agent_has_no_tools(self, verification_deps):
        """Verification Agent has no tools — pure evaluation."""
        agent = create_agent(TestModel(call_tools=[]))
        assert len(agent._function_toolset.tools) == 0

    @pytest.mark.asyncio
    async def test_usage_is_tracked(self, verification_deps):
        agent = create_agent(TestModel(call_tools=[]))
        result = await agent.run("Evaluate.", deps=verification_deps)
        usage = result.usage()
        assert usage.requests >= 1
