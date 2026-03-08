"""
PlaybookRun Repository.

CRUD plus playbook-run-specific queries: list by status,
lookup by playbook name, cost aggregation.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.models.mission import PlaybookRun, PlaybookRunState
from modules.backend.repositories.base import BaseRepository

logger = get_logger(__name__)


class PlaybookRunRepository(BaseRepository[PlaybookRun]):
    """PlaybookRun repository."""

    model = PlaybookRun

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_runs(
        self,
        playbook_name: str | None = None,
        status: PlaybookRunState | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[PlaybookRun], int]:
        """List playbook runs with optional filters."""
        conditions = []
        if playbook_name:
            conditions.append(PlaybookRun.playbook_name == playbook_name)
        if status:
            conditions.append(PlaybookRun.status == status)

        count_stmt = select(func.count()).select_from(PlaybookRun)
        if conditions:
            for cond in conditions:
                count_stmt = count_stmt.where(cond)
        total = (await self.session.execute(count_stmt)).scalar_one()

        data_stmt = (
            select(PlaybookRun)
            .order_by(PlaybookRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if conditions:
            for cond in conditions:
                data_stmt = data_stmt.where(cond)

        result = await self.session.execute(data_stmt)
        return list(result.scalars().all()), total
