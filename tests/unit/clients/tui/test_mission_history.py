"""Tests for MissionHistoryScreen."""

import pytest

from modules.clients.tui.screens.mission_history import (
    MissionHistoryScreen,
    MissionRow,
)
from modules.clients.tui.widgets.context_viewer import ContextViewer


def _make_missions(n: int = 3) -> list[dict]:
    return [
        {
            "id": f"m-{i}",
            "mission_id": f"mission-{i}",
            "objective": f"Do task {i}",
            "status": "completed" if i % 2 == 0 else "failed",
            "total_cost_usd": 0.5 * (i + 1),
            "roster_name": "default",
            "created_at": f"2026-03-{18 - i}T12:00:00",
        }
        for i in range(n)
    ]


class TestMissionHistoryScreen:
    @pytest.mark.asyncio
    async def test_mounts_with_missions(self):
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        missions = _make_missions(3)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

        async with TestApp().run_test() as pilot:
            screen = MissionHistoryScreen(missions)
            pilot.app.push_screen(screen)
            await pilot.pause()

            rows = pilot.app.screen.query(MissionRow)
            assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_mounts_with_empty_list(self):
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

        async with TestApp().run_test() as pilot:
            screen = MissionHistoryScreen([])
            pilot.app.push_screen(screen)
            await pilot.pause()

            rows = pilot.app.screen.query(MissionRow)
            assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_has_context_viewer(self):
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

        async with TestApp().run_test() as pilot:
            screen = MissionHistoryScreen(_make_missions(1))
            pilot.app.push_screen(screen)
            await pilot.pause()

            viewer = pilot.app.screen.query_one(
                "#history-context-viewer", ContextViewer
            )
            assert viewer is not None

    @pytest.mark.asyncio
    async def test_escape_dismisses(self):
        from textual.app import App, ComposeResult
        from textual.containers import Vertical

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield Vertical()

        async with TestApp().run_test() as pilot:
            screen = MissionHistoryScreen(_make_missions(1))
            pilot.app.push_screen(screen)
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()
            # Screen should be dismissed — default screen should be active
            assert not isinstance(pilot.app.screen, MissionHistoryScreen)


class TestMissionRow:
    def test_stores_mission_data(self):
        m = {"id": "1", "objective": "test", "status": "completed", "total_cost_usd": 0.5}
        row = MissionRow(m)
        assert row.mission_data == m
