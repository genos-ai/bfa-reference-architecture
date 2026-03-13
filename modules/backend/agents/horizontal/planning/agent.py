"""Planning Agent — task decomposition via Opus 4.6 extended thinking.

Called by Mission Control (code), not by other agents.
Input: mission brief, agent roster, upstream context, output format spec.
Output: TaskPlan JSON within <task_plan> XML tags.
Thinking trace captured for audit trail.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent

from modules.backend.agents.deps.base import BaseAgentDeps
from modules.backend.agents.mission_control.helpers import (
    _build_model,
    assemble_instructions,
)
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PlanningAgentDeps(BaseAgentDeps):
    """Dependencies injected into the Planning Agent at runtime."""

    mission_brief: str = ""
    roster_description: str = ""
    upstream_context: dict[str, Any] | None = None
    code_map: dict | None = None


def create_agent(config: dict) -> Agent:
    """Create the Planning Agent instance.

    Model resolved from caller-provided config (sourced from agent.yaml).
    System prompt loaded from config/prompts/agents/horizontal/planning/system.md.
    """
    if "model" not in config:
        raise ValueError("Planning agent requires 'model' in config (from agent.yaml)")
    model = _build_model(config["model"])
    system_prompt = assemble_instructions("horizontal", "planning")

    return Agent(
        model,
        system_prompt=system_prompt,
        deps_type=PlanningAgentDeps,
    )


async def run_agent(
    agent: Agent,
    deps: PlanningAgentDeps,
    user_prompt: str,
    **kwargs: Any,
) -> dict:
    """Run the Planning Agent. Returns parsed TaskPlan dict and thinking trace.

    The agent returns JSON within <task_plan> tags. This function extracts,
    parses, and returns the JSON as a dict. The caller (Mission Control)
    validates it via plan_validator.
    """
    result = await agent.run(user_prompt, deps=deps, **kwargs)

    response_text = result.output
    plan_json = extract_task_plan_json(response_text)

    # Capture thinking trace if available
    thinking_trace = None
    if hasattr(result, "all_messages"):
        for msg in result.all_messages():
            for part in getattr(msg, "parts", []):
                if hasattr(part, "content") and hasattr(part, "part_kind"):
                    if "thinking" in str(getattr(part, "part_kind", "")):
                        thinking_trace = part.content

    return {
        "task_plan": plan_json,
        "thinking_trace": thinking_trace,
        "usage": result.usage() if hasattr(result, "usage") else None,
    }


def extract_task_plan_json(text: str) -> dict:
    """Extract TaskPlan JSON from within <task_plan> XML tags.

    Raises ValueError if tags are missing or JSON is malformed.
    """
    pattern = r"<task_plan>\s*(.*?)\s*</task_plan>"
    match = re.search(pattern, text, re.DOTALL)

    if not match:
        raise ValueError(
            "Planning Agent response does not contain <task_plan> tags. "
            "Response must include JSON within <task_plan>...</task_plan> tags."
        )

    json_str = match.group(1).strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Planning Agent response contains invalid JSON within <task_plan> tags: {e}"
        ) from e
