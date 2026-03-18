"""Tests for ContextViewer widget."""

import pytest

from modules.clients.tui.widgets.context_viewer import ContextViewer


def _make_detail() -> dict:
    return {
        "id": "mission-1",
        "objective": "Implement auth module",
        "status": "completed",
        "total_cost_usd": 1.234,
        "roster_name": "default",
        "created_at": "2026-03-18T12:00:00",
        "task_plan_json": '{"version":"1.0","tasks":[]}',
        "mission_outcome_json": None,
        "task_executions": [
            {
                "task_id": "task-1",
                "agent_name": "code.writer.agent",
                "status": "completed",
                "cost_usd": 0.5,
                "input_tokens": 1000,
                "output_tokens": 500,
            },
            {
                "task_id": "task-2",
                "agent_name": "code.quality.agent",
                "status": "failed",
                "cost_usd": 0.3,
                "input_tokens": 800,
                "output_tokens": 200,
            },
        ],
    }


class TestContextViewer:
    @pytest.mark.asyncio
    async def test_mounts_with_tabs(self):
        from textual.app import App, ComposeResult
        from textual.widgets import RichLog, TabbedContent

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ContextViewer(title="Test", id="cv")

        async with TestApp().run_test() as pilot:
            viewer = pilot.app.query_one("#cv", ContextViewer)
            assert viewer is not None
            assert viewer.query_one(TabbedContent)
            assert viewer.query_one("#context-overview", RichLog)
            assert viewer.query_one("#context-json", RichLog)
            assert viewer.query_one("#context-tasks", RichLog)

    @pytest.mark.asyncio
    async def test_load_mission_detail(self):
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ContextViewer(id="cv")

        async with TestApp().run_test() as pilot:
            viewer = pilot.app.query_one("#cv", ContextViewer)
            viewer.load_mission_detail(_make_detail())
            await pilot.pause()
            # Should not crash and data should be loaded

    @pytest.mark.asyncio
    async def test_load_json(self):
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ContextViewer(id="cv")

        async with TestApp().run_test() as pilot:
            viewer = pilot.app.query_one("#cv", ContextViewer)
            viewer.load_json("Test Data", {"key": "value"})
            await pilot.pause()
            # Should not crash

    @pytest.mark.asyncio
    async def test_clear(self):
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ContextViewer(id="cv")

        async with TestApp().run_test() as pilot:
            viewer = pilot.app.query_one("#cv", ContextViewer)
            viewer.load_mission_detail(_make_detail())
            viewer.clear()
            await pilot.pause()
            # Should not crash

    @pytest.mark.asyncio
    async def test_load_json_string(self):
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ContextViewer(id="cv")

        async with TestApp().run_test() as pilot:
            viewer = pilot.app.query_one("#cv", ContextViewer)
            viewer.load_json("Raw", '{"hello": "world"}')
            await pilot.pause()
