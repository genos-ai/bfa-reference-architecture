"""
Project Service.

Business logic for project lifecycle management, membership,
and project-scoping enforcement.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.models.project import (
    Project,
    ProjectMemberRole,
    ProjectStatus,
)
from modules.backend.repositories.project import (
    ProjectMemberRepository,
    ProjectRepository,
)
from modules.backend.services.base import BaseService

logger = get_logger(__name__)


class ProjectService(BaseService):
    """Service for project CRUD, membership, and scoping."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._project_repo = ProjectRepository(session)
        self._member_repo = ProjectMemberRepository(session)

    @staticmethod
    @asynccontextmanager
    async def factory() -> AsyncGenerator["ProjectService", None]:
        """Create a ProjectService with its own DB session."""
        from modules.backend.core.database import get_async_session

        async with get_async_session() as db:
            yield ProjectService(db)
            await db.commit()

    async def create_project(
        self,
        *,
        name: str,
        description: str,
        owner_id: str,
        team_id: str | None = None,
        default_roster: str = "default",
        budget_ceiling_usd: float | None = None,
        repo_url: str | None = None,
        repo_root: str | None = None,
    ) -> Project:
        """Create a new project with initial owner membership.

        Creates: projects row, project_members row (owner).
        PCD creation is added in Sub-Phase 2.
        """
        # Check unique name
        existing = await self._project_repo.get_by_name(name)
        if existing:
            from modules.backend.core.exceptions import ConflictError
            raise ConflictError(f"Project name already exists: {name}")

        project = await self._project_repo.create(
            name=name,
            description=description,
            owner_id=owner_id,
            team_id=team_id,
            default_roster=default_roster,
            budget_ceiling_usd=budget_ceiling_usd,
            repo_url=repo_url,
            repo_root=repo_root,
        )

        # Auto-create owner membership
        await self._member_repo.create(
            project_id=project.id,
            user_id=owner_id,
            role=ProjectMemberRole.OWNER,
        )

        self._log_operation(
            "Project created",
            project_id=project.id,
            project_name=name,
        )
        return project

    async def get_project(self, project_id: str) -> Project:
        """Get a project by ID. Raises NotFoundError if not found."""
        return await self._project_repo.get_by_id(project_id)

    async def get_project_by_name(self, name: str) -> Project | None:
        """Get a project by name. Returns None if not found."""
        return await self._project_repo.get_by_name(name)

    async def list_projects(
        self,
        owner_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Project]:
        """List projects, optionally filtered by owner and/or status."""
        if owner_id:
            status_enum = ProjectStatus(status) if status else None
            return await self._project_repo.list_by_owner(
                owner_id, status=status_enum, limit=limit,
            )
        return await self._project_repo.list_active(limit=limit)

    async def update_project(
        self,
        project_id: str,
        **updates,
    ) -> Project:
        """Update project fields."""
        return await self._project_repo.update(project_id, **updates)

    async def archive_project(self, project_id: str) -> Project:
        """Archive a project. No new missions can be created."""
        return await self._project_repo.update(
            project_id, status=ProjectStatus.ARCHIVED,
        )
