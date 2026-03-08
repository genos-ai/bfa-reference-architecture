"""Tests for Temporal Activities.

send_notification is tested live (it's a stub that logs).
execute_mission mocks handle_mission (LLM calls — not infra we operate).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from modules.backend.temporal.models import (
    MissionWorkflowInput,
    NotificationPayload,
)


class TestSendNotification:
    @pytest.mark.asyncio
    async def test_returns_true(self):
        """send_notification is a logging stub — test it live."""
        from modules.backend.temporal.activities import send_notification

        result = await send_notification(
            NotificationPayload(
                channel="webhook",
                recipient="admin",
                title="Test",
                body="Test body",
                action_url="/test",
            ),
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_handles_all_urgency_levels(self):
        from modules.backend.temporal.activities import send_notification

        for urgency in ("low", "normal", "high", "critical"):
            result = await send_notification(
                NotificationPayload(
                    channel="slack",
                    recipient="team",
                    title="Alert",
                    body="Body",
                    action_url="/url",
                    urgency=urgency,
                ),
            )
            assert result is True


class TestExecuteMission:
    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        """Mock handle_mission (LLM calls) but test the Activity logic live."""
        from modules.backend.temporal.activities import execute_mission

        mock_outcome = MagicMock()
        mock_outcome.status.value = "success"
        mock_outcome.total_cost_usd = 0.05
        mock_outcome.total_duration_seconds = 1.5
        mock_outcome.task_results = []
        mock_outcome.model_dump.return_value = {"status": "success"}

        mock_session = AsyncMock()

        with (
            patch(
                "modules.backend.agents.mission_control.mission_control.handle_mission",
                return_value=mock_outcome,
            ),
            patch(
                "modules.backend.core.database.get_async_session",
            ) as mock_get_session,
            patch(
                "modules.backend.services.session.SessionService",
            ),
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(
                return_value=False,
            )

            result = await execute_mission(
                MissionWorkflowInput(
                    mission_id="test-1",
                    session_id="sess-1",
                    mission_brief="Test mission",
                ),
            )

            assert result.status == "success"
            assert result.mission_id == "test-1"
            assert result.total_cost_usd == 0.05
            assert result.total_duration_seconds == 1.5
            assert result.task_count == 0

    @pytest.mark.asyncio
    async def test_counts_task_results(self):
        from modules.backend.temporal.activities import execute_mission

        mock_task_success = MagicMock()
        mock_task_success.status.value = "success"
        mock_task_failed = MagicMock()
        mock_task_failed.status.value = "failed"

        mock_outcome = MagicMock()
        mock_outcome.status.value = "partial"
        mock_outcome.total_cost_usd = 0.10
        mock_outcome.total_duration_seconds = 3.0
        mock_outcome.task_results = [mock_task_success, mock_task_failed]
        mock_outcome.model_dump.return_value = {"status": "partial"}

        mock_session = AsyncMock()

        with (
            patch(
                "modules.backend.agents.mission_control.mission_control.handle_mission",
                return_value=mock_outcome,
            ),
            patch(
                "modules.backend.core.database.get_async_session",
            ) as mock_get_session,
            patch(
                "modules.backend.services.session.SessionService",
            ),
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(
                return_value=False,
            )

            result = await execute_mission(
                MissionWorkflowInput(
                    mission_id="test-2",
                    session_id="sess-2",
                    mission_brief="Partial mission",
                ),
            )

            assert result.status == "partial"
            assert result.task_count == 2
            assert result.success_count == 1
            assert result.failed_count == 1

    @pytest.mark.asyncio
    async def test_returns_failed_on_exception(self):
        from modules.backend.temporal.activities import execute_mission

        mock_session = AsyncMock()

        with (
            patch(
                "modules.backend.agents.mission_control.mission_control.handle_mission",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "modules.backend.core.database.get_async_session",
            ) as mock_get_session,
            patch(
                "modules.backend.services.session.SessionService",
            ),
        ):
            mock_get_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_get_session.return_value.__aexit__ = AsyncMock(
                return_value=False,
            )

            result = await execute_mission(
                MissionWorkflowInput(
                    mission_id="test-3",
                    session_id="sess-3",
                    mission_brief="Failing mission",
                ),
            )

            assert result.status == "failed"
            assert result.mission_id == "test-3"
            assert "boom" in result.outcome_json["error"]
