"""TUI gate reviewer — bridges dispatch gate calls to Textual modals.

When dispatch() calls `await gate.review(context)`:
1. Creates an asyncio.Future
2. Posts GateReviewRequested message to the Textual App
3. Awaits the Future (dispatch runs in a @work coroutine sharing the event loop)
4. GateReviewModal resolves the Future when the user decides
5. Returns GateDecision to dispatch
"""

from __future__ import annotations

import asyncio

from textual.app import App

from modules.backend.agents.mission_control.gate import (
    GateAction,
    GateContext,
    GateDecision,
    GateReviewer,
)
from modules.clients.tui.messages import GateReviewRequested


class TuiGateReviewer(GateReviewer):
    """GateReviewer implementation that pauses dispatch and shows a Textual modal."""

    def __init__(self, app: App) -> None:
        self._app = app
        self._pending: asyncio.Future[GateDecision] | None = None

    async def review(self, context: GateContext) -> GateDecision:
        """Post a gate request to the app and wait for user decision."""
        loop = asyncio.get_running_loop()
        self._pending = loop.create_future()
        self._app.post_message(GateReviewRequested(context=context))
        try:
            return await self._pending
        finally:
            self._pending = None

    def resolve(self, decision: GateDecision) -> None:
        """Called by the app when the user makes a gate decision."""
        if self._pending and not self._pending.done():
            self._pending.set_result(decision)

    @property
    def is_waiting(self) -> bool:
        """True if a gate review is pending user input."""
        return self._pending is not None and not self._pending.done()
