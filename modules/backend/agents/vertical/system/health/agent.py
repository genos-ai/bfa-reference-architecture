"""
System Health Agent (system.health.agent).

Thin wrapper over shared system tool implementations. Checks backend
service health and provides diagnostic advice. Prompts assembled from
the layered config/prompts/ hierarchy. Config received from coordinator.
"""

from collections.abc import AsyncGenerator

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.models import Model

from modules.backend.agents.coordinator.coordinator import assemble_instructions
from modules.backend.agents.deps.base import HealthAgentDeps
from modules.backend.agents.schemas import HealthCheckResult
from modules.backend.agents.tools import system
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def create_agent(model: str | Model) -> Agent[HealthAgentDeps, HealthCheckResult]:
    """Factory: create a health agent with all tools registered.

    Called by AgentRegistry.get_instance() on first use.
    The registry caches the result — this function is not called again
    unless registry.reset() is called.
    """

    instructions = assemble_instructions("system", "health")

    agent = Agent(
        model,
        deps_type=HealthAgentDeps,
        output_type=HealthCheckResult,
        instructions=instructions,
    )

    @agent.tool
    async def check_system_health(ctx: RunContext[HealthAgentDeps]) -> dict:
        """Check the health of all backend services (database, Redis)."""
        return await system.check_system_health()

    @agent.tool
    async def get_app_info(ctx: RunContext[HealthAgentDeps]) -> dict:
        """Get application metadata (name, version, environment, debug mode)."""
        return await system.get_app_info(ctx.deps.app_config)

    logger.info("Health agent created", extra={"model": str(model)})
    return agent


async def run_agent(
    user_message: str,
    deps: HealthAgentDeps,
    agent: Agent[HealthAgentDeps, HealthCheckResult],
    usage_limits: UsageLimits | None = None,
) -> HealthCheckResult:
    """Standard agent entry point. Called by the coordinator.

    The agent instance is provided by the coordinator (from the registry).
    """

    logger.info("Health agent invoked", extra={"message": user_message})
    result = await agent.run(user_message, deps=deps, usage_limits=usage_limits)

    logger.info(
        "Health agent completed",
        extra={
            "summary": result.output.summary,
            "usage": {
                "requests": result.usage().requests,
                "input_tokens": result.usage().input_tokens,
                "output_tokens": result.usage().output_tokens,
            },
        },
    )
    return result.output


async def run_agent_stream(
    user_message: str,
    deps: HealthAgentDeps,
    agent: Agent[HealthAgentDeps, HealthCheckResult],
    conversation_id: str | None = None,
    usage_limits: UsageLimits | None = None,
) -> AsyncGenerator[dict, None]:
    """Standard streaming entry point. Called by the coordinator."""
    result = await run_agent(user_message, deps, agent, usage_limits=usage_limits)
    yield {
        "type": "complete",
        "result": result.model_dump(),
        "conversation_id": conversation_id,
    }
