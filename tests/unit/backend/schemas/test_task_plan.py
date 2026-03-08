"""Tests for TaskPlan schema validation."""

import pytest

from modules.backend.schemas.task_plan import (
    ExecutionHints,
    FromUpstreamRef,
    TaskDefinition,
    TaskPlan,
)


def _make_task(task_id: str = "task_1", deps: list[str] | None = None) -> dict:
    """Create a minimal task dict for testing."""
    return {
        "task_id": task_id,
        "agent": "test.agent",
        "agent_version": "1.0.0",
        "description": "Test task",
        "instructions": "Do the thing",
        "dependencies": deps or [],
    }


def _make_plan(tasks: list[dict] | None = None) -> dict:
    """Create a minimal plan dict for testing."""
    return {
        "version": "1.0.0",
        "mission_id": "test-mission",
        "summary": "Test plan",
        "estimated_cost_usd": 1.0,
        "estimated_duration_seconds": 60,
        "tasks": tasks or [_make_task()],
    }


class TestTaskPlan:
    def test_minimal_plan_parses(self):
        plan = TaskPlan.model_validate(_make_plan())
        assert plan.mission_id == "test-mission"
        assert len(plan.tasks) == 1

    def test_task_ids_property(self):
        plan = TaskPlan.model_validate(_make_plan([
            _make_task("a"),
            _make_task("b"),
        ]))
        assert plan.task_ids == ["a", "b"]

    def test_get_task(self):
        plan = TaskPlan.model_validate(_make_plan([_make_task("a")]))
        assert plan.get_task("a") is not None
        assert plan.get_task("nonexistent") is None

    def test_from_upstream_ref(self):
        ref = FromUpstreamRef(source_task="task_1", source_field="output_field")
        assert ref.source_task == "task_1"

    def test_execution_hints_defaults(self):
        plan = TaskPlan.model_validate(_make_plan())
        assert plan.execution_hints.min_success_threshold == 1.0
        assert plan.execution_hints.critical_path == []

    def test_negative_cost_rejected(self):
        data = _make_plan()
        data["estimated_cost_usd"] = -1.0
        with pytest.raises(Exception):
            TaskPlan.model_validate(data)

    def test_extra_fields_rejected(self):
        data = _make_plan()
        data["unknown_field"] = "bad"
        with pytest.raises(Exception):
            TaskPlan.model_validate(data)

    def test_full_plan_from_research_doc(self):
        """Validate the full example from the research doc parses."""
        plan_data = {
            "version": "1.0.0",
            "mission_id": "iam-audit-001",
            "summary": "IAM policy audit and remediation",
            "estimated_cost_usd": 2.50,
            "estimated_duration_seconds": 300,
            "tasks": [
                {
                    "task_id": "analyse_config",
                    "agent": "config_scanner",
                    "agent_version": "1.0.0",
                    "description": "Scan current IAM configuration",
                    "instructions": "Scan all environments for IAM config",
                    "inputs": {
                        "static": {"environments": ["prod", "staging"]},
                        "from_upstream": {},
                    },
                    "dependencies": [],
                    "verification": {
                        "tier_1": {
                            "schema_validation": True,
                            "required_output_fields": ["config_data", "confidence"],
                        },
                        "tier_2": {"deterministic_checks": []},
                        "tier_3": {"requires_ai_evaluation": False},
                    },
                },
                {
                    "task_id": "generate_remediation",
                    "agent": "code_generator",
                    "agent_version": "1.0.0",
                    "description": "Generate remediation code",
                    "instructions": "Generate Terraform modules",
                    "inputs": {
                        "static": {"output_format": "terraform"},
                        "from_upstream": {
                            "current_config": {
                                "source_task": "analyse_config",
                                "source_field": "config_data",
                            },
                        },
                    },
                    "dependencies": ["analyse_config"],
                    "verification": {
                        "tier_1": {
                            "schema_validation": True,
                            "required_output_fields": ["code", "confidence"],
                        },
                        "tier_2": {"deterministic_checks": []},
                        "tier_3": {
                            "requires_ai_evaluation": True,
                            "evaluation_criteria": ["Code addresses all gaps"],
                            "evaluator_agent": "verification_agent",
                            "min_evaluation_score": 0.85,
                        },
                    },
                },
            ],
            "execution_hints": {
                "min_success_threshold": 0.66,
                "critical_path": ["analyse_config"],
            },
        }
        plan = TaskPlan.model_validate(plan_data)
        assert len(plan.tasks) == 2
        assert plan.execution_hints.min_success_threshold == 0.66
