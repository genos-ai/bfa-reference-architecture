"""
Agent Coordinator.

Routes user requests to the appropriate vertical agent. Assembles
layered prompt instructions, builds agent deps from YAML config,
composes middleware, and manages agent executors.

Public interface (preserved from previous version):
    handle(user_input) -> dict
    handle_direct(agent_name, user_input) -> dict
    handle_direct_stream(agent_name, user_input, conversation_id) -> AsyncGenerator
    list_agents() -> list[dict]

Usage:
    from modules.backend.agents.coordinator.coordinator import handle, list_agents
    result = await handle("How is the system doing?")
    agents = list_agents()
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from modules.backend.agents.coordinator.middleware import with_cost_tracking, with_guardrails
from modules.backend.agents.coordinator.registry import AgentRegistry, get_registry
from modules.backend.agents.coordinator.router import RuleBasedRouter
from modules.backend.agents.deps.base import FileScope
from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Prompt Assembly
# =============================================================================


def assemble_instructions(category: str, name: str) -> str:
    """Compose layered prompt: organization -> category -> agent.

    Reads markdown files from config/prompts/ and concatenates them.
    Missing layers are silently skipped — not every agent needs all layers.
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
    """Build common dep fields from agent YAML config.

    Returns a dict with project_root, scope, and config — ready to be
    unpacked into a BaseAgentDeps (or subclass) constructor.
    """
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


# =============================================================================
# Executor Registration
# =============================================================================


_AGENT_EXECUTORS: dict[str, Any] = {}


def _register_executors() -> None:
    """Discover agents from registry and register their executor functions.

    Called once on first use. Each executor is wrapped with middleware.
    """
    if _AGENT_EXECUTORS:
        return

    registry = get_registry()
    configs = registry.all_configs()

    if "system.health.agent" in configs:
        from modules.backend.agents.vertical.system.health.agent import run_health_agent

        @with_guardrails
        @with_cost_tracking
        async def _exec_health(user_input: str) -> dict[str, Any]:
            result = await run_health_agent(user_input)
            return {
                "agent_name": "system.health.agent",
                "output": result.summary,
                "components": result.components,
                "advice": result.advice,
            }

        _AGENT_EXECUTORS["system.health.agent"] = _exec_health

    if "code.qa.agent" in configs:
        from modules.backend.agents.vertical.code.qa.agent import run_qa_agent

        @with_guardrails
        @with_cost_tracking
        async def _exec_qa(user_input: str) -> dict[str, Any]:
            result = await run_qa_agent(user_input)
            return {
                "agent_name": "code.qa.agent",
                "output": result.summary,
                "violations": [v.model_dump() for v in result.violations],
                "total_violations": result.total_violations,
                "error_count": result.error_count,
                "warning_count": result.warning_count,
                "fixed_count": result.fixed_count,
                "needs_human_count": result.needs_human_count,
                "tests_passed": result.tests_passed,
            }

        _AGENT_EXECUTORS["code.qa.agent"] = _exec_qa


# =============================================================================
# Public Interface
# =============================================================================


def list_agents() -> list[dict[str, Any]]:
    """List all available agents with their metadata."""
    return get_registry().list_all()


async def handle(user_input: str) -> dict[str, Any]:
    """Route a user request to the appropriate agent via keyword matching.

    Raises:
        ValueError: If no agent matches the request.
    """
    from modules.backend.agents.coordinator.models import CoordinatorRequest

    registry = get_registry()
    router = RuleBasedRouter(registry)
    request = CoordinatorRequest(user_input=user_input)

    agent_name = router.route(request)
    if agent_name is None:
        available = ", ".join(c["agent_name"] for c in registry.list_all()) or "none"
        raise ValueError(f"No agent matched. Available agents: {available}.")

    logger.debug("Routed to agent", extra={"agent_name": agent_name})
    return await _execute(agent_name, user_input)


async def handle_direct(agent_name: str, user_input: str) -> dict[str, Any]:
    """Send a message directly to a named agent, bypassing routing.

    Raises:
        ValueError: If the agent does not exist.
    """
    registry = get_registry()
    if not registry.has(agent_name):
        available = ", ".join(c["agent_name"] for c in registry.list_all()) or "none"
        raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

    logger.info("Direct agent invocation", extra={"agent_name": agent_name})
    return await _execute(agent_name, user_input)


async def handle_direct_stream(
    agent_name: str,
    user_input: str,
    conversation_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream progress events from a named agent with conversation memory.

    Yields dicts with progress events. The final event includes a
    conversation_id for continuing the conversation in the next turn.
    """
    registry = get_registry()
    if not registry.has(agent_name):
        available = ", ".join(c["agent_name"] for c in registry.list_all()) or "none"
        raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

    logger.info(
        "Direct agent invocation (stream)",
        extra={"agent_name": agent_name, "conversation_id": conversation_id},
    )

    agent_config = registry.get(agent_name)
    agent_type = agent_config.get("agent_type", "vertical")

    if agent_type == "vertical" and agent_name == "code.qa.agent":
        from modules.backend.agents.vertical.code.qa.agent import run_qa_agent_stream

        async for event in run_qa_agent_stream(user_input, conversation_id):
            yield event
    else:
        result = await _execute(agent_name, user_input)
        yield {"type": "complete", "result": result}


async def _execute(agent_name: str, user_input: str) -> dict[str, Any]:
    """Execute a named agent with the given input."""
    _register_executors()
    executor = _AGENT_EXECUTORS.get(agent_name)
    if executor is None:
        raise ValueError(f"Agent '{agent_name}' is registered but has no executor.")
    return await executor(user_input)


def _route(user_input: str) -> str:
    """Route user input to an agent name. Raises ValueError if no match."""
    from modules.backend.agents.coordinator.models import CoordinatorRequest

    registry = get_registry()
    router = RuleBasedRouter(registry)
    request = CoordinatorRequest(user_input=user_input)

    agent_name = router.route(request)
    if agent_name is None:
        available = ", ".join(c["agent_name"] for c in registry.list_all()) or "none"
        raise ValueError(f"No agent matched. Available agents: {available}.")
    return agent_name
