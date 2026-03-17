"""MissionOutcome — structured result from Mission Control dispatch.

Returned to the Mission layer (or caller) with per-task results,
cost breakdown, and references to planning artifacts.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from modules.backend.agents.mission_control.verification import VerificationResult


class MissionStatus(StrEnum):
    """Mission completion status."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class TaskStatus(StrEnum):
    """Individual task completion status."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class TaskTokenUsage(BaseModel):
    """Token usage for a single task execution."""

    model_config = ConfigDict(extra="forbid")

    input: int = 0
    output: int = 0
    thinking: int = 0


class Tier1Outcome(BaseModel):
    """Tier 1 structural verification outcome."""

    model_config = ConfigDict(extra="forbid")

    status: str = "skipped"  # "pass" | "fail" | "skipped"
    details: str = ""


class FailedCheck(BaseModel):
    """A single failed Tier 2 check."""

    model_config = ConfigDict(extra="forbid")

    check: str
    reason: str


class Tier2Outcome(BaseModel):
    """Tier 2 deterministic verification outcome."""

    model_config = ConfigDict(extra="forbid")

    status: str = "skipped"  # "pass" | "fail" | "skipped"
    checks_run: int = 0
    checks_passed: int = 0
    failed_checks: list[FailedCheck] = Field(default_factory=list)


class Tier3Outcome(BaseModel):
    """Tier 3 AI evaluation verification outcome."""

    model_config = ConfigDict(extra="forbid")

    status: str = "skipped"  # "pass" | "fail" | "skipped"
    overall_score: float = 0.0
    criteria_results_reference: str = ""
    evaluator_thinking_trace_reference: str = ""
    cost_usd: float = 0.0


class VerificationOutcome(BaseModel):
    """Complete verification outcome per task in MissionOutcome."""

    model_config = ConfigDict(extra="forbid")

    tier_1: Tier1Outcome = Field(default_factory=Tier1Outcome)
    tier_2: Tier2Outcome = Field(default_factory=Tier2Outcome)
    tier_3: Tier3Outcome = Field(default_factory=Tier3Outcome)


class RetryHistoryEntry(BaseModel):
    """Record of a single retry attempt."""

    model_config = ConfigDict(extra="forbid")

    attempt: int
    failure_tier: int  # 0=execution, 1=tier1, 2=tier2, 3=tier3
    failure_reason: str
    feedback_provided: str


class TaskResult(BaseModel):
    """Result of a single task execution."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    agent_name: str
    status: TaskStatus
    output_reference: dict = Field(default_factory=dict)
    token_usage: TaskTokenUsage = Field(default_factory=TaskTokenUsage)
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    verification_outcome: VerificationOutcome = Field(
        default_factory=VerificationOutcome,
    )
    retry_count: int = 0
    retry_history: list[RetryHistoryEntry] = Field(default_factory=list)
    execution_id: str = Field(
        default="",
        description="Globally unique execution ID assigned at dispatch time",
    )
    context_updates: list[dict] = Field(
        default_factory=list,
        description="Structured patches to the PCD proposed by this agent",
    )
    skip_reason: str | None = None


class MissionOutcome(BaseModel):
    """Complete result of a Mission Control dispatch.

    Returned to the Mission layer with per-task results and cost breakdown.
    """

    model_config = ConfigDict(extra="forbid")

    mission_id: str
    status: MissionStatus
    task_results: list[TaskResult] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    total_tokens: TaskTokenUsage = Field(default_factory=TaskTokenUsage)
    abort_reason: str | None = None
    planning_trace_reference: str | None = None
    task_plan_reference: str | None = None


def build_verification_outcome(
    result: VerificationResult,
) -> VerificationOutcome:
    """Convert internal VerificationResult to serializable VerificationOutcome."""
    from modules.backend.agents.mission_control.verification import (
        Tier3Result,
        TierStatus,
    )

    # Tier 1
    tier_1 = Tier1Outcome(
        status=result.tier_1.status.value if result.tier_1 else "skipped",
        details=result.tier_1.details if result.tier_1 else "",
    )

    # Tier 2
    if result.tier_2 and result.tier_2.status != TierStatus.SKIPPED:
        checks_run = len(result.tier_2.check_results)
        failed = [
            FailedCheck(check=cr["check"], reason=cr["details"])
            for cr in result.tier_2.check_results
            if not cr.get("passed")
        ]
        tier_2 = Tier2Outcome(
            status=result.tier_2.status.value,
            checks_run=checks_run,
            checks_passed=checks_run - len(failed),
            failed_checks=failed,
        )
    else:
        tier_2 = Tier2Outcome(
            status=result.tier_2.status.value if result.tier_2 else "skipped",
        )

    # Tier 3
    if result.tier_3 and isinstance(result.tier_3, Tier3Result):
        tier_3 = Tier3Outcome(
            status=result.tier_3.status.value,
            overall_score=result.tier_3.overall_score,
            criteria_results_reference=result.tier_3.criteria_results_reference,
            evaluator_thinking_trace_reference=result.tier_3.evaluator_thinking_trace_reference,
            cost_usd=result.tier_3.cost_usd,
        )
    else:
        tier_3 = Tier3Outcome(
            status=result.tier_3.status.value if result.tier_3 else "skipped",
        )

    return VerificationOutcome(tier_1=tier_1, tier_2=tier_2, tier_3=tier_3)
