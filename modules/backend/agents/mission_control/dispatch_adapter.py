"""Adapter between MissionService and Mission Control dispatch.

MissionService.execute_mission() expects a dispatch object with an
execute() method. This adapter wraps handle_mission() to provide
that interface for direct (non-Temporal) execution.
"""

from typing import Any

from modules.backend.agents.mission_control.mission_control import handle_mission
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


class MissionControlDispatchAdapter:
    """Wraps handle_mission() for use by MissionService."""

    def __init__(
        self,
        session_service: Any,
        db_session: Any,
        event_bus: Any | None = None,
    ) -> None:
        self._session_service = session_service
        self._db_session = db_session
        self._event_bus = event_bus

    async def execute(
        self,
        mission_brief: str,
        roster_ref: str = "default",
        complexity_tier: str = "simple",
        upstream_context: dict | None = None,
        cost_ceiling_usd: float | None = None,
        session_id: str | None = None,
    ) -> dict:
        """Execute a mission via handle_mission() and return result dict."""
        mission_id = f"mission-{session_id}" if session_id else "mission-adhoc"
        budget = cost_ceiling_usd or 10.0

        outcome = await handle_mission(
            mission_id=mission_id,
            mission_brief=mission_brief,
            session_service=self._session_service,
            event_bus=self._event_bus,
            roster_name=roster_ref,
            mission_budget_usd=budget,
            upstream_context=upstream_context,
            session_id=session_id,
        )

        outcome_dict = outcome.model_dump()
        outcome_dict["success"] = outcome.status in ("success", "partial")
        outcome_dict["summary"] = (
            f"Mission {outcome.status}: "
            f"{len(outcome.task_results)} tasks, "
            f"${outcome.total_cost_usd:.4f}"
        )

        return outcome_dict
