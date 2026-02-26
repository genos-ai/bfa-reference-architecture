"""
Horizontal middleware decorators.

Python decorators that wrap agent execution. Every agent passes through
the full chain: guardrails -> cost_tracking -> agent.run().
These are cross-cutting concerns, not agents — they do not call LLMs.
"""

import functools
import re
import time
from functools import lru_cache
from typing import Any

import yaml

from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _load_coordinator_config() -> dict[str, Any]:
    """Load and cache coordinator configuration from YAML."""
    config_path = find_project_root() / "config" / "agents" / "coordinator.yaml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def with_guardrails(agent_config: dict[str, Any] | None = None):
    """Block unsafe input before any LLM call is made.

    Checks coordinator-level injection patterns and respects
    the agent-specific max_input_length when provided.

    Args:
        agent_config: Agent YAML config dict. If provided, uses the
            agent's max_input_length over the coordinator default.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(user_input: str, *args, **kwargs):
            coordinator_config = _load_coordinator_config()
            guardrails = coordinator_config.get("guardrails", {})

            coordinator_max = guardrails.get("max_input_length", 32000)
            agent_max = (agent_config or {}).get("max_input_length")
            max_length = agent_max if agent_max is not None else coordinator_max

            if len(user_input) > max_length:
                raise ValueError(
                    f"Input exceeds maximum length ({len(user_input)} > {max_length})"
                )

            patterns = guardrails.get("injection_patterns", [])
            text_lower = user_input.lower()
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    logger.warning(
                        "Guardrail: injection pattern detected",
                        extra={"pattern": pattern},
                    )
                    raise ValueError("Input blocked by guardrail policy")

            return await func(user_input, *args, **kwargs)
        return wrapper
    return decorator


def with_cost_tracking(func):
    """Log token usage, cost, and duration after each agent run.

    Expects the wrapped function to return a dict with an optional
    'usage' key containing token counts. Logs wall-clock time and
    token metrics when available.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.monotonic()
        result = await func(*args, **kwargs)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        log_extra: dict[str, Any] = {"duration_ms": elapsed_ms}

        if isinstance(result, dict):
            usage = result.get("_usage")
            if usage:
                log_extra["input_tokens"] = usage.get("input_tokens", 0)
                log_extra["output_tokens"] = usage.get("output_tokens", 0)
                log_extra["requests"] = usage.get("requests", 0)

        logger.info("Agent execution completed", extra=log_extra)
        return result
    return wrapper
