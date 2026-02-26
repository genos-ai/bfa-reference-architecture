"""
Agent Coordinator.

Routes user requests to the appropriate vertical agent.
Phase 1: rule-based routing only (keyword matching).

Usage:
    from modules.backend.agents.coordinator.coordinator import handle, handle_direct, list_agents
    result = await handle("How is the system doing?")
    result = await handle_direct("system.health.agent", "check health")
    agents = list_agents()
"""

from typing import Any

from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def _load_agent_registry() -> dict[str, dict]:
    """Load all agent configs from config/agents/**/agent.yaml recursively."""
    agents_dir = find_project_root() / "config" / "agents"
    registry: dict[str, dict] = {}

    if not agents_dir.exists():
        return registry

    import yaml

    for path in sorted(agents_dir.rglob("agent.yaml")):
        with open(path) as f:
            config = yaml.safe_load(f) or {}
        if config.get("enabled"):
            registry[config["agent_name"]] = config

    return registry


def list_agents() -> list[dict[str, Any]]:
    """
    List all available agents with their metadata.

    Returns:
        List of dicts with agent_name, description, keywords, tools
    """
    registry = _load_agent_registry()
    return [
        {
            "agent_name": config["agent_name"],
            "description": config["description"],
            "keywords": config["keywords"],
            "tools": config["tools"],
        }
        for config in registry.values()
    ]


async def handle(user_input: str) -> dict[str, Any]:
    """
    Route a user request to the appropriate agent via keyword matching.

    Args:
        user_input: The user's message

    Returns:
        Dict with agent_name, output text, and metadata

    Raises:
        ValueError: If no agent matches the request
    """
    agent_name = _route(user_input)
    return await _execute(agent_name, user_input)


async def handle_direct(agent_name: str, user_input: str) -> dict[str, Any]:
    """
    Send a message directly to a named agent, bypassing routing.

    Args:
        agent_name: The agent to invoke (e.g., "system.health.agent")
        user_input: The user's message

    Returns:
        Dict with agent_name, output text, and metadata

    Raises:
        ValueError: If the agent does not exist
    """
    registry = _load_agent_registry()
    if agent_name not in registry:
        available = ", ".join(registry.keys()) or "none"
        raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

    logger.info("Direct agent invocation", extra={"agent_name": agent_name})
    return await _execute(agent_name, user_input)


async def handle_direct_stream(
    agent_name: str,
    user_input: str,
    conversation_id: str | None = None,
):
    """
    Stream progress events from a named agent with conversation memory.

    Yields dicts with progress events. The final event includes a
    conversation_id for continuing the conversation in the next turn.

    Args:
        agent_name: The agent to invoke (e.g., "code.qa.agent")
        user_input: The user's message
        conversation_id: ID from a previous turn to continue the conversation
    """
    registry = _load_agent_registry()
    if agent_name not in registry:
        available = ", ".join(registry.keys()) or "none"
        raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

    logger.info(
        "Direct agent invocation (stream)",
        extra={"agent_name": agent_name, "conversation_id": conversation_id},
    )

    if agent_name == "code.qa.agent":
        from modules.backend.agents.vertical.code.qa.agent import run_qa_agent_stream

        async for event in run_qa_agent_stream(user_input, conversation_id):
            yield event
    else:
        result = await _execute(agent_name, user_input)
        yield {"type": "complete", "result": result}


_AGENT_EXECUTORS: dict[str, Any] = {}


def _register_executors() -> None:
    """Register agent executor functions. Called once on first use."""
    if _AGENT_EXECUTORS:
        return

    registry = _load_agent_registry()

    if "system.health.agent" in registry:
        from modules.backend.agents.vertical.system.health.agent import run_health_agent

        async def _exec_health(user_input: str) -> dict[str, Any]:
            result = await run_health_agent(user_input)
            return {
                "agent_name": "system.health.agent",
                "output": result.summary,
                "components": result.components,
                "advice": result.advice,
            }

        _AGENT_EXECUTORS["system.health.agent"] = _exec_health

    if "code.qa.agent" in registry:
        from modules.backend.agents.vertical.code.qa.agent import run_qa_agent

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


async def _execute(agent_name: str, user_input: str) -> dict[str, Any]:
    """Execute a named agent with the given input."""
    _register_executors()
    executor = _AGENT_EXECUTORS.get(agent_name)
    if executor is None:
        raise ValueError(f"Agent '{agent_name}' is registered but has no executor.")
    return await executor(user_input)


def _route(user_input: str) -> str:
    """
    Rule-based routing. Returns the agent name that should handle this input.

    Phase 1: keyword matching against agent configs.
    Phase 2+: add LLM-based classification fallback.
    """
    text = user_input.lower()
    registry = _load_agent_registry()

    for agent_name, config in registry.items():
        keywords = config["keywords"]
        for keyword in keywords:
            if keyword in text:
                logger.debug(
                    "Routed to agent",
                    extra={"agent_name": agent_name, "keyword": keyword},
                )
                return agent_name

    available = ", ".join(registry.keys()) or "none"
    raise ValueError(f"No agent matched. Available agents: {available}.")
