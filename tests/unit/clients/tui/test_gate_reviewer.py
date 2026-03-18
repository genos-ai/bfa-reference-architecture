"""Tests for TuiGateReviewer — Future-based gate bridge."""

import asyncio

import pytest
from unittest.mock import MagicMock

from modules.backend.agents.mission_control.gate import (
    GateAction,
    GateContext,
    GateDecision,
)
from modules.clients.tui.services.gate_reviewer import TuiGateReviewer


def _make_context(**overrides: object) -> GateContext:
    defaults = dict(
        gate_type="pre_dispatch",
        mission_id="test-mission",
        layer_index=0,
        total_layers=2,
        pending_tasks=[],
        total_cost_usd=0.0,
        budget_usd=10.0,
    )
    defaults.update(overrides)
    return GateContext(**defaults)


class TestTuiGateReviewer:
    def test_initial_state(self):
        app = MagicMock()
        reviewer = TuiGateReviewer(app)
        assert not reviewer.is_waiting
        assert reviewer._pending is None

    @pytest.mark.asyncio
    async def test_review_posts_message_and_awaits(self):
        """review() should post GateReviewRequested and block until resolved."""
        app = MagicMock()
        reviewer = TuiGateReviewer(app)
        ctx = _make_context()

        # Start review in background, resolve it immediately
        async def resolve_soon():
            await asyncio.sleep(0.01)
            assert reviewer.is_waiting
            reviewer.resolve(GateDecision(
                action=GateAction.CONTINUE,
                reviewer="test",
            ))

        task = asyncio.create_task(resolve_soon())
        decision = await reviewer.review(ctx)
        await task

        assert decision.action == GateAction.CONTINUE
        assert not reviewer.is_waiting
        # Should have posted a message
        app.post_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_review_returns_abort_decision(self):
        """review() should return whatever decision is resolved."""
        app = MagicMock()
        reviewer = TuiGateReviewer(app)
        ctx = _make_context()

        async def resolve_abort():
            await asyncio.sleep(0.01)
            reviewer.resolve(GateDecision(
                action=GateAction.ABORT,
                reason="Too expensive",
                reviewer="human:tui",
            ))

        task = asyncio.create_task(resolve_abort())
        decision = await reviewer.review(ctx)
        await task

        assert decision.action == GateAction.ABORT
        assert decision.reason == "Too expensive"

    @pytest.mark.asyncio
    async def test_resolve_when_not_waiting_is_safe(self):
        """resolve() should be a no-op when no review is pending."""
        app = MagicMock()
        reviewer = TuiGateReviewer(app)
        # Should not raise
        reviewer.resolve(GateDecision(
            action=GateAction.CONTINUE,
            reviewer="test",
        ))

    @pytest.mark.asyncio
    async def test_pending_cleared_after_review(self):
        """After review() returns, _pending should be None."""
        app = MagicMock()
        reviewer = TuiGateReviewer(app)
        ctx = _make_context()

        async def resolve_soon():
            await asyncio.sleep(0.01)
            reviewer.resolve(GateDecision(
                action=GateAction.SKIP,
                reviewer="test",
            ))

        task = asyncio.create_task(resolve_soon())
        await reviewer.review(ctx)
        await task

        assert reviewer._pending is None
        assert not reviewer.is_waiting
