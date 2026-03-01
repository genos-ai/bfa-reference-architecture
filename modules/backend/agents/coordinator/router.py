"""
Rule-Based Router.

Matches user input against agent keywords for fast, deterministic routing.
Returns None when no rule matches (future: LLM fallback via coordinator agent).
"""

from modules.backend.agents.coordinator.models import CoordinatorRequest
from modules.backend.agents.coordinator.registry import AgentRegistry
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class RuleBasedRouter:
    """Routes requests to agents via keyword matching."""

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def route(self, request: CoordinatorRequest) -> str | None:
        """Return agent_name if a keyword matches, else None.

        When the request specifies an agent directly, that takes
        priority over keyword matching.
        """
        if request.agent and self._registry.has(request.agent):
            logger.debug(
                "Direct agent specified",
                extra={"agent_name": request.agent},
            )
            return request.agent

        agent_name = self._registry.get_by_keyword(request.user_input)
        if agent_name:
            logger.debug(
                "Routed by keyword",
                extra={"agent_name": agent_name},
            )
        return agent_name
