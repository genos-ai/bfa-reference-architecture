"""
Tests for project_id threading through the playbook → mission → dispatch chain.

Verifies that project_id flows from PlaybookRunService.run_playbook() (resolved
from --project name) through MissionService.create_mission_from_step() and
execute_mission() down to the DispatchAdapter and handle_mission().

Uses real db_session with transaction rollback (P12).
Only mocks dispatch execution (external agent calls — not infra we operate).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.config_schema import PlaybooksSchema
from modules.backend.models.mission import MissionState
from modules.backend.services.mission import MissionService


def _mock_app_config(**overrides):
    config = MagicMock()
    config.playbooks = PlaybooksSchema(**overrides)
    return config


# =============================================================================
# MissionService: project_id on create_mission_from_step
# =============================================================================


class TestMissionServiceProjectId:
    @pytest.mark.asyncio
    async def test_create_mission_from_step_sets_project_id(
        self, db_session: AsyncSession,
    ):
        """project_id is persisted on the Mission record."""
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = await service.create_mission_from_step(
                playbook_run_id="run-123",
                step_id="step-1",
                objective="Test objective",
                roster_ref="default",
                complexity_tier="simple",
                cost_ceiling_usd=1.0,
                upstream_context={},
                session_id="sess-1",
                project_id="proj-abc",
            )

        assert mission.project_id == "proj-abc"

    @pytest.mark.asyncio
    async def test_create_mission_from_step_project_id_defaults_none(
        self, db_session: AsyncSession,
    ):
        """project_id defaults to None when not provided."""
        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(session=db_session)
            mission = await service.create_mission_from_step(
                playbook_run_id="run-456",
                step_id="step-1",
                objective="No project",
                roster_ref="default",
                complexity_tier="simple",
                cost_ceiling_usd=1.0,
                upstream_context={},
                session_id="sess-2",
            )

        assert mission.project_id is None

    @pytest.mark.asyncio
    async def test_execute_mission_passes_project_id_to_dispatch(
        self, db_session: AsyncSession,
    ):
        """execute_mission() forwards mission.project_id to the dispatch adapter."""
        mock_dispatch = AsyncMock()
        mock_dispatch.execute = AsyncMock(return_value={
            "status": "success",
            "success": True,
            "total_cost_usd": 0.01,
            "task_results": [],
            "summary": "Done",
        })

        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(
                session=db_session,
                mission_control_dispatch=mock_dispatch,
            )
            mission = await service.create_mission_from_step(
                playbook_run_id="run-789",
                step_id="step-1",
                objective="With project",
                roster_ref="default",
                complexity_tier="simple",
                cost_ceiling_usd=1.0,
                upstream_context={},
                session_id="sess-3",
                project_id="proj-xyz",
            )

            await service.execute_mission(mission.id)

        # Verify project_id was forwarded to the adapter
        mock_dispatch.execute.assert_called_once()
        call_kwargs = mock_dispatch.execute.call_args.kwargs
        assert call_kwargs["project_id"] == "proj-xyz"

    @pytest.mark.asyncio
    async def test_execute_mission_passes_none_project_id(
        self, db_session: AsyncSession,
    ):
        """execute_mission() passes None project_id when mission has no project."""
        mock_dispatch = AsyncMock()
        mock_dispatch.execute = AsyncMock(return_value={
            "status": "success",
            "success": True,
            "total_cost_usd": 0.01,
            "task_results": [],
            "summary": "Done",
        })

        with patch(
            "modules.backend.services.mission.get_app_config",
            return_value=_mock_app_config(),
        ):
            service = MissionService(
                session=db_session,
                mission_control_dispatch=mock_dispatch,
            )
            mission = await service.create_mission_from_step(
                playbook_run_id="run-000",
                step_id="step-1",
                objective="No project",
                roster_ref="default",
                complexity_tier="simple",
                cost_ceiling_usd=1.0,
                upstream_context={},
                session_id="sess-4",
            )

            await service.execute_mission(mission.id)

        call_kwargs = mock_dispatch.execute.call_args.kwargs
        assert call_kwargs["project_id"] is None


# =============================================================================
# DispatchAdapter: project_id forwarded to handle_mission
# =============================================================================


class TestDispatchAdapterProjectId:
    @pytest.mark.asyncio
    async def test_execute_forwards_project_id(self, db_session: AsyncSession):
        """DispatchAdapter.execute() passes project_id and db_session to handle_mission()."""
        from modules.backend.agents.mission_control.dispatch_adapter import (
            MissionControlDispatchAdapter,
        )

        mock_session_service = MagicMock()
        adapter = MissionControlDispatchAdapter(
            session_service=mock_session_service,
            db_session=db_session,
        )

        mock_outcome = MagicMock()
        mock_outcome.status = "success"
        mock_outcome.task_results = []
        mock_outcome.total_cost_usd = 0.01
        mock_outcome.model_dump.return_value = {
            "status": "success",
            "task_results": [],
            "total_cost_usd": 0.01,
        }

        with patch(
            "modules.backend.agents.mission_control.dispatch_adapter.handle_mission",
            new_callable=AsyncMock,
            return_value=mock_outcome,
        ) as mock_handle:
            result = await adapter.execute(
                mission_brief="Test brief",
                project_id="proj-test-123",
            )

        mock_handle.assert_called_once()
        call_kwargs = mock_handle.call_args.kwargs
        assert call_kwargs["project_id"] == "proj-test-123"
        assert call_kwargs["db_session"] is db_session

    @pytest.mark.asyncio
    async def test_execute_without_project_id(self, db_session: AsyncSession):
        """DispatchAdapter.execute() passes None project_id when not provided."""
        from modules.backend.agents.mission_control.dispatch_adapter import (
            MissionControlDispatchAdapter,
        )

        mock_session_service = MagicMock()
        adapter = MissionControlDispatchAdapter(
            session_service=mock_session_service,
            db_session=db_session,
        )

        mock_outcome = MagicMock()
        mock_outcome.status = "success"
        mock_outcome.task_results = []
        mock_outcome.total_cost_usd = 0.0
        mock_outcome.model_dump.return_value = {
            "status": "success",
            "task_results": [],
            "total_cost_usd": 0.0,
        }

        with patch(
            "modules.backend.agents.mission_control.dispatch_adapter.handle_mission",
            new_callable=AsyncMock,
            return_value=mock_outcome,
        ) as mock_handle:
            await adapter.execute(mission_brief="Test brief")

        call_kwargs = mock_handle.call_args.kwargs
        assert call_kwargs["project_id"] is None


# =============================================================================
# PlaybookRunService: name-based project resolution and threading
# =============================================================================


class TestPlaybookRunProjectName:
    """Tests for name-based project resolution in PlaybookRunService."""

    def _mock_playbook_service(self):
        mock_playbook_service = MagicMock()
        mock_playbook = MagicMock()
        mock_playbook.playbook_name = "test-playbook"
        mock_playbook.version = "1.0"
        mock_playbook.enabled = True
        mock_playbook.trigger.type = "manual"
        mock_playbook.context = {}
        mock_playbook.budget.max_cost_usd = 10.0
        mock_playbook.description = "Test playbook"
        mock_playbook.steps = []
        mock_playbook_service.get_playbook.return_value = mock_playbook
        mock_playbook_service.validate_playbook_capabilities.return_value = []
        return mock_playbook_service, mock_playbook

    @pytest.mark.asyncio
    async def test_run_playbook_resolves_project_by_name(
        self, db_session: AsyncSession,
    ):
        """--project my-app resolves to a project UUID via _resolve_project."""
        from modules.backend.services.playbook_run import PlaybookRunService

        mock_ps, _ = self._mock_playbook_service()

        mock_project = MagicMock()
        mock_project.id = "resolved-uuid-123"

        with (
            patch(
                "modules.backend.services.session.SessionService",
            ) as mock_ss_cls,
            patch(
                "modules.backend.services.project.ProjectService.get_project_by_name",
                new_callable=AsyncMock,
                return_value=mock_project,
            ),
        ):
            mock_ss = AsyncMock()
            mock_session = MagicMock()
            mock_session.id = "sess-playbook"
            mock_ss.create_session = AsyncMock(return_value=mock_session)
            mock_ss_cls.return_value = mock_ss

            service = PlaybookRunService(
                session=db_session, playbook_service=mock_ps,
            )
            run = await service.run_playbook(
                playbook_name="test-playbook",
                project_name="my-app",
            )

        assert run.project_id == "resolved-uuid-123"

    @pytest.mark.asyncio
    async def test_run_playbook_creates_project_when_new(
        self, db_session: AsyncSession,
    ):
        """A new project is auto-created when the name doesn't exist yet."""
        from modules.backend.services.playbook_run import PlaybookRunService

        mock_ps, _ = self._mock_playbook_service()

        created_project = MagicMock()
        created_project.id = "new-uuid-456"

        with (
            patch(
                "modules.backend.services.session.SessionService",
            ) as mock_ss_cls,
            patch(
                "modules.backend.services.project.ProjectService.get_project_by_name",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "modules.backend.services.project.ProjectService.create_project",
                new_callable=AsyncMock,
                return_value=created_project,
            ) as mock_create,
        ):
            mock_ss = AsyncMock()
            mock_session = MagicMock()
            mock_session.id = "sess-playbook"
            mock_ss.create_session = AsyncMock(return_value=mock_session)
            mock_ss_cls.return_value = mock_ss

            service = PlaybookRunService(
                session=db_session, playbook_service=mock_ps,
            )
            run = await service.run_playbook(
                playbook_name="test-playbook",
                project_name="brand-new-app",
            )

        assert run.project_id == "new-uuid-456"
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["name"] == "brand-new-app"
        assert call_kwargs["owner_id"] == "system:playbook"

    @pytest.mark.asyncio
    async def test_run_playbook_requires_project_name(
        self, db_session: AsyncSession,
    ):
        """Omitting --project raises ValueError."""
        from modules.backend.services.playbook_run import PlaybookRunService

        mock_ps, _ = self._mock_playbook_service()

        service = PlaybookRunService(
            session=db_session, playbook_service=mock_ps,
        )
        with pytest.raises(ValueError, match="Project name is required"):
            await service.run_playbook(playbook_name="test-playbook")
