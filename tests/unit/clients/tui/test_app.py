"""Tests for BfaTuiApp using Textual's Pilot testing framework.

These tests mock the ServiceBridge so no real DB is needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.clients.tui.app import BfaTuiApp
from modules.clients.tui.messages import (
    MissionStartRequested,
    ProjectCreated,
    ProjectSelected,
    SessionEventReceived,
)
from modules.clients.tui.widgets.agent_sidebar import AgentSidebar, MissionSummary
from modules.clients.tui.widgets.cost_bar import CostBar


# ── Helpers ───────────────────────────────────────────────────────────

def _mock_bridge():
    """Create a mock ServiceBridge with sensible defaults."""
    bridge = MagicMock()
    bridge.list_projects = AsyncMock(return_value=[])
    bridge.create_project = AsyncMock(return_value={"id": "p-new", "name": "Test"})
    bridge.run_mission = AsyncMock()
    bridge.load_roster = MagicMock()
    bridge.load_roster.return_value = MagicMock(agents=[])
    return bridge


# ── App mount tests ───────────────────────────────────────────────────

class TestAppMount:
    @pytest.mark.asyncio
    async def test_app_mounts_main_screen(self):
        """App should mount with all core widgets present."""
        app = BfaTuiApp()
        app.bridge = _mock_bridge()

        async with app.run_test() as pilot:
            await pilot.pause()  # wait for on_mount to push MainScreen + picker
            # Dismiss the project picker that opens on startup
            await pilot.press("escape")
            await pilot.pause()
            assert pilot.app.screen.query_one("#agent-sidebar", AgentSidebar)
            assert pilot.app.screen.query_one("#cost-bar", CostBar)
            assert pilot.app.screen.query_one("#mission-summary", MissionSummary)

    @pytest.mark.asyncio
    async def test_initial_state_is_idle(self):
        app = BfaTuiApp()
        app.bridge = _mock_bridge()

        async with app.run_test():
            assert app.state.mission_status == "idle"
            assert app.state.current_project_id is None


# ── Project handling ──────────────────────────────────────────────────

class TestProjectHandling:
    @pytest.mark.asyncio
    async def test_project_selected_updates_state(self):
        app = BfaTuiApp()
        app.bridge = _mock_bridge()

        async with app.run_test() as pilot:
            app.post_message(
                ProjectSelected(project_id="proj-1", project_name="Alpha")
            )
            await pilot.pause()
            assert app.state.current_project_id == "proj-1"
            assert app.state.current_project_name == "Alpha"

    @pytest.mark.asyncio
    async def test_project_created_calls_bridge(self):
        app = BfaTuiApp()
        app.bridge = _mock_bridge()

        async with app.run_test() as pilot:
            app.post_message(
                ProjectCreated(project_name="NewProj", description="My desc")
            )
            await pilot.pause()
            app.bridge.create_project.assert_called_once_with(
                name="NewProj", description="My desc"
            )
            assert app.state.current_project_id == "p-new"
            assert app.state.current_project_name == "Test"

    @pytest.mark.asyncio
    async def test_project_created_uses_fallback_description(self):
        app = BfaTuiApp()
        app.bridge = _mock_bridge()

        async with app.run_test() as pilot:
            app.post_message(ProjectCreated(project_name="Bare"))
            await pilot.pause()
            app.bridge.create_project.assert_called_once_with(
                name="Bare", description="Created from TUI"
            )


# ── Mission guards ────────────────────────────────────────────────────

class TestMissionGuards:
    @pytest.mark.asyncio
    async def test_mission_requires_project(self):
        """Starting a mission without a project should show a warning, not crash."""
        app = BfaTuiApp()
        app.bridge = _mock_bridge()

        async with app.run_test() as pilot:
            app.post_message(MissionStartRequested(brief="Do something"))
            await pilot.pause()
            # No project selected, mission should NOT start
            assert app.state.mission_status == "idle"
            app.bridge.run_mission.assert_not_called()

    @pytest.mark.asyncio
    async def test_mission_blocks_duplicate(self):
        """Cannot start a second mission while one is running."""
        app = BfaTuiApp()
        app.bridge = _mock_bridge()

        async with app.run_test() as pilot:
            app.state.current_project_id = "proj-1"
            app.state.mission_status = "running"
            app.post_message(MissionStartRequested(brief="Second mission"))
            await pilot.pause()
            app.bridge.run_mission.assert_not_called()


# ── Event routing ─────────────────────────────────────────────────────

class TestEventRouting:
    @pytest.mark.asyncio
    async def test_agent_thinking_started_adds_to_active(self):
        app = BfaTuiApp()
        app.bridge = _mock_bridge()

        async with app.run_test() as pilot:
            event = MagicMock()
            event.event_type = "agent.thinking.started"
            event.agent_id = "researcher"
            app.post_message(SessionEventReceived(event=event))
            await pilot.pause()
            assert "researcher" in app.state.active_agents

    @pytest.mark.asyncio
    async def test_agent_response_complete_removes_from_active(self):
        app = BfaTuiApp()
        app.bridge = _mock_bridge()

        async with app.run_test() as pilot:
            app.state.active_agents.add("researcher")

            event = MagicMock()
            event.event_type = "agent.response.complete"
            event.agent_id = "researcher"
            event.cost_usd = 0.05
            event.input_tokens = 1000
            event.output_tokens = 500
            app.post_message(SessionEventReceived(event=event))
            await pilot.pause()

            assert "researcher" not in app.state.active_agents
            assert app.state.total_input_tokens == 1000
            assert app.state.total_output_tokens == 500

    @pytest.mark.asyncio
    async def test_cost_updated_event(self):
        app = BfaTuiApp()
        app.bridge = _mock_bridge()

        async with app.run_test() as pilot:
            event = MagicMock()
            event.event_type = "session.cost.updated"
            event.cumulative_cost_usd = 2.5
            app.post_message(SessionEventReceived(event=event))
            await pilot.pause()
            assert app.state.total_cost_usd == 2.5

    @pytest.mark.asyncio
    async def test_events_appended_to_state(self):
        app = BfaTuiApp()
        app.bridge = _mock_bridge()

        async with app.run_test() as pilot:
            event = MagicMock()
            event.event_type = "plan.created"
            app.post_message(SessionEventReceived(event=event))
            await pilot.pause()
            assert len(app.state.events) == 1
            assert app.state.events[0] is event
