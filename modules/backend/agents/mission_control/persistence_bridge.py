"""Bridge between Mission Control dispatch and the persistence layer.

Converts MissionOutcome (in-memory) to persisted MissionRecord (database).
Best-effort — persistence failure does not crash the mission.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from modules.backend.agents.mission_control.outcome import (
    MissionOutcome,
    MissionStatus,
    TaskStatus,
)
from modules.backend.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


async def persist_mission_results(
    outcome: MissionOutcome,
    *,
    session_id: str,
    roster_name: str | None = None,
    task_plan_json: dict | None = None,
    thinking_trace: str | None = None,
    db_session: AsyncSession,
) -> None:
    """Persist mission execution results. Best-effort — does not raise."""
    try:
        from modules.backend.services.mission_persistence import (
            MissionPersistenceService,
        )

        service = MissionPersistenceService(db_session)

        status_map = {
            MissionStatus.SUCCESS: "completed",
            MissionStatus.PARTIAL: "completed",
            MissionStatus.FAILED: "failed",
        }
        record_status = status_map.get(outcome.status, "failed")

        record = await service.save_mission(
            session_id=session_id,
            status=record_status,
            roster_name=roster_name,
            task_plan_json=task_plan_json,
            mission_outcome_json=outcome.model_dump(),
            planning_thinking_trace=thinking_trace,
            total_cost_usd=outcome.total_cost_usd,
        )

        for task_result in outcome.task_results:
            verification_dict = None
            if task_result.verification_outcome:
                verification_dict = task_result.verification_outcome.model_dump()

            token_dict = None
            if task_result.token_usage:
                token_dict = {
                    "input_tokens": task_result.token_usage.input,
                    "output_tokens": task_result.token_usage.output,
                }

            task_status_map = {
                TaskStatus.SUCCESS: "completed",
                TaskStatus.FAILED: "failed",
                TaskStatus.TIMEOUT: "failed",
                TaskStatus.SKIPPED: "skipped",
            }
            exec_status = task_status_map.get(task_result.status, "failed")

            execution = await service.save_task_execution(
                mission_record_id=record.id,
                task_id=task_result.task_id,
                agent_name=task_result.agent_name,
                status=exec_status,
                output_data=task_result.output_reference or None,
                token_usage=token_dict,
                cost_usd=task_result.cost_usd,
                duration_seconds=task_result.duration_seconds,
                verification_outcome=verification_dict,
                execution_id=task_result.execution_id or None,
            )

            for retry_entry in task_result.retry_history:
                failure_tier_map = {
                    1: "tier_1_structural",
                    2: "tier_2_quality",
                    3: "tier_3_integration",
                    0: "agent_error",
                }
                ft = failure_tier_map.get(retry_entry.failure_tier)

                await service.save_attempt(
                    task_execution_id=execution.id,
                    attempt_number=retry_entry.attempt,
                    status="failed",
                    failure_tier=ft,
                    failure_reason=retry_entry.failure_reason,
                    feedback_provided=retry_entry.feedback_provided,
                )

        await db_session.commit()

        logger.info(
            "Mission results persisted",
            extra={
                "mission_record_id": record.id,
                "task_count": len(outcome.task_results),
            },
        )

    except Exception as e:
        logger.error(
            "Failed to persist mission results",
            extra={"session_id": session_id, "error": str(e)},
        )
