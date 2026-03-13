"""Tests for agent roster loading and validation."""

import pytest

from modules.backend.agents.mission_control.roster import (
    PLANNING_AGENT_NAME,
    VERIFICATION_AGENT_NAME,
    Roster,
    RosterAgentEntry,
    RosterInterfaceSchema,
    RosterModelSchema,
    load_roster,
)


def _make_entry(name: str = "test.agent", version: str = "1.0.0") -> RosterAgentEntry:
    """Create a minimal roster entry for testing."""
    return RosterAgentEntry(
        agent_name=name,
        agent_version=version,
        description="Test agent",
        model=RosterModelSchema(name="test-model"),
        interface=RosterInterfaceSchema(
            input={"query": "string"},
            output={"result": "string", "confidence": "float"},
        ),
    )


class TestRoster:
    def test_get_agent_by_name_and_version(self):
        roster = Roster(agents=[_make_entry()])
        assert roster.get_agent("test.agent", "1.0.0") is not None
        assert roster.get_agent("test.agent", "2.0.0") is None
        assert roster.get_agent("nonexistent", "1.0.0") is None

    def test_get_agent_by_name_only(self):
        roster = Roster(agents=[_make_entry()])
        assert roster.get_agent_by_name("test.agent") is not None
        assert roster.get_agent_by_name("nonexistent") is None

    def test_agent_names(self):
        roster = Roster(agents=[_make_entry("a"), _make_entry("b")])
        assert roster.agent_names == ["a", "b"]

    def test_extra_fields_rejected(self):
        with pytest.raises(Exception):
            RosterAgentEntry(
                agent_name="test",
                agent_version="1.0.0",
                description="Test",
                model=RosterModelSchema(name="test"),
                interface=RosterInterfaceSchema(),
                unknown_field="bad",
            )


class TestLoadRoster:
    def test_load_default_roster(self):
        roster = load_roster("default")
        assert len(roster.agents) >= 4  # 2 worker + planning + verification

    def test_planning_agent_loaded_from_yaml(self):
        roster = load_roster("default")
        planning = roster.get_agent_by_name(PLANNING_AGENT_NAME)
        assert planning is not None

    def test_verification_agent_loaded_from_yaml(self):
        roster = load_roster("default")
        verification = roster.get_agent_by_name(VERIFICATION_AGENT_NAME)
        assert verification is not None

    def test_worker_agents_present(self):
        roster = load_roster("default")
        assert roster.get_agent_by_name("code.quality.agent") is not None
        assert roster.get_agent_by_name("system.health.agent") is not None

    def test_missing_roster_raises(self):
        with pytest.raises(FileNotFoundError):
            load_roster("nonexistent_roster")
