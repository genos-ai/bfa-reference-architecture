"""Tests for AgentDetailWidget."""

import pytest

from modules.clients.tui.widgets.agent_detail import AgentDetailWidget


class TestAgentDetailWidget:
    @pytest.mark.asyncio
    async def test_mounts_with_tabs(self):
        """AgentDetailWidget should mount with Output, Thinking, Tools tabs."""
        from textual.app import App, ComposeResult
        from textual.widgets import RichLog, TabbedContent

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentDetailWidget("code.quality.agent", id="agent-detail")

        async with TestApp().run_test() as pilot:
            detail = pilot.app.query_one("#agent-detail", AgentDetailWidget)
            assert detail.agent_name == "code.quality.agent"
            # Should have tabbed content with three tabs
            assert detail.query_one(TabbedContent)
            assert detail.query_one("#output-log", RichLog)
            assert detail.query_one("#thinking-log", RichLog)
            assert detail.query_one("#tool-log", RichLog)

    @pytest.mark.asyncio
    async def test_display_name_extraction(self):
        """Agent name 'code.quality.agent' should display as 'quality'."""
        detail = AgentDetailWidget("code.quality.agent")
        assert detail._display_name == "quality"

    @pytest.mark.asyncio
    async def test_display_name_simple(self):
        """Simple agent name should display as-is."""
        detail = AgentDetailWidget("planner")
        assert detail._display_name == "planner"

    @pytest.mark.asyncio
    async def test_append_output(self):
        """append_output should write content to the output log."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentDetailWidget("test-agent", id="agent-detail")

        async with TestApp().run_test() as pilot:
            detail = pilot.app.query_one("#agent-detail", AgentDetailWidget)
            detail.append_output("Hello ")
            detail.append_output("World")
            await pilot.pause()
            # The RichLog should have content (we can't easily inspect
            # RichLog contents, but we verify no crash)
            assert detail.query_one("#output-log")

    @pytest.mark.asyncio
    async def test_add_tool_call_and_result(self):
        """Tool call + result should be written to the tool log."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentDetailWidget("test-agent", id="agent-detail")

        async with TestApp().run_test() as pilot:
            detail = pilot.app.query_one("#agent-detail", AgentDetailWidget)
            detail.add_tool_call(
                tool_name="code_search",
                tool_args={"query": "def main"},
                tool_call_id="tc-1",
            )
            detail.add_tool_result(
                tool_name="code_search",
                status="success",
                result="Found 3 matches",
            )
            await pilot.pause()
            assert detail.query_one("#tool-log")

    @pytest.mark.asyncio
    async def test_clear_resets_all_logs(self):
        """clear() should reset all RichLog content."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentDetailWidget("test-agent", id="agent-detail")

        async with TestApp().run_test() as pilot:
            detail = pilot.app.query_one("#agent-detail", AgentDetailWidget)
            detail.append_output("some output")
            detail.add_tool_call(tool_name="test")
            detail.clear()
            await pilot.pause()
            # No crash on clear
            assert detail.query_one("#output-log")

    @pytest.mark.asyncio
    async def test_update_header(self):
        """update_header should update the label without crashing."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentDetailWidget("test-agent", id="agent-detail")

        async with TestApp().run_test() as pilot:
            detail = pilot.app.query_one("#agent-detail", AgentDetailWidget)
            detail.update_header(
                status="running", cost=0.05,
                input_tokens=1500, output_tokens=400,
            )
            await pilot.pause()
            assert detail.query_one("#agent-header-label")
