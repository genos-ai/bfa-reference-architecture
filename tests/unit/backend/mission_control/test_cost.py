"""
Unit Tests for mission_control/cost.py.

Tests exercise real config loading (model_pricing from mission_control.yaml).
"""

from modules.backend.agents.mission_control.cost import compute_cost_usd, estimate_cost


class TestComputeCostUsd:
    """Tests for compute_cost_usd()."""

    def test_zero_tokens(self):
        assert compute_cost_usd(0, 0, "anthropic:claude-haiku-4-5-20251001") == 0.0

    def test_known_model(self):
        cost = compute_cost_usd(1_000_000, 1_000_000, "anthropic:claude-haiku-4-5-20251001")
        assert cost > 0

    def test_unknown_model_uses_default(self):
        cost = compute_cost_usd(1_000_000, 1_000_000, "unknown:model")
        assert cost > 0

    def test_none_model_uses_default(self):
        cost = compute_cost_usd(1_000_000, 1_000_000, None)
        assert cost > 0

    def test_cost_scales_with_tokens(self):
        small = compute_cost_usd(1_000, 1_000)
        large = compute_cost_usd(1_000_000, 1_000_000)
        assert large > small

    def test_cost_precision(self):
        """Cost is rounded to 6 decimal places."""
        cost = compute_cost_usd(1, 1)
        decimals = str(cost).split(".")[-1] if "." in str(cost) else ""
        assert len(decimals) <= 6


class TestEstimateCost:
    """Tests for estimate_cost()."""

    def test_estimate_assumes_output_equals_input(self):
        """estimate_cost(N, model) == compute_cost_usd(N, N, model)."""
        estimated = estimate_cost(10_000, "anthropic:claude-haiku-4-5-20251001")
        computed = compute_cost_usd(10_000, 10_000, "anthropic:claude-haiku-4-5-20251001")
        assert estimated == computed

    def test_estimate_zero(self):
        assert estimate_cost(0) == 0.0
