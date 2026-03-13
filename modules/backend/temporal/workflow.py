"""
Agent Mission Workflow.

Temporal Workflow that executes a mission and handles lifecycle:
planning, execution, persistence, approval, and escalation.

Key rules:
- Workflow code is deterministic — no I/O, no random, no datetime.now()
- All side effects happen in Activities
- Temporal owns orchestration state (position, signals, timers)
- PostgreSQL owns domain state (missions, tasks, decisions)
"""

from datetime import timedelta

from temporalio import workflow

from modules.backend.temporal.models import (
    ApprovalDecision,
    MissionWorkflowInput,
    NotificationPayload,
    WorkflowStatus,
)

with workflow.unsafe.imports_passed_through():
    from modules.backend.core.config import get_app_config
    from modules.backend.temporal import activities


@workflow.defn
class AgentMissionWorkflow:
    """Execute a mission as a Temporal Workflow.

    Flow:
    1. Execute mission via handle_mission() Activity
    2. Persist results to PostgreSQL Activity
    3. If approval needed (future): wait for Signal
    4. Return WorkflowStatus
    """

    def __init__(self) -> None:
        self._approval: ApprovalDecision | None = None
        self._status = WorkflowStatus(mission_id="")

    # ---- Signals ----

    @workflow.signal
    async def submit_approval(self, decision: ApprovalDecision) -> None:
        """Receive approval from any source: human, AI, or automated rule."""
        self._approval = decision
        self._status.waiting_for_approval = False

    # ---- Queries ----

    @workflow.query
    def get_status(self) -> WorkflowStatus:
        """Read-only status for dashboards. Does not interrupt workflow."""
        return self._status

    # ---- Main workflow ----

    @workflow.run
    async def run(self, input: MissionWorkflowInput) -> WorkflowStatus:
        """Execute a mission with durable execution guarantees."""
        self._status.mission_id = input.mission_id
        self._status.workflow_status = "running"

        temporal_config = get_app_config().temporal
        activity_timeout = timedelta(
            seconds=max(
                input.mission_budget_usd
                * temporal_config.budget_timeout_multiplier_seconds,
                temporal_config.min_activity_timeout_seconds,
            ),
        )
        notification_timeout = timedelta(
            seconds=input.notification_timeout_seconds,
        )

        # Step 1: Execute the mission
        result = await workflow.execute_activity(
            activities.execute_mission,
            input,
            start_to_close_timeout=activity_timeout,
            retry_policy=workflow.RetryPolicy(
                maximum_attempts=temporal_config.execution_retry_max_attempts,
                initial_interval=timedelta(
                    seconds=temporal_config.execution_retry_initial_interval_seconds,
                ),
                maximum_interval=timedelta(
                    seconds=temporal_config.execution_retry_max_interval_seconds,
                ),
                non_retryable_error_types=["BudgetExceededError"],
            ),
        )

        self._status.mission_status = result.status
        self._status.total_cost_usd = result.total_cost_usd

        # Step 2: Persist results (best-effort)
        await workflow.execute_activity(
            activities.persist_mission_outcome,
            args=[
                input.mission_id,
                input.session_id,
                input.roster_name,
                result.outcome_json,
            ],
            start_to_close_timeout=timedelta(
                seconds=temporal_config.persistence_timeout_seconds,
            ),
            retry_policy=workflow.RetryPolicy(
                maximum_attempts=temporal_config.persistence_retry_max_attempts,
            ),
        )

        # Step 3: If mission failed, optionally wait for approval to retry
        if result.status == "failed" and result.failed_count > 0:
            self._status.workflow_status = "waiting_approval"
            self._status.waiting_for_approval = True

            # Notify about failure
            await workflow.execute_activity(
                activities.send_notification,
                NotificationPayload(
                    channel="webhook",
                    recipient="admin",
                    title=f"Mission failed: {input.mission_id[:8]}",
                    body=(
                        f"Mission '{input.mission_brief[:100]}' failed. "
                        f"{result.failed_count}/{result.task_count} tasks failed. "
                        f"Cost: ${result.total_cost_usd:.2f}"
                    ),
                    action_url=f"/api/v1/missions/{input.mission_id}",
                    urgency="high",
                ),
                start_to_close_timeout=notification_timeout,
            )

            # Wait for approval with escalation
            await self._wait_for_approval_with_escalation(
                input, notification_timeout,
            )

            # If approved, retry the mission
            if self._approval and self._approval.decision == "approved":
                self._status.workflow_status = "running"
                self._approval = None

                retry_result = await workflow.execute_activity(
                    activities.execute_mission,
                    input,
                    start_to_close_timeout=activity_timeout,
                    retry_policy=workflow.RetryPolicy(maximum_attempts=1),
                )

                self._status.mission_status = retry_result.status
                self._status.total_cost_usd += retry_result.total_cost_usd

                # Persist retry results
                await workflow.execute_activity(
                    activities.persist_mission_outcome,
                    args=[
                        input.mission_id,
                        input.session_id,
                        input.roster_name,
                        retry_result.outcome_json,
                    ],
                    start_to_close_timeout=timedelta(
                        seconds=temporal_config.persistence_timeout_seconds,
                    ),
                    retry_policy=workflow.RetryPolicy(
                        maximum_attempts=temporal_config.persistence_retry_max_attempts,
                    ),
                )

        # Final status
        self._status.workflow_status = (
            "completed"
            if self._status.mission_status in ("success", "partial")
            else "failed"
        )

        return self._status

    async def _wait_for_approval_with_escalation(
        self,
        input: MissionWorkflowInput,
        notification_timeout: timedelta,
    ) -> None:
        """Wait for approval with durable escalation timer.

        Phase 1: wait approval_timeout_seconds, then escalate.
        Phase 2: wait remaining time up to escalation_timeout_seconds total.
        """
        approval_timeout = timedelta(
            seconds=input.approval_timeout_seconds,
        )
        remaining_timeout = timedelta(
            seconds=input.escalation_timeout_seconds
            - input.approval_timeout_seconds,
        )
        total_timeout = timedelta(
            seconds=input.escalation_timeout_seconds,
        )

        # Phase 1: wait for initial approval window
        try:
            await workflow.wait_condition(
                lambda: self._approval is not None,
                timeout=approval_timeout,
            )
            return
        except TimeoutError:
            pass

        # Escalate: re-notify with critical urgency
        await workflow.execute_activity(
            activities.send_notification,
            NotificationPayload(
                channel="webhook",
                recipient="admin",
                title=f"ESCALATION: Mission {input.mission_id[:8]}",
                body=(
                    f"Approval pending for "
                    f"{input.approval_timeout_seconds // 3600} hours. "
                    f"Escalating."
                ),
                action_url=f"/api/v1/missions/{input.mission_id}",
                urgency="critical",
            ),
            start_to_close_timeout=notification_timeout,
        )

        # Phase 2: wait remaining time up to total escalation timeout
        try:
            await workflow.wait_condition(
                lambda: self._approval is not None,
                timeout=remaining_timeout,
            )
        except TimeoutError:
            # Give up — mark as failed
            self._status.workflow_status = "failed"
            total_hours = total_timeout.total_seconds() / 3600
            self._status.error = (
                f"Approval timed out after {total_hours:.0f} hours"
            )
