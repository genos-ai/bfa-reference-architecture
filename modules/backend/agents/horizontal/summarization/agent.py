"""
Summarization Agent — compresses mission outcomes into milestone summaries.

Generates narrative summaries from structured mission outcome data for the
fractal summarization pipeline. Uses Haiku for cost efficiency — input is
structured data, output is compressed narrative.
"""

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from modules.backend.agents.mission_control.helpers import (
    _build_model,
    assemble_instructions,
)
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"


class SummarizationOutput(BaseModel):
    """Structured output from the summarization agent."""

    title: str = Field(..., description="Short title for the milestone")
    summary: str = Field(..., description="Compressed narrative summary")
    key_outcomes: list[str] = Field(
        default_factory=list,
        description="Bullet-point key outcomes",
    )
    domain_tags: list[str] = Field(
        default_factory=list,
        description="Domain tags derived from the missions",
    )


@lru_cache(maxsize=1)
def _get_agent() -> Agent[None, SummarizationOutput]:
    """Cached summarization agent instance."""
    model = _build_model(_DEFAULT_MODEL)
    instructions = assemble_instructions("horizontal", "summarization")

    return Agent(
        model,
        system_prompt=instructions,
        output_type=SummarizationOutput,
    )


def get_agent(model: Model | None = None) -> Agent[None, SummarizationOutput]:
    """Get or create the summarization agent.

    Args:
        model: Optional model override for testing or roster-driven execution.
    """
    if model is not None:
        instructions = assemble_instructions("horizontal", "summarization")
        return Agent(
            model,
            system_prompt=instructions,
            output_type=SummarizationOutput,
        )
    return _get_agent()


async def summarize_missions(
    mission_outcomes: list[dict],
    *,
    target_length: int = 500,
    model: Model | None = None,
) -> dict[str, Any]:
    """Summarize a batch of mission outcomes into a milestone summary.

    Args:
        mission_outcomes: List of mission outcome dicts to compress.
        target_length: Target summary length in characters.
        model: Optional model override.

    Returns:
        Dict with title, summary, key_outcomes, and domain_tags.
    """
    agent = get_agent(model)

    prompt = (
        f"Summarize these {len(mission_outcomes)} mission outcomes "
        f"into a single milestone summary. "
        f"Target summary length: {target_length} characters.\n\n"
        f"Mission outcomes:\n"
    )
    for i, outcome in enumerate(mission_outcomes, 1):
        prompt += f"\n--- Mission {i} ---\n"
        prompt += str(outcome)

    result = await agent.run(prompt)
    output = result.output

    return {
        "title": output.title,
        "summary": output.summary,
        "key_outcomes": output.key_outcomes,
        "domain_tags": output.domain_tags,
    }
