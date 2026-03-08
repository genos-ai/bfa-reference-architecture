"""3-tier verification pipeline for Mission Control.

Called by the dispatch loop's verify_task() hook after each agent returns
output. Each tier is cheaper and faster than the next. Execution stops
at the first tier failure.

Tier 1: Structural (code, zero tokens, milliseconds)
Tier 2: Deterministic functional (code, zero tokens)
Tier 3: AI evaluation (Verification Agent, Opus 4.6)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class TierStatus(str, Enum):
    """Verification tier outcome status."""

    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class TierResult:
    """Result from a single verification tier."""

    tier: int
    status: TierStatus
    details: str
    execution_time_ms: float
    check_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Tier3Result(TierResult):
    """Extended result for Tier 3 with AI evaluation details."""

    overall_score: float = 0.0
    criteria_results_reference: str = ""
    evaluator_thinking_trace_reference: str = ""
    cost_usd: float = 0.0


@dataclass
class VerificationResult:
    """Combined result of the full verification pipeline."""

    passed: bool
    tier_1: TierResult | None = None
    tier_2: TierResult | None = None
    tier_3: TierResult | Tier3Result | None = None
    failed_tier: int | None = None
    total_execution_time_ms: float = 0.0


async def run_verification_pipeline(
    output: dict[str, Any],
    task: dict[str, Any],
    agent_interface: dict[str, Any] | None,
    roster: dict[str, Any] | None = None,
    execute_agent_fn: Any | None = None,
    session_id: str | None = None,
) -> VerificationResult:
    """Execute the 3-tier verification pipeline.

    Args:
        output: Agent's actual output dict.
        task: TaskPlan task dict containing verification config.
        agent_interface: AgentInterfaceSchema dict for the agent
            (used by Tier 1 structural validation).
        roster: Agent roster dict (used to validate evaluator_agent exists).
        execute_agent_fn: Async callable to dispatch the Verification Agent
            for Tier 3. Signature: async (agent_name, instructions, context) -> dict.
        session_id: Session ID for tracing.

    Returns:
        VerificationResult with per-tier results and overall pass/fail.
    """
    pipeline_start = time.perf_counter()
    result = VerificationResult(passed=True)
    verification_config = task.get("verification", {})

    # ---- Tier 1: Structural Validation ----
    tier_1_result = await _run_tier_1(output, verification_config, agent_interface)
    result.tier_1 = tier_1_result

    if tier_1_result.status == TierStatus.FAIL:
        result.passed = False
        result.failed_tier = 1
        result.total_execution_time_ms = _elapsed_ms(pipeline_start)
        logger.warning(
            "Verification failed at Tier 1",
            extra={"task_id": task.get("task_id"), "details": tier_1_result.details},
        )
        return result

    # ---- Tier 2: Deterministic Functional Checks ----
    tier_2_result = await _run_tier_2(output, verification_config)
    result.tier_2 = tier_2_result

    if tier_2_result.status == TierStatus.FAIL:
        result.passed = False
        result.failed_tier = 2
        result.total_execution_time_ms = _elapsed_ms(pipeline_start)
        logger.warning(
            "Verification failed at Tier 2",
            extra={"task_id": task.get("task_id"), "details": tier_2_result.details},
        )
        return result

    # ---- Tier 3: AI Evaluation ----
    tier_3_result = await _run_tier_3(
        output, task, verification_config,
        execute_agent_fn=execute_agent_fn,
        session_id=session_id,
    )
    result.tier_3 = tier_3_result

    if tier_3_result.status == TierStatus.FAIL:
        result.passed = False
        result.failed_tier = 3
        result.total_execution_time_ms = _elapsed_ms(pipeline_start)
        logger.warning(
            "Verification failed at Tier 3",
            extra={"task_id": task.get("task_id"), "details": tier_3_result.details},
        )
        return result

    result.total_execution_time_ms = _elapsed_ms(pipeline_start)
    logger.info(
        "Verification pipeline passed",
        extra={
            "task_id": task.get("task_id"),
            "tier_1_ms": tier_1_result.execution_time_ms,
            "tier_2_ms": tier_2_result.execution_time_ms,
            "tier_3_ms": tier_3_result.execution_time_ms,
        },
    )
    return result


async def _run_tier_1(
    output: dict[str, Any],
    verification_config: dict[str, Any],
    agent_interface: dict[str, Any] | None,
) -> TierResult:
    """Tier 1: Structural validation against agent interface contract."""
    start = time.perf_counter()

    tier_1_config = verification_config.get("tier_1", {})
    schema_validation = tier_1_config.get("schema_validation", True)

    if not schema_validation:
        return TierResult(
            tier=1,
            status=TierStatus.SKIPPED,
            details="Schema validation disabled for this task",
            execution_time_ms=_elapsed_ms(start),
        )

    if not isinstance(output, dict):
        return TierResult(
            tier=1,
            status=TierStatus.FAIL,
            details=f"Output is not a dict: got {type(output).__name__}",
            execution_time_ms=_elapsed_ms(start),
        )

    if not output:
        return TierResult(
            tier=1,
            status=TierStatus.FAIL,
            details="Output is an empty dict",
            execution_time_ms=_elapsed_ms(start),
        )

    errors = []

    # Check against AgentInterfaceSchema output contract
    if agent_interface:
        expected_output_fields = agent_interface.get("output", {})
        for field_name in expected_output_fields:
            if field_name not in output:
                errors.append(f"Missing interface field: '{field_name}'")

    # Check against TaskPlan-specified required output fields
    required_fields = tier_1_config.get("required_output_fields", [])
    for field_name in required_fields:
        if field_name not in output:
            errors.append(f"Missing required field: '{field_name}'")

    if errors:
        return TierResult(
            tier=1,
            status=TierStatus.FAIL,
            details=f"{len(errors)} structural error(s): {'; '.join(errors)}",
            execution_time_ms=_elapsed_ms(start),
        )

    return TierResult(
        tier=1,
        status=TierStatus.PASS,
        details="Structural validation passed",
        execution_time_ms=_elapsed_ms(start),
    )


async def _run_tier_2(
    output: dict[str, Any],
    verification_config: dict[str, Any],
) -> TierResult:
    """Tier 2: Deterministic functional checks from the check registry.

    Runs ALL specified checks (even if one fails) to collect complete
    diagnostic information.
    """
    start = time.perf_counter()

    tier_2_config = verification_config.get("tier_2", {})
    checks = tier_2_config.get("deterministic_checks", [])

    if not checks:
        return TierResult(
            tier=2,
            status=TierStatus.SKIPPED,
            details="No deterministic checks specified",
            execution_time_ms=_elapsed_ms(start),
        )

    from modules.backend.agents.mission_control.check_registry import get_check

    check_results = []
    failed_checks = []

    for check_spec in checks:
        check_name = check_spec.get("check", "")
        check_params = check_spec.get("params", {})

        check_fn = get_check(check_name)
        if check_fn is None:
            check_results.append({
                "check": check_name,
                "passed": False,
                "details": f"Check '{check_name}' not found in registry",
                "execution_time_ms": 0.0,
            })
            failed_checks.append(check_name)
            continue

        try:
            cr = await check_fn(output, check_params)
            check_results.append({
                "check": check_name,
                "passed": cr.passed,
                "details": cr.details,
                "execution_time_ms": cr.execution_time_ms,
            })
            if not cr.passed:
                failed_checks.append(check_name)
        except Exception as exc:
            check_results.append({
                "check": check_name,
                "passed": False,
                "details": f"Check raised exception: {exc}",
                "execution_time_ms": _elapsed_ms(start),
            })
            failed_checks.append(check_name)
            logger.error(
                "Tier 2 check raised exception",
                extra={"check": check_name, "error": str(exc)},
                exc_info=True,
            )

    checks_run = len(check_results)

    if failed_checks:
        return TierResult(
            tier=2,
            status=TierStatus.FAIL,
            details=(
                f"{len(failed_checks)}/{checks_run} checks failed: "
                f"{', '.join(failed_checks)}"
            ),
            execution_time_ms=_elapsed_ms(start),
            check_results=check_results,
        )

    return TierResult(
        tier=2,
        status=TierStatus.PASS,
        details=f"All {checks_run} checks passed",
        execution_time_ms=_elapsed_ms(start),
        check_results=check_results,
    )


async def _run_tier_3(
    output: dict[str, Any],
    task: dict[str, Any],
    verification_config: dict[str, Any],
    execute_agent_fn: Any | None = None,
    session_id: str | None = None,
) -> TierResult | Tier3Result:
    """Tier 3: AI-based quality evaluation via Verification Agent."""
    start = time.perf_counter()

    tier_3_config = verification_config.get("tier_3", {})
    requires_evaluation = tier_3_config.get("requires_ai_evaluation", False)

    if not requires_evaluation:
        return TierResult(
            tier=3,
            status=TierStatus.SKIPPED,
            details="AI evaluation not required for this task",
            execution_time_ms=_elapsed_ms(start),
        )

    if execute_agent_fn is None:
        return TierResult(
            tier=3,
            status=TierStatus.FAIL,
            details="Tier 3 required but no execute_agent_fn provided",
            execution_time_ms=_elapsed_ms(start),
        )

    evaluation_criteria = tier_3_config.get("evaluation_criteria", [])
    evaluator_agent = tier_3_config.get("evaluator_agent", "verification_agent")
    min_score = tier_3_config.get("min_evaluation_score", 0.8)

    # Self-evaluation prevention (P13) — enforced in code
    task_agent = task.get("agent", "")
    if evaluator_agent == task_agent:
        return TierResult(
            tier=3,
            status=TierStatus.FAIL,
            details=(
                f"Self-evaluation prevented: task agent '{task_agent}' "
                f"cannot be its own evaluator (P13)"
            ),
            execution_time_ms=_elapsed_ms(start),
        )

    # Build evaluation context for the Verification Agent
    evaluation_context = {
        "task_instructions": task.get("instructions", ""),
        "task_description": task.get("description", ""),
        "evaluation_criteria": evaluation_criteria,
        "agent_output": output,
        "upstream_context": task.get("inputs", {}).get("static", {}),
    }

    try:
        evaluation = await execute_agent_fn(
            agent_name=evaluator_agent,
            instructions="Evaluate the agent output against the provided criteria.",
            context=evaluation_context,
        )

        overall_score = evaluation.get("overall_score", 0.0)
        blocking_issues = evaluation.get("blocking_issues", [])
        thinking_trace = evaluation.get("_thinking_trace", "")
        cost_usd = evaluation.get("_cost_usd", 0.0)

        # Deterministic pass/fail decision (Mission Control, not AI)
        passed = overall_score >= min_score and len(blocking_issues) == 0

        status = TierStatus.PASS if passed else TierStatus.FAIL
        details = (
            f"Score: {overall_score:.2f} (threshold: {min_score:.2f}), "
            f"blocking issues: {len(blocking_issues)}"
        )

        if not passed:
            if blocking_issues:
                details += f" — issues: {'; '.join(blocking_issues[:5])}"
            if overall_score < min_score:
                details += " — score below threshold"

        criteria_reference = f"verification:{task.get('task_id', 'unknown')}:criteria"
        trace_reference = f"verification:{task.get('task_id', 'unknown')}:thinking"

        return Tier3Result(
            tier=3,
            status=status,
            details=details,
            execution_time_ms=_elapsed_ms(start),
            overall_score=overall_score,
            criteria_results_reference=criteria_reference,
            evaluator_thinking_trace_reference=trace_reference,
            cost_usd=cost_usd,
        )

    except Exception as exc:
        logger.error(
            "Tier 3 evaluation failed",
            extra={"evaluator": evaluator_agent, "error": str(exc)},
            exc_info=True,
        )
        return TierResult(
            tier=3,
            status=TierStatus.FAIL,
            details=f"Verification Agent raised exception: {exc}",
            execution_time_ms=_elapsed_ms(start),
        )


def build_retry_feedback(
    verification_result: VerificationResult,
    attempt: int,
) -> dict[str, Any]:
    """Build feedback dict for retry-with-feedback (Reflection pattern).

    Returns:
        Dict with keys: attempt, failure_tier, failure_reason, feedback_provided.
    """
    if verification_result.passed:
        return {}

    failed_tier = verification_result.failed_tier
    feedback_parts = []

    if failed_tier == 1 and verification_result.tier_1:
        feedback_parts.append(
            f"Structural validation failed: {verification_result.tier_1.details}"
        )

    elif failed_tier == 2 and verification_result.tier_2:
        feedback_parts.append(
            f"Deterministic checks failed: {verification_result.tier_2.details}"
        )
        for check_result in verification_result.tier_2.check_results:
            if not check_result.get("passed"):
                feedback_parts.append(
                    f"  - {check_result['check']}: {check_result['details']}"
                )

    elif failed_tier == 3 and verification_result.tier_3:
        feedback_parts.append(
            f"Quality evaluation failed: {verification_result.tier_3.details}"
        )
        if isinstance(verification_result.tier_3, Tier3Result):
            feedback_parts.append(
                f"  Score: {verification_result.tier_3.overall_score:.2f}"
            )

    failure_reason = ""
    if failed_tier == 1 and verification_result.tier_1:
        failure_reason = verification_result.tier_1.details
    elif failed_tier == 2 and verification_result.tier_2:
        failure_reason = verification_result.tier_2.details
    elif failed_tier == 3 and verification_result.tier_3:
        failure_reason = verification_result.tier_3.details

    return {
        "attempt": attempt,
        "failure_tier": failed_tier,
        "failure_reason": failure_reason or "Unknown failure",
        "feedback_provided": "\n".join(feedback_parts),
    }


def _elapsed_ms(start: float) -> float:
    """Calculate elapsed time in milliseconds since start."""
    return round((time.perf_counter() - start) * 1000, 3)
