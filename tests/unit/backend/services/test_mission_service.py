"""
Tests for MissionService.

Uses real db_session with transaction rollback (P12).
Only mocks get_app_config (config loading — not infra we operate).
"""

import pytest
from unittest.mock import MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.config_schema import PlaybooksSchema
from modules.backend.models.mission import Mission, MissionState
from modules.backend.repositories.mission import MissionRepository
from modules.backend.services.mission import MissionService


def _mock_app_config(**overrides):
    config = MagicMock()
    config.playbooks = PlaybooksSchema(**overrides)
    return config


@pytest.fixture
def mission_service(db_session: AsyncSession) -> MissionService:
    with patch(
        "modules.backend.services.mission.get_app_config",
        return_value=_mock_app_config(),
    ):
        return MissionService(session=db_session)


class TestCreateAdhocMission:
    @pytest.mark.asyncio
    async def test_creates_mission(self, db_session: AsyncSession):
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = await service.create_adhoc_mission(
                objective="Test objective",
                triggered_by="user:test",
                session_id="test-session-id",
            )

        assert mission.id is not None
        assert mission.objective == "Test objective"
        assert mission.status == MissionState.PENDING
        assert mission.roster_ref == "default"
        assert mission.complexity_tier == "simple"
        assert mission.triggered_by == "user:test"
        assert mission.trigger_type == "on_demand"
        assert mission.total_cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_custom_roster_and_tier(self, db_session: AsyncSession):
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = await service.create_adhoc_mission(
                objective="Complex task",
                triggered_by="user:test",
                session_id="test-session-id",
                roster_ref="research_team",
                complexity_tier="complex",
                cost_ceiling_usd=25.0,
            )

        assert mission.roster_ref == "research_team"
        assert mission.complexity_tier == "complex"
        assert mission.cost_ceiling_usd == 25.0

    @pytest.mark.asyncio
    async def test_concurrency_limit(self, db_session: AsyncSession):
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(max_concurrent_missions=1),
        ):
            service = MissionService(session=db_session)

            # Create first mission (should succeed)
            await service.create_adhoc_mission(
                objective="First",
                triggered_by="user:test",
                session_id="sess-1",
            )

            # Second should fail due to concurrency limit
            from modules.backend.core.exceptions import ValidationError
            with pytest.raises(ValidationError, match="Maximum concurrent"):
                await service.create_adhoc_mission(
                    objective="Second",
                    triggered_by="user:test",
                    session_id="sess-2",
                )


class TestCreateMissionFromStep:
    @pytest.mark.asyncio
    async def test_creates_from_step(self, db_session: AsyncSession):
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = await service.create_mission_from_step(
                playbook_run_id="run-123",
                step_id="scrape",
                objective="Fetch articles",
                roster_ref="research_team",
                complexity_tier="simple",
                cost_ceiling_usd=0.50,
                upstream_context={"sources": ["url1"]},
                session_id="test-session-id",
            )

        assert mission.playbook_run_id == "run-123"
        assert mission.playbook_step_id == "scrape"
        assert mission.roster_ref == "research_team"
        assert mission.upstream_context == {"sources": ["url1"]}
        assert mission.trigger_type == "playbook"


class TestMissionStateTransitions:
    @pytest.mark.asyncio
    async def test_pending_to_cancelled(self, db_session: AsyncSession):
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = await service.create_adhoc_mission(
                objective="Cancellable",
                triggered_by="user:test",
                session_id="sess-1",
            )

            cancelled = await service.cancel_mission(
                mission.id, reason="Changed mind",
            )

        assert cancelled.status == MissionState.CANCELLED
        assert cancelled.error_data == {"cancelled_reason": "Changed mind"}
        assert cancelled.completed_at is not None

    @pytest.mark.asyncio
    async def test_invalid_transition_rejected(self, db_session: AsyncSession):
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = await service.create_adhoc_mission(
                objective="Test",
                triggered_by="user:test",
                session_id="sess-1",
            )
            await service.cancel_mission(mission.id, reason="done")

            from modules.backend.core.exceptions import ValidationError
            with pytest.raises(ValidationError, match="Cannot transition"):
                await service.complete_mission(mission.id)

    @pytest.mark.asyncio
    async def test_complete_mission(self, db_session: AsyncSession):
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = await service.create_adhoc_mission(
                objective="Complete me",
                triggered_by="user:test",
                session_id="sess-1",
            )

            # Transition to running first
            m = await service._get_mission(mission.id)
            m.status = MissionState.RUNNING
            m.started_at = "2026-01-01T00:00:00"
            await db_session.flush()

            completed = await service.complete_mission(mission.id)

        assert completed.status == MissionState.COMPLETED
        assert completed.completed_at is not None

    @pytest.mark.asyncio
    async def test_fail_mission(self, db_session: AsyncSession):
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = await service.create_adhoc_mission(
                objective="Fail me",
                triggered_by="user:test",
                session_id="sess-1",
            )

            m = await service._get_mission(mission.id)
            m.status = MissionState.RUNNING
            await db_session.flush()

            failed = await service.fail_mission(
                mission.id, error="Something went wrong",
            )

        assert failed.status == MissionState.FAILED
        assert failed.error_data == {"message": "Something went wrong"}


class TestOutputExtraction:
    @pytest.mark.asyncio
    async def test_extract_summary_key(self, db_session: AsyncSession):
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = await service.create_adhoc_mission(
                objective="Extract test",
                triggered_by="user:test",
                session_id="sess-1",
            )
            mission.mission_outcome = {"summary": "All done"}
            await db_session.flush()

        output_mapping = {"summary_key": "result"}
        extracted = service.extract_outputs(mission, output_mapping)
        assert extracted == {"result": "All done"}

    @pytest.mark.asyncio
    async def test_extract_field_mappings(self, db_session: AsyncSession):
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = await service.create_adhoc_mission(
                objective="Extract fields",
                triggered_by="user:test",
                session_id="sess-1",
            )
            mission.mission_outcome = {
                "task_results": {
                    "scrape_articles": {"articles": ["a1", "a2"]},
                },
            }
            await db_session.flush()

        output_mapping = {
            "field_mappings": [
                {
                    "source_task": "scrape_articles",
                    "source_field": "articles",
                    "target_key": "raw_articles",
                },
            ],
        }
        extracted = service.extract_outputs(mission, output_mapping)
        assert extracted == {"raw_articles": ["a1", "a2"]}

    def test_extract_no_mapping(self, db_session: AsyncSession):
        service = MissionService(session=db_session)
        mission = MagicMock()
        mission.mission_outcome = {"summary": "test"}
        assert service.extract_outputs(mission, None) == {}

    def test_extract_no_outcome(self, db_session: AsyncSession):
        service = MissionService(session=db_session)
        mission = MagicMock()
        mission.mission_outcome = None
        assert service.extract_outputs(mission, {"summary_key": "r"}) == {}


class TestListAndGetMissions:
    @pytest.mark.asyncio
    async def test_list_missions(self, db_session: AsyncSession):
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            await service.create_adhoc_mission(
                objective="Mission 1",
                triggered_by="user:test",
                session_id="sess-1",
            )
            await service.create_adhoc_mission(
                objective="Mission 2",
                triggered_by="user:test",
                session_id="sess-2",
            )

            missions, total = await service.list_missions()

        assert total == 2
        assert len(missions) == 2

    @pytest.mark.asyncio
    async def test_get_mission_not_found(self, db_session: AsyncSession):
        service = MissionService(session=db_session)

        from modules.backend.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await service.get_mission("nonexistent-id")


class TestExtractOutputs:
    """P0.5: extract_outputs reliability fixes."""

    def _make_mission(self, outcome=None):
        mission = MagicMock()
        mission.id = "test-mission"
        mission.mission_outcome = outcome
        mission.result_summary = "Test summary"
        return mission

    def test_no_output_mapping_returns_empty(self, db_session: AsyncSession):
        """Returns {} and logs debug when output_mapping is None."""
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = self._make_mission(outcome={"task_results": []})
            result = service.extract_outputs(mission, None)
            assert result == {}

    def test_no_outcome_returns_empty(self, db_session: AsyncSession):
        """Returns {} and logs warning when mission has no outcome."""
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = self._make_mission(outcome=None)
            result = service.extract_outputs(mission, {"field_mappings": []})
            assert result == {}

    def test_duplicate_agents_both_accessible(self, db_session: AsyncSession):
        """Multiple tasks with same agent_name are all searchable."""
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = self._make_mission(outcome={
                "task_results": [
                    {
                        "task_id": "task-001",
                        "agent_name": "code.qa.agent",
                        "output_reference": {"report": "first report"},
                    },
                    {
                        "task_id": "task-002",
                        "agent_name": "code.qa.agent",
                        "output_reference": {"analysis": "second analysis"},
                    },
                ],
            })
            mapping = {
                "field_mappings": [
                    {
                        "source_task": "code.qa.agent",
                        "source_field": "analysis",
                        "target_key": "qa_analysis",
                    },
                ],
            }
            result = service.extract_outputs(mission, mapping)
            # Should find 'analysis' from the second entry, not be overwritten
            assert result["qa_analysis"] == "second analysis"
