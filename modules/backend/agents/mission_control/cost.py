"""Cost calculation for agent executions.

Pricing comes from mission_control.yaml model_pricing config.
Budget enforcement lives in SessionService — this module only computes costs.
"""

from modules.backend.agents.mission_control.middleware import _load_mission_control_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def compute_cost_usd(
    input_tokens: int,
    output_tokens: int,
    model: str | None = None,
) -> float:
    """Compute dollar cost from token counts and model pricing config."""
    config = _load_mission_control_config()
    default_rates = config.model_pricing.get("default")
    rates = config.model_pricing.get(model or "", default_rates)
    if rates is None:
        rates = default_rates
    if rates is None:
        logger.warning("No pricing config found", extra={"model": model})
        return 0.0
    input_cost = (input_tokens / 1_000_000) * rates.input
    output_cost = (output_tokens / 1_000_000) * rates.output
    return round(input_cost + output_cost, 6)


def estimate_cost(
    estimated_input_tokens: int,
    model: str | None = None,
) -> float:
    """Estimate cost before execution. Assumes output ~= input."""
    return compute_cost_usd(estimated_input_tokens, estimated_input_tokens, model)
