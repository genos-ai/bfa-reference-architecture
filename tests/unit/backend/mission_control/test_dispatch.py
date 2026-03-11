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
        entry = _entry("agent_a")
        entry.constraints.retry_budget = 0
        roster = Roster(agents=[entry])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            if "task_b" in instructions:
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
            if "task_a" in instructions:
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

    @pytest.mark.asyncio
    async def test_timeout_retry_then_exhaustion(self):
        """Timeout retries up to retry_budget then reports TIMEOUT status."""
        plan = _plan([_task("t1")])
        entry = _entry("agent_a")
        entry.constraints.timeout_seconds = 1
        entry.constraints.retry_budget = 2
        roster = Roster(agents=[entry])
        call_count = 0

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(10)  # always timeout

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.task_results[0].status == TaskStatus.TIMEOUT
        assert call_count == 3  # initial + 2 retries
        assert len(outcome.task_results[0].retry_history) == 2

    @pytest.mark.asyncio
    async def test_execution_error_retries_then_fails(self):
        """Execution errors retry up to budget, then fail with history."""
        plan = _plan([_task("t1")])
        entry = _entry("agent_a")
        entry.constraints.retry_budget = 2
        roster = Roster(agents=[entry])
        call_count = 0

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            nonlocal call_count
            call_count += 1
            raise RuntimeError(f"Error on attempt {call_count}")

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.task_results[0].status == TaskStatus.FAILED
        assert call_count == 3  # initial + 2 retries
        assert len(outcome.task_results[0].retry_history) == 2
        assert "Error on attempt 1" in outcome.task_results[0].retry_history[0].failure_reason

    @pytest.mark.asyncio
    async def test_verification_failure_exhausts_retry_budget(self):
        """Verification failure retries, then fails with verification outcome."""
        plan = _plan([_task("t1")])
        entry = _entry("agent_a")
        entry.constraints.retry_budget = 1
        roster = Roster(agents=[entry])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            # Always missing 'confidence' — tier 1 always fails
            return {"result": "done", "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.task_results[0].status == TaskStatus.FAILED
        assert outcome.task_results[0].retry_count == 1
        assert outcome.task_results[0].verification_outcome is not None

    @pytest.mark.asyncio
    async def test_timeout_retry_then_success(self):
        """Task recovers after timeout on first attempt."""
        plan = _plan([_task("t1")])
        entry = _entry("agent_a")
        entry.constraints.timeout_seconds = 1
        entry.constraints.retry_budget = 1
        roster = Roster(agents=[entry])
        call_count = 0

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(10)  # timeout first attempt
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.task_results[0].status == TaskStatus.SUCCESS
        assert outcome.task_results[0].retry_count == 1
        assert len(outcome.task_results[0].retry_history) == 1

    @pytest.mark.asyncio
    async def test_agent_not_in_roster_fails_task(self):
        """Task referencing unknown agent is marked failed."""
        plan = _plan([_task("t1", agent="unknown_agent")])
        roster = Roster(agents=[_entry("agent_a")])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.FAILED
        assert outcome.task_results[0].status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_failed_upstream_skips_dependent(self):
        """Downstream task fails when upstream has no output."""
        tasks = [
            {**_task("a"), "instructions": "task_a"},
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
        entry = _entry("agent_a")
        entry.constraints.retry_budget = 0
        roster = Roster(agents=[entry])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            if "task_a" in instructions:
                raise RuntimeError("Agent a failed")
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.status == MissionStatus.FAILED
        # Both tasks should fail — a from error, b from missing upstream
        assert all(r.status == TaskStatus.FAILED for r in outcome.task_results)

    @pytest.mark.asyncio
    async def test_retry_records_feedback_in_history(self):
        """Retry history records failure reason and feedback."""
        plan = _plan([_task("t1")])
        entry = _entry("agent_a")
        entry.constraints.retry_budget = 1
        roster = Roster(agents=[entry])
        call_count = 0

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First attempt failed")
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.task_results[0].status == TaskStatus.SUCCESS
        assert call_count == 2
        assert len(outcome.task_results[0].retry_history) == 1
        history_entry = outcome.task_results[0].retry_history[0]
        assert "First attempt failed" in history_entry.failure_reason
        assert history_entry.feedback_provided is not None

    # ---- Pre-Phase 0 tests ----

    @pytest.mark.asyncio
    async def test_budget_enforcement_cancels_remaining_tasks(self):
        """P0.1: Budget exceeded after first layer cancels remaining tasks."""
        tasks = [
            _task("a"),
            _task("b", deps=["a"]),
        ]
        plan = _plan(tasks)
        roster = Roster(agents=[_entry("agent_a")])
        call_count = 0

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            nonlocal call_count
            call_count += 1
            return {
                "result": "done", "confidence": 0.9,
                "_meta": {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.06},
            }

        outcome = await dispatch(plan, roster, mock_execute, mission_budget_usd=0.05)
        assert outcome.status == MissionStatus.FAILED
        # Only first task should execute — budget exceeded after layer 1
        assert call_count == 1
        assert outcome.total_cost_usd == pytest.approx(0.06, abs=0.001)

    @pytest.mark.asyncio
    async def test_budget_zero_allows_all_tasks(self):
        """P0.1: Budget of 0 means no budget enforcement."""
        plan = _plan([_task("a"), _task("b")])
        roster = Roster(agents=[_entry("agent_a")])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            return {
                "result": "done", "confidence": 0.9,
                "_meta": {"cost_usd": 5.0},
            }

        outcome = await dispatch(plan, roster, mock_execute, mission_budget_usd=0)
        assert outcome.status == MissionStatus.SUCCESS
        assert len(outcome.task_results) == 2

    @pytest.mark.asyncio
    async def test_retry_feedback_delivered_to_agent(self):
        """P0.2: Enriched instructions with feedback are delivered on retry."""
        plan = _plan([_task("t1")])
        entry = _entry("agent_a")
        entry.constraints.retry_budget = 1
        roster = Roster(agents=[entry])
        received_instructions = []

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            received_instructions.append(instructions)
            if len(received_instructions) == 1:
                raise RuntimeError("First attempt failed")
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.task_results[0].status == TaskStatus.SUCCESS
        assert len(received_instructions) == 2
        # Second call should have feedback appended
        assert "FEEDBACK FROM PREVIOUS ATTEMPT" in received_instructions[1]
        assert "First attempt failed" in received_instructions[1]

    @pytest.mark.asyncio
    async def test_execution_id_assigned_per_task(self):
        """P0.6: Each task gets a unique non-empty execution_id."""
        plan = _plan([_task("a"), _task("b")])
        roster = Roster(agents=[_entry("agent_a")])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            return {"result": "done", "confidence": 0.9, "_meta": {}}

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert len(outcome.task_results) == 2
        ids = [r.execution_id for r in outcome.task_results]
        # All non-empty
        assert all(eid for eid in ids)
        # All unique
        assert len(set(ids)) == 2

    @pytest.mark.asyncio
    async def test_execution_id_on_failed_task(self):
        """P0.6: Failed tasks also get an execution_id."""
        plan = _plan([_task("t1")])
        entry = _entry("agent_a")
        entry.constraints.retry_budget = 0
        roster = Roster(agents=[entry])

        async def mock_execute(agent_name, instructions, inputs, usage_limits):
            raise RuntimeError("fail")

        outcome = await dispatch(plan, roster, mock_execute, 10.0)
        assert outcome.task_results[0].status == TaskStatus.FAILED
        assert outcome.task_results[0].execution_id != ""
