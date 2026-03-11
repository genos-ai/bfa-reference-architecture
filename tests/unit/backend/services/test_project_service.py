"""Tests for ProjectService.

Per P12: tests run against the live platform. Uses real db_session fixture
with transaction rollback for isolation.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.exceptions import ConflictError, NotFoundError
from modules.backend.models.project import ProjectMemberRole, ProjectStatus
from modules.backend.services.project import ProjectService


@pytest.fixture
def service(db_session: AsyncSession) -> ProjectService:
    return ProjectService(db_session)


class TestCreateProject:
    @pytest.mark.asyncio
    async def test_creates_project(self, service):
        project = await service.create_project(
            name="test-project",
            description="A test project",
            owner_id="user:test",
        )
        assert project.id is not None
        assert project.name == "test-project"
        assert project.description == "A test project"
        assert project.owner_id == "user:test"
        assert project.status == ProjectStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_creates_owner_membership(self, service):
        project = await service.create_project(
            name="test-membership",
            description="Test membership creation",
            owner_id="user:owner",
        )
        members = await service._member_repo.get_members(project.id)
        assert len(members) == 1
        assert members[0].user_id == "user:owner"
        assert members[0].role == ProjectMemberRole.OWNER

    @pytest.mark.asyncio
    async def test_duplicate_name_raises_conflict(self, service):
        await service.create_project(
            name="unique-name",
            description="First project",
            owner_id="user:test",
        )
        with pytest.raises(ConflictError, match="already exists"):
            await service.create_project(
                name="unique-name",
                description="Second project",
                owner_id="user:test",
            )

    @pytest.mark.asyncio
    async def test_optional_fields(self, service):
        project = await service.create_project(
            name="full-project",
            description="With all fields",
            owner_id="user:test",
            team_id="team-alpha",
            default_roster="research",
            budget_ceiling_usd=50.0,
            repo_url="https://github.com/test/repo",
            repo_root="/home/test/repo",
        )
        assert project.team_id == "team-alpha"
        assert project.default_roster == "research"
        assert project.budget_ceiling_usd == 50.0
        assert project.repo_url == "https://github.com/test/repo"
        assert project.repo_root == "/home/test/repo"


class TestGetProject:
    @pytest.mark.asyncio
    async def test_get_by_id(self, service):
        created = await service.create_project(
            name="get-test", description="Get test", owner_id="user:test",
        )
        result = await service.get_project(created.id)
        assert result.name == "get-test"

    @pytest.mark.asyncio
    async def test_get_not_found_raises(self, service):
        with pytest.raises(NotFoundError):
            await service.get_project("nonexistent-id")

    @pytest.mark.asyncio
    async def test_get_by_name(self, service):
        await service.create_project(
            name="named-project", description="Named", owner_id="user:test",
        )
        result = await service.get_project_by_name("named-project")
        assert result is not None
        assert result.name == "named-project"

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(self, service):
        result = await service.get_project_by_name("no-such-project")
        assert result is None


class TestListProjects:
    @pytest.mark.asyncio
    async def test_list_active(self, service):
        await service.create_project(
            name="active-one", description="Active", owner_id="user:test",
        )
        await service.create_project(
            name="active-two", description="Active", owner_id="user:test",
        )
        projects = await service.list_projects()
        assert len(projects) >= 2

    @pytest.mark.asyncio
    async def test_list_by_owner(self, service):
        await service.create_project(
            name="owner-a", description="A", owner_id="user:alice",
        )
        await service.create_project(
            name="owner-b", description="B", owner_id="user:bob",
        )
        alice_projects = await service.list_projects(owner_id="user:alice")
        assert all(p.owner_id == "user:alice" for p in alice_projects)


class TestUpdateProject:
    @pytest.mark.asyncio
    async def test_update_description(self, service):
        project = await service.create_project(
            name="update-test", description="Original", owner_id="user:test",
        )
        updated = await service.update_project(
            project.id, description="Updated description",
        )
        assert updated.description == "Updated description"


class TestArchiveProject:
    @pytest.mark.asyncio
    async def test_archive(self, service):
        project = await service.create_project(
            name="archive-test", description="To archive", owner_id="user:test",
        )
        archived = await service.archive_project(project.id)
        assert archived.status == ProjectStatus.ARCHIVED

    @pytest.mark.asyncio
    async def test_archived_not_in_active_list(self, service):
        project = await service.create_project(
            name="archived-hidden", description="Hidden", owner_id="user:test",
        )
        await service.archive_project(project.id)
        active = await service.list_projects()
        assert all(p.id != project.id for p in active)
