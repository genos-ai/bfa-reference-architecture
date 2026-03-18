"""Tests for shared display primitives."""

import pytest
from rich.panel import Panel
from rich.table import Table

from modules.clients.common.display import (
    DOTTED_ROWS,
    OUTPUT_FORMATS,
    SEVERITY_ORDER,
    build_table,
    cost_line,
    format_json_body,
    info_panel,
    primary_panel,
    severity_color,
    status_color,
    status_panel,
    styled_status,
    summary_table,
    thinking_panel,
)


# ── Constants ──────────────────────────────────────────────────────────


def test_output_formats():
    assert OUTPUT_FORMATS == ("human", "json", "jsonl")


def test_severity_order_keys():
    assert set(SEVERITY_ORDER.keys()) == {"critical", "error", "warning", "info"}
    assert SEVERITY_ORDER["critical"] < SEVERITY_ORDER["error"]
    assert SEVERITY_ORDER["error"] < SEVERITY_ORDER["warning"]
    assert SEVERITY_ORDER["warning"] < SEVERITY_ORDER["info"]


def test_dotted_rows_is_box():
    from rich import box

    assert isinstance(DOTTED_ROWS, box.Box)


# ── Status & severity colors ──────────────────────────────────────────


@pytest.mark.parametrize(
    "status, expected",
    [
        ("completed", "green"),
        ("failed", "red"),
        ("running", "yellow"),
        ("pending", "yellow"),
        ("unknown", "white"),
    ],
)
def test_status_color(status, expected):
    assert status_color(status) == expected


def test_status_color_with_enum():
    class FakeEnum:
        value = "completed"

    assert status_color(FakeEnum()) == "green"


@pytest.mark.parametrize(
    "status, expected_color",
    [
        ("completed", "green"),
        ("failed", "red"),
        ("unknown", "white"),
    ],
)
def test_styled_status(status, expected_color):
    result = styled_status(status)
    assert f"[{expected_color}]" in result
    assert status in result


def test_styled_status_with_enum():
    class FakeEnum:
        value = "failed"

    result = styled_status(FakeEnum())
    assert "[red]failed[/red]" == result


@pytest.mark.parametrize(
    "severity, expected",
    [
        ("critical", "bold red"),
        ("error", "red"),
        ("warning", "yellow"),
        ("info", "dim"),
        ("unknown", "white"),
        ("CRITICAL", "bold red"),  # case-insensitive
    ],
)
def test_severity_color(severity, expected):
    assert severity_color(severity) == expected


# ── Tables ─────────────────────────────────────────────────────────────


def test_build_table_returns_table():
    table = build_table(columns=[
        ("Name", {"style": "cyan"}),
        ("Value", {"ratio": 1}),
    ])
    assert isinstance(table, Table)
    assert len(table.columns) == 2


def test_build_table_with_title():
    table = build_table("My Title", columns=[
        ("Col", {}),
    ])
    assert table.title == "My Title"


def test_build_table_show_lines():
    table = build_table(columns=[("A", {})], show_lines=True)
    assert table.show_lines is True


def test_build_table_no_wrap_default():
    table = build_table(columns=[("A", {})])
    assert table.columns[0].no_wrap is True


def test_build_table_no_wrap_override():
    table = build_table(columns=[("A", {"no_wrap": False})])
    assert table.columns[0].no_wrap is False


def test_summary_table_structure():
    table = summary_table(
        agent_name="code.qa",
        session_id="abc-123",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.0042,
    )
    assert isinstance(table, Table)
    assert len(table.columns) == 2


# ── Panels ─────────────────────────────────────────────────────────────


def test_status_panel_returns_panel():
    panel = status_panel(content="OK", status="completed")
    assert isinstance(panel, Panel)


def test_status_panel_border_matches_status():
    panel = status_panel(content="OK", status="failed")
    assert panel.border_style == "red"


def test_info_panel():
    panel = info_panel(content="Some info", title="Details")
    assert isinstance(panel, Panel)
    assert panel.border_style == "dim"


def test_primary_panel():
    panel = primary_panel(content="Main content", title="Header")
    assert isinstance(panel, Panel)
    assert panel.border_style == "cyan"


def test_thinking_panel():
    panel = thinking_panel(content="The model is reasoning...")
    assert isinstance(panel, Panel)
    assert panel.border_style == "dim"


def test_panels_require_keyword_args():
    with pytest.raises(TypeError):
        status_panel("content", "status")  # type: ignore[misc]
    with pytest.raises(TypeError):
        info_panel("content")  # type: ignore[misc]
    with pytest.raises(TypeError):
        primary_panel("content")  # type: ignore[misc]
    with pytest.raises(TypeError):
        thinking_panel("content")  # type: ignore[misc]


# ── Formatters ─────────────────────────────────────────────────────────


def test_format_json_body_valid():
    from rich.syntax import Syntax

    result = format_json_body('{"key": "value"}')
    assert isinstance(result, Syntax)


def test_format_json_body_invalid():
    from rich.text import Text

    result = format_json_body("not json")
    assert isinstance(result, Text)


def test_cost_line_format():
    result = cost_line(input_tokens=1000, output_tokens=500, cost_usd=0.0042)
    assert "1,000" in result
    assert "500" in result
    assert "$0.0042" in result


def test_cost_line_requires_keyword_args():
    with pytest.raises(TypeError):
        cost_line(1000, 500, 0.0042)  # type: ignore[misc]
