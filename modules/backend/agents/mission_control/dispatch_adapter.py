"""Adapter between MissionService and Mission Control dispatch.

MissionService.execute_mission() expects a dispatch object with an
execute() method. This adapter wraps handle_mission() to provide
that interface for direct (non-Temporal) execution.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from modules.backend.agents.mission_control.mission_control import handle_mission
from modules.backend.agents.mission_control.models import EventBusProtocol, NoOpEventBus
from modules.backend.core.config import find_project_root
from modules.backend.core.protocols import SessionServiceProtocol
from modules.backend.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class MissionControlDispatchAdapter:
    """Wraps handle_mission() for use by MissionService."""

    def __init__(
        self,
        session_service: SessionServiceProtocol,
        db_session: AsyncSession,
        event_bus: EventBusProtocol = NoOpEventBus(),
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
        project_id: str | None = None,
        gate: object | None = None,
    ) -> dict:
        """Execute a mission via handle_mission() and return result dict."""
        mission_id = f"mission-{session_id}" if session_id else "mission-adhoc"
        budget = cost_ceiling_usd or 10.0

        # Select roster based on complexity_tier if a tier-specific roster exists
        roster_name = roster_ref
        if complexity_tier != "simple":
            tier_roster = (
                find_project_root()
                / "config" / "mission_control" / "rosters"
                / f"{roster_ref}-{complexity_tier}.yaml"
            )
            if os.path.exists(tier_roster):
                roster_name = f"{roster_ref}-{complexity_tier}"
                logger.info(
                    "Using complexity-tier roster",
                    extra={
                        "complexity_tier": complexity_tier,
                        "roster": roster_name,
                    },
                )

        outcome = await handle_mission(
            mission_id=mission_id,
            mission_brief=mission_brief,
            session_service=self._session_service,
            event_bus=self._event_bus,
            roster_name=roster_name,
            mission_budget_usd=budget,
            upstream_context=upstream_context,
            session_id=session_id,
            project_id=project_id,
            db_session=self._db_session,
            gate=gate,
        )

        outcome_dict = outcome.model_dump()
        outcome_dict["success"] = outcome.status in ("success", "partial")
        outcome_dict["summary"] = (
            f"Mission {outcome.status}: "
            f"{len(outcome.task_results)} tasks, "
            f"${outcome.total_cost_usd:.4f}"
        )

        return outcome_dict
