"""Mission Control dispatch loop — deterministic agent execution.

Takes a validated TaskPlan, executes agents in topological order,
enforces timeouts and cost ceilings, resolves from_upstream references,
runs the 3-tier verification pipeline, and aggregates results into
a MissionOutcome.

This is deterministic code. No LLM calls happen here — agents are
invoked through the standard agent execution path.
"""

import asyncio
import time
from collections import deque
from typing import Any

from pydantic_ai import UsageLimits

from modules.backend.agents.mission_control.outcome import (
    MissionOutcome,
    MissionStatus,
    RetryHistoryEntry,
    TaskResult,
    TaskStatus,
    TaskTokenUsage,
    VerificationOutcome,
    build_verification_outcome,
)
from modules.backend.agents.mission_control.roster import Roster, RosterAgentEntry
from modules.backend.agents.mission_control.verification import (
    VerificationResult,
    build_retry_feedback,
    run_verification_pipeline,
)
from modules.backend.core.logging import get_logger
from modules.backend.schemas.task_plan import TaskDefinition, TaskPlan

logger = get_logger(__name__)


def topological_sort(plan: TaskPlan) -> list[list[str]]:
    """Sort tasks into execution layers. Each layer runs in parallel.

    Returns a list of layers, where each layer is a list of task_ids
    that can execute concurrently. Assumes DAG validation already passed.
    """
    task_ids = {t.task_id for t in plan.tasks}
    in_degree: dict[str, int] = {tid: 0 for tid in task_ids}
    dependents: dict[str, list[str]] = {tid: [] for tid in task_ids}

    for task in plan.tasks:
        for dep in task.dependencies:
            dependents[dep].append(task.task_id)
            in_degree[task.task_id] += 1

    layers: list[list[str]] = []
    queue: deque[str] = deque(
        tid for tid, deg in in_degree.items() if deg == 0
    )

    while queue:
        layer = list(queue)
        queue.clear()
        layers.append(layer)

        for node in layer:
            for neighbor in dependents[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

    return layers


def resolve_upstream_inputs(
    task: TaskDefinition,
    completed_outputs: dict[str, dict],
) -> dict[str, Any]:
    """Resolve from_upstream references using outputs from completed tasks.

    Returns the merged input dict (static + resolved upstream).
    Raises KeyError if a referenced task or field is missing.
    """
    resolved = dict(task.inputs.static)

    for field_name, ref in task.inputs.from_upstream.items():
        source_output = completed_outputs.get(ref.source_task)
        if source_output is None:
            raise KeyError(
                f"Task '{task.task_id}': upstream task '{ref.source_task}' "
                f"has no output (did it fail?)"
            )
        if ref.source_field not in source_output:
            raise KeyError(
                f"Task '{task.task_id}': upstream task '{ref.source_task}' "
                f"output missing field '{ref.source_field}'"
            )
        resolved[field_name] = source_output[ref.source_field]

    return resolved


async def verify_task(
    task: TaskDefinition,
    output: dict,
    roster_entry: RosterAgentEntry,
    execute_agent_fn: Any | None = None,
    session_id: str | None = None,
) -> VerificationResult:
    """Run the full 3-tier verification pipeline on a completed task.

    Replaces the Tier-1-only implementation from Plan 13.
    """
    agent_interface = None
    if roster_entry.interface:
        agent_interface = {
            "output": dict(roster_entry.interface.output),
        }

    task_dict = task.model_dump()

    return await run_verification_pipeline(
        output=output,
        task=task_dict,
        agent_interface=agent_interface,
        execute_agent_fn=execute_agent_fn,
        session_id=session_id,
    )


async def execute_task(
    task: TaskDefinition,
    roster_entry: RosterAgentEntry,
    resolved_inputs: dict[str, Any],
    execute_agent_fn: Any,
) -> dict:
    """Execute a single agent task with timeout and cost ceiling enforcement."""
    timeout = (
        task.constraints.timeout_override_seconds
        or roster_entry.constraints.timeout_seconds
    )
    cost_ceiling = roster_entry.constraints.cost_ceiling_usd

    usage_limits = UsageLimits(
        request_limit=50,
        total_tokens_limit=int(cost_ceiling * 1_000_000 / 3),
    )

    return await asyncio.wait_for(
        execute_agent_fn(
            agent_name=task.agent,
            instructions=task.instructions,
            inputs=resolved_inputs,
            usage_limits=usage_limits,
        ),
        timeout=timeout,
    )


async def dispatch(
    plan: TaskPlan,
    roster: Roster,
    execute_agent_fn: Any,
    mission_budget_usd: float,
) -> MissionOutcome:
    """Execute the dispatch loop for a validated TaskPlan.

    1. Topological sort into execution layers
    2. Execute each layer (parallel within layer, sequential across layers)
    3. Resolve from_upstream at dispatch time
    4. 3-tier verification after each task
    5. Retry with feedback on verification failure
    6. Aggregate results into MissionOutcome
    """
    start_time = time.monotonic()
    layers = topological_sort(plan)

    completed_outputs: dict[str, dict] = {}
    task_results: list[TaskResult] = []
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    total_thinking_tokens = 0

    for layer in layers:
        coros = []
        layer_tasks: list[TaskDefinition] = []

        for task_id in layer:
            task = plan.get_task(task_id)
            if task is None:
                continue

            roster_entry = roster.get_agent_by_name(task.agent)
            if roster_entry is None:
                task_results.append(_failed_result(task, "Agent not found in roster"))
                continue

            try:
                resolved_inputs = resolve_upstream_inputs(task, completed_outputs)
            except KeyError as e:
                task_results.append(_failed_result(task, str(e)))
                continue

            layer_tasks.append(task)
            coros.append(
                _execute_with_retry(
                    task=task,
                    roster_entry=roster_entry,
                    resolved_inputs=resolved_inputs,
                    execute_agent_fn=execute_agent_fn,
                )
            )

        if not coros:
            continue

        results = await asyncio.gather(*coros, return_exceptions=True)

        for task, result in zip(layer_tasks, results):
            if isinstance(result, Exception):
                task_results.append(_failed_result(task, str(result)))
                continue

            task_result: TaskResult = result
            task_results.append(task_result)

            if task_result.status == TaskStatus.SUCCESS:
                completed_outputs[task.task_id] = task_result.output_reference

            total_cost += task_result.cost_usd
            total_input_tokens += task_result.token_usage.input
            total_output_tokens += task_result.token_usage.output
            total_thinking_tokens += task_result.token_usage.thinking

    # Determine mission status
    total_tasks = len(plan.tasks)
    successful_tasks = sum(
        1 for r in task_results if r.status == TaskStatus.SUCCESS
    )
    success_ratio = successful_tasks / total_tasks if total_tasks > 0 else 0.0

    critical_path_ids = set(plan.execution_hints.critical_path)
    critical_path_success = all(
        any(
            r.task_id == cp_id and r.status == TaskStatus.SUCCESS
            for r in task_results
        )
        for cp_id in critical_path_ids
    ) if critical_path_ids else True

    if successful_tasks == total_tasks:
        status = MissionStatus.SUCCESS
    elif (
        success_ratio >= plan.execution_hints.min_success_threshold
        and critical_path_success
    ):
        status = MissionStatus.PARTIAL
    else:
        status = MissionStatus.FAILED

    total_duration = time.monotonic() - start_time

    return MissionOutcome(
        mission_id=plan.mission_id,
        status=status,
        task_results=task_results,
        total_cost_usd=round(total_cost, 6),
        total_duration_seconds=round(total_duration, 2),
        total_tokens=TaskTokenUsage(
            input=total_input_tokens,
            output=total_output_tokens,
            thinking=total_thinking_tokens,
        ),
    )


async def _execute_with_retry(
    task: TaskDefinition,
    roster_entry: RosterAgentEntry,
    resolved_inputs: dict[str, Any],
    execute_agent_fn: Any,
) -> TaskResult:
    """Execute a task with 3-tier verification and retry-with-feedback."""
    retry_budget = roster_entry.constraints.retry_budget
    retry_history: list[RetryHistoryEntry] = []
    instructions = task.instructions

    for attempt in range(retry_budget + 1):
        task_start = time.monotonic()

        try:
            output = await execute_task(
                task=task,
                roster_entry=roster_entry,
                resolved_inputs=resolved_inputs,
                execute_agent_fn=execute_agent_fn,
            )
        except asyncio.TimeoutError:
            duration = time.monotonic() - task_start
            if attempt < retry_budget:
                retry_history.append(RetryHistoryEntry(
                    attempt=attempt + 1,
                    failure_tier=0,
                    failure_reason="Timeout",
                    feedback_provided="Previous attempt timed out. Work more efficiently.",
                ))
                instructions = _append_feedback(
                    task.instructions,
                    "Previous attempt timed out. Complete the task more efficiently.",
                )
                continue

            return TaskResult(
                task_id=task.task_id,
                agent_name=task.agent,
                status=TaskStatus.TIMEOUT,
                output_reference={},
                token_usage=TaskTokenUsage(),
                cost_usd=0.0,
                duration_seconds=round(duration, 2),
                retry_count=attempt,
                retry_history=retry_history,
            )
        except Exception as e:
            duration = time.monotonic() - task_start
            logger.error(
                "Task execution failed",
                extra={"task_id": task.task_id, "error": str(e), "attempt": attempt},
            )
            if attempt < retry_budget:
                retry_history.append(RetryHistoryEntry(
                    attempt=attempt + 1,
                    failure_tier=0,
                    failure_reason=str(e),
                    feedback_provided=f"Previous attempt failed: {e}",
                ))
                instructions = _append_feedback(
                    task.instructions,
                    f"Previous attempt failed with error: {e}. Avoid this error.",
                )
                continue

            return _failed_result(
                task, str(e), retry_count=attempt, retry_history=retry_history,
            )

        duration = time.monotonic() - task_start

        # Extract token usage and cost from output metadata
        token_usage = TaskTokenUsage(
            input=output.get("_meta", {}).get("input_tokens", 0),
            output=output.get("_meta", {}).get("output_tokens", 0),
            thinking=output.get("_meta", {}).get("thinking_tokens", 0),
        )
        cost_usd = output.get("_meta", {}).get("cost_usd", 0.0)

        # Run 3-tier verification pipeline
        verification = await verify_task(
            task=task,
            output=output,
            roster_entry=roster_entry,
            execute_agent_fn=execute_agent_fn,
        )

        if not verification.passed:
            feedback = build_retry_feedback(verification, attempt=attempt + 1)

            if attempt < retry_budget:
                retry_history.append(RetryHistoryEntry(
                    attempt=feedback.get("attempt", attempt + 1),
                    failure_tier=feedback.get("failure_tier", 0),
                    failure_reason=feedback.get("failure_reason", "Verification failed"),
                    feedback_provided=feedback.get("feedback_provided", ""),
                ))
                instructions = _append_feedback(
                    task.instructions,
                    f"--- VERIFICATION FEEDBACK (attempt {attempt + 1}) ---\n"
                    f"{feedback.get('feedback_provided', '')}\n"
                    f"Please address the issues above and try again.",
                )
                continue

            return TaskResult(
                task_id=task.task_id,
                agent_name=task.agent,
                status=TaskStatus.FAILED,
                output_reference=output,
                token_usage=token_usage,
                cost_usd=cost_usd,
                duration_seconds=round(duration, 2),
                verification_outcome=build_verification_outcome(verification),
                retry_count=attempt,
                retry_history=retry_history,
            )

        # Success
        return TaskResult(
            task_id=task.task_id,
            agent_name=task.agent,
            status=TaskStatus.SUCCESS,
            output_reference=output,
            token_usage=token_usage,
            cost_usd=cost_usd,
            duration_seconds=round(duration, 2),
            verification_outcome=build_verification_outcome(verification),
            retry_count=attempt,
            retry_history=retry_history,
        )

    # Should not reach here, but defensive
    return _failed_result(task, "Exhausted retry budget")


def _append_feedback(original_instructions: str, feedback: str) -> str:
    """Append failure feedback to agent instructions (Reflection pattern)."""
    return (
        f"{original_instructions}\n\n"
        f"--- FEEDBACK FROM PREVIOUS ATTEMPT ---\n"
        f"{feedback}"
    )


def _failed_result(
    task: TaskDefinition,
    reason: str,
    retry_count: int = 0,
    retry_history: list[RetryHistoryEntry] | None = None,
) -> TaskResult:
    """Create a failed TaskResult."""
    return TaskResult(
        task_id=task.task_id,
        agent_name=task.agent,
        status=TaskStatus.FAILED,
        output_reference={},
        token_usage=TaskTokenUsage(),
        cost_usd=0.0,
        duration_seconds=0.0,
        retry_count=retry_count,
        retry_history=retry_history or [],
    )


