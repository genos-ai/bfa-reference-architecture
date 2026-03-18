"""Async service wrappers for the TUI.

Bridges Textual's @work coroutines to backend service factories.
Each method opens its own DB session, keeping the TUI stateless
with respect to database connections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from modules.backend.agents.mission_control.gate import GateReviewer
from modules.backend.agents.mission_control.mission_control import handle_mission
from modules.backend.agents.mission_control.models import EventBusProtocol, NoOpEventBus
from modules.backend.agents.mission_control.outcome import MissionOutcome
from modules.backend.agents.mission_control.roster import load_roster, Roster
from modules.backend.core.database import get_async_session
from modules.backend.core.logging import get_logger
from modules.backend.services.project import ProjectService
from modules.backend.services.session import SessionService

if TYPE_CHECKING:
    from modules.backend.models.project import Project

logger = get_logger(__name__)


class ServiceBridge:
    """Facade that wraps backend service factories for TUI consumption.

    Every public method manages its own DB session via async context manager.
    The TUI never sees raw SQLAlchemy sessions.
    """

    def __init__(
        self,
        *,
        event_bus: EventBusProtocol = NoOpEventBus(),
    ) -> None:
        self._event_bus = event_bus

    # ── Project operations ───────────────────────────────────────────

    async def list_projects(self) -> list[dict[str, Any]]:
        """Return all active projects as dicts."""
        async with get_async_session() as db:
            svc = ProjectService(db)
            projects = await svc.list_projects()
            return [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "description": p.description,
                    "status": p.status,
                }
                for p in projects
            ]

    async def create_project(
        self,
        *,
        name: str,
        description: str,
    ) -> dict[str, str]:
        """Create a project and return its id and name."""
        async with get_async_session() as db:
            svc = ProjectService(db)
            project = await svc.create_project(name=name, description=description)
            await db.commit()
            return {"id": str(project.id), "name": project.name}

    async def get_project(self, project_id: str) -> Project | None:
        """Fetch a single project by ID."""
        async with get_async_session() as db:
            svc = ProjectService(db)
            return await svc.get_project(project_id)

    # ── Roster ───────────────────────────────────────────────────────

    def load_roster(self, roster_name: str = "default") -> Roster:
        """Load agent roster from YAML config."""
        return load_roster(roster_name)

    # ── Mission execution ────────────────────────────────────────────

    async def run_mission(
        self,
        *,
        brief: str,
        project_id: str,
        session_id: str,
        roster_name: str = "default",
        budget_usd: float = 10.0,
        gate: GateReviewer | None = None,
    ) -> MissionOutcome:
        """Execute a mission in-process with full event streaming.

        This is the TUI's primary execution path. It calls handle_mission()
        directly, wiring the TuiGateReviewer and TuiEventBus.
        """
        async with get_async_session() as db:
            session_service = SessionService(db)
            mission_id = f"tui-{session_id}"

            outcome = await handle_mission(
                mission_id=mission_id,
                mission_brief=brief,
                session_service=session_service,
                event_bus=self._event_bus,
                roster_name=roster_name,
                mission_budget_usd=budget_usd,
                session_id=session_id,
                project_id=project_id,
                db_session=db,
                gate=gate,
            )

            await db.commit()
            return outcome
