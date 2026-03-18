"""
Tests for the Step-Through Gate mechanism (Plan 22).

Tests the gate protocol, NoOpGate, GateContext serialization,
gate integration with the dispatch loop, ConfigurableGate routing,
auto-continue rules, and AI recommendation rendering.
"""

import json
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.backend.agents.mission_control.gate import (
    ConfigurableGate,
    GateAction,
    GateContext,
    GateDecision,
    GateReviewer,
    LlmGateReviewer,
    NoOpGate,
    _parse_action,
)
from modules.backend.agents.mission_control.roster import (
    Roster,
    RosterAgentEntry,
    RosterConstraintsSchema,
    RosterInterfaceSchema,
    RosterModelSchema,
)
from modules.backend.core.config_schema import (
    GateAiSchema,
    GateAutoRulesSchema,
    GatePointSchema,
    GatePointsSchema,
    GateSchema,
)
from modules.backend.schemas.task_plan import TaskPlan


# ── Fixture helpers ───────────────────────────────────────────────


def _entry(name: str) -> RosterAgentEntry:
    return RosterAgentEntry(
        agent_name=name,
        agent_version="1.0.0",
        description=f"Agent {name}",
        model=RosterModelSchema(name="test-model"),
        interface=RosterInterfaceSchema(
            input={"query": "string"},
            output={"result": "string", "confidence": "float"},
        ),
        constraints=RosterConstraintsSchema(
            timeout_seconds=10,
            cost_ceiling_usd=1.0,
            retry_budget=1,
        ),
    )


def _task(task_id: str, agent: str = "test.agent") -> dict:
    return {
        "task_id": task_id,
        "agent": agent,
        "agent_version": "1.0.0",
        "description": "test task",
        "instructions": "do nothing",
        "dependencies": [],
        "verification": {
            "tier_1": {
                "schema_validation": True,
                "required_output_fields": ["result"],
            },
            "tier_2": {"deterministic_checks": []},
            "tier_3": {"requires_ai_evaluation": False},
        },
    }


def _plan(mission_id: str = "test", tasks: list[dict] | None = None) -> TaskPlan:
    return TaskPlan.model_validate({
        "version": "1.0.0",
        "mission_id": mission_id,
        "summary": "Test",
        "estimated_cost_usd": 1.0,
        "estimated_duration_seconds": 60,
        "tasks": tasks or [_task("t1")],
    })


def _gate_config(mode: str = "off", **overrides) -> GateSchema:
    """Build a GateSchema for testing."""
    return GateSchema(mode=mode, **overrides)


# ── Test helpers ──────────────────────────────────────────────────


class AlwaysAbortGate:
    """Test gate that always aborts."""

    async def review(self, context: GateContext) -> GateDecision:
        return GateDecision(action=GateAction.ABORT, reason="test abort", reviewer="test")


class SkipLayerGate:
    """Test gate that skips a specific layer."""

    def __init__(self, skip_layer: int = 0):
        self.skip_layer = skip_layer

    async def review(self, context: GateContext) -> GateDecision:
        if context.gate_type == "pre_layer" and context.layer_index == self.skip_layer:
            return GateDecision(action=GateAction.SKIP, reason="test skip", reviewer="test")
        return GateDecision(action=GateAction.CONTINUE, reviewer="test")


class RecordingGate:
    """Test gate that records all gate calls and continues."""

    def __init__(self):
        self.calls: list[GateContext] = []

    async def review(self, context: GateContext) -> GateDecision:
        self.calls.append(context)
        return GateDecision(action=GateAction.CONTINUE, reviewer="test")


# ── NoOpGate tests ────────────────────────────────────────────────


class TestNoOpGate:
    @pytest.mark.asyncio
    async def test_always_continues(self):
        gate = NoOpGate()
        ctx = GateContext(gate_type="pre_dispatch", mission_id="test-1")
        decision = await gate.review(ctx)
        assert decision.action == GateAction.CONTINUE
        assert decision.reviewer == "noop"

    @pytest.mark.asyncio
    async def test_all_gate_types_continue(self):
        gate = NoOpGate()
        for gate_type in ["pre_dispatch", "pre_layer", "post_task",
                          "verification_failed", "post_layer"]:
            decision = await gate.review(GateContext(
                gate_type=gate_type, mission_id="test",
            ))
            assert decision.action == GateAction.CONTINUE


# ── GateContext tests ─────────────────────────────────────────────


class TestGateContext:
    def test_serializable(self):
        """GateContext must be JSON-serializable for AI reviewer."""
        ctx = GateContext(
            gate_type="pre_layer",
            mission_id="mission-123",
            layer_index=1,
            total_layers=3,
            pending_tasks=[
                {"task_id": "t1", "agent": "test.agent", "description": "do stuff"},
            ],
            total_cost_usd=0.42,
            budget_usd=2.0,
        )
        result = json.dumps(asdict(ctx), default=str)
        assert "mission-123" in result
        assert "pre_layer" in result

    def test_default_values(self):
        ctx = GateContext(gate_type="post_task", mission_id="m1")
        assert ctx.layer_index == 0
        assert ctx.total_layers == 0
        assert ctx.pending_tasks == []
        assert ctx.completed_tasks == []
        assert ctx.total_cost_usd == 0.0
        assert ctx.task_id is None
        assert ctx.task_output is None

    def test_ai_recommendation_field(self):
        """ai_recommendation should accept any value."""
        rec = GateDecision(action=GateAction.CONTINUE, reviewer="ai:test")
        ctx = GateContext(gate_type="pre_dispatch", mission_id="m1", ai_recommendation=rec)
        assert ctx.ai_recommendation is rec


# ── GateDecision tests ───────────────────────────────────────────


class TestGateDecision:
    def test_continue(self):
        d = GateDecision(action=GateAction.CONTINUE)
        assert d.action == GateAction.CONTINUE
        assert d.reviewer == "human"

    def test_abort_with_reason(self):
        d = GateDecision(action=GateAction.ABORT, reason="budget too high")
        assert d.reason == "budget too high"

    def test_retry_with_modified_instructions(self):
        d = GateDecision(
            action=GateAction.RETRY,
            modified_instructions="Try a different approach",
        )
        assert d.modified_instructions == "Try a different approach"

    def test_modify_with_inputs(self):
        d = GateDecision(
            action=GateAction.MODIFY,
            modified_inputs={"scope": "tests/"},
        )
        assert d.modified_inputs["scope"] == "tests/"


# ── GateAction enum tests ────────────────────────────────────────


class TestGateAction:
    def test_all_values(self):
        assert GateAction.CONTINUE == "continue"
        assert GateAction.SKIP == "skip"
        assert GateAction.RETRY == "retry"
        assert GateAction.ABORT == "abort"
        assert GateAction.MODIFY == "modify"

    def test_serializable(self):
        """Enum values should be string-serializable."""
        assert json.dumps(GateAction.CONTINUE) == '"continue"'


# ── _parse_action tests ──────────────────────────────────────────


class TestParseAction:
    def test_valid_actions(self):
        assert _parse_action("continue") == GateAction.CONTINUE
        assert _parse_action("ABORT") == GateAction.ABORT
        assert _parse_action(" retry ") == GateAction.RETRY

    def test_unknown_action_falls_back(self):
        assert _parse_action("explode") == GateAction.CONTINUE


# ── LlmGateReviewer tests ────────────────────────────────────────


class TestLlmGateReviewer:
    def test_lazy_init(self):
        """Agent should not be built until first review call."""
        gate = LlmGateReviewer(model="anthropic:claude-haiku-4-5-20251001")
        assert gate._agent is None

    def test_custom_model_name(self):
        gate = LlmGateReviewer(model="anthropic:claude-sonnet-4-20250514")
        assert gate.model_name == "anthropic:claude-sonnet-4-20250514"

    def test_default_params(self):
        gate = LlmGateReviewer()
        assert gate.temperature == 0.0
        assert gate.max_tokens == 1024

    @pytest.mark.asyncio
    async def test_llm_failure_aborts_for_safety(self):
        """When the LLM call fails, the gate must ABORT — never auto-continue."""
        gate = LlmGateReviewer(model="test")
        # Force _get_agent to raise on review
        gate._agent = MagicMock()
        gate._agent.run = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        ctx = GateContext(
            gate_type="pre_dispatch",
            mission_id="m-1",
        )
        decision = await gate.review(ctx)
        assert decision.action == GateAction.ABORT
        assert "safety" in decision.reason.lower()
        assert "fallback" in decision.reviewer


# ── GateSchema tests ─────────────────────────────────────────────


class TestGateSchema:
    def test_defaults(self):
        schema = GateSchema()
        assert schema.mode == "off"
        assert schema.ai.model == "anthropic:claude-haiku-4-5-20251001"
        assert schema.ai.temperature == 0.0
        assert schema.points.pre_dispatch.enabled is True
        assert schema.points.verification_failed.mode is None
        assert schema.auto_rules.cost_threshold_pct == 80

    def test_mode_override(self):
        schema = GateSchema(mode="autonomous")
        assert schema.mode == "autonomous"

    def test_per_point_mode(self):
        points = GatePointsSchema(
            verification_failed=GatePointSchema(enabled=True, mode="ai_assisted"),
        )
        schema = GateSchema(mode="autonomous", points=points)
        assert schema.points.verification_failed.mode == "ai_assisted"
        assert schema.points.pre_dispatch.mode is None

    def test_disabled_point(self):
        points = GatePointsSchema(
            post_task=GatePointSchema(enabled=False),
        )
        schema = GateSchema(mode="interactive", points=points)
        assert schema.points.post_task.enabled is False

    def test_custom_ai_model(self):
        ai = GateAiSchema(model="anthropic:claude-sonnet-4-20250514", max_tokens=2048)
        schema = GateSchema(ai=ai)
        assert schema.ai.model == "anthropic:claude-sonnet-4-20250514"
        assert schema.ai.max_tokens == 2048

    def test_strict_rejects_unknown_keys(self):
        with pytest.raises(Exception):  # ValidationError
            GateSchema(mode="off", unknown_key="bad")

    def test_rejects_invalid_mode(self):
        with pytest.raises(Exception):  # ValidationError
            GateSchema(mode="banana")


# ── ConfigurableGate tests ───────────────────────────────────────


class TestConfigurableGate:
    @pytest.mark.asyncio
    async def test_off_mode_continues(self):
        config = _gate_config("off")
        gate = ConfigurableGate(config=config)
        ctx = GateContext(gate_type="pre_dispatch", mission_id="test")
        decision = await gate.review(ctx)
        assert decision.action == GateAction.CONTINUE
        assert decision.reviewer == "config:off"

    @pytest.mark.asyncio
    async def test_disabled_point_continues(self):
        points = GatePointsSchema(
            pre_dispatch=GatePointSchema(enabled=False),
        )
        config = _gate_config("interactive", points=points)
        gate = ConfigurableGate(config=config)
        ctx = GateContext(gate_type="pre_dispatch", mission_id="test")
        decision = await gate.review(ctx)
        assert decision.action == GateAction.CONTINUE
        assert decision.reviewer == "config:disabled"

    @pytest.mark.asyncio
    async def test_per_point_mode_overrides_top_level(self):
        """verification_failed set to ai_assisted even when top-level is autonomous."""
        points = GatePointsSchema(
            verification_failed=GatePointSchema(mode="off"),
        )
        config = _gate_config("interactive", points=points)
        gate = ConfigurableGate(config=config)
        ctx = GateContext(gate_type="verification_failed", mission_id="test")
        decision = await gate.review(ctx)
        assert decision.action == GateAction.CONTINUE
        assert decision.reviewer == "config:off"

    def test_effective_mode_inherits(self):
        config = _gate_config("autonomous")
        gate = ConfigurableGate(config=config)
        assert gate._effective_mode("pre_dispatch") == "autonomous"

    def test_effective_mode_overridden(self):
        points = GatePointsSchema(
            pre_dispatch=GatePointSchema(mode="interactive"),
        )
        config = _gate_config("autonomous", points=points)
        gate = ConfigurableGate(config=config)
        assert gate._effective_mode("pre_dispatch") == "interactive"

    def test_rejects_wrong_config_type(self):
        with pytest.raises(TypeError, match="Expected GateSchema"):
            ConfigurableGate(config={"mode": "off"})


# ── Auto-continue rules tests ───────────────────────────────────


class TestAutoRules:
    def _make_gate(self, **rule_overrides) -> ConfigurableGate:
        rules = GateAutoRulesSchema(**rule_overrides)
        config = _gate_config("autonomous", auto_rules=rules)
        return ConfigurableGate(config=config)

    def test_pre_layer_auto_continues_few_tasks(self):
        gate = self._make_gate(max_tasks_per_layer=5)
        ctx = GateContext(
            gate_type="pre_layer", mission_id="test",
            pending_tasks=[{"task_id": "t1"}],
            budget_usd=10.0, total_cost_usd=1.0,
        )
        assert gate._should_auto_continue(ctx) is True

    def test_pre_layer_no_auto_continue_many_tasks(self):
        gate = self._make_gate(max_tasks_per_layer=2)
        ctx = GateContext(
            gate_type="pre_layer", mission_id="test",
            pending_tasks=[{"task_id": f"t{i}"} for i in range(5)],
            budget_usd=10.0, total_cost_usd=1.0,
        )
        assert gate._should_auto_continue(ctx) is False

    def test_post_task_auto_continues_on_pass(self):
        gate = self._make_gate(skip_post_task_on_pass=True)
        ctx = GateContext(
            gate_type="post_task", mission_id="test",
            verification={"tier_1": {"status": "pass"}, "tier_2": {"status": "pass"}},
            budget_usd=10.0, total_cost_usd=1.0,
        )
        assert gate._should_auto_continue(ctx) is True

    def test_post_task_no_auto_on_fail(self):
        gate = self._make_gate(skip_post_task_on_pass=True)
        ctx = GateContext(
            gate_type="post_task", mission_id="test",
            verification={"tier_1": {"status": "fail"}, "tier_2": {"status": "pass"}},
            budget_usd=10.0, total_cost_usd=1.0,
        )
        assert gate._should_auto_continue(ctx) is False

    def test_verification_failed_never_auto_continues(self):
        gate = self._make_gate()
        ctx = GateContext(
            gate_type="verification_failed", mission_id="test",
            budget_usd=10.0, total_cost_usd=0.1,
        )
        assert gate._should_auto_continue(ctx) is False

    def test_pre_dispatch_never_auto_continues(self):
        gate = self._make_gate()
        ctx = GateContext(
            gate_type="pre_dispatch", mission_id="test",
            budget_usd=10.0, total_cost_usd=0.1,
        )
        assert gate._should_auto_continue(ctx) is False

    def test_high_cost_blocks_auto_continue(self):
        gate = self._make_gate(cost_threshold_pct=80)
        ctx = GateContext(
            gate_type="pre_layer", mission_id="test",
            pending_tasks=[{"task_id": "t1"}],
            budget_usd=10.0, total_cost_usd=9.0,  # 90% > 80% threshold
        )
        assert gate._should_auto_continue(ctx) is False

    def test_post_layer_auto_continues_within_budget(self):
        gate = self._make_gate(cost_threshold_pct=80)
        ctx = GateContext(
            gate_type="post_layer", mission_id="test",
            budget_usd=10.0, total_cost_usd=5.0,  # 50% < 80%
        )
        assert gate._should_auto_continue(ctx) is True


# ── Protocol compliance tests ────────────────────────────────────


class TestGateProtocol:
    def test_noop_satisfies_protocol(self):
        """NoOpGate should satisfy GateReviewer protocol structurally."""
        gate: GateReviewer = NoOpGate()
        assert hasattr(gate, "review")

    def test_custom_gate_satisfies_protocol(self):
        gate: GateReviewer = AlwaysAbortGate()
        assert hasattr(gate, "review")

    def test_configurable_gate_satisfies_protocol(self):
        config = _gate_config("off")
        gate: GateReviewer = ConfigurableGate(config=config)
        assert hasattr(gate, "review")


# ── Integration with dispatch ────────────────────────────────────


class TestGateDispatchIntegration:
    """Integration tests that verify gate works with dispatch.

    These use minimal mocks to test the gate mechanism without
    actually calling LLMs.
    """

    @pytest.mark.asyncio
    async def test_abort_at_pre_dispatch(self):
        """Aborting at pre_dispatch should return empty failed outcome."""
        from modules.backend.agents.mission_control.dispatch import dispatch
        from modules.backend.agents.mission_control.outcome import MissionStatus

        roster = Roster(agents=[_entry("test.agent")])

        async def mock_executor(**kwargs):
            return {"result": "should not reach here"}

        outcome = await dispatch(
            plan=_plan("test-abort"),
            roster=roster,
            execute_agent_fn=mock_executor,
            mission_budget_usd=10.0,
            gate=AlwaysAbortGate(),
        )

        assert outcome.status == MissionStatus.FAILED
        assert len(outcome.task_results) == 0

    @pytest.mark.asyncio
    async def test_recording_gate_sees_all_phases(self):
        """A recording gate should see pre_dispatch, pre_layer, post_task, post_layer."""
        from modules.backend.agents.mission_control.dispatch import dispatch

        roster = Roster(agents=[_entry("test.agent")])

        async def mock_executor(**kwargs):
            return {"result": "ok", "confidence": 0.9, "_meta": {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001}}

        gate = RecordingGate()

        outcome = await dispatch(
            plan=_plan("test-record"),
            roster=roster,
            execute_agent_fn=mock_executor,
            mission_budget_usd=10.0,
            gate=gate,
        )

        gate_types = [c.gate_type for c in gate.calls]
        assert "pre_dispatch" in gate_types
        assert "pre_layer" in gate_types
        assert "post_task" in gate_types
        assert "post_layer" in gate_types

    @pytest.mark.asyncio
    async def test_no_gate_works_unchanged(self):
        """Default dispatch (gate=None) should work exactly as before."""
        from modules.backend.agents.mission_control.dispatch import dispatch
        from modules.backend.agents.mission_control.outcome import MissionStatus

        roster = Roster(agents=[_entry("test.agent")])

        async def mock_executor(**kwargs):
            return {"result": "ok", "confidence": 0.9, "_meta": {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001}}

        outcome = await dispatch(
            plan=_plan("test-no-gate"),
            roster=roster,
            execute_agent_fn=mock_executor,
            mission_budget_usd=10.0,
        )

        assert outcome.status == MissionStatus.SUCCESS
        assert len(outcome.task_results) == 1

    @pytest.mark.asyncio
    async def test_skip_layer_marks_tasks_skipped(self):
        """SkipLayerGate should skip layer 0 tasks."""
        from modules.backend.agents.mission_control.dispatch import dispatch
        from modules.backend.agents.mission_control.outcome import TaskStatus

        roster = Roster(agents=[_entry("test.agent")])

        async def mock_executor(**kwargs):
            return {"result": "ok", "confidence": 0.9, "_meta": {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001}}

        outcome = await dispatch(
            plan=_plan("test-skip"),
            roster=roster,
            execute_agent_fn=mock_executor,
            mission_budget_usd=10.0,
            gate=SkipLayerGate(skip_layer=0),
        )

        assert len(outcome.task_results) == 1
        assert outcome.task_results[0].status == TaskStatus.SKIPPED
        assert outcome.task_results[0].skip_reason == "test skip"

    @pytest.mark.asyncio
    async def test_abort_preserves_reason(self):
        """abort_reason should be stored in MissionOutcome."""
        from modules.backend.agents.mission_control.dispatch import dispatch
        from modules.backend.agents.mission_control.outcome import MissionStatus

        roster = Roster(agents=[_entry("test.agent")])

        async def mock_executor(**kwargs):
            return {"result": "should not reach here"}

        outcome = await dispatch(
            plan=_plan("test-reason"),
            roster=roster,
            execute_agent_fn=mock_executor,
            mission_budget_usd=10.0,
            gate=AlwaysAbortGate(),
        )

        assert outcome.status == MissionStatus.FAILED
        assert outcome.abort_reason == "test abort"

    @pytest.mark.asyncio
    async def test_abort_after_success_still_failed(self):
        """Aborting at post_layer after tasks succeed must still be FAILED."""
        from modules.backend.agents.mission_control.dispatch import dispatch
        from modules.backend.agents.mission_control.outcome import MissionStatus, TaskStatus

        class PostLayerAbortGate:
            """Gate that lets tasks run but aborts at post_layer."""

            async def review(self, context: GateContext) -> GateDecision:
                if context.gate_type == "post_layer":
                    return GateDecision(
                        action=GateAction.ABORT,
                        reason="stop after layer",
                        reviewer="test",
                    )
                return GateDecision(action=GateAction.CONTINUE, reviewer="test")

        roster = Roster(agents=[_entry("test.agent")])

        async def mock_executor(**kwargs):
            return {"result": "ok", "confidence": 0.9, "_meta": {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001}}

        outcome = await dispatch(
            plan=_plan("test-post-abort"),
            roster=roster,
            execute_agent_fn=mock_executor,
            mission_budget_usd=10.0,
            gate=PostLayerAbortGate(),
        )

        # Even though the single task succeeded, abort means FAILED
        assert outcome.status == MissionStatus.FAILED
        assert outcome.abort_reason == "stop after layer"
        # The task itself should still show SUCCESS
        assert len(outcome.task_results) == 1
        assert outcome.task_results[0].status == TaskStatus.SUCCESS
