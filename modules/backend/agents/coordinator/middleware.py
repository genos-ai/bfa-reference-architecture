"""
Horizontal middleware decorators.

Python decorators that wrap agent execution. Every agent passes through
the full chain: guardrails -> cost_tracking -> agent.run().
These are cross-cutting concerns, not agents — they do not call LLMs.
"""

import functools
import re
import time
from typing import Any

import yaml

from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def _load_coordinator_config() -> dict[str, Any]:
    """Load coordinator configuration from YAML."""
    config_path = find_project_root() / "config" / "agents" / "coordinator.yaml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def with_guardrails(func):
    """Block unsafe input before any LLM call is made.

    Checks input length and injection patterns from coordinator.yaml.
    Raises ValueError on violation — the coordinator catches this
    and returns an error response.
    """
    @functools.wraps(func)
    async def wrapper(user_input: str, *args, **kwargs):
        config = _load_coordinator_config()
        guardrails = config.get("guardrails", {})

        max_length = guardrails.get("max_input_length", 32000)
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


def with_cost_tracking(func):
    """Log token usage, computed cost, and duration after each agent run."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.monotonic()
        result = await func(*args, **kwargs)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "Agent execution completed",
            extra={"duration_ms": elapsed_ms},
        )
        return result
    return wrapper
