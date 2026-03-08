"""
PlaybookRun Service (Orchestrator).

Executes a playbook end-to-end: creates a PlaybookRun record, resolves
steps into missions, dispatches them in dependency order, chains outputs
between steps, and tracks aggregate cost.

This is the bridge between the stateless PlaybookService (YAML loading)
and the stateful MissionService (mission lifecycle).
"""

from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now
from modules.backend.models.mission import PlaybookRun, PlaybookRunState
from modules.backend.repositories.playbook_run import PlaybookRunRepository
from modules.backend.schemas.playbook import PlaybookSchema, PlaybookStepSchema
from modules.backend.services.base import BaseService
from modules.backend.services.mission import MissionService
from modules.backend.services.playbook import PlaybookService

logger = get_logger(__name__)


class PlaybookRunService(BaseService):
    """Orchestrates playbook execution."""

    def __init__(
        self,
        session: AsyncSession,
        mission_service: MissionService,
        playbook_service: PlaybookService | None = None,
    ) -> None:
        super().__init__(session)
        self._run_repo = PlaybookRunRepository(session)
        self._mission_service = mission_service
        self._playbook_service = playbook_service or PlaybookService()

    async def run_playbook(
        self,
        playbook_name: str,
        triggered_by: str = "user:cli",
        context_overrides: dict[str, Any] | None = None,
        on_progress: Any | None = None,
    ) -> PlaybookRun:
        """Execute a playbook end-to-end.

        1. Load and validate the playbook YAML
        2. Create a PlaybookRun record (PENDING → RUNNING)
        3. Topologically sort steps by dependencies
        4. Execute steps in waves (parallel within each wave)
        5. Chain outputs between steps via output_mapping
        6. Update PlaybookRun with final status and cost
        """
        # Load playbook
        playbook = self._playbook_service.get_playbook(playbook_name)
        if not playbook:
            raise ValueError(f"Playbook '{playbook_name}' not found")
        if not playbook.enabled:
            raise ValueError(f"Playbook '{playbook_name}' is disabled")

        # Validate capabilities resolve to real agents
        errors = self._playbook_service.validate_playbook_capabilities(playbook)
        if errors:
            raise ValueError(
                f"Playbook capability errors: {'; '.join(errors)}"
            )

        # Create session for the playbook run
        from modules.backend.services.session import SessionService
        from modules.backend.schemas.session import SessionCreate

        session_service = SessionService(self._session)
        session = await session_service.create_session(
            SessionCreate(
                agent_id=None,
                goal=f"Playbook: {playbook.description[:200]}",
            ),
        )

        # Create PlaybookRun record
        run = PlaybookRun(
            playbook_name=playbook.playbook_name,
            playbook_version=playbook.version,
            status=PlaybookRunState.RUNNING,
            session_id=session.id,
            trigger_type=playbook.trigger.type,
            triggered_by=triggered_by,
            context=dict(playbook.context),
            total_cost_usd=0.0,
            budget_usd=playbook.budget.max_cost_usd,
            started_at=utc_now().isoformat(),
        )
        if context_overrides:
            run.context.update(context_overrides)

        self._session.add(run)
        await self._session.flush()
        await self._session.refresh(run)

        logger.info(
            "Playbook run started",
            extra={
                "run_id": run.id,
                "playbook": playbook_name,
                "version": playbook.version,
                "steps": len(playbook.steps),
                "budget_usd": run.budget_usd,
            },
        )

        try:
            await self._execute_steps(run, playbook, session.id, on_progress)

            run.status = PlaybookRunState.COMPLETED
            run.completed_at = utc_now().isoformat()
            run.result_summary = (
                f"Playbook completed: {len(playbook.steps)} steps, "
                f"${run.total_cost_usd:.4f}"
            )

        except Exception as e:
            run.status = PlaybookRunState.FAILED
            run.completed_at = utc_now().isoformat()
            run.error_data = {"message": str(e), "type": type(e).__name__}
            run.result_summary = f"Playbook failed: {e}"
            logger.error(
                "Playbook run failed",
                extra={"run_id": run.id, "error": str(e)},
            )

        await self._session.flush()

        logger.info(
            "Playbook run finished",
            extra={
                "run_id": run.id,
                "status": run.status,
                "cost": run.total_cost_usd,
            },
        )

        return run

    async def list_runs(
        self,
        playbook_name: str | None = None,
        limit: int = 20,
    ) -> tuple[list[PlaybookRun], int]:
        """List playbook runs."""
        return await self._run_repo.list_runs(
            playbook_name=playbook_name,
            limit=limit,
        )

    async def get_run(self, run_id: str) -> PlaybookRun | None:
        """Get a playbook run by ID."""
        return await self._run_repo.get_by_id_or_none(run_id)

    # ---- Internal orchestration ----

    async def _execute_steps(
        self,
        run: PlaybookRun,
        playbook: PlaybookSchema,
        session_id: str,
        on_progress: Any | None = None,
    ) -> None:
        """Execute steps in topological wave order."""
        waves = self._compute_waves(playbook.steps)
        completed_outcomes: dict[str, dict] = {}
        step_map = {step.id: step for step in playbook.steps}
        total_steps = len(playbook.steps)

        def _emit(event: dict) -> None:
            if on_progress:
                on_progress(event)

        _emit({"type": "playbook_start", "playbook": playbook.playbook_name, "total_steps": total_steps})

        for wave_num, wave_step_ids in enumerate(waves):
            logger.info(
                "Executing wave",
                extra={
                    "run_id": run.id,
                    "wave": wave_num + 1,
                    "steps": wave_step_ids,
                },
            )

            # Check budget before each wave
            if run.budget_usd and run.total_cost_usd >= run.budget_usd:
                raise RuntimeError(
                    f"Budget exceeded: ${run.total_cost_usd:.4f} >= "
                    f"${run.budget_usd:.2f}"
                )

            # Execute steps in this wave sequentially.
            # SQLAlchemy async sessions are not safe for concurrent
            # coroutines (flush conflicts), so we serialize within
            # each wave. Inter-wave ordering still respects the
            # dependency graph.
            for step_id in wave_step_ids:
                step = step_map[step_id]
                _emit({
                    "type": "step_start",
                    "step_id": step_id,
                    "capability": step.capability,
                    "description": step.description or step_id,
                })
                mission, extracted_outputs = await self._execute_step(
                    run, playbook, step, session_id,
                    completed_outcomes,
                )
                completed_outcomes[step_id] = extracted_outputs
                run.total_cost_usd += mission.total_cost_usd
                status_str = mission.status if isinstance(mission.status, str) else mission.status.value
                _emit({
                    "type": "step_done",
                    "step_id": step_id,
                    "status": status_str,
                    "cost_usd": mission.total_cost_usd,
                    "completed_steps": len(completed_outcomes),
                    "total_steps": total_steps,
                })

    async def _execute_step(
        self,
        run: PlaybookRun,
        playbook: PlaybookSchema,
        step: PlaybookStepSchema,
        session_id: str,
        completed_outcomes: dict[str, dict],
    ) -> tuple[Any, dict]:
        """Execute a single playbook step as a mission."""
        # Resolve upstream context from dependencies
        upstream = self._playbook_service.resolve_upstream_context(
            step, completed_outcomes, run.context,
        )

        # Build the objective from step description + input context
        step_input = upstream.get("_step_input", step.input)
        objective = self._build_step_objective(step, step_input)

        app_config = get_app_config()
        cost_ceiling = (
            step.cost_ceiling_usd
            or app_config.playbooks.default_budget_usd
        )

        # Create mission from playbook step
        mission = await self._mission_service.create_mission_from_step(
            playbook_run_id=run.id,
            step_id=step.id,
            objective=objective,
            roster_ref=step.roster,
            complexity_tier=step.complexity_tier,
            cost_ceiling_usd=cost_ceiling,
            upstream_context=upstream,
            session_id=session_id,
        )

        logger.info(
            "Step mission created",
            extra={
                "run_id": run.id,
                "step_id": step.id,
                "mission_id": mission.id,
                "agent": f"{step.capability}.agent",
            },
        )

        # Execute the mission
        mission = await self._mission_service.execute_mission(mission.id)

        # Extract outputs for downstream steps
        output_mapping = (
            step.output_mapping.model_dump()
            if step.output_mapping
            else None
        )
        extracted = self._mission_service.extract_outputs(
            mission, output_mapping,
        )

        status_str = mission.status if isinstance(mission.status, str) else mission.status.value
        logger.info(
            "Step completed",
            extra={
                "run_id": run.id,
                "step_id": step.id,
                "mission_id": mission.id,
                "status": status_str,
                "cost": mission.total_cost_usd,
            },
        )

        if status_str == "failed":
            raise RuntimeError(
                f"Step '{step.id}' mission failed: "
                f"{mission.error_data}"
            )

        return mission, extracted

    def _build_step_objective(
        self,
        step: PlaybookStepSchema,
        step_input: dict[str, Any],
    ) -> str:
        """Build an objective string from the step definition and resolved input."""
        parts = [step.description or f"Execute step: {step.id}"]

        if step_input:
            context_parts = []
            for key, value in step_input.items():
                if isinstance(value, str):
                    context_parts.append(f"{key}: {value}")
                elif isinstance(value, list):
                    context_parts.append(f"{key}: {', '.join(str(v) for v in value)}")
            if context_parts:
                parts.append("Context: " + "; ".join(context_parts))

        return ". ".join(parts)

    @staticmethod
    def _compute_waves(
        steps: list[PlaybookStepSchema],
    ) -> list[list[str]]:
        """Topologically sort steps into execution waves.

        Steps with no unmet dependencies run in the same wave (parallel).
        Returns a list of waves, each wave is a list of step IDs.
        """
        # Build dependency graph
        in_degree: dict[str, int] = {}
        dependents: dict[str, list[str]] = defaultdict(list)

        for step in steps:
            in_degree[step.id] = len(step.depends_on)
            for dep in step.depends_on:
                dependents[dep].append(step.id)

        waves: list[list[str]] = []
        remaining = set(in_degree.keys())

        while remaining:
            # Find all steps with no unmet dependencies
            wave = [
                sid for sid in remaining
                if in_degree[sid] == 0
            ]

            if not wave:
                raise RuntimeError("Dependency cycle detected in playbook steps")

            waves.append(sorted(wave))

            # Remove completed steps and update degrees
            for sid in wave:
                remaining.remove(sid)
                for dependent in dependents[sid]:
                    in_degree[dependent] -= 1

        return waves
