"""Tests for TuiState — centralized TUI state management."""

from collections import deque

import pytest

from modules.clients.tui.services.state import TuiState


class TestTuiStateDefaults:
    """Verify initial state is sensible."""

    def test_initial_status_is_idle(self):
        state = TuiState()
        assert state.mission_status == "idle"

    def test_initial_project_is_none(self):
        state = TuiState()
        assert state.current_project_id is None
        assert state.current_project_name is None

    def test_initial_cost_is_zero(self):
        state = TuiState()
        assert state.total_cost_usd == 0.0
        assert state.budget_usd == 0.0
        assert state.total_input_tokens == 0
        assert state.total_output_tokens == 0

    def test_events_deque_has_maxlen(self):
        state = TuiState()
        assert isinstance(state.events, deque)
        assert state.events.maxlen == 500

    def test_notifications_deque_has_maxlen(self):
        state = TuiState()
        assert isinstance(state.notifications, deque)
        assert state.notifications.maxlen == 50


class TestTuiStateResetMission:
    """Verify reset_mission clears all mission-specific fields."""

    def test_reset_clears_status(self):
        state = TuiState()
        state.mission_status = "running"
        state.mission_id = "m-123"
        state.reset_mission()
        assert state.mission_status == "idle"
        assert state.mission_id is None

    def test_reset_clears_cost(self):
        state = TuiState()
        state.total_cost_usd = 5.0
        state.total_input_tokens = 10000
        state.total_output_tokens = 5000
        state.reset_mission()
        assert state.total_cost_usd == 0.0
        assert state.total_input_tokens == 0
        assert state.total_output_tokens == 0

    def test_reset_clears_agents(self):
        state = TuiState()
        state.active_agents = {"agent-a", "agent-b"}
        state.agent_output = {"agent-a": "hello"}
        state.reset_mission()
        assert state.active_agents == set()
        assert state.agent_output == {}

    def test_reset_clears_gate(self):
        state = TuiState()
        state.pending_gate = "something"  # type: ignore[assignment]
        state.gate_history = [{"action": "continue"}]
        state.reset_mission()
        assert state.pending_gate is None
        assert state.gate_history == []

    def test_reset_preserves_project(self):
        """reset_mission must NOT touch project or roster state."""
        state = TuiState()
        state.current_project_id = "proj-1"
        state.current_project_name = "My Project"
        state.current_session_id = "sess-1"
        state.reset_mission()
        assert state.current_project_id == "proj-1"
        assert state.current_project_name == "My Project"
        # session_id is also preserved (belongs to the session, not mission)
        assert state.current_session_id == "sess-1"

    def test_reset_preserves_budget(self):
        """Budget is a user setting, not mission state."""
        state = TuiState()
        state.budget_usd = 25.0
        state.total_cost_usd = 12.0
        state.reset_mission()
        # budget stays, cost resets
        assert state.budget_usd == 25.0
        assert state.total_cost_usd == 0.0


class TestTuiStateProperties:
    """Verify computed properties."""

    def test_tasks_completed_empty(self):
        state = TuiState()
        assert state.tasks_completed == 0

    def test_tasks_completed_with_results(self):
        state = TuiState()
        state.task_results = {"t1": "done", "t2": "done"}  # type: ignore[dict-item]
        assert state.tasks_completed == 2

    def test_tasks_total_no_plan(self):
        state = TuiState()
        assert state.tasks_total == 0

    def test_budget_fraction_no_budget(self):
        state = TuiState()
        state.total_cost_usd = 5.0
        assert state.budget_fraction == 0.0

    def test_budget_fraction_normal(self):
        state = TuiState()
        state.budget_usd = 10.0
        state.total_cost_usd = 3.0
        assert state.budget_fraction == pytest.approx(0.3)

    def test_budget_fraction_capped_at_one(self):
        state = TuiState()
        state.budget_usd = 10.0
        state.total_cost_usd = 15.0
        assert state.budget_fraction == 1.0
