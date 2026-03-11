"""Tests for MissionPersistenceService.

Per P12: tests run against the live platform. Uses real db_session fixture
with transaction rollback for isolation. Only mocks: get_app_config()
(config loading, not infrastructure we operate).
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.config_schema import MissionsSchema
from modules.backend.core.exceptions import NotFoundError
from modules.backend.models.mission_record import (
    MissionRecordStatus,
    TaskExecutionStatus,
)
from modules.backend.services.mission_persistence import MissionPersistenceService


def _mock_app_config(**overrides) -> MagicMock:
    """Create a mock AppConfig with a real MissionsSchema."""
    config = MagicMock()
    config.missions = MissionsSchema(**overrides)
    return config


@pytest.fixture
def service(db_session: AsyncSession) -> MissionPersistenceService:
    return MissionPersistenceService(db_session)


@pytest.fixture(autouse=True)
def _patch_config():
    """Patch get_app_config — config loading is not infra we operate."""
    with patch(
        "modules.backend.services.mission_persistence.get_app_config",
        return_value=_mock_app_config(),
    ):
        yield


async def _create_mission(service, **overrides):
    """Helper to create a mission record via the service."""
    defaults = {
        "session_id": "sess-123",
        "status": "completed",
        "roster_name": "code_review",
        "total_cost_usd": 0.05,
    }
    defaults.update(overrides)
    return await service.save_mission(**defaults)


class TestSaveMission:
    @pytest.mark.asyncio
    async def test_creates_record_in_db(self, service):
        record = await _create_mission(service)

        assert record.id is not None
        assert record.session_id == "sess-123"
        assert record.roster_name == "code_review"
        assert record.status == MissionRecordStatus.COMPLETED
        assert record.total_cost_usd == 0.05

    @pytest.mark.asyncio
    async def test_with_objective(self, service):
        record = await _create_mission(
            service,
            objective_statement="Improve coverage",
            objective_category="engineering",
        )

        assert record.objective_statement == "Improve coverage"
        assert record.objective_category == "engineering"

    @pytest.mark.asyncio
    async def test_thinking_trace_truncation(self, service):
        long_trace = "x" * 60000
        record = await _create_mission(
            service,
            planning_thinking_trace=long_trace,
        )

        assert len(record.planning_thinking_trace) < 60000
        assert record.planning_thinking_trace.endswith("[TRUNCATED]")

    @pytest.mark.asyncio
    async def test_thinking_trace_not_persisted_when_disabled(self, service):
        with patch(
            "modules.backend.services.mission_persistence.get_app_config",
            return_value=_mock_app_config(persist_thinking_trace=False),
        ):
            record = await _create_mission(
                service,
                planning_thinking_trace="some trace",
            )

            assert record.planning_thinking_trace is None

    @pytest.mark.asyncio
    async def test_task_plan_json_persisted(self, service):
        plan = {"version": "1.0", "tasks": [{"id": "t1"}]}
        record = await _create_mission(service, task_plan_json=plan)
        assert record.task_plan_json == plan

    @pytest.mark.asyncio
    async def test_parent_mission_link(self, service):
        parent = await _create_mission(service)
        child = await _create_mission(service, parent_mission_id=parent.id)
        assert child.parent_mission_id == parent.id


class TestSaveTaskExecution:
    @pytest.mark.asyncio
    async def test_creates_execution(self, service):
        mission = await _create_mission(service)

        execution = await service.save_task_execution(
            mission_record_id=mission.id,
            task_id="analyze_code",
            agent_name="code.quality.agent",
            status="completed",
            cost_usd=0.01,
        )

        assert execution.id is not None
        assert execution.task_id == "analyze_code"
        assert execution.agent_name == "code.quality.agent"
        assert execution.status == TaskExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_output_truncation(self, service):
        mission = await _create_mission(service)
        large_output = {"data": "x" * 2_000_000}

        execution = await service.save_task_execution(
            mission_record_id=mission.id,
            task_id="task-1",
            agent_name="agent-1",
            status="completed",
            output_data=large_output,
        )

        assert execution.output_data["_truncated"] is True
        assert execution.output_data["_original_size_bytes"] > 1_048_576

    @pytest.mark.asyncio
    async def test_verification_outcome_persisted(self, service):
        mission = await _create_mission(service)
        verification = {"passed": True, "tier": "tier_1", "details": {"checks": 5}}

        execution = await service.save_task_execution(
            mission_record_id=mission.id,
            task_id="task-1",
            agent_name="agent-1",
            status="completed",
            verification_outcome=verification,
        )

        assert execution.verification_outcome["passed"] is True
        assert execution.verification_outcome["details"]["checks"] == 5

    @pytest.mark.asyncio
    async def test_verification_stripped_when_disabled(self, service):
        mission = await _create_mission(service)
        verification = {"passed": True, "tier": "tier_1", "details": {"checks": 5}}

        with patch(
            "modules.backend.services.mission_persistence.get_app_config",
            return_value=_mock_app_config(persist_verification_details=False),
        ):
            execution = await service.save_task_execution(
                mission_record_id=mission.id,
                task_id="task-1",
                agent_name="agent-1",
                status="completed",
                verification_outcome=verification,
            )

        assert execution.verification_outcome["passed"] is True
        assert "details" not in execution.verification_outcome


class TestSaveAttempt:
    @pytest.mark.asyncio
    async def test_creates_attempt(self, service):
        mission = await _create_mission(service)
        execution = await service.save_task_execution(
            mission_record_id=mission.id,
            task_id="task-1",
            agent_name="agent-1",
            status="failed",
        )

        attempt = await service.save_attempt(
            task_execution_id=execution.id,
            attempt_number=1,
            status="failed",
            failure_tier="tier_1_structural",
            failure_reason="Missing field",
            feedback_provided="Add the missing field",
        )

        assert attempt.id is not None
        assert attempt.attempt_number == 1
        assert attempt.failure_reason == "Missing field"
        assert attempt.feedback_provided == "Add the missing field"


class TestSaveDecision:
    @pytest.mark.asyncio
    async def test_creates_decision(self, service):
        mission = await _create_mission(service)

        decision = await service.save_decision(
            mission_record_id=mission.id,
            decision_type="retry",
            reasoning="Tier 1 failed, retrying with feedback",
            task_id="task-1",
        )

        assert decision.id is not None
        assert decision.task_id == "task-1"
        assert decision.reasoning == "Tier 1 failed, retrying with feedback"


class TestListMissions:
    @pytest.mark.asyncio
    async def test_list_returns_created_missions(self, service):
        await _create_mission(service, roster_name="roster_a")
        await _create_mission(service, roster_name="roster_b")

        missions, total = await service.list_missions()
        assert total >= 2
        roster_names = {m.roster_name for m in missions}
        assert "roster_a" in roster_names
        assert "roster_b" in roster_names

    @pytest.mark.asyncio
    async def test_list_filters_by_status(self, service):
        await _create_mission(service, status="completed")
        await _create_mission(service, status="failed")

        missions, total = await service.list_missions(status="completed")
        assert all(m.status == MissionRecordStatus.COMPLETED for m in missions)

    @pytest.mark.asyncio
    async def test_list_caps_page_size(self, service):
        missions, _ = await service.list_missions(limit=500)
        assert isinstance(missions, list)


class TestGetMissionStatus:
    @pytest.mark.asyncio
    async def test_not_found_raises(self, service):
        with pytest.raises(NotFoundError, match="not found"):
            await service.get_mission_status("nonexistent-id")

    @pytest.mark.asyncio
    async def test_status_with_executions(self, service):
        mission = await _create_mission(service, total_cost_usd=0.15)

        await service.save_task_execution(
            mission_record_id=mission.id,
            task_id="t1", agent_name="a1", status="completed",
        )
        await service.save_task_execution(
            mission_record_id=mission.id,
            task_id="t2", agent_name="a2", status="failed",
        )
        await service.save_task_execution(
            mission_record_id=mission.id,
            task_id="t3", agent_name="a3", status="skipped",
        )

        status = await service.get_mission_status(mission.id)
        assert status["mission_id"] == mission.id
        assert status["total_tasks"] == 3
        assert status["completed_tasks"] == 1
        assert status["failed_tasks"] == 1
        assert status["skipped_tasks"] == 1
        assert status["progress_pct"] == 33.3
        assert status["total_cost_usd"] == 0.15

    @pytest.mark.asyncio
    async def test_status_no_executions(self, service):
        mission = await _create_mission(service)

        status = await service.get_mission_status(mission.id)
        assert status["total_tasks"] == 0
        assert status["progress_pct"] == 0.0


class TestGetCostBreakdown:
    @pytest.mark.asyncio
    async def test_not_found_raises(self, service):
        with pytest.raises(NotFoundError, match="not found"):
            await service.get_cost_breakdown("nonexistent-id")

    @pytest.mark.asyncio
    async def test_aggregates_costs(self, service):
        mission = await _create_mission(service, total_cost_usd=0.10)

        await service.save_task_execution(
            mission_record_id=mission.id,
            task_id="t1",
            agent_name="agent_a",
            status="completed",
            cost_usd=0.05,
            duration_seconds=1.5,
            token_usage={"input_tokens": 100, "output_tokens": 50, "model": "test"},
        )

        breakdown = await service.get_cost_breakdown(mission.id)
        assert breakdown.total_cost_usd == 0.10
        assert len(breakdown.task_costs) == 1
        assert breakdown.total_input_tokens == 100
        assert breakdown.total_output_tokens == 50
        assert breakdown.model_costs.get("test") == 0.05


class TestExecutionId:
    """P0.6: execution_id persistence."""

    @pytest.mark.asyncio
    async def test_execution_id_persisted(self, service):
        """execution_id flows from save_task_execution to TaskExecution row."""
        mission = await service.save_mission(
            session_id="sess-eid",
            status="completed",
            total_cost_usd=0.01,
        )

        execution = await service.save_task_execution(
            mission_record_id=mission.id,
            task_id="t1",
            agent_name="agent_a",
            status="completed",
            execution_id="eid-1234-5678",
        )

        assert execution.execution_id == "eid-1234-5678"

    @pytest.mark.asyncio
    async def test_execution_id_defaults_none(self, service):
        """execution_id is None when not provided."""
        mission = await service.save_mission(
            session_id="sess-eid2",
            status="completed",
            total_cost_usd=0.01,
        )

        execution = await service.save_task_execution(
            mission_record_id=mission.id,
            task_id="t1",
            agent_name="agent_a",
            status="completed",
        )

        assert execution.execution_id is None
