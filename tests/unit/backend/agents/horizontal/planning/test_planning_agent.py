"""Tests for the Planning Agent — JSON extraction and agent creation."""

import pytest

from modules.backend.agents.horizontal.planning.agent import (
    extract_task_plan_json,
)


class TestExtractTaskPlanJson:
    def test_valid_json_in_tags(self):
        text = 'Some thinking...\n<task_plan>\n{"version": "1.0.0"}\n</task_plan>'
        result = extract_task_plan_json(text)
        assert result == {"version": "1.0.0"}

    def test_json_with_whitespace(self):
        text = '<task_plan>\n  {\n    "version": "1.0.0"\n  }\n</task_plan>'
        result = extract_task_plan_json(text)
        assert result["version"] == "1.0.0"

    def test_missing_tags_raises(self):
        text = '{"version": "1.0.0"}'
        with pytest.raises(ValueError, match="does not contain <task_plan> tags"):
            extract_task_plan_json(text)

    def test_invalid_json_raises(self):
        text = "<task_plan>not json</task_plan>"
        with pytest.raises(ValueError, match="invalid JSON"):
            extract_task_plan_json(text)

    def test_empty_tags_raises(self):
        text = "<task_plan></task_plan>"
        with pytest.raises(ValueError):
            extract_task_plan_json(text)

    def test_complex_plan_json(self):
        plan_json = '''
        <task_plan>
        {
            "version": "1.0.0",
            "mission_id": "test-001",
            "summary": "Test mission",
            "estimated_cost_usd": 2.50,
            "estimated_duration_seconds": 120,
            "tasks": [
                {
                    "task_id": "t1",
                    "agent": "agent_a",
                    "agent_version": "1.0.0",
                    "description": "First task",
                    "instructions": "Do it"
                }
            ]
        }
        </task_plan>
        '''
        result = extract_task_plan_json(plan_json)
        assert result["mission_id"] == "test-001"
        assert len(result["tasks"]) == 1

    def test_text_around_tags(self):
        text = (
            "Let me think about this...\n\n"
            "Here is my plan:\n"
            '<task_plan>{"version": "1.0.0"}</task_plan>\n\n'
            "Done!"
        )
        result = extract_task_plan_json(text)
        assert result["version"] == "1.0.0"
