# Implementation Plan: Verification Pipeline

*Created: 2026-03-04*
*Status: Done*
*Phase: 5 of 8 (AI-First Platform Build)*
*Depends on: Phase 1-4 (Event Bus, Session Model, Streaming Mission Control, Mission Control Dispatch)*
*Blocked by: Phase 4*

---

## Summary

Build the 3-tier verification pipeline that runs after every agent completes a task within Mission Control. Each tier is cheaper and faster than the next. Execution stops at the first failure.

- **Tier 1**: Structural verification (code, zero tokens, milliseconds) — validates output against agent interface contract
- **Tier 2**: Deterministic functional verification (code, zero tokens) — runs registered check functions specified in the TaskPlan
- **Tier 3**: AI-based quality evaluation (Verification Agent, Opus 4.6) — only when the task genuinely requires judgment

Also build the Check Registry (named deterministic check functions that the Planning Agent can reference in TaskPlans) and the Verification Agent (dedicated horizontal agent for Tier 3 evaluation).

This plan replaces the Tier-1-only `verify_task()` hook from Plan 13 with the full pipeline. It also enables TaskPlan validation rule 6 (check registry validation).

**Dev mode: breaking changes allowed.**

## Context

- Research doc: `docs/98-research/11-bfa-workflow-architecture-specification.md` — 3-tier verification, check registry, Verification Agent spec, self-evaluation prevention
- Project principles: `docs/03-principles/01-project-principles.md` — P13 (No Agent Self-Evaluation), P2 (Deterministic Over Non-Deterministic), P11 (Test Without LLMs)
- Plan 13: dispatch loop with `verify_task()` hook, MissionOutcome schema, TaskPlan verification fields
- Plan 12: `AgentInterfaceSchema` (typed I/O contracts) — used by Tier 1 structural validation
- Plan 13 (Mission Control Dispatch): TaskPlan validation rules, rule 6 disabled pending check registry

## What to Build

- `modules/backend/agents/mission_control/check_registry.py` — Check registry with decorator registration (~100 lines)
- `modules/backend/agents/mission_control/checks/__init__.py` — package init
- `modules/backend/agents/mission_control/checks/builtin.py` — Built-in checks: `validate_json_schema`, `validate_field_exists`, `validate_field_type`, `validate_field_range` (~120 lines)
- `modules/backend/agents/mission_control/verification.py` — 3-tier pipeline (~200 lines)
- `modules/backend/agents/horizontal/verification/__init__.py` — package init
- `modules/backend/agents/horizontal/verification/agent.py` — Verification Agent (~100 lines)
- `config/agents/horizontal/verification/agent.yaml` — Verification Agent config
- `config/prompts/agents/horizontal/verification/system.md` — Verification Agent system prompt (security-critical)
- `modules/backend/agents/mission_control/outcome.py` — MODIFY: add full verification details per task
- `modules/backend/agents/mission_control/dispatch.py` — MODIFY: replace Tier 1 hook with full pipeline call
- `modules/backend/agents/mission_control/plan_validator.py` — MODIFY: enable rule 6 (check registry validation)
- Tests: check registry, each tier independently, full pipeline, Verification Agent with TestModel

## Key Design Decisions

- **Check Registry** — Simple Python dict mapping check names to async callables. Registration via `@register_check("check_name")` decorator. Checks registered at module import time (no database, no dynamic discovery). Unknown check name in TaskPlan fails validation (rule 6).
- **3-Tier Pipeline** — Called by dispatch loop's `verify_task()` hook (replaces Plan 13's inline Tier 1). Sequential: Tier 1 → Tier 2 → Tier 3. Stops at first failure (cheapest/fastest checks first). Each tier returns `TierResult` with status, details. Overall `VerificationResult` aggregates tier results with combined pass/fail.
- **Tier 1 (structural)** — Validate output conforms to agent interface contract (`AgentInterfaceSchema`). All required output fields present with correct types. Zero tokens, milliseconds.
- **Tier 2 (deterministic functional)** — Run each check specified in `task.verification.tier_2.deterministic_checks`. All checks run (even if one fails) to collect complete diagnostic info. Zero tokens.
- **Tier 3 (AI evaluation)** — Only if `task.verification.tier_3.requires_ai_evaluation` is true. Dispatch Verification Agent. Mission Control makes deterministic pass/fail: `overall_score >= min_evaluation_score` AND `blocking_issues` is empty. Planning Agent is prompted to use Tier 3 sparingly.
- **Verification Agent** — Model: Opus 4.6 with extended thinking. System prompt is security-critical, version-controlled. Isolation: cannot evaluate own output or Planning Agent output (enforced by dispatch code). Thinking trace captured for audit.
- **Retry-with-feedback (Reflection pattern)** — On Tier 1/Tier 2 failure: append failure details to agent instructions, retry within budget. On Tier 3 failure: append evaluation feedback (criteria scores, issues, recommendations) to instructions, retry. `retry_history` records attempt, failure_tier, failure_reason, feedback_provided.
- **MissionOutcome updates** — Per-task `verification_outcome` now has `tier_1`, `tier_2`, `tier_3` with full details. Tier 3 includes `overall_score`, `criteria_results_reference`, `evaluator_thinking_trace_reference`, `cost_usd`. `retry_history` populated with feedback details.
- **Langfuse observability bootstrap** — `@observe()` decorator on Planning Agent and Verification Agent invocations. Thinking traces as span metadata. Verification outcomes as structured log events. `langfuse` added to `requirements.txt`.

## Success Criteria

- [ ] Check registry registers and executes named check functions
- [ ] Built-in checks work: `validate_json_schema`, `validate_field_exists`, `validate_field_type`
- [ ] Unknown check name in TaskPlan fails validation (rule 6 enabled)
- [ ] Full 3-tier pipeline: structural → deterministic → AI evaluation
- [ ] Pipeline stops at first tier failure
- [ ] Verification Agent evaluates output and returns structured scores
- [ ] Mission Control makes deterministic pass/fail based on scores vs threshold
- [ ] Self-evaluation prevention enforced (dispatch code check)
- [ ] Retry-with-feedback includes evaluation feedback from failing tier
- [ ] MissionOutcome includes full verification details per task per tier
- [ ] Planning Agent thinking trace captured
- [ ] Verification Agent thinking trace captured
- [ ] Langfuse `@observe()` produces traces
- [ ] All Plan 13 tests still pass

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Commit any uncommitted work | `git status`, then commit if needed |
| 0.2 | Create feature branch | `git checkout -b feature/verification-pipeline` |

---

### Step 1: Check Registry

**File:** `modules/backend/agents/mission_control/check_registry.py` (NEW, ~100 lines)

The check registry is a simple module-level dict mapping check names to async callables. Registration happens via a `@register_check` decorator at module import time. No database, no dynamic discovery, no service layer — this is a compile-time registry.

```python
"""
Check registry for Tier 2 deterministic verification.

Named check functions are registered via @register_check decorator at
import time. The Planning Agent references these names in TaskPlan
tier_2.deterministic_checks. Mission Control's plan validator (rule 6)
rejects unknown names. The verification pipeline looks up and executes
checks by name.

Adding a new check:
  1. Create a function in checks/ submodule
  2. Decorate with @register_check("your_check_name")
  3. It becomes available to TaskPlans immediately
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class CheckResult:
    """Result from a single deterministic check execution."""

    passed: bool
    details: str
    execution_time_ms: float


# Type alias for check function signature
CheckFn = Callable[[dict[str, Any], dict[str, Any]], Awaitable[CheckResult]]

# Module-level registry — populated at import time by @register_check
_REGISTRY: dict[str, CheckFn] = {}


def register_check(name: str) -> Callable[[CheckFn], CheckFn]:
    """Decorator to register a named check function.

    Usage:
        @register_check("validate_json_schema")
        async def validate_json_schema(output: dict, params: dict) -> CheckResult:
            ...

    Args:
        name: Unique check name. Referenced by Planning Agent in TaskPlans.

    Raises:
        ValueError: If name is already registered (duplicate check names
                    are a programming error, not a runtime condition).
    """
    def decorator(fn: CheckFn) -> CheckFn:
        if name in _REGISTRY:
            raise ValueError(
                f"Duplicate check name '{name}'. "
                f"Already registered by {_REGISTRY[name].__module__}.{_REGISTRY[name].__qualname__}"
            )
        _REGISTRY[name] = fn
        logger.debug("Check registered", extra={"check_name": name})
        return fn
    return decorator


def get_check(name: str) -> CheckFn | None:
    """Look up a registered check by name. Returns None if not found."""
    return _REGISTRY.get(name)


def check_exists(name: str) -> bool:
    """Check if a named check function is registered."""
    return name in _REGISTRY


def list_checks() -> list[str]:
    """Return all registered check names (sorted for deterministic output)."""
    return sorted(_REGISTRY.keys())


def get_registry_snapshot() -> dict[str, CheckFn]:
    """Return a shallow copy of the registry. For testing and introspection."""
    return dict(_REGISTRY)
```

**Key decisions:**
- `CheckResult` is a frozen dataclass (immutable, simple). Not a Pydantic model — checks are internal infrastructure, not API contracts.
- `_REGISTRY` is module-level. No class wrapper, no singleton pattern. A dict is sufficient.
- `register_check` raises `ValueError` on duplicate names. This is a programming error caught at import time, not a runtime condition.
- `check_exists()` is the function used by plan_validator rule 6.

**Verify:** Import the module, confirm `_REGISTRY` is empty (no built-in checks registered yet — those come in Step 2).

---

### Step 2: Built-in Checks

**File:** `modules/backend/agents/mission_control/checks/__init__.py` (NEW)

```python
"""Built-in deterministic checks for Tier 2 verification.

Import this package to register all built-in checks in the check registry.
Domain-specific checks are added in separate submodules.
"""

from modules.backend.agents.mission_control.checks import builtin  # noqa: F401
```

**File:** `modules/backend/agents/mission_control/checks/builtin.py` (NEW, ~120 lines)

Four built-in checks that cover the most common structural validation needs. These are the checks available from day one — domain-specific checks are added as agents and missions are built.

```python
"""
Built-in deterministic checks for Tier 2 verification.

These checks are generic and reusable across any agent output. They are
registered in the check registry at import time. The Planning Agent
references them by name in TaskPlan tier_2.deterministic_checks.

Adding domain-specific checks: create a new module in checks/ and
import it from checks/__init__.py.
"""

from __future__ import annotations

import time
from typing import Any

from modules.backend.agents.mission_control.check_registry import (
    CheckResult,
    register_check,
)
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@register_check("validate_json_schema")
async def validate_json_schema(output: dict[str, Any], params: dict[str, Any]) -> CheckResult:
    """Validate output against a JSON Schema.

    Params:
        schema (dict): JSON Schema to validate against.

    Uses jsonschema for validation. Collects all errors, not just the first.
    """
    start = time.perf_counter()
    try:
        import jsonschema

        schema = params.get("schema")
        if not schema:
            return CheckResult(
                passed=False,
                details="No 'schema' provided in check params",
                execution_time_ms=_elapsed_ms(start),
            )

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(output))

        if errors:
            error_details = "; ".join(
                f"{'.'.join(str(p) for p in e.absolute_path)}: {e.message}"
                if e.absolute_path else e.message
                for e in errors[:10]  # Cap at 10 errors to avoid log bloat
            )
            return CheckResult(
                passed=False,
                details=f"{len(errors)} validation error(s): {error_details}",
                execution_time_ms=_elapsed_ms(start),
            )

        return CheckResult(
            passed=True,
            details="Output conforms to schema",
            execution_time_ms=_elapsed_ms(start),
        )
    except ImportError:
        return CheckResult(
            passed=False,
            details="jsonschema package not installed",
            execution_time_ms=_elapsed_ms(start),
        )


@register_check("validate_field_exists")
async def validate_field_exists(output: dict[str, Any], params: dict[str, Any]) -> CheckResult:
    """Validate that specified fields exist in the output.

    Params:
        fields (list[str]): Field names that must be present as top-level keys.
    """
    start = time.perf_counter()

    fields = params.get("fields", [])
    if not fields:
        return CheckResult(
            passed=False,
            details="No 'fields' provided in check params",
            execution_time_ms=_elapsed_ms(start),
        )

    missing = [f for f in fields if f not in output]

    if missing:
        return CheckResult(
            passed=False,
            details=f"Missing fields: {', '.join(missing)}",
            execution_time_ms=_elapsed_ms(start),
        )

    return CheckResult(
        passed=True,
        details=f"All {len(fields)} required fields present",
        execution_time_ms=_elapsed_ms(start),
    )


@register_check("validate_field_type")
async def validate_field_type(output: dict[str, Any], params: dict[str, Any]) -> CheckResult:
    """Validate that specified fields have the expected types.

    Params:
        field_types (dict[str, str]): Mapping of field name to expected type name.
            Supported type names: "str", "int", "float", "bool", "list", "dict", "null".
    """
    start = time.perf_counter()

    TYPE_MAP: dict[str, type | None] = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "null": type(None),
    }

    field_types = params.get("field_types", {})
    if not field_types:
        return CheckResult(
            passed=False,
            details="No 'field_types' provided in check params",
            execution_time_ms=_elapsed_ms(start),
        )

    type_errors = []
    for field_name, expected_type_name in field_types.items():
        if field_name not in output:
            type_errors.append(f"'{field_name}' not found in output")
            continue

        expected_type = TYPE_MAP.get(expected_type_name)
        if expected_type is None and expected_type_name != "null":
            type_errors.append(f"Unknown type name '{expected_type_name}' for field '{field_name}'")
            continue

        actual_value = output[field_name]
        if expected_type_name == "null":
            if actual_value is not None:
                type_errors.append(
                    f"'{field_name}': expected null, got {type(actual_value).__name__}"
                )
        elif not isinstance(actual_value, expected_type):
            type_errors.append(
                f"'{field_name}': expected {expected_type_name}, got {type(actual_value).__name__}"
            )

    if type_errors:
        return CheckResult(
            passed=False,
            details=f"{len(type_errors)} type error(s): {'; '.join(type_errors)}",
            execution_time_ms=_elapsed_ms(start),
        )

    return CheckResult(
        passed=True,
        details=f"All {len(field_types)} field types valid",
        execution_time_ms=_elapsed_ms(start),
    )


@register_check("validate_field_range")
async def validate_field_range(output: dict[str, Any], params: dict[str, Any]) -> CheckResult:
    """Validate that numeric fields fall within specified ranges.

    Params:
        ranges (dict[str, dict]): Mapping of field name to range spec.
            Each range spec can have: "min" (float), "max" (float), or both.
    """
    start = time.perf_counter()

    ranges = params.get("ranges", {})
    if not ranges:
        return CheckResult(
            passed=False,
            details="No 'ranges' provided in check params",
            execution_time_ms=_elapsed_ms(start),
        )

    range_errors = []
    for field_name, range_spec in ranges.items():
        if field_name not in output:
            range_errors.append(f"'{field_name}' not found in output")
            continue

        value = output[field_name]
        if not isinstance(value, (int, float)):
            range_errors.append(
                f"'{field_name}': expected numeric, got {type(value).__name__}"
            )
            continue

        min_val = range_spec.get("min")
        max_val = range_spec.get("max")

        if min_val is not None and value < min_val:
            range_errors.append(f"'{field_name}': {value} < min {min_val}")
        if max_val is not None and value > max_val:
            range_errors.append(f"'{field_name}': {value} > max {max_val}")

    if range_errors:
        return CheckResult(
            passed=False,
            details=f"{len(range_errors)} range error(s): {'; '.join(range_errors)}",
            execution_time_ms=_elapsed_ms(start),
        )

    return CheckResult(
        passed=True,
        details=f"All {len(ranges)} field ranges valid",
        execution_time_ms=_elapsed_ms(start),
    )


def _elapsed_ms(start: float) -> float:
    """Calculate elapsed time in milliseconds since start."""
    return round((time.perf_counter() - start) * 1000, 3)
```

**Design decisions:**
- All checks are `async` even though the built-ins are synchronous. This keeps the interface uniform — domain-specific checks may need I/O (e.g., running `terraform validate`, calling a schema registry).
- `validate_json_schema` uses `jsonschema` library. Add `jsonschema>=4.20.0` to `requirements.txt`.
- All checks collect all errors (not just the first) for complete diagnostic info.
- `_elapsed_ms` helper measures wall-clock time per check for performance monitoring.
- Error messages are capped (10 schema errors) to avoid log bloat.

**Verify:** Import `checks` package, confirm all four checks are registered:
```bash
python -c "from modules.backend.agents.mission_control.checks import builtin; from modules.backend.agents.mission_control.check_registry import list_checks; print(list_checks())"
```

---

### Step 3: Verification Pipeline

**File:** `modules/backend/agents/mission_control/verification.py` (NEW, ~200 lines)

The 3-tier verification pipeline. Called by the dispatch loop after each agent returns output. Sequential execution: Tier 1 → Tier 2 → Tier 3. Stops at first tier failure.

```python
"""
3-tier verification pipeline for Mission Control.

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
    """Tier 1: Structural validation against agent interface contract.

    Validates:
    - Output is a non-empty dict
    - All required output fields are present (from AgentInterfaceSchema)
    - Required output fields specified in tier_1.required_output_fields are present
    - Basic type conformance where type info is available
    """
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

    # Basic structural check
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
    diagnostic information. This is intentional — the retry-with-feedback
    mechanism benefits from knowing all failures, not just the first.
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
            # This should not happen if plan_validator rule 6 is enabled,
            # but defend against it anyway.
            check_results.append({
                "check": check_name,
                "passed": False,
                "details": f"Check '{check_name}' not found in registry",
                "execution_time_ms": 0.0,
            })
            failed_checks.append(check_name)
            continue

        try:
            result = await check_fn(output, check_params)
            check_results.append({
                "check": check_name,
                "passed": result.passed,
                "details": result.details,
                "execution_time_ms": result.execution_time_ms,
            })
            if not result.passed:
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
    checks_passed = checks_run - len(failed_checks)

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
    """Tier 3: AI-based quality evaluation via Verification Agent.

    Only runs if task.verification.tier_3.requires_ai_evaluation is true.
    Dispatches the Verification Agent with task context and evaluation
    criteria. Mission Control makes deterministic pass/fail based on
    scores vs threshold.
    """
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
                details += f" — score below threshold"

        # Store thinking trace and criteria results as references
        # In production, these would be stored in object storage and referenced
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

    Extracts failure details from the failing tier and formats them
    as structured feedback that can be appended to the agent's
    instructions on retry.

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
        # Include per-check details for targeted fixes
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

    return {
        "attempt": attempt,
        "failure_tier": failed_tier,
        "failure_reason": verification_result.tier_1.details if failed_tier == 1
            else verification_result.tier_2.details if failed_tier == 2
            else verification_result.tier_3.details if failed_tier == 3
            else "Unknown failure",
        "feedback_provided": "\n".join(feedback_parts),
    }


def _elapsed_ms(start: float) -> float:
    """Calculate elapsed time in milliseconds since start."""
    return round((time.perf_counter() - start) * 1000, 3)
```

**Key patterns:**
- `run_verification_pipeline()` is the single entry point called by the dispatch loop.
- Sequential execution with early exit on failure — Tier 2 never runs if Tier 1 fails.
- Tier 2 runs ALL checks even if one fails (for complete diagnostics).
- Tier 3 self-evaluation prevention is enforced in code (P13), not just by prompt.
- `build_retry_feedback()` formats failure details for the Reflection pattern.
- `execute_agent_fn` is injected — the pipeline does not import the dispatch module (avoids circular imports).

---

### Step 4: Verification Agent

**File:** `modules/backend/agents/horizontal/verification/__init__.py` (NEW)

```python
"""Verification Agent — evaluates other agents' work during Tier 3 verification."""
```

**File:** `modules/backend/agents/horizontal/verification/agent.py` (NEW, ~100 lines)

The Verification Agent is a dedicated PydanticAI agent whose sole job is to evaluate other agents' work. It follows the same `create_agent()` / `run_agent()` pattern as all other agents.

```python
"""
Verification Agent (horizontal.verification.agent).

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
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.models import Model

from modules.backend.agents.mission_control.mission_control import assemble_instructions
from modules.backend.agents.deps.base import BaseAgentDeps
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
```

**File:** `config/agents/horizontal/verification/agent.yaml` (NEW)

```yaml
# =============================================================================
# Verification Agent Configuration
# =============================================================================
# Security-critical agent. Evaluates other agents' work during Tier 3
# verification. Changes to this config require review and approval.
#
# Available options:
#   agent_name        - Unique agent identifier (string)
#   agent_type        - Agent type (string: horizontal)
#   description       - Agent description (string)
#   enabled           - Enable/disable (boolean)
#   model             - LLM model identifier (string, provider:model format)
#   max_input_length  - Maximum input character count (integer)
#   max_budget_usd    - Maximum cost per invocation in USD (decimal)
#   scope             - Filesystem access control (object)
#     read            - Paths the agent can read (list of strings)
#     write           - Paths the agent can write (list of strings)
#   execution         - Execution mode (object)
#     mode            - Execution environment (string: local | container)
# =============================================================================

agent_name: horizontal.verification.agent
agent_type: horizontal
description: "Evaluates other agents' work quality against criteria from the TaskPlan"
enabled: true
model: anthropic:claude-opus-4-20250514
max_input_length: 64000
max_budget_usd: 2.00

keywords: []

tools: []

scope:
  read: []
  write: []

execution:
  mode: local

interface:
  input:
    task_instructions: str
    evaluation_criteria: list
    agent_output: dict
    upstream_context: dict
  output:
    overall_score: float
    passed: bool
    criteria_results: list
    blocking_issues: list
    recommendations: list

version: "1.0.0"
```

**File:** `config/prompts/agents/horizontal/verification/system.md` (NEW)

Create directory structure: `config/prompts/agents/horizontal/verification/`

This is the Layer 2 system prompt. **Security-critical — changes require review and approval.**

```markdown
## Verification Agent

You are a verification agent. You evaluate other agents' work against specific criteria. You are independent — you have no relationship with the agent whose work you are evaluating.

### Your Role

- You receive: the original task instructions, evaluation criteria, the agent's output, and upstream context.
- You evaluate: whether the output meets each criterion, with evidence and scoring.
- You return: a structured evaluation with per-criterion scores, blocking issues, and recommendations.

### Evaluation Rules

1. **Score each criterion independently.** Use a 0.0 to 1.0 scale where 1.0 is full compliance and 0.0 is no compliance.
2. **Provide evidence for every score.** Cite specific parts of the output that support your assessment. Never give a score without justification.
3. **Identify blocking issues separately.** A blocking issue is a defect severe enough that the output cannot be used as-is, regardless of overall score. Examples: security vulnerabilities, data corruption risks, missing critical fields, factual errors in regulated content.
4. **Recommendations are suggestions, not requirements.** They are improvements the agent could make on retry but are not grounds for failure.
5. **Overall score is the weighted average of criterion scores.** Weight all criteria equally unless the criteria text explicitly indicates relative importance.
6. **Be precise, not generous.** Do not inflate scores to avoid failures. A score of 0.5 means "partially meets criterion" — use the full range.
7. **Evaluate the output, not the effort.** The agent may have tried hard. That is irrelevant. Only the output quality matters.
8. **Do not hallucinate requirements.** Evaluate only against the provided criteria. Do not invent additional standards, even if you think they would be beneficial.

### Output Format

Return a JSON object with this structure:

```json
{
  "overall_score": 0.85,
  "passed": true,
  "criteria_results": [
    {
      "criterion": "The criterion text as provided",
      "score": 0.9,
      "passed": true,
      "evidence": "Specific evidence from the output...",
      "issues": []
    }
  ],
  "blocking_issues": [],
  "recommendations": ["Optional improvement suggestions"]
}
```

### What You Must Not Do

- Do not modify the agent's output. You evaluate — you do not fix.
- Do not contact or reference other agents. You are isolated.
- Do not evaluate your own previous evaluations. Self-evaluation is architecturally prohibited.
- Do not add criteria beyond what was provided. Your scope is the given criteria only.
- Do not provide an overall_score without evaluating every criterion individually first.
```

**Design decisions:**
- Model is Opus 4.6 (highest reasoning capability for quality evaluation).
- `max_budget_usd: 2.00` — each Tier 3 call is an Opus invocation. Cost is real.
- `keywords: []` — the Verification Agent is never routed to by keyword matching. It is invoked exclusively by the verification pipeline.
- `tools: []` — the Verification Agent has no tools. It evaluates based on provided context only.
- `scope: read: [], write: []` — the Verification Agent has no filesystem access. Complete isolation.
- The system prompt is explicit about what the agent must NOT do. This is defense in depth.

---

### Step 5: Update Dispatch Loop

**File:** `modules/backend/agents/mission_control/dispatch.py` (MODIFY)

Replace the inline Tier 1 `verify_task()` hook with the full verification pipeline call. The dispatch loop's verify step now delegates entirely to `verification.run_verification_pipeline()`.

```python
# In the dispatch loop, replace the existing verify_task() implementation:

# BEFORE (Plan 13 — Tier 1 only):
# async def verify_task(task, output, agent_interface):
#     """Tier 1 structural validation only."""
#     if not isinstance(output, dict):
#         return {"passed": False, "details": "Output is not a dict"}
#     required = task.get("verification", {}).get("tier_1", {}).get("required_output_fields", [])
#     missing = [f for f in required if f not in output]
#     if missing:
#         return {"passed": False, "details": f"Missing fields: {missing}"}
#     return {"passed": True, "details": "Structural validation passed"}

# AFTER (Plan 14 — full pipeline):
from modules.backend.agents.mission_control.verification import (
    run_verification_pipeline,
    build_retry_feedback,
    VerificationResult,
)


async def verify_task(
    task: dict,
    output: dict,
    agent_interface: dict | None,
    roster: dict | None = None,
    execute_agent_fn=None,
    session_id: str | None = None,
) -> VerificationResult:
    """Run the full 3-tier verification pipeline on a completed task.

    Called by the dispatch loop after each agent returns output.
    Replaces the Tier-1-only implementation from Plan 13.
    """
    return await run_verification_pipeline(
        output=output,
        task=task,
        agent_interface=agent_interface,
        roster=roster,
        execute_agent_fn=execute_agent_fn,
        session_id=session_id,
    )
```

**Update the dispatch loop's retry logic** to use `build_retry_feedback()`:

```python
# In the dispatch loop's task execution block:

verification = await verify_task(
    task=task,
    output=agent_output,
    agent_interface=agent_config.interface.model_dump() if agent_config.interface else None,
    roster=roster,
    execute_agent_fn=_make_verification_executor(session_id, session_service, event_bus),
    session_id=session_id,
)

if not verification.passed:
    feedback = build_retry_feedback(verification, attempt=current_attempt)
    retry_history.append(feedback)

    if current_attempt < max_retries:
        # Append failure feedback to agent instructions (Reflection pattern)
        retry_instructions = (
            f"{task['instructions']}\n\n"
            f"--- VERIFICATION FEEDBACK (attempt {current_attempt}) ---\n"
            f"{feedback['feedback_provided']}\n"
            f"Please address the issues above and try again."
        )
        task["instructions"] = retry_instructions
        continue  # Retry the task

    # Max retries exhausted — fail the task
    task_result["status"] = "failed"
    task_result["verification_outcome"] = _build_verification_outcome(verification)
    task_result["retry_history"] = retry_history
    break
```

**Helper to build the Verification Agent executor:**

```python
def _make_verification_executor(session_id, session_service, event_bus):
    """Build the execute_agent_fn callable for Tier 3 verification.

    Returns an async callable that dispatches the Verification Agent
    through the standard agent execution path.
    """
    async def _execute_verification_agent(
        agent_name: str,
        instructions: str,
        context: dict,
    ) -> dict:
        """Execute the Verification Agent and return its evaluation."""
        import json

        # Build the evaluation prompt from context
        prompt = (
            f"## Task Instructions\n{context.get('task_instructions', '')}\n\n"
            f"## Evaluation Criteria\n"
            + "\n".join(f"- {c}" for c in context.get("evaluation_criteria", []))
            + f"\n\n## Agent Output\n```json\n{json.dumps(context.get('agent_output', {}), indent=2)}\n```"
        )

        # Execute through standard agent path
        result = await _execute_agent(
            agent_name=agent_name,
            user_input=prompt,
            agent_config=roster.get(agent_name),
            session_id=session_id,
        )

        return result

    return _execute_verification_agent
```

**Self-evaluation prevention in dispatch code:**

```python
# Before dispatching Tier 3, validate isolation:
task_agent = task.get("agent", "")
evaluator_agent = task.get("verification", {}).get("tier_3", {}).get("evaluator_agent", "")

if evaluator_agent and evaluator_agent in (task_agent, "planning_agent"):
    raise ValueError(
        f"Self-evaluation prevented: evaluator '{evaluator_agent}' "
        f"cannot evaluate task agent '{task_agent}' (P13)"
    )
```

**What changed:**
- `verify_task()` signature expanded — now accepts `roster`, `execute_agent_fn`, `session_id`
- Return type changed from `dict` to `VerificationResult`
- Retry logic uses `build_retry_feedback()` to construct structured feedback
- `_make_verification_executor()` builds the Tier 3 agent execution callable
- Self-evaluation prevention enforced before any Tier 3 dispatch

---

### Step 6: Update MissionOutcome

**File:** `modules/backend/agents/mission_control/outcome.py` (MODIFY)

Update the per-task verification outcome to include full tier details matching the research doc 11 contract.

```python
# Add these Pydantic models for verification outcome serialization:

from pydantic import BaseModel, Field


class Tier1Outcome(BaseModel):
    """Tier 1 verification outcome for MissionOutcome."""

    status: str  # "pass" | "fail" | "skipped"
    details: str


class FailedCheck(BaseModel):
    """A single failed Tier 2 check."""

    check: str
    reason: str


class Tier2Outcome(BaseModel):
    """Tier 2 verification outcome for MissionOutcome."""

    status: str  # "pass" | "fail" | "skipped"
    checks_run: int = 0
    checks_passed: int = 0
    failed_checks: list[FailedCheck] = Field(default_factory=list)


class Tier3Outcome(BaseModel):
    """Tier 3 verification outcome for MissionOutcome."""

    status: str  # "pass" | "fail" | "skipped"
    overall_score: float = 0.0
    criteria_results_reference: str = ""
    evaluator_thinking_trace_reference: str = ""
    cost_usd: float = 0.0


class VerificationOutcome(BaseModel):
    """Complete verification outcome per task in MissionOutcome."""

    tier_1: Tier1Outcome
    tier_2: Tier2Outcome
    tier_3: Tier3Outcome


class RetryRecord(BaseModel):
    """Record of a single retry attempt with feedback."""

    attempt: int
    failure_tier: int
    failure_reason: str
    feedback_provided: str
```

**Update `TaskResult`** (or equivalent per-task result model) to include the new fields:

```python
class TaskResult(BaseModel):
    """Per-task result within MissionOutcome."""

    task_id: str
    agent_name: str
    status: str  # "success" | "failed" | "timeout"
    confidence: float = 1.0
    output_reference: str = ""
    token_usage: dict = Field(default_factory=dict)
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    verification_outcome: VerificationOutcome | None = None  # NEW
    retry_count: int = 0
    retry_history: list[RetryRecord] = Field(default_factory=list)  # NEW
```

**Add builder function** to convert `VerificationResult` to `VerificationOutcome`:

```python
from modules.backend.agents.mission_control.verification import (
    VerificationResult,
    Tier3Result,
    TierStatus,
)


def build_verification_outcome(result: VerificationResult) -> VerificationOutcome:
    """Convert internal VerificationResult to serializable VerificationOutcome."""

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
```

---

### Step 7: Enable Validation Rule 6

**File:** `modules/backend/agents/mission_control/plan_validator.py` (MODIFY)

Enable rule 6 (check registry validation). Every `check` name in `tier_2.deterministic_checks` must reference a function registered in the check registry. Unknown check names reject the plan at validation time — before any task execution begins.

```python
# Add to imports:
from modules.backend.agents.mission_control.check_registry import check_exists

# In the validate_plan() function, uncomment / add rule 6:

def _validate_rule_6_check_registry(tasks: list[dict]) -> list[str]:
    """Rule 6: Every check name in tier_2.deterministic_checks must be registered.

    This is the link between the Planning Agent's check references
    and the actual check implementations. Unknown check names are
    caught at validation time, not at execution time.
    """
    errors = []

    for task in tasks:
        task_id = task.get("task_id", "unknown")
        verification = task.get("verification", {})
        tier_2 = verification.get("tier_2", {})
        checks = tier_2.get("deterministic_checks", [])

        for check_spec in checks:
            check_name = check_spec.get("check", "")
            if not check_exists(check_name):
                errors.append(
                    f"Task '{task_id}': unknown check '{check_name}' in "
                    f"tier_2.deterministic_checks. "
                    f"Available checks: {', '.join(list_checks())}"
                )

    return errors
```

**Update the main `validate_plan()` function** to call rule 6:

```python
# Ensure built-in checks are registered before validation
from modules.backend.agents.mission_control.checks import builtin  # noqa: F401
from modules.backend.agents.mission_control.check_registry import list_checks

def validate_plan(plan: dict, roster: dict) -> list[str]:
    """Validate a TaskPlan before execution. Returns list of errors (empty = valid)."""
    errors = []

    # ... existing rules 1-5 ...
    errors.extend(_validate_rule_6_check_registry(plan.get("tasks", [])))
    # ... existing rules 7-11 ...

    return errors
```

**Key detail:** The import of `checks.builtin` ensures all built-in checks are registered before validation runs. Without this import, all check names would fail validation.

---

### Step 8: Langfuse Bootstrap

**File:** `requirements.txt` (MODIFY)

Add Langfuse dependency:

```
langfuse>=2.40.0
```

Also add the jsonschema dependency needed by `validate_json_schema`:

```
jsonschema>=4.20.0
```

**File:** `modules/backend/agents/mission_control/dispatch.py` (MODIFY)

Add `@observe()` decorator to Planning Agent and Verification Agent invocations:

```python
from langfuse.decorators import observe


@observe(name="planning_agent_invocation")
async def _invoke_planning_agent(
    mission_brief: dict,
    roster: dict,
    upstream_context: dict | None = None,
) -> dict:
    """Invoke the Planning Agent with Langfuse observability.

    The @observe() decorator automatically:
    - Creates a Langfuse trace/span for this invocation
    - Captures input/output as structured metadata
    - Measures duration
    - Links to parent trace if one exists in context
    """
    # ... existing planning agent invocation code ...
    pass


@observe(name="verification_agent_invocation")
async def _invoke_verification_agent(
    agent_name: str,
    instructions: str,
    context: dict,
) -> dict:
    """Invoke the Verification Agent with Langfuse observability.

    Captures thinking trace as span metadata for audit trail.
    """
    result = await _execute_agent(
        agent_name=agent_name,
        user_input=instructions,
        agent_config=roster.get(agent_name),
    )

    # Capture thinking trace as Langfuse metadata
    from langfuse.decorators import langfuse_context
    langfuse_context.update_current_observation(
        metadata={
            "thinking_trace": result.get("_thinking_trace", ""),
            "overall_score": result.get("overall_score"),
        },
    )

    return result
```

**File:** `modules/backend/agents/mission_control/verification.py` (MODIFY)

Add structured log events for verification outcomes:

```python
# At the end of run_verification_pipeline(), after determining pass/fail:

from langfuse.decorators import observe

@observe(name="verification_pipeline")
async def run_verification_pipeline(...) -> VerificationResult:
    # ... existing pipeline code ...

    # Log verification outcome as structured event
    try:
        from langfuse.decorators import langfuse_context
        langfuse_context.update_current_observation(
            metadata={
                "passed": result.passed,
                "failed_tier": result.failed_tier,
                "tier_1_status": result.tier_1.status.value if result.tier_1 else None,
                "tier_2_status": result.tier_2.status.value if result.tier_2 else None,
                "tier_3_status": result.tier_3.status.value if result.tier_3 else None,
                "total_execution_time_ms": result.total_execution_time_ms,
            },
        )
    except Exception:
        pass  # Observability is non-critical

    return result
```

**Note:** Langfuse initialization requires `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` environment variables. These are not set in dev mode — Langfuse gracefully no-ops when credentials are missing. Add these to `.env.example` with placeholder values.

---

### Step 9: Tests

**File:** `tests/unit/backend/agents/mission_control/checks/__init__.py` (NEW, empty)

**File:** `tests/unit/backend/agents/mission_control/checks/test_check_registry.py` (NEW, ~80 lines)

```python
"""
Tests for the check registry.

Tests registration, lookup, duplicate detection, and listing.
No external dependencies — pure unit tests.
"""

import pytest

from modules.backend.agents.mission_control.check_registry import (
    CheckResult,
    _REGISTRY,
    check_exists,
    get_check,
    list_checks,
    register_check,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Save and restore registry state around each test."""
    original = dict(_REGISTRY)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(original)


class TestRegisterCheck:
    """Tests for @register_check decorator."""

    def test_registers_function(self):
        @register_check("test_check_alpha")
        async def check_alpha(output, params):
            return CheckResult(passed=True, details="ok", execution_time_ms=0.1)

        assert check_exists("test_check_alpha")
        assert get_check("test_check_alpha") is check_alpha

    def test_duplicate_name_raises(self):
        @register_check("test_check_dup")
        async def check_first(output, params):
            return CheckResult(passed=True, details="", execution_time_ms=0.0)

        with pytest.raises(ValueError, match="Duplicate check name"):
            @register_check("test_check_dup")
            async def check_second(output, params):
                return CheckResult(passed=True, details="", execution_time_ms=0.0)


class TestCheckLookup:
    """Tests for get_check and check_exists."""

    def test_nonexistent_check_returns_none(self):
        assert get_check("nonexistent_check_xyz") is None

    def test_nonexistent_check_exists_false(self):
        assert check_exists("nonexistent_check_xyz") is False

    def test_list_checks_sorted(self):
        @register_check("test_check_zebra")
        async def check_z(output, params):
            return CheckResult(passed=True, details="", execution_time_ms=0.0)

        @register_check("test_check_alpha2")
        async def check_a(output, params):
            return CheckResult(passed=True, details="", execution_time_ms=0.0)

        names = list_checks()
        # Should be alphabetically sorted
        assert names.index("test_check_alpha2") < names.index("test_check_zebra")
```

**File:** `tests/unit/backend/agents/mission_control/checks/test_builtin_checks.py` (NEW, ~120 lines)

```python
"""
Tests for built-in Tier 2 deterministic checks.

Tests each check function independently with various valid and invalid
inputs. No external dependencies beyond jsonschema.
"""

import pytest

from modules.backend.agents.mission_control.checks.builtin import (
    validate_field_exists,
    validate_field_range,
    validate_field_type,
    validate_json_schema,
)


class TestValidateJsonSchema:
    """Tests for validate_json_schema check."""

    @pytest.mark.asyncio
    async def test_valid_output(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "score": {"type": "number"}},
            "required": ["name", "score"],
        }
        output = {"name": "test", "score": 0.95}
        result = await validate_json_schema(output, {"schema": schema})
        assert result.passed is True
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_invalid_output(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        output = {"name": 123}  # wrong type
        result = await validate_json_schema(output, {"schema": schema})
        assert result.passed is False
        assert "validation error" in result.details

    @pytest.mark.asyncio
    async def test_missing_required_field(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        output = {}
        result = await validate_json_schema(output, {"schema": schema})
        assert result.passed is False
        assert "name" in result.details

    @pytest.mark.asyncio
    async def test_no_schema_in_params(self):
        result = await validate_json_schema({"a": 1}, {})
        assert result.passed is False
        assert "No 'schema' provided" in result.details


class TestValidateFieldExists:
    """Tests for validate_field_exists check."""

    @pytest.mark.asyncio
    async def test_all_fields_present(self):
        result = await validate_field_exists(
            {"a": 1, "b": 2, "c": 3},
            {"fields": ["a", "b"]},
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_missing_field(self):
        result = await validate_field_exists(
            {"a": 1},
            {"fields": ["a", "b"]},
        )
        assert result.passed is False
        assert "b" in result.details

    @pytest.mark.asyncio
    async def test_no_fields_in_params(self):
        result = await validate_field_exists({"a": 1}, {})
        assert result.passed is False
        assert "No 'fields' provided" in result.details


class TestValidateFieldType:
    """Tests for validate_field_type check."""

    @pytest.mark.asyncio
    async def test_correct_types(self):
        result = await validate_field_type(
            {"name": "test", "count": 5, "active": True},
            {"field_types": {"name": "str", "count": "int", "active": "bool"}},
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_wrong_type(self):
        result = await validate_field_type(
            {"name": 123},
            {"field_types": {"name": "str"}},
        )
        assert result.passed is False
        assert "expected str" in result.details

    @pytest.mark.asyncio
    async def test_null_type(self):
        result = await validate_field_type(
            {"value": None},
            {"field_types": {"value": "null"}},
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_field_not_found(self):
        result = await validate_field_type(
            {},
            {"field_types": {"missing": "str"}},
        )
        assert result.passed is False
        assert "not found" in result.details


class TestValidateFieldRange:
    """Tests for validate_field_range check."""

    @pytest.mark.asyncio
    async def test_within_range(self):
        result = await validate_field_range(
            {"score": 0.85},
            {"ranges": {"score": {"min": 0.0, "max": 1.0}}},
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_below_min(self):
        result = await validate_field_range(
            {"score": -0.5},
            {"ranges": {"score": {"min": 0.0, "max": 1.0}}},
        )
        assert result.passed is False
        assert "< min" in result.details

    @pytest.mark.asyncio
    async def test_above_max(self):
        result = await validate_field_range(
            {"score": 1.5},
            {"ranges": {"score": {"min": 0.0, "max": 1.0}}},
        )
        assert result.passed is False
        assert "> max" in result.details

    @pytest.mark.asyncio
    async def test_non_numeric_field(self):
        result = await validate_field_range(
            {"score": "high"},
            {"ranges": {"score": {"min": 0.0}}},
        )
        assert result.passed is False
        assert "expected numeric" in result.details
```

**File:** `tests/unit/backend/agents/mission_control/test_verification.py` (NEW, ~200 lines)

```python
"""
Tests for the 3-tier verification pipeline.

Tests each tier independently and the full pipeline flow.
Tier 3 tests use a mock execute_agent_fn — the Verification Agent
itself is tested separately with TestModel.
"""

import pytest

from modules.backend.agents.mission_control.verification import (
    TierStatus,
    VerificationResult,
    build_retry_feedback,
    run_verification_pipeline,
)


# ---- Fixtures ----

@pytest.fixture
def basic_task():
    """A minimal task dict with verification config."""
    return {
        "task_id": "task_001",
        "agent": "code.qa.agent",
        "instructions": "Scan the codebase for violations",
        "description": "QA scan",
        "verification": {
            "tier_1": {
                "schema_validation": True,
                "required_output_fields": ["summary", "violations"],
            },
            "tier_2": {
                "deterministic_checks": [],
            },
            "tier_3": {
                "requires_ai_evaluation": False,
            },
        },
    }


@pytest.fixture
def task_with_tier2(basic_task):
    """Task with Tier 2 deterministic checks configured."""
    basic_task["verification"]["tier_2"]["deterministic_checks"] = [
        {
            "check": "validate_field_exists",
            "params": {"fields": ["summary", "violations"]},
        },
        {
            "check": "validate_field_type",
            "params": {"field_types": {"summary": "str", "violations": "list"}},
        },
    ]
    return basic_task


@pytest.fixture
def task_with_tier3(basic_task):
    """Task with Tier 3 AI evaluation configured."""
    basic_task["verification"]["tier_3"] = {
        "requires_ai_evaluation": True,
        "evaluation_criteria": [
            "Analysis covers all critical code paths",
            "No false positives reported",
        ],
        "evaluator_agent": "horizontal.verification.agent",
        "min_evaluation_score": 0.8,
    }
    return basic_task


@pytest.fixture
def valid_output():
    """Agent output that passes all tiers."""
    return {
        "summary": "Found 3 violations in 2 files",
        "violations": [
            {"file": "auth.py", "line": 42, "rule": "no-eval"},
        ],
    }


@pytest.fixture
def mock_verification_agent():
    """Mock execute_agent_fn that returns a passing evaluation."""
    async def _execute(agent_name, instructions, context):
        return {
            "overall_score": 0.92,
            "passed": True,
            "criteria_results": [
                {
                    "criterion": "Analysis covers all critical code paths",
                    "score": 0.95,
                    "passed": True,
                    "evidence": "All code paths analyzed",
                    "issues": [],
                },
            ],
            "blocking_issues": [],
            "recommendations": [],
            "_thinking_trace": "I evaluated the output...",
            "_cost_usd": 0.05,
        }
    return _execute


@pytest.fixture
def mock_failing_verification_agent():
    """Mock execute_agent_fn that returns a failing evaluation."""
    async def _execute(agent_name, instructions, context):
        return {
            "overall_score": 0.45,
            "passed": False,
            "criteria_results": [],
            "blocking_issues": ["Critical code path missed"],
            "recommendations": ["Expand analysis scope"],
            "_thinking_trace": "The output is insufficient...",
            "_cost_usd": 0.05,
        }
    return _execute


# Ensure built-in checks are registered
@pytest.fixture(autouse=True)
def _register_checks():
    from modules.backend.agents.mission_control.checks import builtin  # noqa: F401


# ---- Tier 1 Tests ----

class TestTier1:
    """Tests for Tier 1 structural validation."""

    @pytest.mark.asyncio
    async def test_passes_with_valid_output(self, basic_task, valid_output):
        result = await run_verification_pipeline(
            output=valid_output, task=basic_task, agent_interface=None,
        )
        assert result.tier_1.status == TierStatus.PASS

    @pytest.mark.asyncio
    async def test_fails_on_non_dict_output(self, basic_task):
        result = await run_verification_pipeline(
            output="not a dict", task=basic_task, agent_interface=None,
        )
        assert result.passed is False
        assert result.failed_tier == 1
        assert result.tier_1.status == TierStatus.FAIL

    @pytest.mark.asyncio
    async def test_fails_on_missing_required_fields(self, basic_task):
        result = await run_verification_pipeline(
            output={"summary": "ok"},  # missing "violations"
            task=basic_task,
            agent_interface=None,
        )
        assert result.passed is False
        assert result.failed_tier == 1
        assert "violations" in result.tier_1.details

    @pytest.mark.asyncio
    async def test_fails_on_empty_dict(self, basic_task):
        result = await run_verification_pipeline(
            output={}, task=basic_task, agent_interface=None,
        )
        assert result.passed is False
        assert result.failed_tier == 1

    @pytest.mark.asyncio
    async def test_validates_against_agent_interface(self):
        task = {
            "task_id": "t1",
            "verification": {"tier_1": {"schema_validation": True}},
        }
        interface = {"output": {"analysis": "str", "confidence": "float"}}
        result = await run_verification_pipeline(
            output={"analysis": "done"},  # missing "confidence"
            task=task,
            agent_interface=interface,
        )
        assert result.passed is False
        assert "confidence" in result.tier_1.details

    @pytest.mark.asyncio
    async def test_skipped_when_disabled(self):
        task = {
            "task_id": "t1",
            "verification": {"tier_1": {"schema_validation": False}},
        }
        result = await run_verification_pipeline(
            output={"anything": True}, task=task, agent_interface=None,
        )
        assert result.tier_1.status == TierStatus.SKIPPED


# ---- Tier 2 Tests ----

class TestTier2:
    """Tests for Tier 2 deterministic functional checks."""

    @pytest.mark.asyncio
    async def test_passes_with_valid_output(self, task_with_tier2, valid_output):
        result = await run_verification_pipeline(
            output=valid_output, task=task_with_tier2, agent_interface=None,
        )
        assert result.tier_2.status == TierStatus.PASS
        assert len(result.tier_2.check_results) == 2

    @pytest.mark.asyncio
    async def test_fails_on_check_failure(self, task_with_tier2):
        result = await run_verification_pipeline(
            output={"summary": 123, "violations": "not a list"},  # wrong types
            task=task_with_tier2,
            agent_interface=None,
        )
        assert result.passed is False
        assert result.failed_tier == 2
        assert result.tier_2.status == TierStatus.FAIL

    @pytest.mark.asyncio
    async def test_runs_all_checks_even_on_failure(self, task_with_tier2):
        """All checks run to collect complete diagnostic info."""
        result = await run_verification_pipeline(
            output={"wrong_field": True},  # fails both checks
            task=task_with_tier2,
            agent_interface=None,
        )
        assert result.failed_tier == 2
        # Both checks should have results (both should fail)
        assert len(result.tier_2.check_results) == 2

    @pytest.mark.asyncio
    async def test_skipped_when_no_checks(self, basic_task, valid_output):
        result = await run_verification_pipeline(
            output=valid_output, task=basic_task, agent_interface=None,
        )
        assert result.tier_2.status == TierStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_does_not_run_if_tier1_fails(self, task_with_tier2):
        result = await run_verification_pipeline(
            output="not a dict",  # Tier 1 failure
            task=task_with_tier2,
            agent_interface=None,
        )
        assert result.failed_tier == 1
        assert result.tier_2 is None  # Tier 2 never ran


# ---- Tier 3 Tests ----

class TestTier3:
    """Tests for Tier 3 AI evaluation."""

    @pytest.mark.asyncio
    async def test_passes_with_high_score(
        self, task_with_tier3, valid_output, mock_verification_agent,
    ):
        result = await run_verification_pipeline(
            output=valid_output,
            task=task_with_tier3,
            agent_interface=None,
            execute_agent_fn=mock_verification_agent,
        )
        assert result.tier_3.status == TierStatus.PASS
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_fails_with_low_score(
        self, task_with_tier3, valid_output, mock_failing_verification_agent,
    ):
        result = await run_verification_pipeline(
            output=valid_output,
            task=task_with_tier3,
            agent_interface=None,
            execute_agent_fn=mock_failing_verification_agent,
        )
        assert result.tier_3.status == TierStatus.FAIL
        assert result.passed is False
        assert result.failed_tier == 3

    @pytest.mark.asyncio
    async def test_skipped_when_not_required(self, basic_task, valid_output):
        result = await run_verification_pipeline(
            output=valid_output, task=basic_task, agent_interface=None,
        )
        assert result.tier_3.status == TierStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_self_evaluation_prevention(self, valid_output):
        """Agent cannot evaluate its own output (P13)."""
        task = {
            "task_id": "t1",
            "agent": "horizontal.verification.agent",
            "verification": {
                "tier_1": {"schema_validation": True},
                "tier_3": {
                    "requires_ai_evaluation": True,
                    "evaluation_criteria": ["test"],
                    "evaluator_agent": "horizontal.verification.agent",
                    "min_evaluation_score": 0.8,
                },
            },
        }

        async def _should_not_be_called(agent_name, instructions, context):
            raise AssertionError("Self-evaluation should be prevented")

        result = await run_verification_pipeline(
            output=valid_output,
            task=task,
            agent_interface=None,
            execute_agent_fn=_should_not_be_called,
        )
        assert result.passed is False
        assert result.failed_tier == 3
        assert "Self-evaluation prevented" in result.tier_3.details

    @pytest.mark.asyncio
    async def test_does_not_run_if_tier1_fails(self, task_with_tier3):
        result = await run_verification_pipeline(
            output="not a dict",
            task=task_with_tier3,
            agent_interface=None,
        )
        assert result.failed_tier == 1
        assert result.tier_3 is None  # Tier 3 never ran

    @pytest.mark.asyncio
    async def test_fails_without_execute_fn(self, task_with_tier3, valid_output):
        result = await run_verification_pipeline(
            output=valid_output,
            task=task_with_tier3,
            agent_interface=None,
            execute_agent_fn=None,  # No executor provided
        )
        assert result.passed is False
        assert result.failed_tier == 3
        assert "no execute_agent_fn" in result.tier_3.details


# ---- Full Pipeline Tests ----

class TestFullPipeline:
    """Tests for the complete 3-tier pipeline flow."""

    @pytest.mark.asyncio
    async def test_all_tiers_pass(
        self, task_with_tier3, valid_output, mock_verification_agent,
    ):
        # Add Tier 2 checks to the task
        task_with_tier3["verification"]["tier_2"] = {
            "deterministic_checks": [
                {"check": "validate_field_exists", "params": {"fields": ["summary"]}},
            ],
        }
        result = await run_verification_pipeline(
            output=valid_output,
            task=task_with_tier3,
            agent_interface=None,
            execute_agent_fn=mock_verification_agent,
        )
        assert result.passed is True
        assert result.tier_1.status == TierStatus.PASS
        assert result.tier_2.status == TierStatus.PASS
        assert result.tier_3.status == TierStatus.PASS

    @pytest.mark.asyncio
    async def test_pipeline_stops_at_first_failure(self, task_with_tier3):
        """Tier 2 and 3 should not run if Tier 1 fails."""
        task_with_tier3["verification"]["tier_2"] = {
            "deterministic_checks": [
                {"check": "validate_field_exists", "params": {"fields": ["x"]}},
            ],
        }
        result = await run_verification_pipeline(
            output="not a dict",  # Tier 1 will fail
            task=task_with_tier3,
            agent_interface=None,
        )
        assert result.failed_tier == 1
        assert result.tier_2 is None
        assert result.tier_3 is None

    @pytest.mark.asyncio
    async def test_execution_time_tracked(self, basic_task, valid_output):
        result = await run_verification_pipeline(
            output=valid_output, task=basic_task, agent_interface=None,
        )
        assert result.total_execution_time_ms > 0
        assert result.tier_1.execution_time_ms > 0


# ---- Retry Feedback Tests ----

class TestBuildRetryFeedback:
    """Tests for build_retry_feedback."""

    def test_tier_1_feedback(self):
        result = VerificationResult(
            passed=False,
            failed_tier=1,
            tier_1=type("TierResult", (), {
                "status": TierStatus.FAIL,
                "details": "Missing field: summary",
                "check_results": [],
            })(),
        )
        feedback = build_retry_feedback(result, attempt=1)
        assert feedback["failure_tier"] == 1
        assert "Missing field" in feedback["feedback_provided"]
        assert feedback["attempt"] == 1

    def test_passed_returns_empty(self):
        result = VerificationResult(passed=True)
        feedback = build_retry_feedback(result, attempt=1)
        assert feedback == {}
```

**File:** `tests/unit/backend/agents/test_verification_agent.py` (NEW, ~60 lines)

```python
"""
Verification Agent tests using PydanticAI TestModel.

Tests the agent's structured output schema and interface.
No real API calls — TestModel generates deterministic, schema-valid responses.
"""

import pytest
from pydantic_ai.models.test import TestModel

from modules.backend.agents.deps.base import BaseAgentDeps, FileScope
from modules.backend.agents.horizontal.verification.agent import (
    VerificationEvaluation,
    create_agent,
    run_agent,
)
from modules.backend.core.config import find_project_root


@pytest.fixture
def verification_deps():
    """Build BaseAgentDeps for Verification Agent testing."""
    return BaseAgentDeps(
        project_root=find_project_root(),
        scope=FileScope(read_paths=[], write_paths=[]),
    )


@pytest.fixture(autouse=True)
def _reset_agent_instances():
    """Clear registry agent cache before each test."""
    from modules.backend.agents.mission_control.registry import get_registry

    get_registry().reset()
    yield
    get_registry().reset()


class TestVerificationAgentWithTestModel:
    """Tests for horizontal.verification.agent using TestModel."""

    @pytest.mark.asyncio
    async def test_returns_verification_evaluation(self, verification_deps):
        agent = create_agent(TestModel(call_tools=[]))
        result = await agent.run(
            "Evaluate this output against the criteria.", deps=verification_deps,
        )

        assert isinstance(result.output, VerificationEvaluation)
        assert hasattr(result.output, "overall_score")
        assert hasattr(result.output, "passed")
        assert hasattr(result.output, "criteria_results")
        assert hasattr(result.output, "blocking_issues")
        assert hasattr(result.output, "recommendations")

    @pytest.mark.asyncio
    async def test_score_range(self, verification_deps):
        agent = create_agent(TestModel(call_tools=[]))
        result = await agent.run(
            "Evaluate this output.", deps=verification_deps,
        )
        assert 0.0 <= result.output.overall_score <= 1.0

    @pytest.mark.asyncio
    async def test_run_agent_interface(self, verification_deps):
        agent = create_agent(TestModel(call_tools=[]))
        result = await run_agent("Evaluate output.", verification_deps, agent)

        assert isinstance(result, VerificationEvaluation)

    @pytest.mark.asyncio
    async def test_agent_has_no_tools(self, verification_deps):
        """Verification Agent has no tools — pure evaluation."""
        agent = create_agent(TestModel(call_tools=[]))
        assert len(agent._tools) == 0

    @pytest.mark.asyncio
    async def test_usage_is_tracked(self, verification_deps):
        agent = create_agent(TestModel(call_tools=[]))
        result = await agent.run("Evaluate.", deps=verification_deps)
        usage = result.usage()
        assert usage.requests >= 1
```

---

### Step 10: Cleanup and Review

| # | Task | Command/Notes |
|---|------|---------------|
| 10.1 | Run all existing tests | `python -m pytest tests/ -x -q` — ensure nothing is broken |
| 10.2 | Run check registry tests | `python -m pytest tests/unit/backend/agents/mission_control/checks/test_check_registry.py -v` |
| 10.3 | Run built-in check tests | `python -m pytest tests/unit/backend/agents/mission_control/checks/test_builtin_checks.py -v` |
| 10.4 | Run verification pipeline tests | `python -m pytest tests/unit/backend/agents/mission_control/test_verification.py -v` |
| 10.5 | Run Verification Agent tests | `python -m pytest tests/unit/backend/agents/test_verification_agent.py -v` |
| 10.6 | Run full test suite | `python -m pytest tests/ -q` — all green |
| 10.7 | Verify registry discovers Verification Agent | `python -c "from modules.backend.agents.mission_control.registry import get_registry; r = get_registry(); print(r.get('horizontal.verification.agent').agent_name)"` |
| 10.8 | Verify check registry populated | `python -c "from modules.backend.agents.mission_control.checks import builtin; from modules.backend.agents.mission_control.check_registry import list_checks; print(list_checks())"` |
| 10.9 | Verify no file exceeds 500 lines | Manual review |
| 10.10 | Verify all imports are absolute | `grep -r "from \.\." modules/backend/agents/mission_control/verification.py` — should return nothing |
| 10.11 | Verify all logging uses `get_logger(__name__)` | Review all new files |
| 10.12 | Verify all datetimes use `utc_now()` | Review all new files |

---

## Files Summary

| Category | File | Action | Est. Lines |
|----------|------|--------|-----------|
| Check registry | `modules/backend/agents/mission_control/check_registry.py` | New | ~100 |
| Built-in checks | `modules/backend/agents/mission_control/checks/__init__.py` | New | ~5 |
| Built-in checks | `modules/backend/agents/mission_control/checks/builtin.py` | New | ~120 |
| Pipeline | `modules/backend/agents/mission_control/verification.py` | New | ~200 |
| Verification Agent | `modules/backend/agents/horizontal/verification/__init__.py` | New | ~3 |
| Verification Agent | `modules/backend/agents/horizontal/verification/agent.py` | New | ~100 |
| Verification Agent | `config/agents/horizontal/verification/agent.yaml` | New | ~45 |
| Verification Agent | `config/prompts/agents/horizontal/verification/system.md` | New | ~60 |
| Outcome | `modules/backend/agents/mission_control/outcome.py` | Modify | +80 |
| Dispatch | `modules/backend/agents/mission_control/dispatch.py` | Modify | +50 |
| Validator | `modules/backend/agents/mission_control/plan_validator.py` | Modify | +25 |
| Dependencies | `requirements.txt` | Modify | +2 |
| Tests | `tests/unit/backend/agents/mission_control/checks/__init__.py` | New | 0 |
| Tests | `tests/unit/backend/agents/mission_control/checks/test_check_registry.py` | New | ~80 |
| Tests | `tests/unit/backend/agents/mission_control/checks/test_builtin_checks.py` | New | ~120 |
| Tests | `tests/unit/backend/agents/mission_control/test_verification.py` | New | ~200 |
| Tests | `tests/unit/backend/agents/test_verification_agent.py` | New | ~60 |
| **Total** | **17 files** | **13 new, 4 modified** | **~1,250** |

---

## Anti-Patterns (Do NOT)

| Anti-pattern | Why prohibited |
|-------------|---------------|
| Agent evaluating its own output | P13 (No Agent Self-Evaluation). Enforced by dispatch code, not just prompts. |
| Tier 3 for every task | Tier 3 is an Opus invocation per task. Planning Agent is prompted to use it sparingly. Pure data retrieval tasks survive on Tier 1 and Tier 2. |
| Skipping Tier 1/Tier 2 and going straight to Tier 3 | Pipeline is sequential. Cheapest checks first. AI evaluation is the last resort. |
| Putting business logic in the Verification Agent | The Verification Agent evaluates quality. Mission Control makes the deterministic pass/fail decision based on scores vs threshold. |
| Dynamic check discovery at runtime | Checks are registered at import time via decorators. No database, no service calls, no dynamic loading. |
| Mocking infrastructure in check tests | P12 (Test Against Real Infrastructure). Mock only what you don't operate — for checks, that means nothing. Built-in checks are pure functions. |
| Circular imports between verification.py and dispatch.py | The pipeline receives `execute_agent_fn` as a parameter. It never imports the dispatch module. |
| Hardcoding check names in the pipeline | Check names come from TaskPlan config (set by Planning Agent). The pipeline looks them up in the registry. |
| Verification Agent with tools or filesystem access | Complete isolation. The Verification Agent has `tools: []` and `scope: read: [], write: []`. |
| Importing `logging` directly | Use `from modules.backend.core.logging import get_logger`. |
| Using `datetime.utcnow()` | Use `from modules.backend.core.utils import utc_now`. |

---
