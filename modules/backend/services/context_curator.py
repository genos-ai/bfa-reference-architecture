"""
Context Curator.

Validates and applies context_updates from agent task results to the PCD.
Enforces size caps, restricted paths, and guardrail protection.
Delegates actual PCD mutation to ProjectContextManager.
"""

from modules.backend.core.logging import get_logger
from modules.backend.services.project_context import ProjectContextManager

logger = get_logger(__name__)


class ContextCurator:
    """Validates and applies agent context_updates to the PCD.

    Thin orchestration layer between the dispatch loop and
    ProjectContextManager. Keeps dispatch free of PCD internals.
    """

    def __init__(self, context_manager: ProjectContextManager) -> None:
        self._manager = context_manager

    async def get_project_context(self, project_id: str) -> dict:
        """Load the current PCD for a project.

        Returns {} if no PCD exists. Used by dispatch to inject
        project_context into agent inputs.
        """
        return await self._manager.get_context(project_id)

    async def apply_task_updates(
        self,
        project_id: str,
        task_result_context_updates: list[dict],
        *,
        agent_id: str | None = None,
        mission_id: str | None = None,
        task_id: str | None = None,
    ) -> tuple[int, list[str]]:
        """Apply context_updates from a task result to the PCD.

        Returns (new_version, list_of_errors).
        Errors are non-fatal — they are logged but do not fail the task.
        """
        if not task_result_context_updates:
            return 0, []

        new_version, errors = await self._manager.apply_updates(
            project_id,
            task_result_context_updates,
            agent_id=agent_id,
            mission_id=mission_id,
            task_id=task_id,
        )

        if errors:
            logger.warning(
                "Context update errors (non-fatal)",
                extra={
                    "project_id": project_id,
                    "task_id": task_id,
                    "errors": errors,
                },
            )

        return new_version, errors
