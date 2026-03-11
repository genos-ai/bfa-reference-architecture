"""Tests for HistoryQueryService.

Per P12: tests run against the live platform. Uses real db_session fixture
with transaction rollback for isolation.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.mission_record import (
    FailureTier,
    MissionRecord,
    MissionRecordStatus,
    TaskAttempt,
    TaskAttemptStatus,
    TaskExecution,
    TaskExecutionStatus,
)
from modules.backend.services.history_query import HistoryQueryService


@pytest.fixture
def history_service(db_session: AsyncSession) -> HistoryQueryService:
    return HistoryQueryService(db_session)


async def _create_mission(
    db: AsyncSession,
    project_id: str = "proj-1",
    status: MissionRecordStatus = MissionRecordStatus.COMPLETED,
    objective: str = "Test mission",
    cost: float = 0.5,
) -> MissionRecord:
    """Helper to create a MissionRecord."""
    record = MissionRecord(
        session_id="sess-1",
        project_id=project_id,
        status=status,
        objective_statement=objective,
        total_cost_usd=cost,
        started_at="2025-01-01T00:00:00Z",
        completed_at="2025-01-01T00:01:00Z",
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def _create_execution(
    db: AsyncSession,
    mission_record_id: str,
    task_id: str = "task-1",
    agent_name: str = "analyzer",
    status: TaskExecutionStatus = TaskExecutionStatus.COMPLETED,
    domain_tags: list[str] | None = None,
    cost_usd: float = 0.1,
    duration_seconds: float = 5.0,
) -> TaskExecution:
    """Helper to create a TaskExecution."""
    execution = TaskExecution(
        mission_record_id=mission_record_id,
        task_id=task_id,
        agent_name=agent_name,
        status=status,
        cost_usd=cost_usd,
        duration_seconds=duration_seconds,
        domain_tags=domain_tags,
        completed_at="2025-01-01T00:00:30Z",
    )
    db.add(execution)
    await db.flush()
    await db.refresh(execution)
    return execution


async def _create_failed_attempt(
    db: AsyncSession,
    task_execution_id: str,
    attempt_number: int = 1,
    failure_reason: str = "Schema validation failed",
) -> TaskAttempt:
    """Helper to create a failed TaskAttempt."""
    attempt = TaskAttempt(
        task_execution_id=task_execution_id,
        attempt_number=attempt_number,
        status=TaskAttemptStatus.FAILED,
        failure_tier=FailureTier.TIER_1_STRUCTURAL,
        failure_reason=failure_reason,
        feedback_provided="Fix the output schema",
    )
    db.add(attempt)
    await db.flush()
    await db.refresh(attempt)
    return attempt


class TestGetRecentTaskExecutions:
    @pytest.mark.asyncio
    async def test_returns_executions_for_project(
        self, history_service, db_session,
    ):
        mission = await _create_mission(db_session, project_id="proj-exec")
        await _create_execution(
            db_session, mission.id, task_id="t1", domain_tags=["api"],
        )
        await _create_execution(
            db_session, mission.id, task_id="t2", domain_tags=["auth"],
        )

        results = await history_service.get_recent_task_executions("proj-exec")
        assert len(results) == 2
        assert all(r["agent_name"] == "analyzer" for r in results)

    @pytest.mark.asyncio
    async def test_filters_by_domain_tags(self, history_service, db_session):
        mission = await _create_mission(db_session, project_id="proj-tags")
        await _create_execution(
            db_session, mission.id, task_id="t1", domain_tags=["api", "auth"],
        )
        await _create_execution(
            db_session, mission.id, task_id="t2", domain_tags=["frontend"],
        )

        results = await history_service.get_recent_task_executions(
            "proj-tags", domain_tags=["auth"],
        )
        assert len(results) == 1
        assert results[0]["task_id"] == "t1"

    @pytest.mark.asyncio
    async def test_respects_limit(self, history_service, db_session):
        mission = await _create_mission(db_session, project_id="proj-limit")
        for i in range(5):
            await _create_execution(
                db_session, mission.id, task_id=f"t{i}",
            )

        results = await history_service.get_recent_task_executions(
            "proj-limit", limit=2,
        )
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_empty_for_unknown_project(self, history_service):
        results = await history_service.get_recent_task_executions("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_excludes_other_projects(self, history_service, db_session):
        m1 = await _create_mission(db_session, project_id="proj-a")
        m2 = await _create_mission(db_session, project_id="proj-b")
        await _create_execution(db_session, m1.id, task_id="a-task")
        await _create_execution(db_session, m2.id, task_id="b-task")

        results = await history_service.get_recent_task_executions("proj-a")
        assert len(results) == 1
        assert results[0]["task_id"] == "a-task"


class TestGetRecentFailures:
    @pytest.mark.asyncio
    async def test_returns_failed_attempts(self, history_service, db_session):
        mission = await _create_mission(db_session, project_id="proj-fail")
        execution = await _create_execution(
            db_session, mission.id, domain_tags=["api"],
        )
        await _create_failed_attempt(
            db_session, execution.id, failure_reason="Missing required field",
        )

        failures = await history_service.get_recent_failures("proj-fail")
        assert len(failures) == 1
        assert failures[0]["failure_reason"] == "Missing required field"
        assert failures[0]["failure_tier"] == FailureTier.TIER_1_STRUCTURAL

    @pytest.mark.asyncio
    async def test_filters_by_domain_tags(self, history_service, db_session):
        mission = await _create_mission(db_session, project_id="proj-fail-tag")
        exec_api = await _create_execution(
            db_session, mission.id, task_id="api-task", domain_tags=["api"],
        )
        exec_ui = await _create_execution(
            db_session, mission.id, task_id="ui-task", domain_tags=["frontend"],
        )
        await _create_failed_attempt(db_session, exec_api.id)
        await _create_failed_attempt(db_session, exec_ui.id)

        failures = await history_service.get_recent_failures(
            "proj-fail-tag", domain_tags=["api"],
        )
        assert len(failures) == 1
        assert failures[0]["task_id"] == "api-task"

    @pytest.mark.asyncio
    async def test_respects_limit(self, history_service, db_session):
        mission = await _create_mission(db_session, project_id="proj-fail-lim")
        execution = await _create_execution(db_session, mission.id)
        for i in range(5):
            await _create_failed_attempt(
                db_session, execution.id, attempt_number=i + 1,
            )

        failures = await history_service.get_recent_failures(
            "proj-fail-lim", limit=2,
        )
        assert len(failures) == 2

    @pytest.mark.asyncio
    async def test_empty_when_no_failures(self, history_service, db_session):
        mission = await _create_mission(db_session, project_id="proj-ok")
        await _create_execution(db_session, mission.id)

        failures = await history_service.get_recent_failures("proj-ok")
        assert failures == []


class TestGetMissionSummaries:
    @pytest.mark.asyncio
    async def test_returns_summaries(self, history_service, db_session):
        await _create_mission(
            db_session, project_id="proj-sum", objective="Build API",
        )
        await _create_mission(
            db_session, project_id="proj-sum", objective="Fix auth",
            status=MissionRecordStatus.FAILED,
        )

        summaries = await history_service.get_mission_summaries("proj-sum")
        assert len(summaries) == 2
        objectives = {s["objective"] for s in summaries}
        assert objectives == {"Build API", "Fix auth"}

    @pytest.mark.asyncio
    async def test_respects_limit(self, history_service, db_session):
        for i in range(5):
            await _create_mission(
                db_session, project_id="proj-sum-lim", objective=f"Mission {i}",
            )

        summaries = await history_service.get_mission_summaries(
            "proj-sum-lim", limit=3,
        )
        assert len(summaries) == 3

    @pytest.mark.asyncio
    async def test_empty_for_unknown_project(self, history_service):
        summaries = await history_service.get_mission_summaries("nonexistent")
        assert summaries == []
