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
import uuid
from collections import deque
from typing import Any

from pydantic_ai import UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded

from modules.backend.agents.mission_control.gate import (
    GateAction,
    GateContext,
    GateReviewer,
    NoOpGate,
)
from modules.backend.agents.mission_control.middleware import _load_mission_control_config
from modules.backend.agents.mission_control.helpers import _emit
from modules.backend.agents.mission_control.models import (
    ContextAssemblerProtocol,
    ContextCuratorProtocol,
    EventBusProtocol,
    ExecuteAgentFn,
    NoOpEventBus,
)
from modules.backend.agents.mission_control.outcome import (
    MissionOutcome,
    MissionStatus,
    RetryHistoryEntry,
    TaskResult,
    TaskStatus,
    TaskTokenUsage,
    build_verification_outcome,
)
from modules.backend.agents.mission_control.roster import Roster, RosterAgentEntry
from modules.backend.agents.mission_control.verification import (
    VerificationResult,
    build_retry_feedback,
    run_verification_pipeline,
)
from modules.backend.core.logging import get_logger
from modules.backend.events.types import (
    PlanCreatedEvent,
    PlanStepCompletedEvent,
    PlanStepStartedEvent,
)
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
    execute_agent_fn: ExecuteAgentFn | None = None,
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
    execute_agent_fn: ExecuteAgentFn,
    instructions: str | None = None,
) -> dict:
    """Execute a single agent task with timeout and cost ceiling enforcement.

    Args:
        instructions: Override for task.instructions (used to deliver retry feedback).
    """
    timeout = (
        task.constraints.timeout_override_seconds
        or roster_entry.constraints.timeout_seconds
    )
    cost_ceiling = roster_entry.constraints.cost_ceiling_usd

    mc_config = _load_mission_control_config()
    usage_limits = UsageLimits(
        request_limit=mc_config.dispatch.default_request_limit,
        total_tokens_limit=int(cost_ceiling * mc_config.dispatch.token_cost_factor),
    )

    return await asyncio.wait_for(
        execute_agent_fn(
            agent_name=task.agent,
            instructions=instructions or task.instructions,
            inputs=resolved_inputs,
            usage_limits=usage_limits,
        ),
        timeout=timeout,
    )


async def dispatch(
    plan: TaskPlan,
    roster: Roster,
    execute_agent_fn: ExecuteAgentFn,
    mission_budget_usd: float,
    *,
    gate: GateReviewer | None = None,
    project_id: str | None = None,
    context_curator: ContextCuratorProtocol | None = None,
    context_assembler: ContextAssemblerProtocol | None = None,
    event_bus: EventBusProtocol | None = None,
    session_id: str | None = None,
) -> MissionOutcome:
    """Execute the dispatch loop for a validated TaskPlan.

    1. Topological sort into execution layers
    2. Execute each layer (parallel within layer, sequential across layers)
    3. Resolve from_upstream at dispatch time
    4. 3-tier verification after each task
    5. Retry with feedback on verification failure
    6. Aggregate results into MissionOutcome

    When gate is provided, pauses at key decision points for review.
    """
    start_time = time.monotonic()
    _gate = gate or NoOpGate()
    _bus = event_bus or NoOpEventBus()
    _sid = session_id or plan.mission_id
    layers = topological_sort(plan)

    # Gate 1: pre_dispatch — review full plan before execution
    decision = await _gate.review(GateContext(
        gate_type="pre_dispatch",
        mission_id=plan.mission_id,
        layer_index=0,
        total_layers=len(layers),
        pending_tasks=[
            {"task_id": t.task_id, "agent": t.agent, "description": t.description}
            for t in plan.tasks
        ],
        total_cost_usd=0.0,
        budget_usd=mission_budget_usd,
    ))
    if decision.action == GateAction.ABORT:
        logger.info("Mission aborted at pre_dispatch gate", extra={"reason": decision.reason})
        return _aborted_outcome(plan, decision.reason, start_time)

    # Emit plan.created so TUI/listeners can render the DAG
    await _emit(_bus, PlanCreatedEvent,
        session_id=_sid,
        source=f"dispatch:{plan.mission_id}",
        plan_id=plan.mission_id,
        goal=plan.summary,
        step_count=len(plan.tasks),
        metadata={"task_plan_json": plan.model_dump_json()},
    )

    # Load PCD for agent context (if project is set)
    project_context: dict | None = None
    if project_id and context_curator:
        try:
            pcd = await context_curator.get_project_context(project_id)
            project_context = pcd or None
        except (OSError, ValueError, RuntimeError):
            logger.warning(
                "Failed to load PCD for dispatch (non-fatal)",
                extra={"project_id": project_id},
                exc_info=True,
            )

    completed_outputs: dict[str, dict] = {}
    task_results: list[TaskResult] = []
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    total_thinking_tokens = 0

    aborted = False
    abort_reason: str | None = None
    for layer_idx, layer in enumerate(layers):
        coros = []
        layer_tasks: list[TaskDefinition] = []
        resolved_inputs_map: dict[str, dict] = {}

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

            # Shallow copy so context injection doesn't mutate shared upstream dicts
            resolved_inputs = dict(resolved_inputs)

            # Inject context: full assembled packet (preferred) or raw PCD
            if context_assembler and project_id:
                try:
                    assembled = await context_assembler.build(
                        project_id=project_id,
                        task_definition=task.model_dump(),
                        resolved_inputs=dict(resolved_inputs),
                        domain_tags=task.domain_tags or None,
                    )
                    resolved_inputs["project_context"] = assembled.get(
                        "project_context", {}
                    )
                    # Inject Code Map separately so it's clearly labeled
                    code_map_content = assembled.get("code_map")
                    if code_map_content:
                        resolved_inputs["code_map"] = code_map_content
                    # Inject history so agents see past work in same domain
                    history_content = assembled.get("history")
                    if history_content:
                        resolved_inputs["project_history"] = history_content
                except (OSError, ValueError, RuntimeError):
                    logger.warning(
                        "Context assembly failed, falling back to PCD",
                        extra={"task_id": task.task_id, "project_id": project_id},
                        exc_info=True,
                    )
                    if project_context:
                        resolved_inputs["project_context"] = project_context
            elif project_context:
                resolved_inputs["project_context"] = project_context

            layer_tasks.append(task)
            resolved_inputs_map[task.task_id] = resolved_inputs
            coros.append(
                _execute_with_step_events(
                    task=task,
                    roster_entry=roster_entry,
                    resolved_inputs=resolved_inputs,
                    execute_agent_fn=execute_agent_fn,
                    execution_id=str(uuid.uuid4()),
                    gate=_gate,
                    mission_id=plan.mission_id,
                    budget_usd=mission_budget_usd,
                    event_bus=_bus,
                    session_id=_sid,
                )
            )

        if not coros:
            continue

        # Gate 2: pre_layer — review tasks about to execute
        decision = await _gate.review(GateContext(
            gate_type="pre_layer",
            mission_id=plan.mission_id,
            layer_index=layer_idx,
            total_layers=len(layers),
            pending_tasks=[
                {
                    "task_id": t.task_id,
                    "agent": t.agent,
                    "description": t.description,
                    "instructions": (t.instructions or "")[:500],
                    "input_keys": list(resolved_inputs_map.get(t.task_id, {}).keys()),
                }
                for t in layer_tasks
            ],
            completed_tasks=[r.model_dump() for r in task_results],
            total_cost_usd=total_cost,
            budget_usd=mission_budget_usd,
        ))
        if decision.action == GateAction.ABORT:
            logger.info("Mission aborted at pre_layer gate", extra={"layer": layer_idx})
            for c in coros:
                c.close()
            aborted = True
            abort_reason = decision.reason
            break
        if decision.action == GateAction.SKIP:
            for c in coros:
                c.close()
            for t in layer_tasks:
                task_results.append(_skipped_result(t, decision.reason))
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

                # Apply context_updates to PCD (non-fatal)
                if context_curator and project_id and task_result.context_updates:
                    try:
                        await context_curator.apply_task_updates(
                            project_id,
                            task_result.context_updates,
                            agent_id=task_result.agent_name,
                            mission_id=plan.mission_id,
                            task_id=task_result.task_id,
                        )
                    except (OSError, ValueError, RuntimeError):
                        logger.warning(
                            "Context update failed (non-fatal)",
                            extra={"task_id": task_result.task_id},
                            exc_info=True,
                        )

            total_cost += task_result.cost_usd
            total_input_tokens += task_result.token_usage.input
            total_output_tokens += task_result.token_usage.output
            total_thinking_tokens += task_result.token_usage.thinking

        # Gate 5: post_layer — review layer results before proceeding
        decision = await _gate.review(GateContext(
            gate_type="post_layer",
            mission_id=plan.mission_id,
            layer_index=layer_idx,
            total_layers=len(layers),
            completed_tasks=[r.model_dump() for r in task_results],
            total_cost_usd=total_cost,
            budget_usd=mission_budget_usd,
        ))
        if decision.action == GateAction.ABORT:
            logger.info("Mission aborted at post_layer gate", extra={"layer": layer_idx})
            aborted = True
            abort_reason = decision.reason
            break

        # Check budget after each layer completes
        if mission_budget_usd and total_cost > mission_budget_usd:
            logger.warning(
                "Mission budget exceeded, cancelling remaining tasks",
                extra={
                    "cumulative_cost": total_cost,
                    "budget": mission_budget_usd,
                },
            )
            break

    # Determine mission status
    budget_exceeded = bool(mission_budget_usd and total_cost > mission_budget_usd)
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

    if aborted:
        status = MissionStatus.FAILED
    elif budget_exceeded:
        status = MissionStatus.FAILED
    elif successful_tasks == total_tasks:
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
        abort_reason=abort_reason,
    )


async def _execute_with_step_events(
    task: TaskDefinition,
    roster_entry: RosterAgentEntry,
    resolved_inputs: dict[str, Any],
    execute_agent_fn: ExecuteAgentFn,
    execution_id: str,
    gate: GateReviewer | None,
    mission_id: str,
    budget_usd: float,
    event_bus: EventBusProtocol,
    session_id: str,
) -> TaskResult:
    """Wrap _execute_with_retry with PlanStep lifecycle events."""
    await _emit(event_bus, PlanStepStartedEvent,
        session_id=session_id,
        source=f"dispatch:{mission_id}",
        plan_id=mission_id,
        step_id=task.task_id,
        step_name=task.description or task.task_id,
        assigned_agent=task.agent,
    )

    result = await _execute_with_retry(
        task=task,
        roster_entry=roster_entry,
        resolved_inputs=resolved_inputs,
        execute_agent_fn=execute_agent_fn,
        execution_id=execution_id,
        gate=gate,
        mission_id=mission_id,
        budget_usd=budget_usd,
    )

    await _emit(event_bus, PlanStepCompletedEvent,
        session_id=session_id,
        source=f"dispatch:{mission_id}",
        plan_id=mission_id,
        step_id=task.task_id,
        result_summary=f"{result.agent_name}: {result.status.value}",
        status=result.status.value,
    )

    return result


async def _execute_with_retry(
    task: TaskDefinition,
    roster_entry: RosterAgentEntry,
    resolved_inputs: dict[str, Any],
    execute_agent_fn: ExecuteAgentFn,
    execution_id: str = "",
    gate: GateReviewer | None = None,
    mission_id: str = "",
    budget_usd: float = 0.0,
) -> TaskResult:
    """Execute a task with 3-tier verification and retry-with-feedback.

    gate is always provided by dispatch() — defaults to NoOpGate there.
    """
    _gate: GateReviewer = gate or NoOpGate()
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
                instructions=instructions,
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
                execution_id=execution_id,
            )
        except Exception as e:
            duration = time.monotonic() - task_start
            is_token_limit = isinstance(e, UsageLimitExceeded)
            logger.error(
                "Task execution failed",
                extra={
                    "task_id": task.task_id,
                    "error": str(e),
                    "attempt": attempt,
                    "token_limit_exceeded": is_token_limit,
                },
            )
            # Token limit errors won't resolve on retry — fail fast
            if attempt < retry_budget and not is_token_limit:
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
                execution_id=execution_id,
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
                # Gate 4: verification_failed — review before retry
                gate_decision = await _gate.review(GateContext(
                    gate_type="verification_failed",
                    mission_id=mission_id,
                    task_id=task.task_id,
                    task_output=output,
                    verification=build_verification_outcome(verification).model_dump(),
                    current_instructions=instructions,
                    current_inputs=resolved_inputs,
                    budget_usd=budget_usd,
                ))
                if gate_decision.action == GateAction.ABORT:
                    return _failed_result(
                        task, "Aborted at verification gate",
                        retry_count=attempt, retry_history=retry_history,
                        execution_id=execution_id,
                    )
                if gate_decision.action == GateAction.SKIP:
                    return _skipped_result(task, gate_decision.reason, execution_id=execution_id)
                if gate_decision.action == GateAction.MODIFY:
                    # Accept output despite verification failure
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
                        execution_id=execution_id,
                    )

                # Default (CONTINUE/RETRY): proceed with retry as normal
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
                if gate_decision.modified_instructions:
                    instructions = gate_decision.modified_instructions
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
                execution_id=execution_id,
            )

        # Gate 3: post_task — review successful output before accepting
        gate_decision = await _gate.review(GateContext(
            gate_type="post_task",
            mission_id=mission_id,
            task_id=task.task_id,
            task_output=output,
            verification=build_verification_outcome(verification).model_dump(),
            current_instructions=instructions,
            current_inputs=resolved_inputs,
            total_cost_usd=cost_usd,
            budget_usd=budget_usd,
        ))
        if gate_decision.action == GateAction.ABORT:
            return _failed_result(
                task, "Aborted at post_task gate",
                retry_count=attempt, retry_history=retry_history,
                execution_id=execution_id,
            )
        if gate_decision.action == GateAction.SKIP:
            return _skipped_result(task, gate_decision.reason, execution_id=execution_id)
        if gate_decision.action == GateAction.RETRY and attempt < retry_budget:
            retry_history.append(RetryHistoryEntry(
                attempt=attempt + 1,
                failure_tier=0,
                failure_reason="Reviewer requested retry",
                feedback_provided=gate_decision.reason or "",
            ))
            instructions = gate_decision.modified_instructions or _append_feedback(
                task.instructions,
                gate_decision.reason or "Reviewer requested retry.",
            )
            continue

        # Extract context_updates from agent output (if any)
        context_updates = output.pop("context_updates", [])

        # Auto-generate PQI context_update for project tracking
        pqi = output.get("pqi")
        if isinstance(pqi, dict) and pqi.get("composite") is not None:
            context_updates.append({
                "key": "pqi_score",
                "value": {
                    "composite": pqi["composite"],
                    "quality_band": pqi.get("quality_band"),
                    "dimensions": {
                        name: dim.get("score")
                        for name, dim in pqi.get("dimensions", {}).items()
                    },
                    "file_count": pqi.get("file_count"),
                    "line_count": pqi.get("line_count"),
                },
            })

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
            execution_id=execution_id,
            context_updates=context_updates if isinstance(context_updates, list) else [],
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


def _aborted_outcome(
    plan: TaskPlan,
    reason: str | None,
    start_time: float,
    task_results: list[TaskResult] | None = None,
) -> MissionOutcome:
    """Build a MissionOutcome for an aborted mission."""
    return MissionOutcome(
        mission_id=plan.mission_id,
        status=MissionStatus.FAILED,
        task_results=task_results or [],
        total_cost_usd=0.0,
        total_duration_seconds=round(time.monotonic() - start_time, 2),
        total_tokens=TaskTokenUsage(),
        abort_reason=reason,
    )


def _skipped_result(
    task: TaskDefinition,
    reason: str | None = None,
    execution_id: str = "",
) -> TaskResult:
    """Build a TaskResult with SKIPPED status."""
    return TaskResult(
        task_id=task.task_id,
        agent_name=task.agent,
        status=TaskStatus.SKIPPED,
        output_reference={},
        token_usage=TaskTokenUsage(),
        cost_usd=0.0,
        duration_seconds=0.0,
        retry_count=0,
        retry_history=[],
        execution_id=execution_id,
        skip_reason=reason,
    )


def _failed_result(
    task: TaskDefinition,
    reason: str,
    retry_count: int = 0,
    retry_history: list[RetryHistoryEntry] | None = None,
    execution_id: str = "",
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
        execution_id=execution_id,
    )


