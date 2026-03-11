"""
Summarization Service.

Fractal compression pipeline for project history:
  Task executions -> Mission summaries -> Milestone summaries -> PCD

Runs periodically or on-demand. Never deletes raw data — only marks
as summarized and excludes from default queries.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

from modules.backend.core.logging import get_logger
from modules.backend.models.project_history import DecisionStatus
from modules.backend.repositories.project_history import (
    MilestoneSummaryRepository,
    ProjectDecisionRepository,
)
from modules.backend.services.base import BaseService
from modules.backend.services.project_context import ProjectContextManager

from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class SummarizationService(BaseService):
    """Fractal compression pipeline for project history."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._decision_repo = ProjectDecisionRepository(session)
        self._milestone_repo = MilestoneSummaryRepository(session)
        self._context_manager = ProjectContextManager(session)

    @staticmethod
    @asynccontextmanager
    async def factory() -> AsyncGenerator["SummarizationService", None]:
        """Create a SummarizationService with its own DB session."""
        from modules.backend.core.database import get_async_session

        async with get_async_session() as db:
            yield SummarizationService(db)
            await db.commit()

    async def prune_pcd_decisions(
        self,
        project_id: str,
        max_age_days: int = 90,
    ) -> int:
        """Archive decisions older than max_age_days from PCD to project_decisions table.

        Returns count of decisions archived.
        """
        data, version = await self._context_manager.get_context_with_version(
            project_id,
        )
        if not data:
            return 0

        decisions = data.get("decisions", [])
        if not decisions:
            return 0

        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max_age_days)
        ).isoformat()[:10]
        to_archive = []
        to_keep = []

        for d in decisions:
            if d.get("date", "") < cutoff:
                to_archive.append(d)
            else:
                to_keep.append(d)

        if not to_archive:
            return 0

        # Archive to project_decisions table
        for d in to_archive:
            await self._decision_repo.create(
                project_id=project_id,
                decision_id=d.get("id", ""),
                domain=d.get("domain", "general"),
                decision=d.get("decision", ""),
                rationale=d.get("rationale", ""),
                made_by=d.get("made_by", "unknown"),
                mission_id=d.get("mission_id"),
                status=DecisionStatus.ACTIVE,
            )

        # Update PCD with pruned decisions list
        await self._context_manager.apply_updates(
            project_id,
            [{
                "op": "replace",
                "path": "decisions",
                "value": to_keep,
                "reason": (
                    f"Archived {len(to_archive)} decisions "
                    f"older than {max_age_days} days"
                ),
            }],
            agent_id="system:summarization",
        )

        self._log_operation(
            "PCD decisions pruned",
            project_id=project_id,
            archived=len(to_archive),
            remaining=len(to_keep),
        )

        return len(to_archive)

    async def prune_completed_workstreams(
        self,
        project_id: str,
        keep_recent: int = 5,
    ) -> int:
        """Move old milestones from current_state to milestone_summaries table.

        Keeps the most recent `keep_recent` milestones in the PCD.
        Returns count of milestones archived.
        """
        data, version = await self._context_manager.get_context_with_version(
            project_id,
        )
        if not data:
            return 0

        current_state = data.get("current_state", {})
        milestones = current_state.get("recent_milestones", [])

        if len(milestones) <= keep_recent:
            return 0

        to_keep = milestones[:keep_recent]
        to_archive = milestones[keep_recent:]

        # Create milestone summary for archived items
        await self._milestone_repo.create(
            project_id=project_id,
            title=f"Milestones batch ({len(to_archive)} items)",
            summary="; ".join(
                m if isinstance(m, str) else str(m) for m in to_archive
            ),
            mission_ids=[],
            key_outcomes={"milestones": to_archive},
            domain_tags=[],
            period_end=datetime.now(timezone.utc).isoformat(),
        )

        # Update PCD with pruned milestones list
        await self._context_manager.apply_updates(
            project_id,
            [{
                "op": "replace",
                "path": "current_state.recent_milestones",
                "value": to_keep,
                "reason": f"Archived {len(to_archive)} old milestones",
            }],
            agent_id="system:summarization",
        )

        self._log_operation(
            "Milestones pruned",
            project_id=project_id,
            archived=len(to_archive),
            remaining=len(to_keep),
        )

        return len(to_archive)

    async def run_full_pipeline(
        self,
        project_id: str,
    ) -> dict:
        """Run the full summarization pipeline for a project.

        Returns summary of actions taken.
        """
        results = {
            "decisions_archived": 0,
            "milestones_archived": 0,
        }

        results["decisions_archived"] = await self.prune_pcd_decisions(
            project_id,
        )
        results["milestones_archived"] = await self.prune_completed_workstreams(
            project_id,
        )

        self._log_operation(
            "Summarization pipeline complete",
            project_id=project_id,
            **results,
        )

        return results
