"""Tests for SummarizationService.

Per P12: tests run against the live platform. Uses real db_session fixture
with transaction rollback for isolation.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.project_history import (
    DecisionStatus,
    ProjectDecision,
    MilestoneSummary,
)
from modules.backend.repositories.project_history import (
    ProjectDecisionRepository,
    MilestoneSummaryRepository,
)
from modules.backend.services.project_context import (
    ProjectContextManager,
    _cache,
)
from modules.backend.services.summarization import SummarizationService


@pytest.fixture
def manager(db_session: AsyncSession) -> ProjectContextManager:
    return ProjectContextManager(db_session)


@pytest.fixture
def summarization_service(db_session: AsyncSession) -> SummarizationService:
    return SummarizationService(db_session)


@pytest.fixture
def decision_repo(db_session: AsyncSession) -> ProjectDecisionRepository:
    return ProjectDecisionRepository(db_session)


@pytest.fixture
def milestone_repo(db_session: AsyncSession) -> MilestoneSummaryRepository:
    return MilestoneSummaryRepository(db_session)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear PCD cache between tests."""
    _cache.clear()
    yield
    _cache.clear()


class TestPrunePcdDecisions:
    @pytest.mark.asyncio
    async def test_no_pcd_returns_zero(self, summarization_service):
        """Returns 0 when project has no PCD."""
        result = await summarization_service.prune_pcd_decisions("nonexistent")
        assert result == 0

    @pytest.mark.asyncio
    async def test_no_decisions_returns_zero(
        self, summarization_service, manager,
    ):
        """Returns 0 when PCD has no decisions section."""
        await manager.create_context("proj-no-dec", "test", "desc")
        result = await summarization_service.prune_pcd_decisions("proj-no-dec")
        assert result == 0

    @pytest.mark.asyncio
    async def test_archives_old_decisions(
        self, summarization_service, manager, decision_repo,
    ):
        """Old decisions are archived to project_decisions table."""
        await manager.create_context("proj-prune", "test", "desc")

        # Add decisions to PCD — mix of old and recent
        decisions = [
            {
                "id": "d1", "domain": "api", "decision": "Use REST",
                "rationale": "Standard", "made_by": "architect",
                "date": "2020-01-01",
            },
            {
                "id": "d2", "domain": "auth", "decision": "Use JWT",
                "rationale": "Stateless", "made_by": "architect",
                "date": "2020-06-01",
            },
            {
                "id": "d3", "domain": "db", "decision": "Use PostgreSQL",
                "rationale": "ACID", "made_by": "architect",
                "date": "2099-01-01",  # far future — should be kept
            },
        ]
        await manager.apply_updates(
            "proj-prune",
            [{"op": "add", "path": "decisions", "value": decisions,
              "reason": "seed decisions"}],
            agent_id="test",
        )

        result = await summarization_service.prune_pcd_decisions(
            "proj-prune", max_age_days=90,
        )
        assert result == 2  # d1 and d2 archived

        # Verify archived in DB
        archived = await decision_repo.list_active("proj-prune")
        assert len(archived) == 2
        domains = {d.domain for d in archived}
        assert domains == {"api", "auth"}

        # Verify PCD only has the recent decision
        data = await manager.get_context("proj-prune")
        assert len(data["decisions"]) == 1
        assert data["decisions"][0]["id"] == "d3"

    @pytest.mark.asyncio
    async def test_all_recent_decisions_kept(
        self, summarization_service, manager,
    ):
        """All recent decisions stay in PCD, nothing archived."""
        await manager.create_context("proj-recent", "test", "desc")

        decisions = [
            {
                "id": "d1", "domain": "api", "decision": "Use REST",
                "rationale": "Standard", "made_by": "architect",
                "date": "2099-01-01",
            },
        ]
        await manager.apply_updates(
            "proj-recent",
            [{"op": "add", "path": "decisions", "value": decisions,
              "reason": "seed"}],
            agent_id="test",
        )

        result = await summarization_service.prune_pcd_decisions("proj-recent")
        assert result == 0


class TestPruneCompletedWorkstreams:
    @pytest.mark.asyncio
    async def test_no_pcd_returns_zero(self, summarization_service):
        result = await summarization_service.prune_completed_workstreams(
            "nonexistent",
        )
        assert result == 0

    @pytest.mark.asyncio
    async def test_few_milestones_not_pruned(
        self, summarization_service, manager,
    ):
        """5 or fewer milestones are not pruned."""
        await manager.create_context("proj-few", "test", "desc")
        await manager.apply_updates(
            "proj-few",
            [{"op": "add", "path": "current_state",
              "value": {"recent_milestones": ["m1", "m2", "m3"]},
              "reason": "seed"}],
            agent_id="test",
        )

        result = await summarization_service.prune_completed_workstreams(
            "proj-few",
        )
        assert result == 0

    @pytest.mark.asyncio
    async def test_archives_excess_milestones(
        self, summarization_service, manager, milestone_repo,
    ):
        """Milestones beyond keep_recent are archived."""
        await manager.create_context("proj-mile", "test", "desc")
        milestones = [f"milestone-{i}" for i in range(8)]
        await manager.apply_updates(
            "proj-mile",
            [{"op": "add", "path": "current_state",
              "value": {"recent_milestones": milestones},
              "reason": "seed"}],
            agent_id="test",
        )

        result = await summarization_service.prune_completed_workstreams(
            "proj-mile",
        )
        assert result == 3  # 8 - 5 = 3 archived

        # Verify milestone summary created
        summaries = await milestone_repo.list_by_project("proj-mile")
        assert len(summaries) == 1
        assert "3 items" in summaries[0].title
        assert len(summaries[0].key_outcomes["milestones"]) == 3

        # Verify PCD has only 5 milestones
        data = await manager.get_context("proj-mile")
        assert len(data["current_state"]["recent_milestones"]) == 5


class TestRunFullPipeline:
    @pytest.mark.asyncio
    async def test_runs_both_operations(
        self, summarization_service, manager,
    ):
        """Full pipeline runs both decision and milestone pruning."""
        await manager.create_context("proj-full", "test", "desc")

        # Add old decisions and excess milestones
        await manager.apply_updates(
            "proj-full",
            [
                {"op": "add", "path": "decisions", "value": [
                    {"id": "d1", "domain": "api", "decision": "x",
                     "rationale": "y", "made_by": "z", "date": "2020-01-01"},
                ], "reason": "seed"},
                {"op": "add", "path": "current_state", "value": {
                    "recent_milestones": [f"m{i}" for i in range(7)],
                }, "reason": "seed"},
            ],
            agent_id="test",
        )

        results = await summarization_service.run_full_pipeline("proj-full")
        assert results["decisions_archived"] == 1
        assert results["milestones_archived"] == 2

    @pytest.mark.asyncio
    async def test_pipeline_on_empty_project(self, summarization_service):
        """Pipeline on nonexistent project returns zeros."""
        results = await summarization_service.run_full_pipeline("nonexistent")
        assert results == {"decisions_archived": 0, "milestones_archived": 0}


class TestProjectDecisionRepository:
    @pytest.mark.asyncio
    async def test_list_by_domain(self, decision_repo, db_session):
        """Filters decisions by domain."""
        for domain in ["api", "api", "auth"]:
            await decision_repo.create(
                project_id="proj-repo",
                decision_id=f"d-{domain}",
                domain=domain,
                decision="test",
                rationale="test",
                made_by="test",
                status=DecisionStatus.ACTIVE,
            )

        api_decisions = await decision_repo.list_by_domain("proj-repo", "api")
        assert len(api_decisions) == 2

        auth_decisions = await decision_repo.list_by_domain("proj-repo", "auth")
        assert len(auth_decisions) == 1

    @pytest.mark.asyncio
    async def test_list_active_excludes_superseded(
        self, decision_repo, db_session,
    ):
        """Only active decisions are returned."""
        await decision_repo.create(
            project_id="proj-sup",
            decision_id="d-active",
            domain="api",
            decision="active",
            rationale="test",
            made_by="test",
            status=DecisionStatus.ACTIVE,
        )
        await decision_repo.create(
            project_id="proj-sup",
            decision_id="d-old",
            domain="api",
            decision="superseded",
            rationale="test",
            made_by="test",
            status=DecisionStatus.SUPERSEDED,
        )

        active = await decision_repo.list_active("proj-sup")
        assert len(active) == 1
        assert active[0].decision_id == "d-active"


class TestMilestoneSummaryRepository:
    @pytest.mark.asyncio
    async def test_list_by_project(self, milestone_repo, db_session):
        """Returns milestones for a specific project."""
        await milestone_repo.create(
            project_id="proj-ms",
            title="Phase 1",
            summary="Completed auth",
            mission_ids=["m1"],
            key_outcomes={"done": True},
            domain_tags=["auth"],
            period_end="2025-01-01",
        )
        await milestone_repo.create(
            project_id="proj-ms",
            title="Phase 2",
            summary="Completed API",
            mission_ids=["m2"],
            key_outcomes={"done": True},
            domain_tags=["api"],
            period_end="2025-02-01",
        )
        await milestone_repo.create(
            project_id="proj-other",
            title="Other",
            summary="Other project",
            mission_ids=[],
            key_outcomes={},
            domain_tags=[],
            period_end="2025-03-01",
        )

        results = await milestone_repo.list_by_project("proj-ms")
        assert len(results) == 2
        titles = {m.title for m in results}
        assert titles == {"Phase 1", "Phase 2"}

    @pytest.mark.asyncio
    async def test_respects_limit(self, milestone_repo, db_session):
        for i in range(5):
            await milestone_repo.create(
                project_id="proj-lim",
                title=f"Phase {i}",
                summary=f"Summary {i}",
                mission_ids=[],
                key_outcomes={},
                domain_tags=[],
                period_end=f"2025-0{i+1}-01",
            )

        results = await milestone_repo.list_by_project("proj-lim", limit=2)
        assert len(results) == 2
