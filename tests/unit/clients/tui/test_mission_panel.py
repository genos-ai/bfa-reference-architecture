"""Tests for MissionPanel widget."""

import pytest

from modules.backend.agents.mission_control.outcome import TaskResult, TaskStatus
from modules.backend.schemas.task_plan import TaskDefinition, TaskInputs, TaskPlan
from modules.clients.tui.widgets.mission_panel import (
    MissionPanel,
    TaskNode,
    _agent_short_name,
    _task_status_icon,
)


# ── Helpers ───────────────────────────────────────────────────────────

def _make_plan(task_count: int = 3) -> TaskPlan:
    """Build a minimal TaskPlan with `task_count` sequential tasks."""
    tasks = []
    for i in range(task_count):
        deps = [f"task-{i - 1}"] if i > 0 else []
        tasks.append(
            TaskDefinition(
                task_id=f"task-{i}",
                agent=f"code.quality.agent-{i}",
                agent_version="1.0.0",
                description=f"Do thing {i}",
                instructions=f"Instructions for task {i}",
                inputs=TaskInputs(),
                dependencies=deps,
            )
        )
    return TaskPlan(
        mission_id="test-mission",
        summary="Test mission",
        estimated_cost_usd=0.5,
        estimated_duration_seconds=60,
        tasks=tasks,
    )


def _make_layers(plan: TaskPlan) -> list[list[str]]:
    """Simple sequential layers — one task per layer."""
    return [[t.task_id] for t in plan.tasks]


def _make_parallel_plan() -> tuple[TaskPlan, list[list[str]]]:
    """Plan with 2 parallel tasks in layer 0, 1 dependent task in layer 1."""
    tasks = [
        TaskDefinition(
            task_id="a",
            agent="code.lint.agent",
            agent_version="1.0.0",
            description="Lint code",
            instructions="Run linter",
            inputs=TaskInputs(),
            dependencies=[],
        ),
        TaskDefinition(
            task_id="b",
            agent="code.test.agent",
            agent_version="1.0.0",
            description="Run tests",
            instructions="Run test suite",
            inputs=TaskInputs(),
            dependencies=[],
        ),
        TaskDefinition(
            task_id="c",
            agent="code.merge.agent",
            agent_version="1.0.0",
            description="Merge results",
            instructions="Combine outputs",
            inputs=TaskInputs(),
            dependencies=["a", "b"],
        ),
    ]
    plan = TaskPlan(
        mission_id="parallel-mission",
        summary="Parallel test",
        estimated_cost_usd=1.0,
        estimated_duration_seconds=120,
        tasks=tasks,
    )
    layers = [["a", "b"], ["c"]]
    return plan, layers


# ── Pure functions ────────────────────────────────────────────────────

class TestAgentShortName:
    def test_dotted_name(self):
        assert _agent_short_name("code.quality.agent") == "quality"

    def test_simple_name(self):
        assert _agent_short_name("planner") == "planner"

    def test_two_part_name(self):
        assert _agent_short_name("code.agent") == "code"


class TestTaskStatusIcon:
    def test_pending(self):
        icon = _task_status_icon("t1", active_tasks=set(), results={})
        assert "○" in icon

    def test_running(self):
        icon = _task_status_icon("t1", active_tasks={"t1"}, results={})
        assert "●" in icon

    def test_success(self):
        result = TaskResult(task_id="t1", agent_name="a", status=TaskStatus.SUCCESS)
        icon = _task_status_icon("t1", active_tasks=set(), results={"t1": result})
        assert "✓" in icon

    def test_failed(self):
        result = TaskResult(task_id="t1", agent_name="a", status=TaskStatus.FAILED)
        icon = _task_status_icon("t1", active_tasks=set(), results={"t1": result})
        assert "✗" in icon

    def test_timeout(self):
        result = TaskResult(task_id="t1", agent_name="a", status=TaskStatus.TIMEOUT)
        icon = _task_status_icon("t1", active_tasks=set(), results={"t1": result})
        assert "⏱" in icon

    def test_skipped(self):
        result = TaskResult(task_id="t1", agent_name="a", status=TaskStatus.SKIPPED)
        icon = _task_status_icon("t1", active_tasks=set(), results={"t1": result})
        assert "⊘" in icon

    def test_result_takes_priority_over_active(self):
        """If a task has a result, that overrides the active state."""
        result = TaskResult(task_id="t1", agent_name="a", status=TaskStatus.SUCCESS)
        icon = _task_status_icon("t1", active_tasks={"t1"}, results={"t1": result})
        assert "✓" in icon


# ── MissionPanel (Textual Pilot) ─────────────────────────────────────

class TestMissionPanel:
    @pytest.mark.asyncio
    async def test_mounts_with_header(self):
        """MissionPanel should mount with a header and scrollable DAG area."""
        from textual.app import App, ComposeResult
        from textual.containers import VerticalScroll

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield MissionPanel(id="mission-panel")

        async with TestApp().run_test() as pilot:
            panel = pilot.app.query_one("#mission-panel", MissionPanel)
            assert panel is not None
            assert panel.query_one("#dag-scroll", VerticalScroll)
            assert panel.query_one("#mission-panel-title")

    @pytest.mark.asyncio
    async def test_load_plan_renders_layers(self):
        """Loading a plan should render layer headings and task nodes."""
        from textual.app import App, ComposeResult
        from textual.containers import VerticalScroll
        from textual.widgets import Label

        plan = _make_plan(3)
        layers = _make_layers(plan)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield MissionPanel(id="mission-panel")

        async with TestApp().run_test() as pilot:
            panel = pilot.app.query_one("#mission-panel", MissionPanel)
            panel.load_plan(plan, layers)
            await pilot.pause()

            scroll = panel.query_one("#dag-scroll", VerticalScroll)
            # 3 layers + 3 task nodes = 6 children
            assert len(scroll.children) == 6

    @pytest.mark.asyncio
    async def test_load_plan_parallel_layers(self):
        """Parallel plan should render 2 layers with correct task counts."""
        from textual.app import App, ComposeResult
        from textual.containers import VerticalScroll

        plan, layers = _make_parallel_plan()

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield MissionPanel(id="mission-panel")

        async with TestApp().run_test() as pilot:
            panel = pilot.app.query_one("#mission-panel", MissionPanel)
            panel.load_plan(plan, layers)
            await pilot.pause()

            scroll = panel.query_one("#dag-scroll", VerticalScroll)
            # 2 layer headings + 3 task nodes = 5 children
            assert len(scroll.children) == 5

    @pytest.mark.asyncio
    async def test_header_shows_progress(self):
        """Header should show task count and cost after loading a plan."""
        from textual.app import App, ComposeResult
        from textual.widgets import Label

        plan = _make_plan(2)
        layers = _make_layers(plan)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield MissionPanel(id="mission-panel")

        async with TestApp().run_test() as pilot:
            panel = pilot.app.query_one("#mission-panel", MissionPanel)
            panel.load_plan(plan, layers)
            await pilot.pause()

            title = panel.query_one("#mission-panel-title", Label)
            rendered = title.render()
            assert "0/2" in str(rendered)

    @pytest.mark.asyncio
    async def test_set_active_task(self):
        """set_active_task should mark a task as running without crashing."""
        from textual.app import App, ComposeResult

        plan = _make_plan(2)
        layers = _make_layers(plan)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield MissionPanel(id="mission-panel")

        async with TestApp().run_test() as pilot:
            panel = pilot.app.query_one("#mission-panel", MissionPanel)
            panel.load_plan(plan, layers)
            await pilot.pause()

            panel.set_active_task("task-0")
            await pilot.pause()
            assert "task-0" in panel._active_tasks

    @pytest.mark.asyncio
    async def test_clear_active_task(self):
        """clear_active_task should remove a task from active set."""
        from textual.app import App, ComposeResult

        plan = _make_plan(2)
        layers = _make_layers(plan)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield MissionPanel(id="mission-panel")

        async with TestApp().run_test() as pilot:
            panel = pilot.app.query_one("#mission-panel", MissionPanel)
            panel.load_plan(plan, layers)
            panel.set_active_task("task-0")
            panel.clear_active_task("task-0")
            await pilot.pause()
            assert "task-0" not in panel._active_tasks

    @pytest.mark.asyncio
    async def test_update_task_status_with_result(self):
        """update_task_status with a result should record it and re-render."""
        from textual.app import App, ComposeResult
        from textual.widgets import Label

        plan = _make_plan(2)
        layers = _make_layers(plan)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield MissionPanel(id="mission-panel")

        async with TestApp().run_test() as pilot:
            panel = pilot.app.query_one("#mission-panel", MissionPanel)
            panel.load_plan(plan, layers)
            await pilot.pause()

            result = TaskResult(
                task_id="task-0",
                agent_name="code.quality.agent-0",
                status=TaskStatus.SUCCESS,
                cost_usd=0.01,
            )
            panel.update_task_status("task-0", result=result)
            await pilot.pause()

            assert "task-0" in panel._results
            # Header should now show 1/2
            title = panel.query_one("#mission-panel-title", Label)
            assert "1/2" in str(title.render())

    @pytest.mark.asyncio
    async def test_update_task_status_removes_from_active(self):
        """Completing a task should remove it from the active set."""
        from textual.app import App, ComposeResult

        plan = _make_plan(1)
        layers = _make_layers(plan)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield MissionPanel(id="mission-panel")

        async with TestApp().run_test() as pilot:
            panel = pilot.app.query_one("#mission-panel", MissionPanel)
            panel.load_plan(plan, layers)
            panel.set_active_task("task-0")
            assert "task-0" in panel._active_tasks

            result = TaskResult(
                task_id="task-0",
                agent_name="a",
                status=TaskStatus.SUCCESS,
            )
            panel.update_task_status("task-0", result=result)
            await pilot.pause()
            assert "task-0" not in panel._active_tasks

    @pytest.mark.asyncio
    async def test_cost_displayed_for_completed_task(self):
        """Completed tasks with cost should show cost in the header total."""
        from textual.app import App, ComposeResult
        from textual.widgets import Label

        plan = _make_plan(1)
        layers = _make_layers(plan)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield MissionPanel(id="mission-panel")

        async with TestApp().run_test() as pilot:
            panel = pilot.app.query_one("#mission-panel", MissionPanel)
            panel.load_plan(plan, layers)

            result = TaskResult(
                task_id="task-0",
                agent_name="a",
                status=TaskStatus.SUCCESS,
                cost_usd=0.123,
            )
            panel.update_task_status("task-0", result=result)
            await pilot.pause()

            title = panel.query_one("#mission-panel-title", Label)
            assert "0.123" in str(title.render())

    @pytest.mark.asyncio
    async def test_no_plan_render_noop(self):
        """_render_dag with no plan should not crash."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield MissionPanel(id="mission-panel")

        async with TestApp().run_test() as pilot:
            panel = pilot.app.query_one("#mission-panel", MissionPanel)
            panel._render_dag()  # Should be a safe no-op
            await pilot.pause()
