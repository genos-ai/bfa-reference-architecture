"""
Tests for playbook YAML validation schemas.

Pure Pydantic schema tests — no mocks, no infrastructure.
"""

import pytest

from modules.backend.schemas.playbook import (
    PlaybookBudgetSchema,
    PlaybookObjectiveSchema,
    PlaybookOutputFieldMapping,
    PlaybookSchema,
    PlaybookStepOutputMapping,
    PlaybookStepSchema,
    PlaybookTriggerSchema,
)


def _minimal_playbook(**overrides):
    """Build a minimal valid playbook dict."""
    base = {
        "playbook_name": "test.example",
        "description": "Test playbook",
        "objective": {
            "statement": "Test objective",
            "category": "testing",
            "owner": "test-owner",
            "priority": "normal",
        },
        "steps": [
            {"id": "step-one", "capability": "test.agent"},
        ],
    }
    base.update(overrides)
    return base


class TestPlaybookStepSchema:
    def test_minimal_step(self):
        step = PlaybookStepSchema(id="step-one", capability="test.agent")
        assert step.id == "step-one"
        assert step.roster == "default"
        assert step.complexity_tier == "simple"
        assert step.environment == "local"
        assert step.cost_ceiling_usd is None

    def test_full_step(self):
        step = PlaybookStepSchema(
            id="research",
            description="Research step",
            capability="research.scraper",
            roster="research_team",
            complexity_tier="complex",
            cost_ceiling_usd=5.0,
            environment="container",
            input={"key": "value"},
            output_mapping={"summary_key": "result"},
            depends_on=["prior-step"],
            timeout_seconds=300,
        )
        assert step.complexity_tier == "complex"
        assert step.roster == "research_team"
        assert step.cost_ceiling_usd == 5.0

    def test_invalid_complexity_tier(self):
        with pytest.raises(ValueError):
            PlaybookStepSchema(
                id="step", capability="test.agent",
                complexity_tier="medium",
            )

    def test_invalid_environment(self):
        with pytest.raises(ValueError):
            PlaybookStepSchema(
                id="step", capability="test.agent",
                environment="docker",
            )

    def test_invalid_id_pattern(self):
        with pytest.raises(ValueError):
            PlaybookStepSchema(id="Step-One", capability="test.agent")

    def test_invalid_capability_pattern(self):
        with pytest.raises(ValueError):
            PlaybookStepSchema(id="step", capability="singleword")

    def test_cost_ceiling_minimum(self):
        with pytest.raises(ValueError):
            PlaybookStepSchema(
                id="step", capability="test.agent",
                cost_ceiling_usd=0.001,
            )


class TestPlaybookOutputMapping:
    def test_summary_key_only(self):
        mapping = PlaybookStepOutputMapping(summary_key="result")
        assert mapping.summary_key == "result"
        assert mapping.field_mappings == []

    def test_field_mappings(self):
        mapping = PlaybookStepOutputMapping(
            field_mappings=[
                PlaybookOutputFieldMapping(
                    source_task="task_1",
                    source_field="output",
                    target_key="data",
                ),
            ],
        )
        assert len(mapping.field_mappings) == 1
        assert mapping.field_mappings[0].target_key == "data"

    def test_invalid_target_key_pattern(self):
        with pytest.raises(ValueError):
            PlaybookOutputFieldMapping(
                source_task="t", source_field="f",
                target_key="Invalid-Key",
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValueError):
            PlaybookStepOutputMapping(unknown="field")


class TestPlaybookTriggerSchema:
    def test_defaults(self):
        trigger = PlaybookTriggerSchema()
        assert trigger.type == "on_demand"
        assert trigger.match_patterns == []

    def test_with_patterns(self):
        trigger = PlaybookTriggerSchema(
            type="on_demand",
            match_patterns=["ai news", "digest"],
        )
        assert len(trigger.match_patterns) == 2

    def test_invalid_type(self):
        with pytest.raises(ValueError):
            PlaybookTriggerSchema(type="webhook")


class TestPlaybookBudgetSchema:
    def test_defaults(self):
        budget = PlaybookBudgetSchema()
        assert budget.max_cost_usd == 10.00
        assert budget.max_tokens is None

    def test_custom(self):
        budget = PlaybookBudgetSchema(max_cost_usd=50.0, max_tokens=100000)
        assert budget.max_cost_usd == 50.0
        assert budget.max_tokens == 100000


class TestPlaybookObjectiveSchema:
    def test_valid(self):
        obj = PlaybookObjectiveSchema(
            statement="Keep team informed",
            category="research",
            owner="eng-lead",
            priority="high",
        )
        assert obj.priority == "high"
        assert obj.regulatory_reference is None

    def test_with_regulatory_ref(self):
        obj = PlaybookObjectiveSchema(
            statement="Compliance check",
            category="compliance",
            owner="ciso",
            priority="critical",
            regulatory_reference="Basel III Pillar 2",
        )
        assert obj.regulatory_reference == "Basel III Pillar 2"

    def test_invalid_priority(self):
        with pytest.raises(ValueError):
            PlaybookObjectiveSchema(
                statement="X", category="x", owner="x",
                priority="urgent",
            )

    def test_invalid_category_pattern(self):
        with pytest.raises(ValueError):
            PlaybookObjectiveSchema(
                statement="X", category="Bad Category", owner="x",
                priority="normal",
            )


class TestPlaybookSchema:
    def test_minimal_valid(self):
        playbook = PlaybookSchema(**_minimal_playbook())
        assert playbook.playbook_name == "test.example"
        assert len(playbook.steps) == 1
        assert playbook.version == 1
        assert playbook.enabled is True

    def test_extra_fields_rejected(self):
        with pytest.raises(ValueError):
            PlaybookSchema(**_minimal_playbook(unknown_field="oops"))

    def test_duplicate_step_ids(self):
        with pytest.raises(ValueError, match="Duplicate step IDs"):
            PlaybookSchema(**_minimal_playbook(
                steps=[
                    {"id": "step-a", "capability": "test.agent"},
                    {"id": "step-a", "capability": "test.other"},
                ],
            ))

    def test_missing_dependency(self):
        with pytest.raises(ValueError, match="does not exist"):
            PlaybookSchema(**_minimal_playbook(
                steps=[
                    {"id": "step-a", "capability": "test.agent",
                     "depends_on": ["step-z"]},
                ],
            ))

    def test_self_dependency(self):
        with pytest.raises(ValueError, match="depends on itself"):
            PlaybookSchema(**_minimal_playbook(
                steps=[
                    {"id": "step-a", "capability": "test.agent",
                     "depends_on": ["step-a"]},
                ],
            ))

    def test_cycle_detection(self):
        with pytest.raises(ValueError, match="dependency cycle"):
            PlaybookSchema(**_minimal_playbook(
                steps=[
                    {"id": "step-a", "capability": "test.agent",
                     "depends_on": ["step-b"]},
                    {"id": "step-b", "capability": "test.agent",
                     "depends_on": ["step-a"]},
                ],
            ))

    def test_duplicate_output_mapping_keys(self):
        with pytest.raises(ValueError, match="Duplicate output mapping"):
            PlaybookSchema(**_minimal_playbook(
                steps=[
                    {"id": "step-a", "capability": "test.agent",
                     "output_mapping": {"summary_key": "result"}},
                    {"id": "step-b", "capability": "test.agent",
                     "output_mapping": {"summary_key": "result"}},
                ],
            ))

    def test_valid_dependency_chain(self):
        playbook = PlaybookSchema(**_minimal_playbook(
            steps=[
                {"id": "step-a", "capability": "test.agent",
                 "output_mapping": {"summary_key": "a_result"}},
                {"id": "step-b", "capability": "test.agent",
                 "depends_on": ["step-a"],
                 "output_mapping": {"summary_key": "b_result"}},
                {"id": "step-c", "capability": "test.agent",
                 "depends_on": ["step-a", "step-b"]},
            ],
        ))
        assert len(playbook.steps) == 3

    def test_roster_and_complexity_per_step(self):
        playbook = PlaybookSchema(**_minimal_playbook(
            steps=[
                {"id": "research", "capability": "test.agent",
                 "roster": "research_team", "complexity_tier": "complex"},
                {"id": "content", "capability": "test.agent",
                 "roster": "content_team", "complexity_tier": "simple",
                 "depends_on": ["research"]},
            ],
        ))
        assert playbook.steps[0].roster == "research_team"
        assert playbook.steps[0].complexity_tier == "complex"
        assert playbook.steps[1].roster == "content_team"

    def test_invalid_playbook_name(self):
        with pytest.raises(ValueError):
            PlaybookSchema(**_minimal_playbook(playbook_name="BadName"))

    def test_empty_steps_rejected(self):
        with pytest.raises(ValueError):
            PlaybookSchema(**_minimal_playbook(steps=[]))
