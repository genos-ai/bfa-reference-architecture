"""Preflight credit check — verify models have available credits before dispatch.

Provider-agnostic: uses _build_model() + PydanticAI so any supported provider
(Anthropic today, OpenAI/Bedrock tomorrow) goes through the same path.

Callable from CLI, API, or mission control — no rendering, just data.
"""

import asyncio
import time
from dataclasses import dataclass, field

from pydantic_ai import Agent, UsageLimits

from modules.backend.agents.mission_control.helpers import _build_model
from modules.backend.agents.mission_control.roster import load_roster
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ModelCheckResult:
    """Result of a single model ping."""

    model_name: str
    ok: bool
    elapsed_ms: float = 0.0
    error: str | None = None
    error_type: str | None = None


@dataclass
class PreflightResult:
    """Aggregate result of all model checks."""

    ok: bool = True
    checks: list[ModelCheckResult] = field(default_factory=list)

    @property
    def failed(self) -> list[ModelCheckResult]:
        return [c for c in self.checks if not c.ok]


async def _ping_model(model_name: str) -> ModelCheckResult:
    """Make a one-token call through PydanticAI to verify a model works."""
    start = time.monotonic()
    try:
        model = _build_model(model_name)
        agent: Agent[None, str] = Agent(model, output_type=str)
        await agent.run(
            "Reply with OK",
            usage_limits=UsageLimits(request_limit=1),
        )
        elapsed = (time.monotonic() - start) * 1000
        return ModelCheckResult(model_name=model_name, ok=True, elapsed_ms=elapsed)
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        error_msg = str(e)
        error_type = "insufficient_credits" if "credit balance is too low" in error_msg.lower() else "error"
        return ModelCheckResult(
            model_name=model_name,
            ok=False,
            elapsed_ms=elapsed,
            error=error_msg,
            error_type=error_type,
        )


async def preflight_check(
    roster_name: str = "default",
    models: list[str] | None = None,
) -> PreflightResult:
    """Verify all models in a roster (or explicit list) have available credits.

    Args:
        roster_name: Roster to load and extract models from.
        models: Override — check these model strings instead of loading a roster.

    Returns:
        PreflightResult with per-model pass/fail.
    """
    if models is None:
        roster = load_roster(roster_name)
        model_names = list({agent.model.name for agent in roster.agents})
    else:
        model_names = list(set(models))

    model_names.sort()
    logger.info("Preflight check starting", extra={"models": model_names})

    tasks = [_ping_model(name) for name in model_names]
    checks = await asyncio.gather(*tasks)

    result = PreflightResult(checks=list(checks))
    result.ok = all(c.ok for c in checks)

    logger.info(
        "Preflight check complete",
        extra={"ok": result.ok, "models_checked": len(checks), "failures": len(result.failed)},
    )
    return result
