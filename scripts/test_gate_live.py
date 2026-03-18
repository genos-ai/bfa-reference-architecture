#!/usr/bin/env python3
"""
Live Gate Test — exercises the step-through gate system end-to-end.

Tests config loading, factory routing, dispatch integration with a
recording gate, and (optionally) a real LLM call to the gate reviewer.

No database or Redis required. Needs ANTHROPIC_API_KEY in config/.env.

Usage:
    python scripts/test_gate_live.py                # All tests
    python scripts/test_gate_live.py --skip-llm     # Skip the real LLM call
    python scripts/test_gate_live.py -v             # Verbose output
"""

import asyncio
import sys
import traceback
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.core.logging import get_logger, setup_logging

logger = get_logger(__name__)

PASS = click.style("PASS", fg="green", bold=True)
FAIL = click.style("FAIL", fg="red", bold=True)
SKIP = click.style("SKIP", fg="yellow")

results: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    status = PASS if passed else FAIL
    click.echo(f"  {status}  {name}")
    if detail and not passed:
        click.echo(f"         {click.style(detail, fg='red')}")


# ---------------------------------------------------------------------------
# Test 1: Config loading and validation
# ---------------------------------------------------------------------------

def test_config_loading() -> None:
    """Verify gate.yaml loads and validates through AppConfig."""
    click.echo(click.style("\n── Config Loading ──", bold=True))
    try:
        from modules.backend.core.config import get_app_config
        config = get_app_config()
        gate = config.gate

        record(
            "gate.yaml loads via AppConfig",
            gate is not None,
        )
        record(
            "default mode is 'off'",
            gate.mode == "off",
            f"got: {gate.mode}",
        )
        record(
            "AI model configured",
            "claude" in gate.ai.model,
            f"got: {gate.ai.model}",
        )
        record(
            "all 5 gate points present",
            all(hasattr(gate.points, p) for p in
                ["pre_dispatch", "pre_layer", "post_task",
                 "verification_failed", "post_layer"]),
        )
        record(
            "auto_rules have defaults",
            gate.auto_rules.cost_threshold_pct == 80
            and gate.auto_rules.max_tasks_per_layer == 10
            and gate.auto_rules.skip_post_task_on_pass is True,
        )
    except Exception as e:
        record("gate.yaml loads via AppConfig", False, str(e))


# ---------------------------------------------------------------------------
# Test 2: Schema validation rejects bad config
# ---------------------------------------------------------------------------

def test_schema_validation() -> None:
    """Verify Literal-typed mode rejects invalid values."""
    click.echo(click.style("\n── Schema Validation ──", bold=True))
    from modules.backend.core.config_schema import GateSchema

    try:
        GateSchema(mode="banana")
        record("rejects invalid mode 'banana'", False, "no error raised")
    except Exception:
        record("rejects invalid mode 'banana'", True)

    try:
        GateSchema(mode="off", unknown_key="bad")
        record("rejects unknown keys (strict)", False, "no error raised")
    except Exception:
        record("rejects unknown keys (strict)", True)

    try:
        schema = GateSchema(mode="autonomous")
        record("accepts valid mode 'autonomous'", schema.mode == "autonomous")
    except Exception as e:
        record("accepts valid mode 'autonomous'", False, str(e))


# ---------------------------------------------------------------------------
# Test 3: Factory function
# ---------------------------------------------------------------------------

def test_factory() -> None:
    """Verify create_gate returns correct types for each mode."""
    click.echo(click.style("\n── Factory Function ──", bold=True))
    from modules.backend.agents.mission_control.gate import (
        ConfigurableGate,
        create_gate,
    )

    # mode=off should return None
    gate_off = create_gate(mode_override="off")
    record("mode='off' returns None", gate_off is None)

    # mode=interactive should return ConfigurableGate
    gate_interactive = create_gate(mode_override="interactive")
    record(
        "mode='interactive' returns ConfigurableGate",
        isinstance(gate_interactive, ConfigurableGate),
        f"got: {type(gate_interactive).__name__}" if gate_interactive else "got None",
    )

    # mode=autonomous should return ConfigurableGate
    gate_auto = create_gate(mode_override="autonomous")
    record(
        "mode='autonomous' returns ConfigurableGate",
        isinstance(gate_auto, ConfigurableGate),
    )

    # mode=ai_assisted should return ConfigurableGate
    gate_ai = create_gate(mode_override="ai_assisted")
    record(
        "mode='ai_assisted' returns ConfigurableGate",
        isinstance(gate_ai, ConfigurableGate),
    )


# ---------------------------------------------------------------------------
# Test 4: ConfigurableGate routing (off mode, disabled points)
# ---------------------------------------------------------------------------

def test_configurable_gate_routing() -> None:
    """Verify ConfigurableGate routes correctly without needing LLM."""
    click.echo(click.style("\n── ConfigurableGate Routing ──", bold=True))

    from modules.backend.agents.mission_control.gate import (
        ConfigurableGate,
        GateAction,
        GateContext,
    )
    from modules.backend.core.config_schema import (
        GatePointSchema,
        GatePointsSchema,
        GateSchema,
    )

    async def _run():
        # Off mode should auto-continue
        config = GateSchema(mode="off")
        gate = ConfigurableGate(config=config)
        ctx = GateContext(gate_type="pre_dispatch", mission_id="test-routing")
        decision = await gate.review(ctx)
        record(
            "off mode → CONTINUE (config:off)",
            decision.action == GateAction.CONTINUE
            and decision.reviewer == "config:off",
            f"got: {decision.action}, reviewer={decision.reviewer}",
        )

        # Disabled point should auto-continue
        points = GatePointsSchema(
            pre_dispatch=GatePointSchema(enabled=False),
        )
        config2 = GateSchema(mode="interactive", points=points)
        gate2 = ConfigurableGate(config=config2)
        decision2 = await gate2.review(ctx)
        record(
            "disabled point → CONTINUE (config:disabled)",
            decision2.action == GateAction.CONTINUE
            and decision2.reviewer == "config:disabled",
            f"got: {decision2.action}, reviewer={decision2.reviewer}",
        )

        # Per-point override: verification_failed set to off even when top-level is autonomous
        points3 = GatePointsSchema(
            verification_failed=GatePointSchema(mode="off"),
        )
        config3 = GateSchema(mode="autonomous", points=points3)
        gate3 = ConfigurableGate(config=config3)
        ctx3 = GateContext(gate_type="verification_failed", mission_id="test-override")
        decision3 = await gate3.review(ctx3)
        record(
            "per-point mode override works",
            decision3.action == GateAction.CONTINUE
            and decision3.reviewer == "config:off",
            f"got: {decision3.action}, reviewer={decision3.reviewer}",
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 5: Auto-continue rules
# ---------------------------------------------------------------------------

def test_auto_continue_rules() -> None:
    """Verify autonomous auto-continue rules fire correctly."""
    click.echo(click.style("\n── Auto-Continue Rules ──", bold=True))

    from modules.backend.agents.mission_control.gate import (
        ConfigurableGate,
        GateAction,
        GateContext,
    )
    from modules.backend.core.config_schema import GateAutoRulesSchema, GateSchema

    async def _run():
        rules = GateAutoRulesSchema(
            cost_threshold_pct=80,
            max_tasks_per_layer=5,
            skip_post_task_on_pass=True,
        )
        config = GateSchema(mode="autonomous", auto_rules=rules)
        gate = ConfigurableGate(config=config)

        # Pre-layer with few tasks → auto-continue
        ctx = GateContext(
            gate_type="pre_layer", mission_id="test-auto",
            pending_tasks=[{"task_id": "t1"}],
            budget_usd=10.0, total_cost_usd=1.0,
        )
        decision = await gate.review(ctx)
        record(
            "pre_layer (1 task, low cost) → auto-continue",
            decision.action == GateAction.CONTINUE
            and decision.reviewer == "config:auto",
            f"got: {decision.action}, reviewer={decision.reviewer}",
        )

        # Post-task with passing verification → auto-continue
        ctx2 = GateContext(
            gate_type="post_task", mission_id="test-auto",
            verification={"tier_1": {"status": "pass"}, "tier_2": {"status": "pass"}},
            budget_usd=10.0, total_cost_usd=1.0,
        )
        decision2 = await gate.review(ctx2)
        record(
            "post_task (verification pass) → auto-continue",
            decision2.action == GateAction.CONTINUE
            and decision2.reviewer == "config:auto",
            f"got: {decision2.action}, reviewer={decision2.reviewer}",
        )

        # High cost should NOT auto-continue (forces LLM review)
        # We can't actually call the LLM here, so just test the rule directly
        result = gate._should_auto_continue(GateContext(
            gate_type="pre_layer", mission_id="test-auto",
            pending_tasks=[{"task_id": "t1"}],
            budget_usd=10.0, total_cost_usd=9.0,  # 90% > 80%
        ))
        record(
            "high cost (90%) blocks auto-continue",
            result is False,
        )

        # verification_failed never auto-continues
        result2 = gate._should_auto_continue(GateContext(
            gate_type="verification_failed", mission_id="test-auto",
            budget_usd=10.0, total_cost_usd=0.1,
        ))
        record(
            "verification_failed never auto-continues",
            result2 is False,
        )

        # post_layer auto-continues when cost is low
        ctx3 = GateContext(
            gate_type="post_layer", mission_id="test-auto",
            budget_usd=10.0, total_cost_usd=3.0,
        )
        decision3 = await gate.review(ctx3)
        record(
            "post_layer (low cost) → auto-continue",
            decision3.action == GateAction.CONTINUE
            and decision3.reviewer == "config:auto",
            f"got: {decision3.action}, reviewer={decision3.reviewer}",
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 6: Dispatch integration with RecordingGate
# ---------------------------------------------------------------------------

def test_dispatch_with_recording_gate() -> None:
    """Run a real dispatch pipeline with a RecordingGate to verify all gate points fire."""
    click.echo(click.style("\n── Dispatch Integration (RecordingGate) ──", bold=True))

    from modules.backend.agents.mission_control.gate import (
        GateAction,
        GateContext,
        GateDecision,
    )
    from modules.backend.agents.mission_control.roster import (
        Roster,
        RosterAgentEntry,
        RosterConstraintsSchema,
        RosterInterfaceSchema,
        RosterModelSchema,
    )
    from modules.backend.schemas.task_plan import TaskPlan

    class RecordingGate:
        def __init__(self):
            self.calls: list[GateContext] = []

        async def review(self, context: GateContext) -> GateDecision:
            self.calls.append(context)
            return GateDecision(action=GateAction.CONTINUE, reviewer="test:recording")

    async def _run():
        from modules.backend.agents.mission_control.dispatch import dispatch

        entry = RosterAgentEntry(
            agent_name="test.agent",
            agent_version="1.0.0",
            description="Test agent",
            model=RosterModelSchema(name="test-model"),
            interface=RosterInterfaceSchema(
                input={"query": "string"},
                output={"result": "string", "confidence": "float"},
            ),
            constraints=RosterConstraintsSchema(
                timeout_seconds=10, cost_ceiling_usd=1.0, retry_budget=1,
            ),
        )
        roster = Roster(agents=[entry])

        plan = TaskPlan.model_validate({
            "version": "1.0.0",
            "mission_id": "gate-live-test",
            "summary": "Gate integration test",
            "estimated_cost_usd": 1.0,
            "estimated_duration_seconds": 10,
            "tasks": [
                {
                    "task_id": "t1",
                    "agent": "test.agent",
                    "agent_version": "1.0.0",
                    "description": "First test task",
                    "instructions": "Return a simple result",
                    "dependencies": [],
                    "verification": {
                        "tier_1": {"schema_validation": True, "required_output_fields": ["result"]},
                        "tier_2": {"deterministic_checks": []},
                        "tier_3": {"requires_ai_evaluation": False},
                    },
                },
                {
                    "task_id": "t2",
                    "agent": "test.agent",
                    "agent_version": "1.0.0",
                    "description": "Second test task",
                    "instructions": "Return another result",
                    "dependencies": [],
                    "verification": {
                        "tier_1": {"schema_validation": True, "required_output_fields": ["result"]},
                        "tier_2": {"deterministic_checks": []},
                        "tier_3": {"requires_ai_evaluation": False},
                    },
                },
            ],
        })

        async def mock_executor(**kwargs):
            return {
                "result": "mock output",
                "confidence": 0.95,
                "_meta": {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.001},
            }

        gate = RecordingGate()

        outcome = await dispatch(
            plan=plan,
            roster=roster,
            execute_agent_fn=mock_executor,
            mission_budget_usd=10.0,
            gate=gate,
        )

        gate_types = [c.gate_type for c in gate.calls]
        gate_types_set = set(gate_types)

        record(
            "dispatch completes with gate",
            outcome.status.value in ("success", "partial"),
            f"status={outcome.status.value}",
        )

        record(
            "pre_dispatch gate fires",
            "pre_dispatch" in gate_types_set,
            f"gate calls: {gate_types}",
        )
        record(
            "pre_layer gate fires",
            "pre_layer" in gate_types_set,
            f"gate calls: {gate_types}",
        )
        record(
            "post_task gate fires",
            "post_task" in gate_types_set,
            f"gate calls: {gate_types}",
        )
        record(
            "post_layer gate fires",
            "post_layer" in gate_types_set,
            f"gate calls: {gate_types}",
        )

        # Verify context data is populated
        pre_dispatch = next((c for c in gate.calls if c.gate_type == "pre_dispatch"), None)
        record(
            "pre_dispatch has pending_tasks",
            pre_dispatch is not None and len(pre_dispatch.pending_tasks) == 2,
            f"tasks: {len(pre_dispatch.pending_tasks) if pre_dispatch else 'N/A'}",
        )

        post_tasks = [c for c in gate.calls if c.gate_type == "post_task"]
        record(
            f"post_task fires for each task ({len(post_tasks)} calls)",
            len(post_tasks) == 2,
            f"expected 2, got {len(post_tasks)}",
        )

        if post_tasks:
            record(
                "post_task has verification data",
                post_tasks[0].verification is not None,
            )
            record(
                "post_task tracks cost",
                post_tasks[0].total_cost_usd > 0,
                f"cost: ${post_tasks[0].total_cost_usd:.4f}",
            )

        click.echo(
            f"\n    Gate call sequence: {' → '.join(gate_types)}"
        )
        click.echo(
            f"    Mission status: {outcome.status.value}, "
            f"tasks: {len(outcome.task_results)}, "
            f"cost: ${outcome.total_cost_usd:.4f}"
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 7: LLM Gate Reviewer (real Haiku call)
# ---------------------------------------------------------------------------

def test_llm_gate_reviewer() -> None:
    """Send a real gate context to Haiku and get a structured decision back."""
    click.echo(click.style("\n── LLM Gate Reviewer (real Haiku call) ──", bold=True))

    from modules.backend.agents.mission_control.gate import (
        GateAction,
        GateContext,
        LlmGateReviewer,
    )

    async def _run():
        reviewer = LlmGateReviewer(
            model="anthropic:claude-haiku-4-5-20251001",
            temperature=0.0,
            max_tokens=1024,
        )

        # Simple post_task context with passing verification
        ctx = GateContext(
            gate_type="post_task",
            mission_id="live-test-gate",
            layer_index=0,
            total_layers=1,
            task_id="t1",
            task_output={
                "result": "Found 3 compliance violations in modules/backend/",
                "confidence": 0.92,
                "_meta": {"input_tokens": 500, "output_tokens": 200, "cost_usd": 0.003},
            },
            verification={
                "tier_1": {"status": "pass", "details": "Schema valid"},
                "tier_2": {"status": "pass", "details": "All checks passed"},
            },
            total_cost_usd=0.003,
            budget_usd=10.0,
        )

        decision = await reviewer.review(ctx)

        record(
            "Haiku returns a valid GateAction",
            isinstance(decision.action, GateAction),
            f"action={decision.action}, type={type(decision.action).__name__}",
        )
        record(
            "Haiku provides a reason",
            decision.reason is not None and len(decision.reason) > 0,
            f"reason={decision.reason!r}",
        )
        record(
            "reviewer tag includes model name",
            "ai:" in decision.reviewer and "haiku" in decision.reviewer,
            f"reviewer={decision.reviewer}",
        )
        record(
            "healthy post_task → likely CONTINUE",
            decision.action == GateAction.CONTINUE,
            f"got: {decision.action.value} (non-fatal if not CONTINUE)",
        )

        click.echo(
            f"\n    Haiku decision: {decision.action.value}"
            f"\n    Reason: {decision.reason}"
            f"\n    Reviewer: {decision.reviewer}"
        )

        # Test verification_failed — should suggest retry or abort
        ctx_fail = GateContext(
            gate_type="verification_failed",
            mission_id="live-test-gate",
            task_id="t2",
            verification={
                "tier_1": {"status": "fail", "details": "Missing required field: result"},
                "tier_2": {"status": "fail", "details": "Output schema mismatch"},
            },
            total_cost_usd=0.005,
            budget_usd=10.0,
        )

        decision_fail = await reviewer.review(ctx_fail)
        record(
            "verification_failed → non-CONTINUE action",
            decision_fail.action in (GateAction.RETRY, GateAction.ABORT, GateAction.MODIFY),
            f"got: {decision_fail.action.value} (non-fatal if CONTINUE)",
        )

        click.echo(
            f"\n    Haiku decision (failed verification): {decision_fail.action.value}"
            f"\n    Reason: {decision_fail.reason}"
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Verbose output.")
@click.option("--skip-llm", is_flag=True, help="Skip the real LLM call test.")
def main(verbose: bool, skip_llm: bool) -> None:
    """Run live gate system tests."""
    if verbose:
        setup_logging(level="INFO", format_type="console")
    else:
        setup_logging(level="WARNING", format_type="console")

    click.echo(click.style("\n" + "=" * 60, fg="cyan"))
    click.echo(click.style("  GATE SYSTEM — LIVE TESTS", fg="cyan", bold=True))
    click.echo(click.style("=" * 60, fg="cyan"))

    test_config_loading()
    test_schema_validation()
    test_factory()
    test_configurable_gate_routing()
    test_auto_continue_rules()
    test_dispatch_with_recording_gate()

    if skip_llm:
        click.echo(click.style("\n── LLM Gate Reviewer ──", bold=True))
        click.echo(f"  {SKIP}  Skipped (--skip-llm)")
    else:
        try:
            test_llm_gate_reviewer()
        except Exception:
            click.echo(f"  {FAIL}  LLM test crashed:")
            traceback.print_exc()
            record("LLM gate reviewer", False, "exception — see traceback above")

    # Summary
    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    total = len(results)

    click.echo(click.style("\n" + "=" * 60, fg="cyan"))
    color = "green" if failed == 0 else "red"
    click.echo(
        click.style(
            f"  {passed}/{total} passed, {failed} failed",
            fg=color, bold=True,
        )
    )
    click.echo(click.style("=" * 60, fg="cyan"))

    if failed:
        click.echo(click.style("\nFailed tests:", fg="red"))
        for name, p, detail in results:
            if not p:
                click.echo(f"  ✗ {name}: {detail}")
        sys.exit(1)


if __name__ == "__main__":
    main()
