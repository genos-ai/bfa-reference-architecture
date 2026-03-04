"""
Horizontal middleware.

Guardrails and config loading for mission control. Cost tracking is now
handled inline by handle() via SessionService (Plan 12), so
with_cost_tracking has been removed. Cost computation lives in cost.py.
"""

import functools
import re
from functools import lru_cache

import yaml

from modules.backend.agents.config_schema import AgentConfigSchema, MissionControlConfigSchema
from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _load_mission_control_config() -> MissionControlConfigSchema:
    """Load, validate, and cache mission control configuration from YAML."""
    config_path = find_project_root() / "config" / "agents" / "mission_control.yaml"
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return MissionControlConfigSchema(**raw)


def check_guardrails(
    user_input: str,
    agent_config: AgentConfigSchema | None = None,
) -> None:
    """Check guardrails on user input. Raises ValueError if blocked.

    Checks mission control-level injection patterns and respects
    the agent-specific max_input_length when provided.
    """
    mc_config = _load_mission_control_config()

    mc_max = mc_config.guardrails.max_input_length
    agent_max = agent_config.max_input_length if agent_config else None
    max_length = agent_max if agent_max is not None else mc_max

    if len(user_input) > max_length:
        raise ValueError(
            f"Input exceeds maximum length ({len(user_input)} > {max_length})"
        )

    patterns = mc_config.guardrails.injection_patterns
    text_lower = user_input.lower()
    for pattern in patterns:
        if re.search(pattern, text_lower):
            logger.warning(
                "Guardrail: injection pattern detected",
                extra={"pattern": pattern},
            )
            raise ValueError("Input blocked by guardrail policy")


def with_guardrails(agent_config: AgentConfigSchema | None = None):
    """Decorator: block unsafe input before any LLM call is made.

    Kept for backward compatibility with the old handle() path.
    New code should call check_guardrails() directly.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(user_input: str, *args, **kwargs):
            check_guardrails(user_input, agent_config)
            return await func(user_input, *args, **kwargs)
        return wrapper
    return decorator
