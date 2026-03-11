"""
Project Repository.

Data access for projects and project membership.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.project import (
    Project,
    ProjectMember,
    ProjectStatus,
)
from modules.backend.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for Project CRUD and queries."""

    model = Project

    async def get_by_name(self, name: str) -> Project | None:
        """Get a project by unique name."""
        result = await self.session.execute(
            select(Project).where(Project.name == name)
        )
        return result.scalar_one_or_none()

    async def list_by_owner(
        self,
        owner_id: str,
        status: ProjectStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        """List projects owned by a user, optionally filtered by status."""
        query = select(Project).where(Project.owner_id == owner_id)
        if status:
            query = query.where(Project.status == status)
        query = query.order_by(Project.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_active(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        """List all active projects."""
        result = await self.session.execute(
            select(Project)
            .where(Project.status == ProjectStatus.ACTIVE)
            .order_by(Project.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())


class ProjectMemberRepository(BaseRepository[ProjectMember]):
    """Repository for project membership queries."""

    model = ProjectMember

    async def get_members(
        self,
        project_id: str,
    ) -> list[ProjectMember]:
        """Get all members of a project."""
        result = await self.session.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.created_at)
        )
        return list(result.scalars().all())

    async def get_membership(
        self,
        project_id: str,
        user_id: str,
    ) -> ProjectMember | None:
        """Get a specific user's membership in a project."""
        result = await self.session.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .where(ProjectMember.user_id == user_id)
        )
        return result.scalar_one_or_none()
