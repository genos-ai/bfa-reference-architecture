"""Tests for EventStreamWidget and event summarization."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from modules.clients.tui.widgets.event_stream import (
    EventStreamWidget,
    _summarize_event,
)


# ── _summarize_event (pure function) ──────────────────────────────────

class TestSummarizeEvent:
    def _make_event(self, event_type: str, **attrs: object) -> MagicMock:
        ev = MagicMock()
        ev.event_type = event_type
        ev.timestamp = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
        for k, v in attrs.items():
            setattr(ev, k, v)
        return ev

    def test_thinking_started(self):
        ev = self._make_event("agent.thinking.started", agent_id="code.qa")
        assert "code.qa" in _summarize_event(ev)
        assert "thinking" in _summarize_event(ev)

    def test_response_complete(self):
        ev = self._make_event(
            "agent.response.complete", agent_id="planner", cost_usd=0.042
        )
        summary = _summarize_event(ev)
        assert "planner" in summary
        assert "0.042" in summary

    def test_tool_called(self):
        ev = self._make_event("agent.tool.called", tool_name="code_search")
        assert "code_search" in _summarize_event(ev)

    def test_tool_returned(self):
        ev = self._make_event(
            "agent.tool.returned", tool_name="code_search", status="success"
        )
        summary = _summarize_event(ev)
        assert "code_search" in summary
        assert "success" in summary

    def test_cost_updated(self):
        ev = self._make_event("session.cost.updated", cumulative_cost_usd=1.2345)
        assert "1.2345" in _summarize_event(ev)

    def test_plan_created(self):
        ev = self._make_event("plan.created", step_count=5)
        assert "5" in _summarize_event(ev)
        assert "tasks" in _summarize_event(ev)

    def test_plan_step_started(self):
        ev = self._make_event(
            "plan.step.started", assigned_agent="code.qa", step_name="Analyze code"
        )
        summary = _summarize_event(ev)
        assert "code.qa" in summary

    def test_chunk_skipped_in_stream(self):
        """Response chunks should be summarized but filtered from the stream widget."""
        ev = self._make_event("agent.response.chunk", content="Hello world")
        summary = _summarize_event(ev)
        assert "Hello" in summary

    def test_unknown_event_type(self):
        ev = self._make_event("custom.something.happened")
        summary = _summarize_event(ev)
        assert "happened" in summary

    def test_approval_requested(self):
        ev = self._make_event("agent.approval.requested", action="pre_dispatch")
        assert "gate" in _summarize_event(ev)


# ── EventStreamWidget (Textual Pilot) ─────────────────────────────────

class TestEventStreamWidget:
    @pytest.mark.asyncio
    async def test_mounts_with_heading(self):
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield EventStreamWidget(id="event-stream")

        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one("#event-stream", EventStreamWidget)
            assert widget is not None

    @pytest.mark.asyncio
    async def test_add_event_creates_entry(self):
        from textual.app import App, ComposeResult
        from textual.containers import VerticalScroll

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield EventStreamWidget(id="event-stream")

        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one("#event-stream", EventStreamWidget)
            ev = MagicMock()
            ev.event_type = "plan.created"
            ev.timestamp = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
            ev.step_count = 3
            widget.add_event(ev)
            await pilot.pause()
            scroll = widget.query_one("#event-scroll", VerticalScroll)
            assert len(scroll.children) == 1

    @pytest.mark.asyncio
    async def test_chunk_events_filtered(self):
        """Response chunks should NOT appear in the event stream."""
        from textual.app import App, ComposeResult
        from textual.containers import VerticalScroll

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield EventStreamWidget(id="event-stream")

        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one("#event-stream", EventStreamWidget)
            ev = MagicMock()
            ev.event_type = "agent.response.chunk"
            ev.timestamp = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
            ev.content = "Hello"
            widget.add_event(ev)
            await pilot.pause()
            scroll = widget.query_one("#event-scroll", VerticalScroll)
            assert len(scroll.children) == 0
