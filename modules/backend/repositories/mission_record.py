"""
Mission Record Repository.

Standard CRUD plus mission-specific queries: cost aggregation,
status filtering, session lookups, re-plan lineage.
"""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.backend.core.logging import get_logger
from modules.backend.models.mission_record import (
    MissionDecision,
    MissionRecord,
    MissionRecordStatus,
    TaskExecution,
)
from modules.backend.repositories.base import BaseRepository

logger = get_logger(__name__)


class MissionRecordRepository(BaseRepository[MissionRecord]):
    """Mission record repository with audit-specific queries."""

    model = MissionRecord

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_with_details(self, mission_id: str) -> MissionRecord | None:
        """Get mission record with task executions and decisions eagerly loaded."""
        stmt = (
            select(MissionRecord)
            .where(MissionRecord.id == mission_id)
            .options(
                selectinload(MissionRecord.task_executions)
                .selectinload(TaskExecution.attempts),
                selectinload(MissionRecord.decisions),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_session(self, session_id: str) -> list[MissionRecord]:
        """Get all mission records for a session, newest first."""
        stmt = (
            select(MissionRecord)
            .where(MissionRecord.session_id == session_id)
            .order_by(MissionRecord.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_missions(
        self,
        status: MissionRecordStatus | None = None,
        roster_name: str | None = None,
        objective_category: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[MissionRecord], int]:
        """List mission records with optional filters and pagination."""
        conditions = []
        if status:
            conditions.append(MissionRecord.status == status)
        if roster_name:
            conditions.append(MissionRecord.roster_name == roster_name)
        if objective_category:
            conditions.append(MissionRecord.objective_category == objective_category)

        count_stmt = select(func.count()).select_from(MissionRecord)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.session.execute(count_stmt)).scalar_one()

        data_stmt = (
            select(MissionRecord)
            .order_by(MissionRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if conditions:
            data_stmt = data_stmt.where(and_(*conditions))

        result = await self.session.execute(data_stmt)
        return list(result.scalars().all()), total

    async def get_decisions(self, mission_id: str) -> list[MissionDecision]:
        """Get all decisions for a mission, ordered chronologically."""
        stmt = (
            select(MissionDecision)
            .where(MissionDecision.mission_record_id == mission_id)
            .order_by(MissionDecision.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_task_executions(
        self, mission_id: str,
    ) -> list[TaskExecution]:
        """Get all task executions for a mission with attempts loaded."""
        stmt = (
            select(TaskExecution)
            .where(TaskExecution.mission_record_id == mission_id)
            .options(selectinload(TaskExecution.attempts))
            .order_by(TaskExecution.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_cost_by_model(self, mission_id: str) -> dict[str, float]:
        """Aggregate cost by model for a mission."""
        executions = await self.get_task_executions(mission_id)
        model_costs: dict[str, float] = {}
        for execution in executions:
            if execution.token_usage and "model" in execution.token_usage:
                model = execution.token_usage["model"]
                model_costs[model] = model_costs.get(model, 0.0) + execution.cost_usd
        return model_costs

    async def get_replan_chain(self, mission_id: str) -> list[MissionRecord]:
        """Get the full re-plan lineage for a mission.

        Follows parent_mission_id links to build the chain.
        Returns oldest-first.
        """
        chain: list[MissionRecord] = []
        current_id: str | None = mission_id

        while current_id:
            mission = await self.get_by_id_or_none(current_id)
            if not mission:
                break
            chain.append(mission)
            current_id = mission.parent_mission_id

        chain.reverse()
        return chain
