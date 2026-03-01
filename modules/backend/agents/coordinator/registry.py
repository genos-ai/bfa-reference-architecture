"""
Agent Registry.

Discovers all agent configurations from config/agents/**/agent.yaml.
Provides lookup by name, keyword matching, module path resolution,
and listing. Caches results after first load.
"""

import importlib
from functools import lru_cache
from typing import Any

import yaml
from pydantic import ValidationError

from modules.backend.agents.config_schema import AgentConfigSchema
from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class AgentRegistry:
    """Discovers and caches agent configurations from YAML files."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentConfigSchema] = {}
        self._instances: dict[str, Any] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        agents_dir = find_project_root() / "config" / "agents"
        if not agents_dir.exists():
            self._loaded = True
            return

        for path in sorted(agents_dir.rglob("agent.yaml")):
            try:
                with open(path) as f:
                    raw = yaml.safe_load(f)
            except yaml.YAMLError as e:
                logger.error("Failed to parse agent config", extra={"path": str(path), "error": str(e)})
                continue

            if raw is None:
                logger.warning("Empty agent config file", extra={"path": str(path)})
                continue

            if not raw.get("agent_name"):
                logger.warning("Agent config missing agent_name", extra={"path": str(path)})
                continue

            try:
                config = AgentConfigSchema(**raw)
            except ValidationError as e:
                logger.error(
                    "Invalid agent config",
                    extra={"path": str(path), "error": str(e)},
                )
                continue

            if not config.enabled:
                logger.debug("Agent disabled", extra={"agent_name": config.agent_name})
                continue

            self._agents[config.agent_name] = config

        self._loaded = True
        logger.debug(
            "Agent registry loaded",
            extra={"agent_count": len(self._agents)},
        )

    def get(self, agent_name: str) -> AgentConfigSchema:
        """Get agent config by name. Raises KeyError if not found."""
        self._ensure_loaded()
        if agent_name not in self._agents:
            available = ", ".join(self._agents.keys()) or "none"
            raise KeyError(f"Agent '{agent_name}' not found. Available: {available}")
        return self._agents[agent_name]

    def has(self, agent_name: str) -> bool:
        """Check if an agent exists in the registry."""
        self._ensure_loaded()
        return agent_name in self._agents

    def list_all(self) -> list[dict[str, Any]]:
        """List all registered agents with their metadata."""
        self._ensure_loaded()
        return [
            {
                "agent_name": config.agent_name,
                "description": config.description,
                "keywords": config.keywords,
                "tools": config.tools,
            }
            for config in self._agents.values()
        ]

    def get_by_keyword(self, text: str) -> str | None:
        """Find an agent whose keywords match the given text.

        Returns the agent_name if a match is found, None otherwise.
        """
        self._ensure_loaded()
        text_lower = text.lower()
        for agent_name, config in self._agents.items():
            for keyword in config.keywords:
                if keyword in text_lower:
                    return agent_name
        return None

    def resolve_module_path(self, agent_name: str) -> str:
        """Derive the Python import path from agent name and type.

        vertical agents: modules.backend.agents.vertical.{category}.{name}.agent
        horizontal agents: modules.backend.agents.horizontal.{name}.agent
        """
        config = self.get(agent_name)
        agent_type = config.agent_type
        parts = agent_name.replace(".agent", "").split(".")

        if agent_type == "horizontal":
            name = parts[-1]
            return f"modules.backend.agents.horizontal.{name}.agent"

        category = parts[0]
        name = parts[1]
        return f"modules.backend.agents.vertical.{category}.{name}.agent"

    def get_instance(self, agent_name: str, model: Any) -> Any:
        """Get or create a cached PydanticAI Agent instance.

        First call imports the agent module and calls its create_agent() factory.
        Subsequent calls return the cached instance. Call reset() to clear.
        """
        if agent_name in self._instances:
            return self._instances[agent_name]

        module_path = self.resolve_module_path(agent_name)
        module = importlib.import_module(module_path)
        agent = module.create_agent(model)
        self._instances[agent_name] = agent

        logger.info(
            "Agent instance created",
            extra={"agent_name": agent_name},
        )
        return agent

    def reset(self) -> None:
        """Clear all cached agent instances.

        Call this in test fixtures to allow TestModel injection.
        Config cache (_agents) is not affected.
        """
        self._instances.clear()


@lru_cache(maxsize=1)
def get_registry() -> AgentRegistry:
    """Get the cached registry instance."""
    return AgentRegistry()
