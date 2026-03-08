"""Tests for TaskPlan validation — all 11 rules."""

import pytest

from modules.backend.agents.mission_control.plan_validator import validate_plan
from modules.backend.agents.mission_control.roster import (
    Roster,
    RosterAgentEntry,
    RosterConstraintsSchema,
    RosterInterfaceSchema,
    RosterModelSchema,
)
from modules.backend.schemas.task_plan import TaskPlan


def _entry(name: str, version: str = "1.0.0", timeout: int = 120) -> RosterAgentEntry:
    return RosterAgentEntry(
        agent_name=name,
        agent_version=version,
        description=f"Agent {name}",
        model=RosterModelSchema(name="test-model"),
        interface=RosterInterfaceSchema(
            input={"query": "string"},
            output={"result": "string", "confidence": "float"},
        ),
        constraints=RosterConstraintsSchema(timeout_seconds=timeout),
    )


def _roster(*names: str) -> Roster:
    return Roster(agents=[_entry(n) for n in names])


def _plan(tasks: list[dict], **overrides) -> TaskPlan:
    data = {
        "version": "1.0.0",
        "mission_id": "test",
        "summary": "Test",
        "estimated_cost_usd": 1.0,
        "estimated_duration_seconds": 60,
        "tasks": tasks,
        **overrides,
    }
    return TaskPlan.model_validate(data)


def _task(
    task_id: str, agent: str = "agent_a", deps: list[str] | None = None, **kw,
) -> dict:
    return {
        "task_id": task_id,
        "agent": agent,
        "agent_version": "1.0.0",
        "description": "Test",
        "instructions": "Do it",
        "dependencies": deps or [],
        **kw,
    }


class TestRule2AgentValidation:
    def test_valid_agents_pass(self):
        plan = _plan([_task("t1", "agent_a")])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_unknown_agent_fails(self):
        plan = _plan([_task("t1", "unknown_agent")])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("agent_validation" in e for e in result.errors)


class TestRule3DagValidation:
    def test_valid_dag_passes(self):
        plan = _plan([
            _task("t1", "agent_a"),
            _task("t2", "agent_a", deps=["t1"]),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_cycle_fails(self):
        plan = _plan([
            _task("t1", "agent_a", deps=["t2"]),
            _task("t2", "agent_a", deps=["t1"]),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("dag_validation" in e for e in result.errors)

    def test_duplicate_task_id_fails(self):
        plan = _plan([_task("t1", "agent_a"), _task("t1", "agent_a")])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid

    def test_unknown_dependency_fails(self):
        plan = _plan([_task("t1", "agent_a", deps=["nonexistent"])])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid


class TestRule4DependencyConsistency:
    def test_consistent_deps_pass(self):
        plan = _plan([
            _task("t1", "agent_a"),
            _task("t2", "agent_a", deps=["t1"], inputs={
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "result"},
                },
            }),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_upstream_not_in_deps_fails(self):
        plan = _plan([
            _task("t1", "agent_a"),
            _task("t2", "agent_a", deps=[], inputs={
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "result"},
                },
            }),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("dependency_consistency" in e for e in result.errors)


class TestRule5InputCompatibility:
    def test_valid_source_field_passes(self):
        plan = _plan([
            _task("t1", "agent_a"),
            _task("t2", "agent_a", deps=["t1"], inputs={
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "result"},
                },
            }),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_invalid_source_field_fails(self):
        plan = _plan([
            _task("t1", "agent_a"),
            _task("t2", "agent_a", deps=["t1"], inputs={
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "nonexistent_field"},
                },
            }),
        ])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("input_compatibility" in e for e in result.errors)


class TestRule7BudgetValidation:
    def test_within_budget_passes(self):
        plan = _plan([_task("t1", "agent_a")], estimated_cost_usd=5.0)
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_over_budget_fails(self):
        plan = _plan([_task("t1", "agent_a")], estimated_cost_usd=15.0)
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("budget_validation" in e for e in result.errors)


class TestRule8TimeoutValidation:
    def test_within_timeout_passes(self):
        plan = _plan([_task("t1", "agent_a", constraints={
            "timeout_override_seconds": 60,
            "priority": "normal",
        })])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_over_timeout_fails(self):
        plan = _plan([_task("t1", "agent_a", constraints={
            "timeout_override_seconds": 999,
            "priority": "normal",
        })])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("timeout_validation" in e for e in result.errors)


class TestRule9CriticalPathValidation:
    def test_valid_critical_path_passes(self):
        plan = _plan(
            [_task("t1", "agent_a")],
            execution_hints={"min_success_threshold": 1.0, "critical_path": ["t1"]},
        )
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert result.is_valid

    def test_unknown_critical_path_fails(self):
        plan = _plan(
            [_task("t1", "agent_a")],
            execution_hints={
                "min_success_threshold": 1.0,
                "critical_path": ["nonexistent"],
            },
        )
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("critical_path" in e for e in result.errors)


class TestRule10Tier3Completeness:
    def test_complete_tier3_passes(self):
        roster = Roster(agents=[
            _entry("agent_a"),
            _entry("horizontal.verification.agent"),
        ])
        plan = _plan([_task("t1", "agent_a", verification={
            "tier_1": {"schema_validation": True, "required_output_fields": []},
            "tier_2": {"deterministic_checks": []},
            "tier_3": {
                "requires_ai_evaluation": True,
                "evaluation_criteria": ["Is it good?"],
                "evaluator_agent": "horizontal.verification.agent",
                "min_evaluation_score": 0.85,
            },
        })])
        result = validate_plan(plan, roster, 10.0)
        assert result.is_valid

    def test_missing_criteria_fails(self):
        roster = Roster(agents=[
            _entry("agent_a"),
            _entry("horizontal.verification.agent"),
        ])
        plan = _plan([_task("t1", "agent_a", verification={
            "tier_1": {"schema_validation": True, "required_output_fields": []},
            "tier_2": {"deterministic_checks": []},
            "tier_3": {
                "requires_ai_evaluation": True,
                "evaluation_criteria": [],
                "evaluator_agent": "horizontal.verification.agent",
                "min_evaluation_score": 0.85,
            },
        })])
        result = validate_plan(plan, roster, 10.0)
        assert not result.is_valid
        assert any("tier3_completeness" in e for e in result.errors)

    def test_missing_evaluator_fails(self):
        plan = _plan([_task("t1", "agent_a", verification={
            "tier_1": {"schema_validation": True, "required_output_fields": []},
            "tier_2": {"deterministic_checks": []},
            "tier_3": {
                "requires_ai_evaluation": True,
                "evaluation_criteria": ["Check quality"],
                "evaluator_agent": None,
                "min_evaluation_score": 0.85,
            },
        })])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid

    def test_missing_score_fails(self):
        roster = Roster(agents=[
            _entry("agent_a"),
            _entry("horizontal.verification.agent"),
        ])
        plan = _plan([_task("t1", "agent_a", verification={
            "tier_1": {"schema_validation": True, "required_output_fields": []},
            "tier_2": {"deterministic_checks": []},
            "tier_3": {
                "requires_ai_evaluation": True,
                "evaluation_criteria": ["Check quality"],
                "evaluator_agent": "horizontal.verification.agent",
                "min_evaluation_score": None,
            },
        })])
        result = validate_plan(plan, roster, 10.0)
        assert not result.is_valid


class TestRule11SelfEvaluationPrevention:
    def test_different_evaluator_passes(self):
        roster = Roster(agents=[
            _entry("agent_a"),
            _entry("horizontal.verification.agent"),
        ])
        plan = _plan([_task("t1", "agent_a", verification={
            "tier_1": {"schema_validation": True, "required_output_fields": []},
            "tier_2": {"deterministic_checks": []},
            "tier_3": {
                "requires_ai_evaluation": True,
                "evaluation_criteria": ["Check quality"],
                "evaluator_agent": "horizontal.verification.agent",
                "min_evaluation_score": 0.85,
            },
        })])
        result = validate_plan(plan, roster, 10.0)
        assert result.is_valid

    def test_self_evaluation_fails(self):
        plan = _plan([_task("t1", "agent_a", verification={
            "tier_1": {"schema_validation": True, "required_output_fields": []},
            "tier_2": {"deterministic_checks": []},
            "tier_3": {
                "requires_ai_evaluation": True,
                "evaluation_criteria": ["Check quality"],
                "evaluator_agent": "agent_a",
                "min_evaluation_score": 0.85,
            },
        })])
        result = validate_plan(plan, _roster("agent_a"), 10.0)
        assert not result.is_valid
        assert any("self_evaluation" in e for e in result.errors)
