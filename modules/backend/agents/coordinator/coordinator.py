"""
Agent Coordinator.

Routes user requests to the appropriate vertical agent. Assembles
layered prompt instructions, builds agent deps from YAML config,
dynamically discovers agent executors from the registry, and composes
middleware around every execution.

No agent-specific code in this file. Adding a new agent requires only
a YAML config and an agent.py with run_agent() / run_agent_stream()
— no coordinator changes needed.

Public interface:
    handle(user_input) -> dict
    handle_direct(agent_name, user_input) -> dict
    handle_direct_stream(agent_name, user_input, conversation_id) -> AsyncGenerator
    list_agents() -> list[dict]
"""

import importlib
import os
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

import yaml
from pydantic_ai import UsageLimits

from modules.backend.agents.coordinator.middleware import (
    _load_coordinator_config,
    with_cost_tracking,
    with_guardrails,
)
from modules.backend.agents.coordinator.registry import get_registry
from modules.backend.agents.coordinator.router import RuleBasedRouter
from modules.backend.agents.deps.base import (
    BaseAgentDeps,
    FileScope,
    HealthAgentDeps,
    QaAgentDeps,
)
from modules.backend.core.config import find_project_root, get_app_config, get_settings
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

_api_key_set = False


def _ensure_api_key() -> None:
    """Set the ANTHROPIC_API_KEY once at coordinator level."""
    global _api_key_set
    if _api_key_set:
        return
    settings = get_settings()
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    _api_key_set = True


# =============================================================================
# Prompt Assembly
# =============================================================================


def assemble_instructions(category: str, name: str) -> str:
    """Compose layered prompt: organization -> category -> agent.

    Reads markdown files from config/prompts/ and concatenates them.
    Missing layers are silently skipped.
    """
    project_root = find_project_root()
    prompts_dir = project_root / "config" / "prompts"
    layers: list[str] = []

    org_dir = prompts_dir / "organization"
    if org_dir.exists():
        for org_file in sorted(org_dir.glob("*.md")):
            layers.append(org_file.read_text(encoding="utf-8").strip())

    cat_file = prompts_dir / "categories" / f"{category}.md"
    if cat_file.exists():
        layers.append(cat_file.read_text(encoding="utf-8").strip())

    agent_file = prompts_dir / "agents" / category / name / "system.md"
    if agent_file.exists():
        layers.append(agent_file.read_text(encoding="utf-8").strip())

    return "\n\n".join(layers)


# =============================================================================
# Deps Construction
# =============================================================================


def build_deps_from_config(agent_config: dict[str, Any]) -> dict[str, Any]:
    """Build common dep fields from agent YAML config."""
    scope_config = agent_config.get("scope", {})
    scope = FileScope(
        read_paths=scope_config.get("read", []),
        write_paths=scope_config.get("write", []),
    )
    return {
        "project_root": find_project_root(),
        "scope": scope,
        "config": agent_config,
    }


def _build_agent_deps(agent_name: str, agent_config: dict[str, Any]) -> BaseAgentDeps:
    """Build the appropriate deps dataclass for a given agent."""
    common = build_deps_from_config(agent_config)
    category = agent_name.split(".")[0]

    if category == "system" and "health" in agent_name:
        return HealthAgentDeps(**common, app_config=get_app_config())
    if category == "code" and "qa" in agent_name:
        return QaAgentDeps(**common)

    return BaseAgentDeps(**common)


# =============================================================================
# UsageLimits
# =============================================================================


def _get_usage_limits() -> UsageLimits:
    """Build UsageLimits from coordinator.yaml."""
    config = _load_coordinator_config()
    limits = config.get("limits", {})
    return UsageLimits(
        request_limit=limits.get("max_requests_per_task", 10),
        total_tokens_limit=limits.get("max_tokens_per_task", 50000),
    )


# =============================================================================
# Dynamic Executor Discovery
# =============================================================================


def _import_agent_module(agent_name: str) -> Any:
    """Dynamically import an agent module from the registry."""
    registry = get_registry()
    module_path = registry.resolve_module_path(agent_name)
    return importlib.import_module(module_path)


def _format_response(agent_name: str, result: Any) -> "CoordinatorResponse":
    """Format an agent result into a standard CoordinatorResponse.

    Every agent returns a Pydantic BaseModel. We extract the summary as
    the output string and pack the full model data into metadata.
    """
    from modules.backend.agents.coordinator.models import CoordinatorResponse

    if hasattr(result, "model_dump"):
        data = result.model_dump()
    else:
        data = {"raw": str(result)}

    output = data.pop("summary", str(result))

    return CoordinatorResponse(
        agent_name=agent_name,
        output=output,
        metadata=data,
    )


async def _execute_agent(
    agent_name: str,
    user_input: str,
    agent_config: dict[str, Any],
) -> dict[str, Any]:
    """Execute any agent dynamically. No agent-specific code needed.

    1. Import the agent module from registry
    2. Build deps from config
    3. Call agent_module.run_agent(user_input, deps, usage_limits)
    4. Format into standard CoordinatorResponse and return as dict

    Returns dict for backward compatibility with API endpoints.
    The dict is a flattened CoordinatorResponse: {agent_name, output, **metadata}.
    """
    _ensure_api_key()
    module = _import_agent_module(agent_name)
    deps = _build_agent_deps(agent_name, agent_config)
    limits = _get_usage_limits()

    result = await module.run_agent(user_input, deps, usage_limits=limits)
    response = _format_response(agent_name, result)

    return {
        "agent_name": response.agent_name,
        "output": response.output,
        **response.metadata,
    }


# =============================================================================
# Public Interface
# =============================================================================


def list_agents() -> list[dict[str, Any]]:
    """List all available agents with their metadata."""
    return get_registry().list_all()


async def handle(user_input: str) -> dict[str, Any]:
    """Route a user request to the appropriate agent via keyword matching.

    Falls back to the configured fallback_agent when no keyword matches.

    Raises:
        ValueError: If no agent matches and no fallback is configured.
    """
    from modules.backend.agents.coordinator.models import CoordinatorRequest

    registry = get_registry()
    router = RuleBasedRouter(registry)
    request = CoordinatorRequest(user_input=user_input)

    agent_name = router.route(request)

    if agent_name is None:
        coordinator_config = _load_coordinator_config()
        fallback = coordinator_config.get("routing", {}).get("fallback_agent")
        if fallback and registry.has(fallback):
            agent_name = fallback
            logger.debug("Using fallback agent", extra={"agent_name": fallback})
        else:
            available = ", ".join(c["agent_name"] for c in registry.list_all()) or "none"
            raise ValueError(f"No agent matched. Available agents: {available}.")

    agent_config = registry.get(agent_name)

    @with_guardrails(agent_config)
    @with_cost_tracking
    async def _run(user_input: str) -> dict[str, Any]:
        return await _execute_agent(agent_name, user_input, agent_config)

    return await _run(user_input)


async def handle_direct(agent_name: str, user_input: str) -> dict[str, Any]:
    """Send a message directly to a named agent, bypassing routing.

    Raises:
        ValueError: If the agent does not exist.
    """
    registry = get_registry()
    if not registry.has(agent_name):
        available = ", ".join(c["agent_name"] for c in registry.list_all()) or "none"
        raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

    agent_config = registry.get(agent_name)
    logger.info("Direct agent invocation", extra={"agent_name": agent_name})

    @with_guardrails(agent_config)
    @with_cost_tracking
    async def _run(user_input: str) -> dict[str, Any]:
        return await _execute_agent(agent_name, user_input, agent_config)

    return await _run(user_input)


async def handle_direct_stream(
    agent_name: str,
    user_input: str,
    conversation_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream progress events from any agent that supports streaming.

    Dynamically imports the agent module and calls run_agent_stream().
    No agent-specific checks — any agent with run_agent_stream() works.
    """
    registry = get_registry()
    if not registry.has(agent_name):
        available = ", ".join(c["agent_name"] for c in registry.list_all()) or "none"
        raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

    logger.info(
        "Direct agent invocation (stream)",
        extra={"agent_name": agent_name, "conversation_id": conversation_id},
    )

    _ensure_api_key()
    agent_config = registry.get(agent_name)
    module = _import_agent_module(agent_name)

    if hasattr(module, "run_agent_stream"):
        deps = _build_agent_deps(agent_name, agent_config)
        limits = _get_usage_limits()
        async for event in module.run_agent_stream(
            user_input, deps, conversation_id=conversation_id, usage_limits=limits,
        ):
            yield event
    else:
        result = await _execute_agent(agent_name, user_input, agent_config)
        yield {"type": "complete", "result": result}


def _route(user_input: str) -> str:
    """Route user input to an agent name. Used by the API streaming endpoint."""
    from modules.backend.agents.coordinator.models import CoordinatorRequest

    registry = get_registry()
    router = RuleBasedRouter(registry)
    request = CoordinatorRequest(user_input=user_input)

    agent_name = router.route(request)
    if agent_name is None:
        coordinator_config = _load_coordinator_config()
        fallback = coordinator_config.get("routing", {}).get("fallback_agent")
        if fallback and registry.has(fallback):
            return fallback
        available = ", ".join(c["agent_name"] for c in registry.list_all()) or "none"
        raise ValueError(f"No agent matched. Available agents: {available}.")
    return agent_name
