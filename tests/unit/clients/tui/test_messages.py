"""Tests for TUI Textual Message types."""

import pytest

from modules.clients.tui.messages import (
    AgentSelected,
    GateReviewCompleted,
    GateReviewRequested,
    MissionCancelRequested,
    MissionStartRequested,
    ProjectCreated,
    ProjectSelected,
    SessionEventReceived,
)


class TestSessionEventReceived:
    def test_stores_event(self):
        class FakeEvent:
            event_type = "agent.thinking.started"

        msg = SessionEventReceived(event=FakeEvent())
        assert msg.event.event_type == "agent.thinking.started"


class TestMissionStartRequested:
    def test_stores_brief(self):
        msg = MissionStartRequested(brief="Analyse the market")
        assert msg.brief == "Analyse the market"


class TestMissionCancelRequested:
    def test_can_instantiate(self):
        msg = MissionCancelRequested()
        assert isinstance(msg, MissionCancelRequested)


class TestProjectSelected:
    def test_stores_id_and_name(self):
        msg = ProjectSelected(project_id="p-1", project_name="Alpha")
        assert msg.project_id == "p-1"
        assert msg.project_name == "Alpha"


class TestProjectCreated:
    def test_stores_name_and_description(self):
        msg = ProjectCreated(project_name="Beta", description="A new project")
        assert msg.project_name == "Beta"
        assert msg.description == "A new project"

    def test_description_defaults_to_empty(self):
        msg = ProjectCreated(project_name="Gamma")
        assert msg.description == ""


class TestAgentSelected:
    def test_stores_agent_name(self):
        msg = AgentSelected(agent_name="modules.agents.researcher")
        assert msg.agent_name == "modules.agents.researcher"
