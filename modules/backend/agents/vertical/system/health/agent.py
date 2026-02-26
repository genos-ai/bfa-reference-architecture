"""
System Health Agent (system.health.agent).

Thin wrapper over shared system tool implementations. Checks backend
service health and provides diagnostic advice. Prompts assembled from
the layered config/prompts/ hierarchy. Config received from coordinator.
"""

from collections.abc import AsyncGenerator

from pydantic_ai import Agent, RunContext, UsageLimits

from modules.backend.agents.coordinator.coordinator import assemble_instructions
from modules.backend.agents.deps.base import HealthAgentDeps
from modules.backend.agents.schemas import HealthCheckResult
from modules.backend.agents.tools import system
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

_agent: Agent[HealthAgentDeps, HealthCheckResult] | None = None


def _get_agent(model: str) -> Agent[HealthAgentDeps, HealthCheckResult]:
    """Lazy initialization — creates the agent on first call."""
    global _agent
    if _agent is not None:
        return _agent

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

    _agent = agent
    logger.info("Health agent initialized", extra={"model": model})
    return _agent


async def run_agent(
    user_message: str,
    deps: HealthAgentDeps,
    usage_limits: UsageLimits | None = None,
) -> HealthCheckResult:
    """Standard agent entry point. Called by the coordinator."""
    model = deps.config.model
    agent = _get_agent(model)

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
    conversation_id: str | None = None,
    usage_limits: UsageLimits | None = None,
) -> AsyncGenerator[dict, None]:
    """Standard streaming entry point. Called by the coordinator."""
    result = await run_agent(user_message, deps, usage_limits)
    yield {
        "type": "complete",
        "result": result.model_dump(),
        "conversation_id": conversation_id,
    }
