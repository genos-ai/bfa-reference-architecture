"""Tests for TUI widgets using Textual's testing framework."""

import pytest

from modules.clients.tui.widgets.cost_bar import CostBar, _fmt_tokens


# ── _fmt_tokens (pure function) ──────────────────────────────────────

class TestFmtTokens:
    @pytest.mark.parametrize(
        "n, expected",
        [
            (0, "0"),
            (999, "999"),
            (1000, "1.0k"),
            (1500, "1.5k"),
            (10000, "10.0k"),
            (123456, "123.5k"),
        ],
    )
    def test_formatting(self, n, expected):
        assert _fmt_tokens(n) == expected


# ── CostBar (Textual Pilot) ─────────────────────────────────────────

class TestCostBarWidget:
    @pytest.mark.asyncio
    async def test_cost_bar_mounts_with_defaults(self):
        """CostBar should mount and show default labels."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield CostBar(id="cost-bar")

        async with TestApp().run_test() as pilot:
            bar = pilot.app.query_one("#cost-bar", CostBar)
            assert bar.cost_usd == 0.0
            assert bar.budget_usd == 0.0
            assert bar.connected is True

    @pytest.mark.asyncio
    async def test_cost_bar_reactive_update(self):
        """Setting cost_usd should update the label."""
        from textual.app import App, ComposeResult
        from textual.widgets import Label

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield CostBar(id="cost-bar")

        async with TestApp().run_test() as pilot:
            bar = pilot.app.query_one("#cost-bar", CostBar)
            bar.cost_usd = 1.2345
            await pilot.pause()
            label = bar.query_one("#cost-label", Label)
            # Label should contain the formatted cost
            assert "1.2345" in str(label.render())

    @pytest.mark.asyncio
    async def test_cost_bar_token_update(self):
        """Setting token counts should update the token label."""
        from textual.app import App, ComposeResult
        from textual.widgets import Label

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield CostBar(id="cost-bar")

        async with TestApp().run_test() as pilot:
            bar = pilot.app.query_one("#cost-bar", CostBar)
            bar.input_tokens = 2500
            bar.output_tokens = 800
            await pilot.pause()
            label = bar.query_one("#token-label", Label)
            text = str(label.render())
            assert "2.5k" in text
            assert "800" in text

    @pytest.mark.asyncio
    async def test_cost_bar_gate_indicator(self):
        """Setting pending_gates > 0 should show the gate label."""
        from textual.app import App, ComposeResult
        from textual.widgets import Label

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield CostBar(id="cost-bar")

        async with TestApp().run_test() as pilot:
            bar = pilot.app.query_one("#cost-bar", CostBar)
            bar.pending_gates = 1
            await pilot.pause()
            label = bar.query_one("#gate-label", Label)
            assert "gate" in str(label.render()).lower()
