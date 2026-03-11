"""
History Query Service.

Structured queries over project history for Layer 2 context retrieval.
All queries are project-scoped. No semantic search — only structured filters.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.logging import get_logger
from modules.backend.models.mission_record import (
    MissionRecord,
    TaskAttemptStatus,
    TaskAttempt,
    TaskExecution,
)
from modules.backend.services.base import BaseService

logger = get_logger(__name__)


class HistoryQueryService(BaseService):
    """Structured queries over project history."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    @staticmethod
    @asynccontextmanager
    async def factory() -> AsyncGenerator["HistoryQueryService", None]:
        """Create a HistoryQueryService with its own DB session."""
        from modules.backend.core.database import get_async_session

        async with get_async_session() as db:
            yield HistoryQueryService(db)

    async def get_recent_task_executions(
        self,
        project_id: str,
        *,
        domain_tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Get recent task executions, optionally filtered by domain tags.

        Returns dicts with task_id, agent_name, status, domain_tags,
        cost_usd, duration_seconds, completed_at.
        """
        query = (
            select(TaskExecution)
            .join(MissionRecord, TaskExecution.mission_record_id == MissionRecord.id)
            .where(MissionRecord.project_id == project_id)
            .order_by(desc(TaskExecution.completed_at))
            .limit(limit)
        )
        result = await self.session.execute(query)
        executions = list(result.scalars().all())

        # Domain tag filtering (post-filter for SQLite compatibility)
        if domain_tags:
            executions = [
                e for e in executions
                if e.domain_tags and any(tag in e.domain_tags for tag in domain_tags)
            ]

        return [
            {
                "task_id": e.task_id,
                "agent_name": e.agent_name,
                "status": e.status,
                "domain_tags": e.domain_tags,
                "cost_usd": e.cost_usd,
                "duration_seconds": e.duration_seconds,
                "completed_at": e.completed_at,
            }
            for e in executions[:limit]
        ]

    async def get_recent_failures(
        self,
        project_id: str,
        *,
        domain_tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Get recent failed task attempts for a project.

        Returns failure reason and feedback so agents don't repeat mistakes.
        """
        query = (
            select(TaskAttempt, TaskExecution)
            .join(TaskExecution, TaskAttempt.task_execution_id == TaskExecution.id)
            .join(MissionRecord, TaskExecution.mission_record_id == MissionRecord.id)
            .where(MissionRecord.project_id == project_id)
            .where(TaskAttempt.status == TaskAttemptStatus.FAILED)
            .order_by(desc(TaskAttempt.created_at))
            .limit(limit)
        )
        result = await self.session.execute(query)
        rows = result.all()

        failures = []
        for attempt, execution in rows:
            if domain_tags and execution.domain_tags:
                if not any(tag in execution.domain_tags for tag in domain_tags):
                    continue
            failures.append({
                "task_id": execution.task_id,
                "agent_name": execution.agent_name,
                "failure_tier": attempt.failure_tier,
                "failure_reason": attempt.failure_reason,
                "feedback_provided": attempt.feedback_provided,
                "domain_tags": execution.domain_tags,
            })

        return failures[:limit]

    async def get_mission_summaries(
        self,
        project_id: str,
        *,
        limit: int = 10,
    ) -> list[dict]:
        """Get recent mission outcome summaries for a project."""
        result = await self.session.execute(
            select(MissionRecord)
            .where(MissionRecord.project_id == project_id)
            .order_by(desc(MissionRecord.completed_at))
            .limit(limit)
        )
        records = list(result.scalars().all())

        return [
            {
                "id": r.id,
                "objective": r.objective_statement,
                "status": r.status,
                "total_cost_usd": r.total_cost_usd,
                "completed_at": r.completed_at,
            }
            for r in records
        ]
