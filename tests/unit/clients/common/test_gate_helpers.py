"""Tests for shared gate display helpers."""

from unittest.mock import MagicMock

import pytest

from modules.clients.common.gate_helpers import (
    ACTION_COLORS,
    cost_color,
    gate_header,
    status_icon,
)


# ── cost_color ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cost, budget, expected",
    [
        (0.0, 1.0, "green"),
        (0.5, 1.0, "green"),
        (0.61, 1.0, "yellow"),
        (0.89, 1.0, "yellow"),
        (0.91, 1.0, "red"),
        (1.0, 1.0, "red"),
        (2.0, 1.0, "red"),
    ],
)
def test_cost_color_thresholds(cost, budget, expected):
    assert cost_color(cost, budget) == expected


def test_cost_color_zero_budget():
    assert cost_color(0.5, 0.0) == "white"


def test_cost_color_negative_budget():
    assert cost_color(0.5, -1.0) == "white"


# ── status_icon ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status, expected_substring",
    [
        ("success", "green"),
        ("failed", "red"),
        ("timeout", "yellow"),
        ("skipped", "dim"),
    ],
)
def test_status_icon_known(status, expected_substring):
    result = status_icon(status)
    assert f"[{expected_substring}]" in result


def test_status_icon_unknown_wraps_in_dim():
    result = status_icon("mystery")
    assert result == "[dim]mystery[/dim]"


# ── ACTION_COLORS ──────────────────────────────────────────────────────


def test_action_colors_keys():
    assert set(ACTION_COLORS.keys()) == {"continue", "skip", "retry", "abort", "modify"}


def test_action_colors_values_are_strings():
    for v in ACTION_COLORS.values():
        assert isinstance(v, str)


# ── gate_header ────────────────────────────────────────────────────────


def _make_ctx(*, mission_id="abc123def456ghij", total_cost=0.05, budget=1.0):
    ctx = MagicMock()
    ctx.mission_id = mission_id
    ctx.total_cost_usd = total_cost
    ctx.budget_usd = budget
    return ctx


def test_gate_header_contains_title():
    ctx = _make_ctx()
    result = gate_header(ctx, "Pre-Dispatch")
    assert "Pre-Dispatch" in result


def test_gate_header_contains_mission_id_truncated():
    ctx = _make_ctx(mission_id="a" * 32)
    result = gate_header(ctx, "Test")
    assert "a" * 16 in result
    assert "a" * 17 not in result


def test_gate_header_contains_cost():
    ctx = _make_ctx(total_cost=0.1234)
    result = gate_header(ctx, "Test")
    assert "$0.1234" in result


def test_gate_header_contains_budget():
    ctx = _make_ctx(budget=2.50)
    result = gate_header(ctx, "Test")
    assert "$2.50" in result


def test_gate_header_cost_color_green():
    ctx = _make_ctx(total_cost=0.1, budget=1.0)
    result = gate_header(ctx, "Test")
    assert "[green]" in result


def test_gate_header_cost_color_red():
    ctx = _make_ctx(total_cost=0.95, budget=1.0)
    result = gate_header(ctx, "Test")
    assert "[red]" in result
