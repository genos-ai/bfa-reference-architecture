"""Tests for PlaybookProgressWidget."""

import pytest

from modules.clients.tui.widgets.playbook_progress import (
    PlaybookProgressWidget,
    StepNode,
)


def _make_waves() -> list[list[str]]:
    return [["lint", "test"], ["merge"]]


class TestPlaybookProgressWidget:
    @pytest.mark.asyncio
    async def test_mounts_with_header(self):
        from textual.app import App, ComposeResult
        from textual.containers import VerticalScroll

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield PlaybookProgressWidget(id="playbook-widget")

        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one("#playbook-widget", PlaybookProgressWidget)
            assert widget is not None
            assert widget.query_one("#wave-scroll", VerticalScroll)
            assert widget.query_one("#playbook-title")

    @pytest.mark.asyncio
    async def test_load_playbook_renders_waves(self):
        from textual.app import App, ComposeResult
        from textual.containers import VerticalScroll

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield PlaybookProgressWidget(id="playbook-widget")

        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one("#playbook-widget", PlaybookProgressWidget)
            widget.load_playbook("my-playbook", _make_waves(), budget=5.0)
            await pilot.pause()

            scroll = widget.query_one("#wave-scroll", VerticalScroll)
            # 2 wave headings + 3 step nodes = 5 children
            assert len(scroll.children) == 5

    @pytest.mark.asyncio
    async def test_header_shows_playbook_name(self):
        from textual.app import App, ComposeResult
        from textual.widgets import Label

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield PlaybookProgressWidget(id="playbook-widget")

        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one("#playbook-widget", PlaybookProgressWidget)
            widget.load_playbook("deploy-prod", _make_waves())
            await pilot.pause()

            title = widget.query_one("#playbook-title", Label)
            assert "deploy-prod" in str(title.render())

    @pytest.mark.asyncio
    async def test_update_step_status(self):
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield PlaybookProgressWidget(id="playbook-widget")

        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one("#playbook-widget", PlaybookProgressWidget)
            widget.load_playbook("test-pb", _make_waves())
            await pilot.pause()

            widget.update_step("lint", status="running")
            await pilot.pause()
            assert widget._step_status["lint"] == "running"

            widget.update_step("lint", status="success", cost=0.05)
            await pilot.pause()
            assert widget._step_status["lint"] == "success"
            assert widget._step_cost["lint"] == 0.05

    @pytest.mark.asyncio
    async def test_set_completed(self):
        from textual.app import App, ComposeResult
        from textual.widgets import Label

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield PlaybookProgressWidget(id="playbook-widget")

        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one("#playbook-widget", PlaybookProgressWidget)
            widget.load_playbook("test-pb", _make_waves())
            widget.set_completed(total_cost=1.5, summary="All done")
            await pilot.pause()

            title = widget.query_one("#playbook-title", Label)
            rendered = str(title.render())
            assert "Complete" in rendered or "1.5" in rendered

    @pytest.mark.asyncio
    async def test_set_failed(self):
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield PlaybookProgressWidget(id="playbook-widget")

        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one("#playbook-widget", PlaybookProgressWidget)
            widget.load_playbook("test-pb", _make_waves())
            widget.set_failed(error="Timeout", failed_step="test")
            await pilot.pause()

            assert widget._step_status["test"] == "failed"

    @pytest.mark.asyncio
    async def test_total_cost_tracks_steps(self):
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield PlaybookProgressWidget(id="playbook-widget")

        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one("#playbook-widget", PlaybookProgressWidget)
            widget.load_playbook("test-pb", _make_waves())
            widget.update_step("lint", cost=0.1)
            widget.update_step("test", cost=0.2)
            assert abs(widget._total_cost - 0.3) < 0.001
