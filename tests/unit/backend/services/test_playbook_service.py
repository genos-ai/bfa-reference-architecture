"""
Tests for PlaybookService.

Tests playbook loading, validation, capability resolution,
mission brief generation, output mapping, and playbook matching.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

import yaml

from modules.backend.schemas.playbook import PlaybookSchema
from modules.backend.services.playbook import PlaybookService


def _make_playbook(**overrides) -> PlaybookSchema:
    """Build a valid PlaybookSchema for testing."""
    base = {
        "playbook_name": "test.example",
        "description": "Test playbook",
        "project": "Test Project",
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
    return PlaybookSchema(**base)


class TestCapabilityResolution:
    def test_resolve_with_registry(self):
        registry = {
            "content.summarizer.agent": {
                "agent_name": "content.summarizer.agent",
                "enabled": True,
            },
        }
        service = PlaybookService(agent_registry=registry)
        result = service.resolve_capability("content.summarizer")
        assert result == "content.summarizer.agent"

    def test_resolve_missing_raises(self):
        service = PlaybookService(agent_registry={})
        with pytest.raises(ValueError, match="No agent found"):
            service.resolve_capability("nonexistent.agent")

    def test_resolve_disabled_raises(self):
        registry = {
            "test.disabled.agent": {
                "agent_name": "test.disabled.agent",
                "enabled": False,
            },
        }
        service = PlaybookService(agent_registry=registry)
        with pytest.raises(ValueError, match="disabled"):
            service.resolve_capability("test.disabled")

    def test_validate_playbook_capabilities(self):
        registry = {
            "test.agent.agent": {"agent_name": "test.agent.agent", "enabled": True},
        }
        service = PlaybookService(agent_registry=registry)
        playbook = _make_playbook()
        errors = service.validate_playbook_capabilities(playbook)
        assert errors == []

    def test_validate_capabilities_with_errors(self):
        service = PlaybookService(agent_registry={})
        playbook = _make_playbook()
        errors = service.validate_playbook_capabilities(playbook)
        assert len(errors) == 1
        assert "Step 'step-one'" in errors[0]


class TestMissionBriefGeneration:
    def test_generate_briefs(self):
        registry = {
            "test.step_one.agent": {"agent_name": "test.step_one.agent", "enabled": True},
            "test.step_two.agent": {"agent_name": "test.step_two.agent", "enabled": True},
        }
        service = PlaybookService(agent_registry=registry)

        playbook = PlaybookSchema(
            playbook_name="test.pipeline",
            description="Test pipeline",
            project="Test Project",
            objective={
                "statement": "Test", "category": "test",
                "owner": "test", "priority": "normal",
            },
            steps=[
                {
                    "id": "step-one",
                    "capability": "test.step_one",
                    "roster": "research_team",
                    "complexity_tier": "complex",
                    "cost_ceiling_usd": 5.0,
                    "input": {"key": "value"},
                    "output_mapping": {"summary_key": "result_one"},
                },
                {
                    "id": "step-two",
                    "capability": "test.step_two",
                    "roster": "content_team",
                    "input": {"data": "@context.result_one"},
                    "depends_on": ["step-one"],
                },
            ],
        )

        briefs = service.generate_mission_briefs(playbook)

        assert len(briefs) == 2
        assert briefs[0]["step_id"] == "step-one"
        assert briefs[0]["roster_ref"] == "research_team"
        assert briefs[0]["complexity_tier"] == "complex"
        assert briefs[0]["cost_ceiling_usd"] == 5.0
        assert briefs[0]["resolved_agent"] == "test.step_one.agent"
        assert briefs[0]["dependencies"] == []

        assert briefs[1]["step_id"] == "step-two"
        assert briefs[1]["roster_ref"] == "content_team"
        assert briefs[1]["complexity_tier"] == "simple"
        assert len(briefs[1]["dependencies"]) == 1
        assert briefs[1]["dependencies"][0]["depends_on_step"] == "step-one"


class TestPlaybookMatching:
    def test_match_by_pattern(self):
        service = PlaybookService(agent_registry={})
        playbook = _make_playbook(
            playbook_name="test.digest",
            trigger={
                "type": "on_demand",
                "match_patterns": ["ai news", "ai digest"],
            },
        )
        service._playbooks = {"test.digest": playbook}

        result = service.match_playbook("Show me the latest ai news")
        assert result is not None
        assert result.playbook_name == "test.digest"

    def test_no_match(self):
        service = PlaybookService(agent_registry={})
        service._playbooks = {}

        result = service.match_playbook("Tell me about the weather")
        assert result is None

    def test_disabled_playbook_not_matched(self):
        service = PlaybookService(agent_registry={})
        playbook = _make_playbook(
            playbook_name="test.disabled",
            enabled=False,
            trigger={
                "type": "on_demand",
                "match_patterns": ["test"],
            },
        )
        service._playbooks = {"test.disabled": playbook}

        result = service.match_playbook("test something")
        assert result is None

    def test_case_insensitive_matching(self):
        service = PlaybookService(agent_registry={})
        playbook = _make_playbook(
            trigger={
                "type": "on_demand",
                "match_patterns": ["AI News"],
            },
        )
        service._playbooks = {"test.example": playbook}

        result = service.match_playbook("give me ai news please")
        assert result is not None


class TestUpstreamContextResolution:
    def test_resolve_context_references(self):
        service = PlaybookService(agent_registry={})
        step = PlaybookSchema(
            playbook_name="test.ctx",
            description="Test context",
            project="Test Project",
            objective={
                "statement": "T", "category": "t",
                "owner": "t", "priority": "low",
            },
            steps=[
                {"id": "step-a", "capability": "test.agent"},
                {
                    "id": "step-b", "capability": "test.agent",
                    "depends_on": ["step-a"],
                    "input": {
                        "articles": "@context.raw_articles",
                        "static": "hello",
                    },
                },
            ],
        ).steps[1]

        completed_outcomes = {
            "step-a": {"raw_articles": ["article1", "article2"]},
        }

        result = service.resolve_upstream_context(
            step, completed_outcomes, {"base_key": "base_value"},
        )

        assert result["base_key"] == "base_value"
        assert result["raw_articles"] == ["article1", "article2"]
        assert result["_step_input"]["articles"] == ["article1", "article2"]
        assert result["_step_input"]["static"] == "hello"

    def test_unresolved_reference_raises(self):
        """Unresolved @context.* references raise ValueError (P0.3)."""
        service = PlaybookService(agent_registry={})
        step = PlaybookSchema(
            playbook_name="test.unresolved",
            description="Test",
            project="Test Project",
            objective={
                "statement": "T", "category": "t",
                "owner": "t", "priority": "low",
            },
            steps=[
                {
                    "id": "step-a", "capability": "test.agent",
                    "input": {"data": "@context.missing_key"},
                },
            ],
        ).steps[0]

        with pytest.raises(ValueError, match="unresolvable @context reference"):
            service.resolve_upstream_context(step, {}, {})


class TestPlaybookLoading:
    def test_load_from_directory(self, tmp_path):
        """Load playbooks from a tmp directory via config override."""
        playbooks_dir = tmp_path / "playbooks"
        playbooks_dir.mkdir()

        playbook_data = {
            "playbook_name": "test.loaded",
            "description": "Loaded from disk",
            "project": "Test Project",
            "objective": {
                "statement": "Test loading",
                "category": "testing",
                "owner": "test",
                "priority": "normal",
            },
            "steps": [
                {"id": "step-one", "capability": "test.agent"},
            ],
        }
        (playbooks_dir / "test.yaml").write_text(yaml.dump(playbook_data))

        service = PlaybookService(agent_registry={})
        # Override the project root and config for this test
        service._project_root = tmp_path

        from unittest.mock import MagicMock
        mock_config = MagicMock()
        mock_config.playbooks.playbooks_dir = "playbooks"
        mock_config.playbooks.max_steps_per_playbook = 20
        mock_config.playbooks.max_budget_usd = 100.0

        with patch(
            "modules.backend.services.playbook.get_app_config",
            return_value=mock_config,
        ):
            loaded = service.load_playbooks()

        assert "test.loaded" in loaded
        assert loaded["test.loaded"].description == "Loaded from disk"

    def test_list_playbooks_enabled_only(self):
        service = PlaybookService(agent_registry={})
        service._playbooks = {
            "enabled": _make_playbook(
                playbook_name="test.enabled", enabled=True,
            ),
            "disabled": _make_playbook(
                playbook_name="test.disabled", enabled=False,
            ),
        }

        enabled = service.list_playbooks(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].playbook_name == "test.enabled"

    def test_list_playbooks_all(self):
        service = PlaybookService(agent_registry={})
        service._playbooks = {
            "enabled": _make_playbook(
                playbook_name="test.enabled", enabled=True,
            ),
            "disabled": _make_playbook(
                playbook_name="test.disabled", enabled=False,
            ),
        }

        all_playbooks = service.list_playbooks(enabled_only=False)
        assert len(all_playbooks) == 2

    def test_get_playbook(self):
        service = PlaybookService(agent_registry={})
        playbook = _make_playbook()
        service._playbooks = {"test.example": playbook}

        result = service.get_playbook("test.example")
        assert result is not None
        assert result.playbook_name == "test.example"

    def test_get_playbook_not_found(self):
        service = PlaybookService(agent_registry={})
        service._playbooks = {}

        result = service.get_playbook("nonexistent")
        assert result is None
