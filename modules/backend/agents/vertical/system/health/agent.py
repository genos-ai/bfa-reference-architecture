"""
System Health Agent (system.health.agent).

PydanticAI agent that checks system health and provides
diagnostic advice in natural language. Uses the existing
health check functions from modules/backend/api/health.py
as tools.

Usage:
    from modules.backend.agents.vertical.system.health.agent import run_health_agent
    result = await run_health_agent("How is the system doing?")
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from modules.backend.core.config import find_project_root, get_app_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a system health diagnostic agent. "
    "You check the health of backend services and provide clear, "
    "actionable advice. Be concise. Report what is healthy, what is "
    "unhealthy, and suggest specific fixes for any issues found."
)
# NOTE: This constant is in the agent system prompt.
# Moving it to config would require significant refactoring of agent initialization.
# It is kept here because it represents core behavioral instructions for the agent.


@dataclass
class HealthAgentDeps:
    """Dependencies injected into the health agent at runtime."""

    app_config: Any


class HealthCheckResult(BaseModel):
    """Structured output from the health agent."""

    summary: str
    components: dict[str, str]
    advice: str | None = None


def _load_agent_config() -> dict:
    """Load health agent configuration from YAML."""
    project_root = find_project_root()
    config_path = project_root / "config" / "agents" / "system" / "health" / "agent.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Agent config not found: {config_path}")

    with open(config_path) as f:
        import yaml
        return yaml.safe_load(f) or {}


_agent: Agent[HealthAgentDeps, HealthCheckResult] | None = None


def _get_agent() -> Agent[HealthAgentDeps, HealthCheckResult]:
    """Lazy initialization — only creates the agent when first called."""
    global _agent
    if _agent is not None:
        return _agent

    import os

    from modules.backend.core.config import get_settings

    settings = get_settings()
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)

    config = _load_agent_config()
    model = config["model"]

    agent = Agent(
        model,
        deps_type=HealthAgentDeps,
        output_type=HealthCheckResult,
        instructions=SYSTEM_PROMPT,
    )

    @agent.tool
    async def check_system_health(ctx: RunContext[HealthAgentDeps]) -> dict:
        """Check the health of all backend services (database, Redis).

        Returns status, latency, and error details for each component.
        """
        import asyncio

        from modules.backend.api.health import check_database, check_redis

        db_check, redis_check = await asyncio.gather(
            check_database(),
            check_redis(),
            return_exceptions=True,
        )

        if isinstance(db_check, Exception):
            db_check = {"status": "error", "error": str(db_check)}
        if isinstance(redis_check, Exception):
            redis_check = {"status": "error", "error": str(redis_check)}

        return {
            "database": db_check,
            "redis": redis_check,
        }

    @agent.tool
    async def get_app_info(ctx: RunContext[HealthAgentDeps]) -> dict:
        """Get application metadata (name, version, environment, debug mode)."""
        app = ctx.deps.app_config.application
        return {
            "name": app.name,
            "version": app.version,
            "environment": app.environment,
            "debug": app.debug,
        }

    _agent = agent
    logger.info("Health agent initialized", extra={"model": model})
    return _agent


async def run_health_agent(user_message: str) -> HealthCheckResult:
    """
    Run the health agent with a user message.

    Args:
        user_message: The user's health-related question

    Returns:
        HealthCheckResult with summary, component status, and advice
    """
    agent = _get_agent()
    deps = HealthAgentDeps(app_config=get_app_config())

    logger.info("Health agent invoked", extra={"message": user_message})

    result = await agent.run(user_message, deps=deps)

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
