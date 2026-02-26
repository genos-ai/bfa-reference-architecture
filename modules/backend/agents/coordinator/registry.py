"""
Agent Registry.

Discovers all agent configurations from config/agents/**/agent.yaml.
Provides lookup by name, keyword matching, module path resolution,
and listing. Caches results after first load.
"""

from functools import lru_cache
from typing import Any

import yaml

from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class AgentRegistry:
    """Discovers and caches agent configurations from YAML files."""

    def __init__(self) -> None:
        self._agents: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        agents_dir = find_project_root() / "config" / "agents"
        if not agents_dir.exists():
            self._loaded = True
            return

        for path in sorted(agents_dir.rglob("agent.yaml")):
            with open(path) as f:
                config = yaml.safe_load(f) or {}
            if config.get("enabled", False):
                name = config.get("agent_name")
                if name:
                    self._agents[name] = config

        self._loaded = True
        logger.debug(
            "Agent registry loaded",
            extra={"agent_count": len(self._agents)},
        )

    def get(self, agent_name: str) -> dict[str, Any]:
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
                "agent_name": config["agent_name"],
                "description": config.get("description", ""),
                "keywords": config.get("keywords", []),
                "tools": config.get("tools", []),
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
            for keyword in config.get("keywords", []):
                if keyword in text_lower:
                    return agent_name
        return None

    def resolve_module_path(self, agent_name: str) -> str:
        """Derive the Python import path from agent name and type.

        vertical agents: modules.backend.agents.vertical.{category}.{name}.agent
        horizontal agents: modules.backend.agents.horizontal.{name}.agent
        """
        config = self.get(agent_name)
        agent_type = config.get("agent_type", "vertical")
        parts = agent_name.replace(".agent", "").split(".")

        if agent_type == "horizontal":
            name = parts[-1]
            return f"modules.backend.agents.horizontal.{name}.agent"

        category = parts[0]
        name = parts[1]
        return f"modules.backend.agents.vertical.{category}.{name}.agent"


@lru_cache(maxsize=1)
def get_registry() -> AgentRegistry:
    """Get the cached registry instance."""
    return AgentRegistry()
