"""
Project Context Repository.

Data access for PCD and context change audit trail.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.project_context import (
    ContextChange,
    ProjectContext,
)
from modules.backend.repositories.base import BaseRepository


class ProjectContextRepository(BaseRepository[ProjectContext]):
    """Repository for ProjectContext CRUD."""

    model = ProjectContext

    async def get_by_project_id(self, project_id: str) -> ProjectContext | None:
        """Get PCD by project ID."""
        result = await self.session.execute(
            select(ProjectContext)
            .where(ProjectContext.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def update_context(
        self,
        project_id: str,
        context_data: dict,
        new_version: int,
        size_characters: int,
        size_tokens: int,
    ) -> int:
        """Atomically update PCD with optimistic concurrency.

        Returns number of rows updated (0 if version conflict).
        """
        result = await self.session.execute(
            update(ProjectContext)
            .where(ProjectContext.project_id == project_id)
            .where(ProjectContext.version == new_version - 1)
            .values(
                context_data=context_data,
                version=new_version,
                size_characters=size_characters,
                size_tokens=size_tokens,
            )
        )
        return result.rowcount


class ContextChangeRepository(BaseRepository[ContextChange]):
    """Repository for context change audit trail."""

    model = ContextChange

    async def list_by_context(
        self,
        context_id: str,
        limit: int = 50,
    ) -> list[ContextChange]:
        """List recent changes for a PCD."""
        result = await self.session.execute(
            select(ContextChange)
            .where(ContextChange.context_id == context_id)
            .order_by(ContextChange.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_agent(
        self,
        context_id: str,
        agent_id: str,
        limit: int = 20,
    ) -> list[ContextChange]:
        """List changes made by a specific agent."""
        result = await self.session.execute(
            select(ContextChange)
            .where(ContextChange.context_id == context_id)
            .where(ContextChange.agent_id == agent_id)
            .order_by(ContextChange.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
