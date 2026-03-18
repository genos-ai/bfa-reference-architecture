"""Tests for GateReviewModal widget."""

import pytest

from modules.backend.agents.mission_control.gate import (
    GateAction,
    GateContext,
    GateDecision,
)
from modules.clients.tui.widgets.gate_modal import (
    GateReviewModal,
    _GATE_ACTIONS,
    _GATE_TITLES,
    _render_context_body,
)


def _make_context(**overrides: object) -> GateContext:
    defaults = dict(
        gate_type="pre_dispatch",
        mission_id="test-mission",
        layer_index=0,
        total_layers=2,
        pending_tasks=[],
        total_cost_usd=0.5,
        budget_usd=10.0,
    )
    defaults.update(overrides)
    return GateContext(**defaults)


# ── Pure function tests ──────────────────────────────────────────────

class TestRenderContextBody:
    def test_shows_cost(self):
        ctx = _make_context(total_cost_usd=1.23, budget_usd=5.0)
        body = _render_context_body(ctx)
        assert "1.23" in body

    def test_shows_layer_info(self):
        ctx = _make_context(layer_index=1, total_layers=3)
        body = _render_context_body(ctx)
        assert "2 / 3" in body

    def test_shows_pending_tasks(self):
        ctx = _make_context(pending_tasks=[
            {"agent": "code.qa", "description": "Run quality check"},
            {"agent": "code.lint", "description": "Lint files"},
        ])
        body = _render_context_body(ctx)
        assert "code.qa" in body
        assert "Lint files" in body
        assert "2" in body

    def test_shows_task_id(self):
        ctx = _make_context(gate_type="post_task", task_id="task-42")
        body = _render_context_body(ctx)
        assert "task-42" in body

    def test_shows_ai_recommendation(self):
        ctx = _make_context(ai_recommendation="Continue — all tasks look good")
        body = _render_context_body(ctx)
        assert "Continue" in body
        assert "AI Recommendation" in body

    def test_shows_output_preview(self):
        ctx = _make_context(
            gate_type="post_task",
            task_output={"result": "analysis complete"},
        )
        body = _render_context_body(ctx)
        assert "analysis complete" in body

    def test_shows_verification(self):
        ctx = _make_context(
            gate_type="verification_failed",
            task_id="task-1",
            verification={
                "tier_1": {"passed": True},
                "tier_2": {"passed": False, "details": "Test failed"},
            },
        )
        body = _render_context_body(ctx)
        assert "tier_1" in body
        assert "tier_2" in body
        assert "Test failed" in body

    def test_shows_completed_tasks(self):
        ctx = _make_context(
            gate_type="post_layer",
            completed_tasks=[{"task_id": "t1"}, {"task_id": "t2"}],
        )
        body = _render_context_body(ctx)
        assert "2" in body

    def test_truncates_many_pending_tasks(self):
        tasks = [{"agent": f"a{i}", "description": f"task {i}"} for i in range(15)]
        ctx = _make_context(pending_tasks=tasks)
        body = _render_context_body(ctx)
        assert "5 more" in body


class TestGateConfig:
    def test_all_gate_types_have_titles(self):
        for gate_type in ("pre_dispatch", "pre_layer", "post_task",
                          "verification_failed", "post_layer"):
            assert gate_type in _GATE_TITLES

    def test_all_gate_types_have_actions(self):
        for gate_type in ("pre_dispatch", "pre_layer", "post_task",
                          "verification_failed", "post_layer"):
            assert gate_type in _GATE_ACTIONS
            assert len(_GATE_ACTIONS[gate_type]) >= 2

    def test_pre_dispatch_actions(self):
        actions = _GATE_ACTIONS["pre_dispatch"]
        assert GateAction.CONTINUE in actions
        assert GateAction.ABORT in actions

    def test_verification_failed_actions(self):
        actions = _GATE_ACTIONS["verification_failed"]
        assert GateAction.RETRY in actions
        assert GateAction.MODIFY in actions
        assert GateAction.ABORT in actions


# ── Modal widget tests (Textual Pilot) ───────────────────────────────

class TestGateReviewModal:
    @pytest.mark.asyncio
    async def test_mounts_with_header_and_body(self):
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        ctx = _make_context()

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

        async with TestApp().run_test() as pilot:
            modal = GateReviewModal(ctx)
            pilot.app.push_screen(modal)
            await pilot.pause()

            assert pilot.app.screen.query_one("#gate-header")
            assert pilot.app.screen.query_one("#gate-body")
            assert pilot.app.screen.query_one("#gate-actions")

    @pytest.mark.asyncio
    async def test_continue_via_keyboard(self):
        """Pressing 'c' should resolve with CONTINUE."""
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        ctx = _make_context()
        decisions: list[GateDecision] = []

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

            def on_gate_review_completed(self, msg):
                decisions.append(msg.decision)

        async with TestApp().run_test() as pilot:
            pilot.app.push_screen(GateReviewModal(ctx))
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert len(decisions) == 1
            assert decisions[0].action == GateAction.CONTINUE

    @pytest.mark.asyncio
    async def test_abort_via_keyboard(self):
        """Pressing 'a' should resolve with ABORT."""
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        ctx = _make_context()
        decisions: list[GateDecision] = []

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

            def on_gate_review_completed(self, msg):
                decisions.append(msg.decision)

        async with TestApp().run_test() as pilot:
            pilot.app.push_screen(GateReviewModal(ctx))
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()

            assert len(decisions) == 1
            assert decisions[0].action == GateAction.ABORT

    @pytest.mark.asyncio
    async def test_escape_defaults_to_continue(self):
        """Pressing Escape should resolve with CONTINUE."""
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        ctx = _make_context()
        decisions: list[GateDecision] = []

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

            def on_gate_review_completed(self, msg):
                decisions.append(msg.decision)

        async with TestApp().run_test() as pilot:
            pilot.app.push_screen(GateReviewModal(ctx))
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            assert len(decisions) == 1
            assert decisions[0].action == GateAction.CONTINUE

    @pytest.mark.asyncio
    async def test_skip_unavailable_falls_back(self):
        """Pressing 's' on pre_dispatch (no skip) should fallback to continue."""
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        ctx = _make_context(gate_type="pre_dispatch")
        decisions: list[GateDecision] = []

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

            def on_gate_review_completed(self, msg):
                decisions.append(msg.decision)

        async with TestApp().run_test() as pilot:
            pilot.app.push_screen(GateReviewModal(ctx))
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()

            assert len(decisions) == 1
            assert decisions[0].action == GateAction.CONTINUE

    @pytest.mark.asyncio
    async def test_post_task_has_retry_button(self):
        """post_task modal should have retry action available."""
        from textual.app import App, ComposeResult
        from textual.containers import Vertical
        from textual.widgets import Button

        ctx = _make_context(gate_type="post_task", task_id="t1")

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

        async with TestApp().run_test() as pilot:
            pilot.app.push_screen(GateReviewModal(ctx))
            await pilot.pause()

            buttons = pilot.app.screen.query(Button)
            button_ids = [b.id for b in buttons]
            assert "gate-btn-retry" in button_ids

    @pytest.mark.asyncio
    async def test_verification_failed_has_modify(self):
        """verification_failed modal should have modify action."""
        from textual.app import App, ComposeResult
        from textual.containers import Vertical
        from textual.widgets import Button

        ctx = _make_context(gate_type="verification_failed", task_id="t1")

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

        async with TestApp().run_test() as pilot:
            pilot.app.push_screen(GateReviewModal(ctx))
            await pilot.pause()

            buttons = pilot.app.screen.query(Button)
            button_ids = [b.id for b in buttons]
            assert "gate-btn-modify" in button_ids
            assert "gate-btn-retry" in button_ids

    @pytest.mark.asyncio
    async def test_retry_shows_input_first_press(self):
        """First 'r' press should show the retry input, not resolve."""
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        ctx = _make_context(gate_type="post_task", task_id="t1")
        decisions: list[GateDecision] = []

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

            def on_gate_review_completed(self, msg):
                decisions.append(msg.decision)

        async with TestApp().run_test() as pilot:
            pilot.app.push_screen(GateReviewModal(ctx))
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()

            # Should NOT have resolved yet — just showing the input
            assert len(decisions) == 0
            section = pilot.app.screen.query_one("#retry-section")
            assert "visible" in section.classes
