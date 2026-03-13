"""
Temporal Activities.

Non-deterministic operations that run outside the Workflow's
deterministic replay. Each Activity is idempotent and safe to retry.
Activities receive IDs and brief strings, not large objects.
"""

from temporalio import activity

from modules.backend.core.logging import get_logger
from modules.backend.temporal.models import (
    MissionExecutionResult,
    MissionWorkflowInput,
    NotificationPayload,
)

logger = get_logger(__name__)


@activity.defn
async def execute_mission(input: MissionWorkflowInput) -> MissionExecutionResult:
    """Execute a full mission via handle_mission().

    This is the critical Activity — it bridges Temporal and Mission Control.
    The dispatch loop (Plan 13) runs inside this Activity with full middleware:
    topological DAG execution, retry-with-feedback, 3-tier verification,
    cost tracking, and budget enforcement.

    On Temporal retry (worker crash), the entire mission re-executes.
    This is acceptable because missions are idempotent at the outcome level —
    re-running produces equivalent results (possibly different cost).
    """
    from modules.backend.agents.mission_control.mission_control import handle_mission
    from modules.backend.core.database import get_async_session
    from modules.backend.services.session import SessionService

    activity.logger.info(
        "Starting mission execution",
        extra={
            "mission_id": input.mission_id,
            "roster": input.roster_name,
            "budget": input.mission_budget_usd,
        },
    )

    async with get_async_session() as db:
        session_service = SessionService(db)

        try:
            outcome = await handle_mission(
                mission_id=input.mission_id,
                mission_brief=input.mission_brief,
                session_service=session_service,
                roster_name=input.roster_name,
                mission_budget_usd=input.mission_budget_usd,
                project_id=input.project_id,
            )

            outcome_dict = outcome.model_dump()

            success_count = sum(
                1 for r in outcome.task_results if r.status.value == "success"
            )
            failed_count = sum(
                1 for r in outcome.task_results if r.status.value != "success"
            )

            return MissionExecutionResult(
                mission_id=input.mission_id,
                status=outcome.status.value,
                total_cost_usd=outcome.total_cost_usd,
                total_duration_seconds=outcome.total_duration_seconds,
                task_count=len(outcome.task_results),
                success_count=success_count,
                failed_count=failed_count,
                outcome_json=outcome_dict,
            )

        except Exception as e:
            activity.logger.error(
                "Mission execution failed",
                extra={"mission_id": input.mission_id, "error": str(e)},
            )
            return MissionExecutionResult(
                mission_id=input.mission_id,
                status="failed",
                outcome_json={"error": str(e)},
            )


@activity.defn
async def persist_mission_outcome(
    mission_id: str,
    session_id: str,
    roster_name: str,
    outcome_json: dict,
    project_id: str | None = None,
) -> bool:
    """Persist mission results to PostgreSQL. Best-effort."""
    from modules.backend.agents.mission_control.outcome import MissionOutcome
    from modules.backend.agents.mission_control.persistence_bridge import (
        persist_mission_results,
    )
    from modules.backend.core.database import get_async_session

    try:
        outcome = MissionOutcome.model_validate(outcome_json)
        async with get_async_session() as db:
            await persist_mission_results(
                outcome,
                session_id=session_id,
                roster_name=roster_name,
                task_plan_json=outcome_json.get("task_plan_reference"),
                thinking_trace=outcome_json.get("planning_trace_reference"),
                project_id=project_id,
                db_session=db,
            )
            await db.commit()
        return True
    except (OSError, ValueError, RuntimeError) as e:
        activity.logger.error(
            "Failed to persist mission results",
            extra={"mission_id": mission_id, "error": str(e)},
        )
        return False


@activity.defn
async def send_notification(payload: NotificationPayload) -> bool:
    """Send notification via configured channel.

    Stub implementation — integrate with real Slack/email/webhook SDKs
    when needed. Logs the notification for now.
    """
    activity.logger.info(
        "Notification sent",
        extra={
            "channel": payload.channel,
            "recipient": payload.recipient,
            "title": payload.title,
            "urgency": payload.urgency,
        },
    )
    return True
