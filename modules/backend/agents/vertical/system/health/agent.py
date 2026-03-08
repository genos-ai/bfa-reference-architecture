"""
System Health Agent (system.health.agent).

Read-only health audit of the platform: log errors, config validation,
dependency consistency, and file structure. Reports but does not fix (P13).
Prompts assembled from the layered config/prompts/ hierarchy.
"""

from collections.abc import AsyncGenerator

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.models import Model

from modules.backend.agents.deps.base import HealthAgentDeps
from modules.backend.agents.mission_control.helpers import assemble_instructions
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
    async def scan_log_errors(ctx: RunContext[HealthAgentDeps]) -> dict:
        """Scan system.jsonl for errors, warnings, and patterns."""
        return await system.scan_log_errors(
            ctx.deps.project_root, ctx.deps.scope,
        )

    @agent.tool
    async def validate_config(ctx: RunContext[HealthAgentDeps]) -> dict:
        """Validate all YAML config files and .env secrets."""
        return await system.validate_config_files(
            ctx.deps.project_root, ctx.deps.scope,
        )

    @agent.tool
    async def check_dependencies(ctx: RunContext[HealthAgentDeps]) -> dict:
        """Check Python dependencies for consistency with requirements.txt."""
        return await system.check_dependencies(
            ctx.deps.project_root, ctx.deps.scope,
        )

    @agent.tool
    async def check_file_structure(ctx: RunContext[HealthAgentDeps]) -> dict:
        """Validate expected project file structure exists."""
        return await system.check_file_structure(
            ctx.deps.project_root, ctx.deps.scope,
        )

    @agent.tool
    async def get_app_info(ctx: RunContext[HealthAgentDeps]) -> dict:
        """Get application metadata (name, version, environment, debug mode)."""
        return await system.get_app_info(ctx.deps.app_config)

    logger.info(
        "Health agent created (read-only audit)",
        extra={"model": str(model)},
    )
    return agent


async def run_agent(
    user_message: str,
    deps: HealthAgentDeps,
    agent: Agent[HealthAgentDeps, HealthCheckResult],
    usage_limits: UsageLimits | None = None,
) -> HealthCheckResult:
    """Standard agent entry point. Called by mission control."""

    logger.info("Health agent invoked", extra={"message": user_message})
    result = await agent.run(user_message, deps=deps, usage_limits=usage_limits)

    logger.info(
        "Health agent completed",
        extra={
            "summary": result.output.summary,
            "overall_status": result.output.overall_status,
            "error_count": result.output.error_count,
            "warning_count": result.output.warning_count,
            "checks_performed": result.output.checks_performed,
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
    """Standard streaming entry point. Called by mission control."""
    result = await run_agent(user_message, deps, agent, usage_limits=usage_limits)
    yield {
        "type": "complete",
        "result": result.model_dump(),
        "conversation_id": conversation_id,
    }
