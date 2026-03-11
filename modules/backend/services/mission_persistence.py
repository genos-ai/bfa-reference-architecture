"""
Mission Persistence Service.

Saves Mission Control execution artifacts to PostgreSQL for audit,
compliance, cost analytics, and historical queries.

Called by the dispatch loop (Plan 13) during and after mission execution.
This service is write-heavy during execution and read-heavy afterward.
"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now
from modules.backend.models.mission_record import (
    DecisionType,
    FailureTier,
    MissionDecision,
    MissionRecord,
    MissionRecordStatus,
    TaskAttempt,
    TaskAttemptStatus,
    TaskExecution,
    TaskExecutionStatus,
)
from modules.backend.repositories.mission_record import MissionRecordRepository
from modules.backend.schemas.mission_record import MissionCostBreakdown
from modules.backend.services.base import BaseService

logger = get_logger(__name__)


class MissionPersistenceService(BaseService):
    """Persist and query mission execution records.

    Write methods are called during/after dispatch loop execution.
    Read methods serve the REST API and analytics.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = MissionRecordRepository(session)

    # ---- Write operations (called by dispatch loop) ----

    async def save_mission(
        self,
        session_id: str,
        status: str,
        *,
        roster_name: str | None = None,
        task_plan_json: dict | None = None,
        mission_outcome_json: dict | None = None,
        planning_thinking_trace: str | None = None,
        total_cost_usd: float = 0.0,
        started_at: str | None = None,
        completed_at: str | None = None,
        parent_mission_id: str | None = None,
        objective_statement: str | None = None,
        objective_category: str | None = None,
    ) -> MissionRecord:
        """Persist a complete mission record.

        Called after the dispatch loop completes (or fails/times out).
        """
        config = get_app_config().missions

        if planning_thinking_trace and config.persist_thinking_trace:
            if len(planning_thinking_trace) > config.max_thinking_trace_length:
                planning_thinking_trace = (
                    planning_thinking_trace[: config.max_thinking_trace_length]
                    + "\n\n[TRUNCATED]"
                )
        elif not config.persist_thinking_trace:
            planning_thinking_trace = None

        record = MissionRecord(
            session_id=session_id,
            roster_name=roster_name,
            status=MissionRecordStatus(status),
            task_plan_json=task_plan_json,
            mission_outcome_json=mission_outcome_json,
            planning_thinking_trace=planning_thinking_trace,
            total_cost_usd=total_cost_usd,
            started_at=started_at or utc_now().isoformat(),
            completed_at=completed_at or utc_now().isoformat(),
            parent_mission_id=parent_mission_id,
            objective_statement=objective_statement,
            objective_category=objective_category,
        )

        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)

        logger.info(
            "Mission record saved",
            extra={
                "mission_id": record.id,
                "session_id": session_id,
                "roster": roster_name,
                "status": status,
                "cost": total_cost_usd,
            },
        )

        return record

    async def save_task_execution(
        self,
        mission_record_id: str,
        task_id: str,
        agent_name: str,
        status: str,
        *,
        output_data: dict | None = None,
        token_usage: dict | None = None,
        cost_usd: float = 0.0,
        duration_seconds: float | None = None,
        verification_outcome: dict | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        execution_id: str | None = None,
        domain_tags: list[str] | None = None,
    ) -> TaskExecution:
        """Persist a single task execution result."""
        config = get_app_config().missions

        if output_data:
            output_size = len(json.dumps(output_data).encode("utf-8"))
            if output_size > config.max_task_output_size_bytes:
                output_data = {
                    "_truncated": True,
                    "_original_size_bytes": output_size,
                    "_message": "Output truncated. Exceeded max_task_output_size_bytes.",
                }

        if verification_outcome and not config.persist_verification_details:
            verification_outcome = {
                "passed": verification_outcome.get("passed"),
                "tier": verification_outcome.get("tier"),
            }

        execution = TaskExecution(
            mission_record_id=mission_record_id,
            task_id=task_id,
            agent_name=agent_name,
            status=TaskExecutionStatus(status),
            output_data=output_data,
            token_usage=token_usage,
            cost_usd=cost_usd,
            duration_seconds=duration_seconds,
            verification_outcome=verification_outcome,
            started_at=started_at,
            completed_at=completed_at,
            execution_id=execution_id,
            domain_tags=domain_tags,
        )

        self._session.add(execution)
        await self._session.flush()
        await self._session.refresh(execution)

        logger.debug(
            "Task execution saved",
            extra={
                "execution_id": execution.id,
                "mission_id": mission_record_id,
                "task_id": task_id,
                "agent": agent_name,
                "status": status,
                "cost": cost_usd,
            },
        )

        return execution

    async def save_attempt(
        self,
        task_execution_id: str,
        attempt_number: int,
        status: str,
        *,
        failure_tier: str | None = None,
        failure_reason: str | None = None,
        feedback_provided: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> TaskAttempt:
        """Persist a single task attempt within a task execution."""
        attempt = TaskAttempt(
            task_execution_id=task_execution_id,
            attempt_number=attempt_number,
            status=TaskAttemptStatus(status),
            failure_tier=FailureTier(failure_tier) if failure_tier else None,
            failure_reason=failure_reason,
            feedback_provided=feedback_provided,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

        self._session.add(attempt)
        await self._session.flush()
        await self._session.refresh(attempt)

        return attempt

    async def save_decision(
        self,
        mission_record_id: str,
        decision_type: str,
        reasoning: str,
        *,
        task_id: str | None = None,
    ) -> MissionDecision:
        """Log a Mission Control decision."""
        decision = MissionDecision(
            mission_record_id=mission_record_id,
            decision_type=DecisionType(decision_type),
            task_id=task_id,
            reasoning=reasoning,
        )

        self._session.add(decision)
        await self._session.flush()
        await self._session.refresh(decision)

        logger.debug(
            "Decision logged",
            extra={
                "decision_id": decision.id,
                "mission_id": mission_record_id,
                "type": decision_type,
                "task_id": task_id,
            },
        )

        return decision

    # ---- Read operations (serve REST API) ----

    async def get_mission(self, mission_id: str) -> MissionRecord | None:
        """Get a mission record with all details loaded."""
        return await self._repo.get_with_details(mission_id)

    async def get_task_executions(self, mission_id: str) -> list:
        """Get task executions for a mission."""
        return await self._repo.get_task_executions(mission_id)

    async def list_missions(
        self,
        status: str | None = None,
        roster_name: str | None = None,
        objective_category: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[MissionRecord], int]:
        """List mission records with optional filters."""
        config = get_app_config().missions
        if limit is None:
            limit = config.default_page_size
        limit = min(limit, config.max_page_size)

        mission_status = MissionRecordStatus(status) if status else None
        return await self._repo.list_missions(
            status=mission_status,
            roster_name=roster_name,
            objective_category=objective_category,
            limit=limit,
            offset=offset,
        )

    async def get_decisions(self, mission_id: str) -> list[MissionDecision]:
        """Get the decision audit trail for a mission."""
        return await self._repo.get_decisions(mission_id)

    async def get_cost_breakdown(self, mission_id: str) -> MissionCostBreakdown:
        """Get detailed cost breakdown for a mission."""
        mission = await self._repo.get_by_id_or_none(mission_id)
        if not mission:
            from modules.backend.core.exceptions import NotFoundError
            raise NotFoundError(f"Mission '{mission_id}' not found")

        executions = await self._repo.get_task_executions(mission_id)
        model_costs = await self._repo.get_cost_by_model(mission_id)

        task_costs: list[dict[str, Any]] = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_attempts = 0

        for execution in executions:
            task_cost: dict[str, Any] = {
                "task_id": execution.task_id,
                "agent_name": execution.agent_name,
                "cost_usd": execution.cost_usd,
                "status": execution.status,
                "duration_seconds": execution.duration_seconds,
            }
            if execution.token_usage:
                task_cost["input_tokens"] = execution.token_usage.get(
                    "input_tokens", 0,
                )
                task_cost["output_tokens"] = execution.token_usage.get(
                    "output_tokens", 0,
                )
                total_input_tokens += task_cost.get("input_tokens", 0)
                total_output_tokens += task_cost.get("output_tokens", 0)

            total_attempts += len(execution.attempts)
            task_costs.append(task_cost)

        return MissionCostBreakdown(
            mission_id=mission_id,
            total_cost_usd=mission.total_cost_usd,
            task_costs=task_costs,
            model_costs=model_costs,
            attempt_count=total_attempts,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )

    async def get_mission_status(self, mission_id: str) -> dict:
        """Get mission progress summary as a dict.

        Returns a dict with mission_id, status, objective, task counts,
        and progress percentage. Used by Temporal Queries and the
        /missions/{id}/status API endpoint.
        """
        mission = await self._repo.get_by_id_or_none(mission_id)
        if not mission:
            from modules.backend.core.exceptions import NotFoundError
            raise NotFoundError(f"Mission '{mission_id}' not found")

        executions = await self._repo.get_task_executions(mission_id)

        total = len(executions)
        completed = sum(
            1 for e in executions
            if e.status == TaskExecutionStatus.COMPLETED
        )
        failed = sum(
            1 for e in executions
            if e.status == TaskExecutionStatus.FAILED
        )
        skipped = sum(
            1 for e in executions
            if e.status == TaskExecutionStatus.SKIPPED
        )

        progress_pct = (completed / total * 100.0) if total > 0 else 0.0

        return {
            "mission_id": mission_id,
            "status": mission.status.value if hasattr(mission.status, "value") else str(mission.status),
            "objective": mission.objective_statement,
            "roster_name": mission.roster_name,
            "total_tasks": total,
            "completed_tasks": completed,
            "failed_tasks": failed,
            "skipped_tasks": skipped,
            "progress_pct": round(progress_pct, 1),
            "total_cost_usd": mission.total_cost_usd,
        }

    async def get_missions_by_session(
        self, session_id: str,
    ) -> list[MissionRecord]:
        """Get all mission records for a session."""
        return await self._repo.get_by_session(session_id)

    async def get_replan_chain(self, mission_id: str) -> list[MissionRecord]:
        """Get the full re-plan lineage for a mission."""
        return await self._repo.get_replan_chain(mission_id)
