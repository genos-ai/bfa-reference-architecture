"""
Mission Service.

Orchestrates mission lifecycle: creates missions from playbook steps,
instantiates Mission Control with the appropriate roster, tracks
MissionOutcome results, and manages inter-mission data flow.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.config import get_app_config
from modules.backend.core.exceptions import NotFoundError, ValidationError
from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now
from modules.backend.models.mission import (
    Mission,
    MissionState,
    VALID_MISSION_TRANSITIONS,
)
from modules.backend.repositories.mission import MissionRepository
from modules.backend.services.base import BaseService

logger = get_logger(__name__)


class MissionService(BaseService):
    """Mission lifecycle management."""

    def __init__(
        self,
        session: AsyncSession,
        mission_control_dispatch: Any | None = None,
        session_service: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        super().__init__(session)
        self._mission_repo = MissionRepository(session)
        self._mission_control_dispatch = mission_control_dispatch
        self._session_service = session_service
        self._event_bus = event_bus

    async def _publish_event(self, event: Any) -> None:
        """Publish event to session event bus (best-effort)."""
        if self._event_bus is None:
            return
        try:
            await self._event_bus.publish(event)
        except Exception:
            logger.warning(
                "Failed to publish mission event",
                extra={"event_type": getattr(event, "event_type", "unknown")},
            )

    # ---- Mission creation ----

    async def create_mission_from_step(
        self,
        playbook_run_id: str,
        step_id: str,
        objective: str,
        roster_ref: str,
        complexity_tier: str,
        cost_ceiling_usd: float,
        upstream_context: dict,
        session_id: str,
        environment: str = "local",
    ) -> Mission:
        """Create a mission from a playbook step."""

        async def _create() -> Mission:
            app_config = get_app_config()
            active_count = await self._mission_repo.count_active()
            if active_count >= app_config.playbooks.max_concurrent_missions:
                raise ValidationError(
                    message=(
                        f"Maximum concurrent missions "
                        f"({app_config.playbooks.max_concurrent_missions}) "
                        f"reached. {active_count} currently active."
                    ),
                )

            mission = Mission(
                playbook_run_id=playbook_run_id,
                playbook_step_id=step_id,
                objective=objective,
                roster_ref=roster_ref,
                complexity_tier=complexity_tier,
                status=MissionState.PENDING,
                session_id=session_id,
                trigger_type="playbook",
                triggered_by=f"playbook_run:{playbook_run_id}",
                upstream_context=upstream_context,
                context={},
                total_cost_usd=0.0,
                cost_ceiling_usd=cost_ceiling_usd,
            )
            self._session.add(mission)
            await self._session.flush()
            await self._session.refresh(mission)

            logger.info(
                "Mission created from playbook step",
                extra={
                    "mission_id": mission.id,
                    "playbook_run_id": playbook_run_id,
                    "step_id": step_id,
                    "roster_ref": roster_ref,
                    "complexity_tier": complexity_tier,
                    "cost_ceiling_usd": cost_ceiling_usd,
                },
            )
            return mission

        return await self._execute_db_operation(
            "create_mission_from_step", _create(),
        )

    async def create_adhoc_mission(
        self,
        objective: str,
        triggered_by: str,
        session_id: str,
        roster_ref: str = "default",
        complexity_tier: str = "simple",
        cost_ceiling_usd: float | None = None,
        upstream_context: dict | None = None,
    ) -> Mission:
        """Create an ad-hoc mission (not from a playbook)."""

        async def _create() -> Mission:
            app_config = get_app_config()

            active_count = await self._mission_repo.count_active()
            if active_count >= app_config.playbooks.max_concurrent_missions:
                raise ValidationError(
                    message=(
                        f"Maximum concurrent missions "
                        f"({app_config.playbooks.max_concurrent_missions}) "
                        f"reached. {active_count} currently active."
                    ),
                )

            mission = Mission(
                objective=objective,
                roster_ref=roster_ref,
                complexity_tier=complexity_tier,
                status=MissionState.PENDING,
                session_id=session_id,
                trigger_type="on_demand",
                triggered_by=triggered_by,
                upstream_context=upstream_context or {},
                context={},
                total_cost_usd=0.0,
                cost_ceiling_usd=(
                    cost_ceiling_usd
                    or app_config.playbooks.default_budget_usd
                ),
            )
            self._session.add(mission)
            await self._session.flush()
            await self._session.refresh(mission)

            logger.info(
                "Ad-hoc mission created",
                extra={
                    "mission_id": mission.id,
                    "session_id": session_id,
                    "roster_ref": roster_ref,
                },
            )
            return mission

        return await self._execute_db_operation(
            "create_adhoc_mission", _create(),
        )

    # ---- Mission execution ----

    async def execute_mission(self, mission_id: str) -> Mission:
        """Execute a mission by dispatching to Mission Control."""
        mission = await self._get_mission(mission_id)
        self._validate_transition(mission, MissionState.RUNNING)

        mission.status = MissionState.RUNNING
        mission.started_at = utc_now().isoformat()
        await self._session.flush()

        if self._mission_control_dispatch is None:
            logger.warning(
                "Mission Control dispatch not available, "
                "mission stays in RUNNING",
                extra={"mission_id": mission_id},
            )
            return mission

        try:
            outcome = await self._mission_control_dispatch.execute(
                mission_brief=mission.objective,
                roster_ref=mission.roster_ref,
                complexity_tier=mission.complexity_tier,
                upstream_context=mission.upstream_context,
                cost_ceiling_usd=mission.cost_ceiling_usd,
                session_id=mission.session_id,
            )

            mission.mission_outcome = (
                outcome if isinstance(outcome, dict)
                else outcome.model_dump()
            )
            mission.total_cost_usd = (
                outcome.get("total_cost_usd", 0.0)
                if isinstance(outcome, dict)
                else getattr(outcome, "total_cost_usd", 0.0)
            )
            mission.result_summary = (
                outcome.get("summary", None)
                if isinstance(outcome, dict)
                else getattr(outcome, "summary", None)
            )

            if (
                mission.cost_ceiling_usd
                and mission.total_cost_usd > mission.cost_ceiling_usd
            ):
                logger.warning(
                    "Mission exceeded cost ceiling",
                    extra={
                        "mission_id": mission_id,
                        "cost": mission.total_cost_usd,
                        "ceiling": mission.cost_ceiling_usd,
                    },
                )

            success = (
                outcome.get("success", False)
                if isinstance(outcome, dict)
                else getattr(outcome, "success", False)
            )
            if success:
                mission.status = MissionState.COMPLETED
            else:
                mission.status = MissionState.FAILED
                mission.error_data = {
                    "message": "Mission Control dispatch returned failure",
                }

            mission.completed_at = utc_now().isoformat()
            await self._session.flush()

        except Exception as e:
            mission.status = MissionState.FAILED
            mission.completed_at = utc_now().isoformat()
            mission.error_data = {
                "message": str(e), "type": type(e).__name__,
            }
            await self._session.flush()
            logger.error(
                "Mission execution failed",
                extra={"mission_id": mission_id, "error": str(e)},
            )

        return mission

    # ---- Mission lifecycle ----

    async def complete_mission(self, mission_id: str) -> Mission:
        """Mark mission as completed."""
        mission = await self._get_mission(mission_id)
        self._validate_transition(mission, MissionState.COMPLETED)

        mission.status = MissionState.COMPLETED
        mission.completed_at = utc_now().isoformat()
        await self._session.flush()
        return mission

    async def fail_mission(
        self, mission_id: str, error: str,
        error_data: dict | None = None,
    ) -> Mission:
        """Mark mission as failed."""
        mission = await self._get_mission(mission_id)
        self._validate_transition(mission, MissionState.FAILED)

        mission.status = MissionState.FAILED
        mission.completed_at = utc_now().isoformat()
        mission.error_data = error_data or {"message": error}
        await self._session.flush()
        return mission

    async def cancel_mission(self, mission_id: str, reason: str) -> Mission:
        """Cancel a mission."""
        mission = await self._get_mission(mission_id)
        self._validate_transition(mission, MissionState.CANCELLED)

        mission.status = MissionState.CANCELLED
        mission.completed_at = utc_now().isoformat()
        mission.error_data = {"cancelled_reason": reason}
        await self._session.flush()
        return mission

    # ---- Output extraction (anti-corruption layer) ----

    def extract_outputs(
        self, mission: Mission, output_mapping: dict | None,
    ) -> dict[str, Any]:
        """Extract outputs from a completed mission's MissionOutcome
        according to the playbook step's output_mapping.

        task_results in the outcome is a list of TaskResult dicts.
        We index them by task_id for direct lookup, but also support
        matching source_task against agent_name (since the Planning
        Agent assigns dynamic task IDs like 'task-001' that won't
        match playbook-defined source_task names).
        """
        if not output_mapping or not mission.mission_outcome:
            return {}

        extracted: dict[str, Any] = {}
        outcome = mission.mission_outcome

        summary_key = output_mapping.get("summary_key")
        if summary_key:
            extracted[summary_key] = (
                outcome.get("summary") or mission.result_summary
            )

        field_mappings = output_mapping.get("field_mappings", [])
        raw_results = outcome.get("task_results", [])

        # Build lookup indices: by task_id and by agent_name
        by_task_id: dict[str, dict] = {}
        by_agent: dict[str, dict] = {}
        if isinstance(raw_results, list):
            for tr in raw_results:
                if isinstance(tr, dict):
                    by_task_id[tr.get("task_id", "")] = tr.get(
                        "output_reference", {},
                    )
                    agent = tr.get("agent_name", "")
                    by_agent[agent] = tr.get("output_reference", {})
        elif isinstance(raw_results, dict):
            # Legacy: already a dict keyed by task name
            by_task_id = raw_results

        for mapping in field_mappings:
            source_task = mapping["source_task"]
            source_field = mapping["source_field"]
            target_key = mapping["target_key"]

            # Try exact task_id match, then agent_name match
            task_output = by_task_id.get(source_task)
            if task_output is None:
                task_output = by_agent.get(source_task)

            if task_output is not None:
                if isinstance(task_output, dict) and source_field in task_output:
                    extracted[target_key] = task_output[source_field]
                else:
                    logger.warning(
                        "Output mapping source field not found",
                        extra={
                            "mission_id": mission.id,
                            "source_task": source_task,
                            "source_field": source_field,
                            "available_fields": (
                                list(task_output.keys())
                                if isinstance(task_output, dict) else None
                            ),
                        },
                    )
            else:
                logger.warning(
                    "Output mapping source task not found",
                    extra={
                        "mission_id": mission.id,
                        "source_task": source_task,
                        "available_task_ids": list(by_task_id.keys()),
                        "available_agents": list(by_agent.keys()),
                    },
                )

        return extracted

    # ---- Status and queries ----

    async def get_mission(self, mission_id: str) -> Mission:
        """Get a mission by ID."""
        return await self._get_mission(mission_id)

    async def list_missions(
        self,
        status: str | None = None,
        playbook_run_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Mission], int]:
        """List missions with optional filters."""
        mission_status = MissionState(status) if status else None
        return await self._mission_repo.list_missions(
            status=mission_status,
            playbook_run_id=playbook_run_id,
            limit=limit,
            offset=offset,
        )

    # ---- Internal helpers ----

    async def _get_mission(self, mission_id: str) -> Mission:
        """Get mission or raise NotFoundError."""
        mission = await self._mission_repo.get_by_id_or_none(mission_id)
        if not mission:
            raise NotFoundError(
                message=f"Mission '{mission_id}' not found",
            )
        return mission

    def _validate_transition(
        self, mission: Mission, new_status: MissionState,
    ) -> None:
        """Validate mission status transition."""
        current = MissionState(mission.status)
        allowed = VALID_MISSION_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise ValidationError(
                message=(
                    f"Cannot transition mission from '{current.value}' "
                    f"to '{new_status.value}'. "
                    f"Allowed: {[s.value for s in allowed]}"
                ),
            )
