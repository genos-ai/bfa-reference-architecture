"""
Project History Repository.

Data access for archived decisions and milestone summaries.
"""

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.project_history import (
    DecisionStatus,
    MilestoneSummary,
    ProjectDecision,
)
from modules.backend.repositories.base import BaseRepository


class ProjectDecisionRepository(BaseRepository[ProjectDecision]):
    """Repository for project decisions."""

    model = ProjectDecision

    async def list_by_domain(
        self,
        project_id: str,
        domain: str,
        limit: int = 20,
    ) -> list[ProjectDecision]:
        """Get active decisions for a domain, most recent first."""
        result = await self.session.execute(
            select(ProjectDecision)
            .where(ProjectDecision.project_id == project_id)
            .where(ProjectDecision.domain == domain)
            .where(ProjectDecision.status == DecisionStatus.ACTIVE)
            .order_by(desc(ProjectDecision.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_active(
        self,
        project_id: str,
        limit: int = 50,
    ) -> list[ProjectDecision]:
        """Get all active decisions for a project."""
        result = await self.session.execute(
            select(ProjectDecision)
            .where(ProjectDecision.project_id == project_id)
            .where(ProjectDecision.status == DecisionStatus.ACTIVE)
            .order_by(desc(ProjectDecision.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())


class MilestoneSummaryRepository(BaseRepository[MilestoneSummary]):
    """Repository for milestone summaries."""

    model = MilestoneSummary

    async def list_by_project(
        self,
        project_id: str,
        limit: int = 20,
    ) -> list[MilestoneSummary]:
        """Get milestones for a project, most recent first."""
        result = await self.session.execute(
            select(MilestoneSummary)
            .where(MilestoneSummary.project_id == project_id)
            .order_by(desc(MilestoneSummary.period_end))
            .limit(limit)
        )
        return list(result.scalars().all())
