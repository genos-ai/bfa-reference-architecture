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

from modules.backend.agents.config_schema import AgentConfigSchema, CoordinatorConfigSchema
from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _load_coordinator_config() -> CoordinatorConfigSchema:
    """Load, validate, and cache coordinator configuration from YAML."""
    config_path = find_project_root() / "config" / "agents" / "coordinator.yaml"
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return CoordinatorConfigSchema(**raw)


def compute_cost_usd(
    input_tokens: int,
    output_tokens: int,
    model: str | None = None,
) -> float:
    """Compute dollar cost from token counts and model pricing config."""
    config = _load_coordinator_config()
    default_rates = config.model_pricing.get("default")
    rates = config.model_pricing.get(model or "", default_rates)
    if rates is None:
        rates = default_rates
    input_cost = (input_tokens / 1_000_000) * rates.input
    output_cost = (output_tokens / 1_000_000) * rates.output
    return round(input_cost + output_cost, 6)


def with_guardrails(agent_config: AgentConfigSchema | None = None):
    """Block unsafe input before any LLM call is made.

    Checks coordinator-level injection patterns and respects
    the agent-specific max_input_length when provided.

    Also enforces per-agent max_budget_usd when configured.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(user_input: str, *args, **kwargs):
            coordinator_config = _load_coordinator_config()

            coordinator_max = coordinator_config.guardrails.max_input_length
            agent_max = agent_config.max_input_length if agent_config else None
            max_length = agent_max if agent_max is not None else coordinator_max

            if len(user_input) > max_length:
                raise ValueError(
                    f"Input exceeds maximum length ({len(user_input)} > {max_length})"
                )

            patterns = coordinator_config.guardrails.injection_patterns
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
    """Track token usage, compute dollar cost, and enforce budget limits.

    Reads max_cost_per_plan and max_cost_per_user_daily from coordinator.yaml.
    Extracts usage data from the agent result dict (_usage key) when present.
    Logs tokens, cost, and duration. Raises ValueError if cost exceeds limits.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.monotonic()
        result = await func(*args, **kwargs)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        log_extra: dict[str, Any] = {"duration_ms": elapsed_ms}
        cost_usd = 0.0

        if isinstance(result, dict):
            usage = result.get("_usage")
            if usage:
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                model = usage.get("model")
                cost_usd = compute_cost_usd(input_tokens, output_tokens, model)

                log_extra["input_tokens"] = input_tokens
                log_extra["output_tokens"] = output_tokens
                log_extra["cost_usd"] = cost_usd
                log_extra["model"] = model

        coordinator_config = _load_coordinator_config()

        max_cost_plan = coordinator_config.limits.max_cost_per_plan
        if max_cost_plan and cost_usd > max_cost_plan:
            logger.error(
                "Cost limit exceeded",
                extra={"cost_usd": cost_usd, "limit": max_cost_plan, "scope": "plan"},
            )
            raise ValueError(
                f"Agent cost ${cost_usd:.4f} exceeds plan limit ${max_cost_plan:.2f}"
            )

        logger.info("Agent execution completed", extra=log_extra)
        return result
    return wrapper
