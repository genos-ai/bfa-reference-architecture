"""
Mission Repository.

Standard CRUD plus mission-specific queries: lookup by playbook run,
active mission count, and status filtering.
"""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.models.mission import Mission, MissionState
from modules.backend.repositories.base import BaseRepository

logger = get_logger(__name__)


class MissionRepository(BaseRepository[Mission]):
    """Mission repository with workflow-specific queries."""

    model = Mission

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_session(self, session_id: str) -> list[Mission]:
        """Get all missions for a session."""
        stmt = (
            select(Mission)
            .where(Mission.session_id == session_id)
            .order_by(Mission.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_playbook_run(
        self, playbook_run_id: str,
    ) -> list[Mission]:
        """Get all missions for a specific playbook run."""
        stmt = (
            select(Mission)
            .where(Mission.playbook_run_id == playbook_run_id)
            .order_by(Mission.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_active(self) -> int:
        """Count currently running missions (for concurrency limits)."""
        stmt = (
            select(func.count())
            .select_from(Mission)
            .where(
                Mission.status.in_([
                    MissionState.PENDING,
                    MissionState.RUNNING,
                ])
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_missions(
        self,
        status: MissionState | None = None,
        playbook_run_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Mission], int]:
        """List missions with optional filters and pagination.

        Returns:
            Tuple of (missions, total_count).
        """
        conditions = []
        if status:
            conditions.append(Mission.status == status)
        if playbook_run_id:
            conditions.append(Mission.playbook_run_id == playbook_run_id)

        count_stmt = select(func.count()).select_from(Mission)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.session.execute(count_stmt)).scalar_one()

        data_stmt = (
            select(Mission)
            .order_by(Mission.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if conditions:
            data_stmt = data_stmt.where(and_(*conditions))

        result = await self.session.execute(data_stmt)
        return list(result.scalars().all()), total
