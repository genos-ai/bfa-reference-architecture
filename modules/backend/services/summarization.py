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

from sqlalchemy import select, update, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.backend.core.logging import get_logger
from modules.backend.models.mission_record import (
    MissionRecord,
    MissionRecordStatus,
    TaskExecution,
)
from modules.backend.models.project_history import DecisionStatus
from modules.backend.repositories.project_history import (
    MilestoneSummaryRepository,
    ProjectDecisionRepository,
)
from modules.backend.services.base import BaseService
from modules.backend.services.project_context import ProjectContextManager

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

    async def summarize_mission_records(
        self,
        project_id: str,
        max_age_days: int = 30,
        batch_size: int = 10,
    ) -> int:
        """Compress old completed mission records into milestone summaries.

        Finds MissionRecords older than max_age_days that haven't been
        summarized yet, groups them into batches, and creates
        MilestoneSummary records. Marks originals as summarized=True.

        Raw data is never deleted — only excluded from default queries.
        Returns count of missions summarized.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max_age_days)
        ).isoformat()

        result = await self.session.execute(
            select(MissionRecord)
            .options(selectinload(MissionRecord.task_executions))
            .where(
                and_(
                    MissionRecord.project_id == project_id,
                    MissionRecord.summarized == False,  # noqa: E712
                    MissionRecord.status.in_([
                        MissionRecordStatus.COMPLETED,
                        MissionRecordStatus.FAILED,
                    ]),
                    MissionRecord.completed_at < cutoff,
                )
            )
            .order_by(desc(MissionRecord.completed_at))
            .limit(batch_size * 5)
        )
        records = list(result.scalars().all())

        if not records:
            return 0

        # Process in batches
        total_summarized = 0
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            mission_ids = [r.id for r in batch]
            objectives = [
                r.objective_statement or "(no objective)"
                for r in batch
            ]
            statuses = [r.status for r in batch]

            # Determine period range
            completed_dates = [
                r.completed_at for r in batch if r.completed_at
            ]
            period_start = min(completed_dates) if completed_dates else None
            period_end = max(completed_dates) if completed_dates else None

            # Collect domain tags from task executions
            all_domain_tags: set[str] = set()
            for r in batch:
                if r.task_executions:
                    for te in r.task_executions:
                        if te.domain_tags:
                            all_domain_tags.update(te.domain_tags)

            # Build deterministic summary (no LLM needed for structured data)
            completed_count = sum(
                1 for s in statuses if s == MissionRecordStatus.COMPLETED
            )
            failed_count = sum(
                1 for s in statuses if s == MissionRecordStatus.FAILED
            )
            total_cost = sum(r.total_cost_usd for r in batch)

            summary_parts = [
                f"{len(batch)} missions ({completed_count} completed, "
                f"{failed_count} failed). Total cost: ${total_cost:.4f}.",
            ]
            for obj in objectives[:5]:
                summary_parts.append(f"- {obj[:100]}")
            if len(objectives) > 5:
                summary_parts.append(f"  ... and {len(objectives) - 5} more")

            await self._milestone_repo.create(
                project_id=project_id,
                title=f"Missions batch ({len(batch)} missions)",
                summary="\n".join(summary_parts),
                mission_ids=mission_ids,
                key_outcomes={
                    "completed": completed_count,
                    "failed": failed_count,
                    "total_cost_usd": round(total_cost, 4),
                    "objectives": objectives[:10],
                },
                domain_tags=sorted(all_domain_tags),
                period_start=period_start,
                period_end=period_end,
            )

            # Mark missions as summarized
            await self.session.execute(
                update(MissionRecord)
                .where(MissionRecord.id.in_(mission_ids))
                .values(summarized=True)
            )

            total_summarized += len(batch)

        self._log_operation(
            "Mission records summarized",
            project_id=project_id,
            missions_summarized=total_summarized,
        )

        return total_summarized

    async def run_full_pipeline(
        self,
        project_id: str,
    ) -> dict:
        """Run the full summarization pipeline for a project.

        Returns summary of actions taken.
        """
        results = {
            "decisions_archived": 0,
            "missions_summarized": 0,
            "milestones_archived": 0,
        }

        results["decisions_archived"] = await self.prune_pcd_decisions(
            project_id,
        )
        results["missions_summarized"] = await self.summarize_mission_records(
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
