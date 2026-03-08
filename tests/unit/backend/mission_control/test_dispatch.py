"""Tests for the dispatch loop — topological sort, parallel execution, verification."""

import asyncio

import pytest

from modules.backend.agents.mission_control.dispatch import (
    dispatch,
    resolve_upstream_inputs,
    topological_sort,
    verify_task,
)
from modules.backend.agents.mission_control.outcome import MissionStatus, TaskStatus
from modules.backend.agents.mission_control.roster import (
    Roster,
    RosterAgentEntry,
    RosterConstraintsSchema,
    RosterInterfaceSchema,
    RosterModelSchema,
)
from modules.backend.schemas.task_plan import TaskPlan


def _entry(name: str) -> RosterAgentEntry:
    return RosterAgentEntry(
        agent_name=name,
        agent_version="1.0.0",
        description=f"Agent {name}",
        model=RosterModelSchema(name="test-model"),
        interface=RosterInterfaceSchema(
            input={"query": "string"},
            output={"result": "string", "confidence": "float"},
        ),
        constraints=RosterConstraintsSchema(
            timeout_seconds=10,
            cost_ceiling_usd=1.0,
            retry_budget=1,
        ),
    )


def _plan(tasks: list[dict], **kw) -> TaskPlan:
    return TaskPlan.model_validate({
        "version": "1.0.0",
        "mission_id": "test",
        "summary": "Test",
        "estimated_cost_usd": 1.0,
        "estimated_duration_seconds": 60,
        "tasks": tasks,
        **kw,
    })


def _task(
    task_id: str, agent: str = "agent_a", deps: list[str] | None = None,
) -> dict:
    return {
        "task_id": task_id,
        "agent": agent,
        "agent_version": "1.0.0",
        "description": "Test",
        "instructions": "Do it",
        "dependencies": deps or [],
        "verification": {
            "tier_1": {
                "schema_validation": True,
                "required_output_fields": ["result"],
            },
            "tier_2": {"deterministic_checks": []},
            "tier_3": {"requires_ai_evaluation": False},
        },
    }


class TestTopologicalSort:
    def test_no_deps_single_layer(self):
        plan = _plan([_task("a"), _task("b")])
        layers = topological_sort(plan)
        assert len(layers) == 1
        assert set(layers[0]) == {"a", "b"}

    def test_linear_chain(self):
        plan = _plan([
            _task("a"),
            _task("b", deps=["a"]),
            _task("c", deps=["b"]),
        ])
        layers = topological_sort(plan)
        assert len(layers) == 3
        assert layers[0] == ["a"]
        assert layers[1] == ["b"]
        assert layers[2] == ["c"]

    def test_diamond_pattern(self):
        plan = _plan([
            _task("a"),
            _task("b", deps=["a"]),
            _task("c", deps=["a"]),
            _task("d", deps=["b", "c"]),
        ])
        layers = topological_sort(plan)
        assert len(layers) == 3
        assert layers[0] == ["a"]
        assert set(layers[1]) == {"b", "c"}
        assert layers[2] == ["d"]


class TestResolveUpstreamInputs:
    def test_static_only(self):
        task = _plan([{
            **_task("t1"),
            "inputs": {"static": {"key": "value"}, "from_upstream": {}},
        }]).tasks[0]
        result = resolve_upstream_inputs(task, {})
        assert result == {"key": "value"}

    def test_upstream_resolution(self):
        task = _plan([{
            **_task("t2", deps=["t1"]),
            "inputs": {
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "result"},
                },
            },
        }]).tasks[0]
        completed = {"t1": {"result": "hello", "confidence": 0.9}}
        result = resolve_upstream_inputs(task, completed)
        assert result["data"] == "hello"

    def test_missing_upstream_raises(self):
        task = _plan([{
            **_task("t2", deps=["t1"]),
            "inputs": {
                "static": {},
                "from_upstream": {
                    "data": {"source_task": "t1", "source_field": "result"},
                },
            },
        }]).tasks[0]
        with pytest.raises(KeyError):
            resolve_upstream_inputs(task, {})


class TestVerifyTask:
    @pytest.mark.asyncio
    async def test_all_fields_present_passes(self):
        task = _plan([_task("t1")]).tasks[0]
        entry = _entry("agent_a")
        output = {"result": "hello", "confidence": 0.9}
        result = await verify_task(task=task, output=output, roster_entry=entry)
        assert result.passed is True
        assert result.tier_1.status.value == "pass"

    @pytest.mark.asyncio
    async def test_missing_field_fails(self):
        task = _plan([_task("t1")]).tasks[0]
        entry = _entry("agent_a")
        output = {"result": "hello"}  # missing 'confidence'
        result = await verify_task(task=task, output=output, roster_entry=entry)
        assert result.passed is False
        assert "confidence" in result.tier_1.details


class TestDispatch:
    @pytest.mark.asyncio
    async def test_simple_plan_succeeds(self):
        """Single task, agent returns valid output."""
        plan = _plan([_task("t1")])
        roster = Roster(agents=[_entry("agent_a")])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            return {"result": "done", "confidence": 0.95, "_meta": {
                "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.01,
            }}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.SUCCESS
        assert len(outcome.task_results) == 1
        assert outcome.task_results[0].status == TaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """Two independent tasks run concurrently."""
        plan = _plan([_task("a"), _task("b")])
        roster = Roster(agents=[_entry("agent_a")])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            await asyncio.sleep(0.01)
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.SUCCESS
        assert len(outcome.task_results) == 2

    @pytest.mark.asyncio
    async def test_upstream_resolution_in_dispatch(self):
        """Task B receives output from Task A via from_upstream."""
        tasks = [
            _task("a"),
            {
                **_task("b", deps=["a"]),
                "inputs": {
                    "static": {},
                    "from_upstream": {
                        "data": {"source_task": "a", "source_field": "result"},
                    },
                },
            },
        ]
        plan = _plan(tasks)
        roster = Roster(agents=[_entry("agent_a")])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            return {"result": "from_a", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_tier1_failure_triggers_retry(self):
        """Agent output missing required fields triggers retry."""
        plan = _plan([_task("t1")])
        roster = Roster(agents=[_entry("agent_a")])
        call_count = 0

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"result": "done", "_meta": {}}  # missing confidence
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.SUCCESS
        assert outcome.task_results[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_timeout_handled(self):
        """Agent exceeding timeout is handled gracefully."""
        plan = _plan([_task("t1")])
        entry = _entry("agent_a")
        entry.constraints.timeout_seconds = 1
        entry.constraints.retry_budget = 0
        roster = Roster(agents=[entry])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            await asyncio.sleep(10)
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.task_results[0].status == TaskStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_partial_success(self):
        """Partial success when threshold met and critical path succeeded."""
        tasks = [
            {**_task("a"), "instructions": "task_a"},
            {**_task("b"), "instructions": "task_b"},
        ]
        plan = _plan(
            tasks,
            execution_hints={"min_success_threshold": 0.5, "critical_path": ["a"]},
        )
        roster = Roster(agents=[_entry("agent_a")])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            if instructions == "task_b":
                raise RuntimeError("Agent b failed")
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.PARTIAL

    @pytest.mark.asyncio
    async def test_mission_failure_on_critical_path_failure(self):
        """Mission fails when critical path task fails."""
        tasks = [
            {**_task("a"), "instructions": "task_a"},
            {**_task("b"), "instructions": "task_b"},
        ]
        plan = _plan(
            tasks,
            execution_hints={"min_success_threshold": 0.5, "critical_path": ["a"]},
        )
        entry = _entry("agent_a")
        entry.constraints.retry_budget = 0
        roster = Roster(agents=[entry])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            if instructions == "task_a":
                raise RuntimeError("Agent a (critical) failed")
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.FAILED

    @pytest.mark.asyncio
    async def test_cost_aggregation(self):
        """Total cost is aggregated from all tasks."""
        plan = _plan([_task("a"), _task("b")])
        roster = Roster(agents=[_entry("agent_a")])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            return {
                "result": "done", "confidence": 0.9,
                "_meta": {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.05},
            }

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.total_cost_usd == pytest.approx(0.1, abs=0.001)
        assert outcome.total_tokens.input == 200
        assert outcome.total_tokens.output == 100
