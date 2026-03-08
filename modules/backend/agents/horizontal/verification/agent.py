"""Verification Agent (horizontal.verification.agent).

Dedicated agent for Tier 3 AI-based quality evaluation. Evaluates
other agents' work against criteria defined in the TaskPlan.

Security-critical: the system prompt defines what "good" looks like
for the entire platform. Changes require review and approval.

Isolation rules (P13, enforced by dispatch code):
  - Cannot evaluate its own output
  - Cannot evaluate the Planning Agent's output
  - No agent is judge and jury of its own work
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent, UsageLimits
from pydantic_ai.models import Model

from modules.backend.agents.deps.base import BaseAgentDeps
from modules.backend.agents.mission_control.helpers import assemble_instructions
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class CriterionResult(BaseModel):
    """Evaluation result for a single criterion."""

    criterion: str
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    evidence: str
    issues: list[str] = Field(default_factory=list)


class VerificationEvaluation(BaseModel):
    """Structured output from the Verification Agent.

    This is the contract between the Verification Agent and Mission Control.
    Mission Control reads overall_score and blocking_issues to make a
    deterministic pass/fail decision.
    """

    overall_score: float = Field(ge=0.0, le=1.0)
    passed: bool
    criteria_results: list[CriterionResult] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


def create_agent(model: str | Model) -> Agent[BaseAgentDeps, VerificationEvaluation]:
    """Factory: create a Verification Agent.

    Called by AgentRegistry.get_instance() on first use. The registry
    caches the result.
    """
    instructions = assemble_instructions("horizontal", "verification")

    agent = Agent(
        model,
        deps_type=BaseAgentDeps,
        output_type=VerificationEvaluation,
        instructions=instructions,
    )

    logger.info("Verification Agent created", extra={"model": str(model)})
    return agent


async def run_agent(
    user_message: str,
    deps: BaseAgentDeps,
    agent: Agent[BaseAgentDeps, VerificationEvaluation],
    usage_limits: UsageLimits | None = None,
) -> VerificationEvaluation:
    """Standard agent entry point. Called by Mission Control dispatch.

    The user_message contains the evaluation context (task instructions,
    criteria, agent output) serialized by the verification pipeline.
    """
    logger.info(
        "Verification Agent invoked",
        extra={"message_length": len(user_message)},
    )

    result = await agent.run(user_message, deps=deps, usage_limits=usage_limits)

    logger.info(
        "Verification Agent completed",
        extra={
            "overall_score": result.output.overall_score,
            "passed": result.output.passed,
            "criteria_count": len(result.output.criteria_results),
            "blocking_issues": len(result.output.blocking_issues),
            "usage": {
                "requests": result.usage().requests,
                "input_tokens": result.usage().input_tokens,
                "output_tokens": result.usage().output_tokens,
            },
        },
    )

    return result.output
