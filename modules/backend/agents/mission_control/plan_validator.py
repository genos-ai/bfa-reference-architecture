"""TaskPlan validation — 11 deterministic rules.

Every plan must pass all rules before Mission Control begins execution.
On failure: log the specific error, retry Planning Agent (max 2), then fail mission.

Rules:
  1. Schema validation — Pydantic handles this at parse time
  2. Agent validation — agent+version exists in roster
  3. DAG validation — topological sort succeeds, no cycles
  4. Dependency consistency — from_upstream source_tasks in dependencies
  5. Input compatibility — source_fields exist in source agent output contract
  6. Check registry validation — every check name must be registered
  7. Budget validation — estimated_cost within mission budget
  8. Timeout validation — overrides within roster maximums
  9. Critical path validation — all critical_path task_ids exist
  10. Tier 3 completeness — criteria + evaluator + threshold present
  11. Self-evaluation prevention — no task specifies itself as evaluator
"""

from collections import deque

from modules.backend.agents.mission_control.check_registry import check_exists, list_checks
from modules.backend.agents.mission_control.roster import Roster
from modules.backend.core.logging import get_logger
from modules.backend.schemas.task_plan import TaskPlan

# Ensure built-in checks are registered before validation
from modules.backend.agents.mission_control.checks import builtin  # noqa: F401

logger = get_logger(__name__)


class ValidationResult:
    """Aggregated result from all validation rules."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, rule: str, message: str) -> None:
        self.errors.append(f"[{rule}] {message}")

    def __repr__(self) -> str:
        if self.is_valid:
            return "ValidationResult(valid=True)"
        return f"ValidationResult(valid=False, errors={len(self.errors)})"


def validate_plan(
    plan: TaskPlan,
    roster: Roster,
    mission_budget_usd: float,
) -> ValidationResult:
    """Run all 11 validation rules against the plan. Returns aggregated result."""
    result = ValidationResult()

    # Rule 1: Schema validation — handled by Pydantic at parse time.
    _rule_2_agent_validation(plan, roster, result)
    _rule_3_dag_validation(plan, result)
    _rule_4_dependency_consistency(plan, result)
    _rule_5_input_compatibility(plan, roster, result)
    _rule_6_check_registry(plan, result)
    _rule_7_budget_validation(plan, mission_budget_usd, result)
    _rule_8_timeout_validation(plan, roster, result)
    _rule_9_critical_path_validation(plan, result)
    _rule_10_tier3_completeness(plan, roster, result)
    _rule_11_self_evaluation_prevention(plan, result)

    if result.is_valid:
        logger.info("TaskPlan validation passed", extra={"mission_id": plan.mission_id})
    else:
        logger.warning(
            "TaskPlan validation failed",
            extra={"mission_id": plan.mission_id, "error_count": len(result.errors)},
        )

    return result


def _rule_2_agent_validation(plan: TaskPlan, roster: Roster, result: ValidationResult) -> None:
    """Every agent+version in the plan must exist in the roster."""
    for task in plan.tasks:
        entry = roster.get_agent(task.agent, task.agent_version)
        if entry is None:
            result.add_error(
                "agent_validation",
                f"Task '{task.task_id}': agent '{task.agent}' "
                f"version '{task.agent_version}' not in roster",
            )


def _rule_3_dag_validation(plan: TaskPlan, result: ValidationResult) -> None:
    """Topological sort using Kahn's algorithm. Reject cycles."""
    task_ids = {t.task_id for t in plan.tasks}

    # Check for duplicate task IDs
    if len(task_ids) != len(plan.tasks):
        seen: set[str] = set()
        for t in plan.tasks:
            if t.task_id in seen:
                result.add_error("dag_validation", f"Duplicate task_id: '{t.task_id}'")
            seen.add(t.task_id)
        return

    # Check dependency references exist
    for task in plan.tasks:
        for dep in task.dependencies:
            if dep not in task_ids:
                result.add_error(
                    "dag_validation",
                    f"Task '{task.task_id}' depends on unknown task '{dep}'",
                )

    # Kahn's algorithm for cycle detection
    in_degree: dict[str, int] = {tid: 0 for tid in task_ids}
    adjacency: dict[str, list[str]] = {tid: [] for tid in task_ids}

    for task in plan.tasks:
        for dep in task.dependencies:
            if dep in task_ids:
                adjacency[dep].append(task.task_id)
                in_degree[task.task_id] += 1

    queue: deque[str] = deque(
        tid for tid, deg in in_degree.items() if deg == 0
    )
    sorted_count = 0

    while queue:
        node = queue.popleft()
        sorted_count += 1
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if sorted_count != len(task_ids):
        result.add_error("dag_validation", "Cycle detected in task dependency graph")


def _rule_4_dependency_consistency(plan: TaskPlan, result: ValidationResult) -> None:
    """Every from_upstream source_task must be in the task's dependencies."""
    for task in plan.tasks:
        for field_name, ref in task.inputs.from_upstream.items():
            if ref.source_task not in task.dependencies:
                result.add_error(
                    "dependency_consistency",
                    f"Task '{task.task_id}': from_upstream field '{field_name}' "
                    f"references task '{ref.source_task}' which is not in dependencies",
                )


def _rule_5_input_compatibility(
    plan: TaskPlan, roster: Roster, result: ValidationResult,
) -> None:
    """Every from_upstream source_field must exist in the source agent's output contract."""
    task_agent_map = {t.task_id: t.agent for t in plan.tasks}

    for task in plan.tasks:
        for field_name, ref in task.inputs.from_upstream.items():
            source_agent_name = task_agent_map.get(ref.source_task)
            if source_agent_name is None:
                continue  # Rule 3 catches missing tasks

            source_entry = roster.get_agent_by_name(source_agent_name)
            if source_entry is None:
                continue  # Rule 2 catches missing agents

            if ref.source_field not in source_entry.interface.output:
                result.add_error(
                    "input_compatibility",
                    f"Task '{task.task_id}': from_upstream field '{field_name}' "
                    f"references source_field '{ref.source_field}' which does not "
                    f"exist in agent '{source_agent_name}' output contract "
                    f"(available: {list(source_entry.interface.output.keys())})",
                )


def _rule_6_check_registry(plan: TaskPlan, result: ValidationResult) -> None:
    """Every check name in tier_2.deterministic_checks must be registered."""
    for task in plan.tasks:
        for check_spec in task.verification.tier_2.deterministic_checks:
            check_name = check_spec.check
            if not check_exists(check_name):
                result.add_error(
                    "check_registry",
                    f"Task '{task.task_id}': unknown check '{check_name}' in "
                    f"tier_2.deterministic_checks. "
                    f"Available checks: {', '.join(list_checks())}",
                )


def _rule_7_budget_validation(
    plan: TaskPlan,
    mission_budget_usd: float,
    result: ValidationResult,
) -> None:
    """Estimated cost must be within mission budget."""
    if plan.estimated_cost_usd > mission_budget_usd:
        result.add_error(
            "budget_validation",
            f"Estimated cost ${plan.estimated_cost_usd:.2f} exceeds "
            f"mission budget ${mission_budget_usd:.2f}",
        )


def _rule_8_timeout_validation(
    plan: TaskPlan, roster: Roster, result: ValidationResult,
) -> None:
    """Timeout overrides must not exceed roster maximums."""
    for task in plan.tasks:
        override = task.constraints.timeout_override_seconds
        if override is None:
            continue

        entry = roster.get_agent_by_name(task.agent)
        if entry is None:
            continue  # Rule 2 catches missing agents

        if override > entry.constraints.timeout_seconds:
            result.add_error(
                "timeout_validation",
                f"Task '{task.task_id}': timeout override {override}s exceeds "
                f"roster maximum {entry.constraints.timeout_seconds}s "
                f"for agent '{task.agent}'",
            )


def _rule_9_critical_path_validation(plan: TaskPlan, result: ValidationResult) -> None:
    """All critical_path task_ids must exist in the plan."""
    task_ids = set(plan.task_ids)
    for cp_id in plan.execution_hints.critical_path:
        if cp_id not in task_ids:
            result.add_error(
                "critical_path_validation",
                f"Critical path references unknown task: '{cp_id}'",
            )


def _rule_10_tier3_completeness(
    plan: TaskPlan, roster: Roster, result: ValidationResult,
) -> None:
    """When Tier 3 is required, criteria+evaluator+threshold must all be present."""
    for task in plan.tasks:
        t3 = task.verification.tier_3
        if not t3.requires_ai_evaluation:
            continue

        if not t3.evaluation_criteria:
            result.add_error(
                "tier3_completeness",
                f"Task '{task.task_id}': Tier 3 enabled but evaluation_criteria is empty",
            )
        if not t3.evaluator_agent:
            result.add_error(
                "tier3_completeness",
                f"Task '{task.task_id}': Tier 3 enabled but evaluator_agent is missing",
            )
        if t3.min_evaluation_score is None:
            result.add_error(
                "tier3_completeness",
                f"Task '{task.task_id}': Tier 3 enabled but min_evaluation_score is missing",
            )
        if t3.evaluator_agent and not roster.get_agent_by_name(t3.evaluator_agent):
            result.add_error(
                "tier3_completeness",
                f"Task '{task.task_id}': evaluator_agent "
                f"'{t3.evaluator_agent}' not in roster",
            )


def _rule_11_self_evaluation_prevention(
    plan: TaskPlan, result: ValidationResult,
) -> None:
    """No task may specify itself (its own agent) as the evaluator."""
    for task in plan.tasks:
        t3 = task.verification.tier_3
        if t3.requires_ai_evaluation and t3.evaluator_agent == task.agent:
            result.add_error(
                "self_evaluation_prevention",
                f"Task '{task.task_id}': agent '{task.agent}' "
                f"cannot evaluate its own output (P13)",
            )
