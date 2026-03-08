"""
Synthesis Agent — human-readable narrative from structured outcome data.

Presentation-layer agent. Reads verified, structured mission/playbook
results and produces a concise narrative summary. Uses Haiku for cost
efficiency — the input is already structured, no complex reasoning needed.

P13 compliant: reports facts, does not evaluate agent performance.
"""

import json
from functools import lru_cache
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import Model

from modules.backend.agents.mission_control.helpers import (
    _build_model,
    assemble_instructions,
)
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"


@lru_cache(maxsize=1)
def _get_agent() -> Agent[None, str]:
    """Cached synthesis agent instance.

    Created once, reused across calls. The agent is stateless —
    all context is in the prompt, so caching is safe.
    """
    model = _build_model(_DEFAULT_MODEL)
    instructions = assemble_instructions("horizontal", "synthesis")

    agent = Agent(
        model,
        output_type=str,
        instructions=instructions,
    )

    logger.info("Synthesis agent created", extra={"model": _DEFAULT_MODEL})
    return agent


async def synthesize(outcome_data: dict[str, Any]) -> str:
    """Generate a human-readable narrative from outcome data.

    Public entry point. Returns indented text ready for CLI display.
    Raises on failure — caller decides fallback policy.
    """
    agent = _get_agent()

    prompt = (
        "Summarize the following outcome data into a concise narrative "
        "for a human operator.\n\n"
        f"```json\n{json.dumps(outcome_data, indent=2, default=str)}\n```"
    )

    result = await agent.run(prompt)

    return result.output.strip()
