"""
System Health Agent (system.health.agent).

Thin wrapper over shared system tool implementations. Checks backend
service health and provides diagnostic advice. Prompts assembled from
the layered config/prompts/ hierarchy.
"""

from typing import Any

from pydantic_ai import Agent, RunContext

from modules.backend.agents.coordinator.coordinator import assemble_instructions, build_deps_from_config
from modules.backend.agents.deps.base import HealthAgentDeps
from modules.backend.agents.schemas import HealthCheckResult
from modules.backend.agents.tools import system
from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger
from modules.backend.services.compliance import load_config as _load_qa_config

logger = get_logger(__name__)

_agent: Agent[HealthAgentDeps, HealthCheckResult] | None = None


def _load_agent_config() -> dict[str, Any]:
    """Load health agent configuration from YAML."""
    import yaml
    from modules.backend.core.config import find_project_root
    config_path = find_project_root() / "config" / "agents" / "system" / "health" / "agent.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Agent config not found: {config_path}")
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def _get_agent() -> Agent[HealthAgentDeps, HealthCheckResult]:
    """Lazy initialization — creates the agent on first call."""
    global _agent
    if _agent is not None:
        return _agent

    import os
    from modules.backend.core.config import get_settings
    settings = get_settings()
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)

    config = _load_agent_config()
    model = config["model"]
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


async def run_health_agent(user_message: str) -> HealthCheckResult:
    """Run the health agent. Returns structured health check result."""
    agent = _get_agent()
    config = _load_agent_config()
    deps = HealthAgentDeps(
        **build_deps_from_config(config),
        app_config=get_app_config(),
    )

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
