"""
Context Assembler.

Builds the complete context packet for an agent before task execution.
Combines Layer 0 (PCD), Layer 1 (task + upstream), Layer 3 (Code Map),
and Layer 2 (history) within a configurable token budget.

Priority order (last trimmed first):
  1. PCD (never trimmed)
  2. Task definition (never trimmed)
  3. Upstream outputs (summarized if over budget)
  4. Code Map (for coding tasks, never trimmed by default)
  5. History (reduced/removed if over budget)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from modules.backend.core.logging import get_logger
from modules.backend.core.utils import estimate_tokens
from modules.backend.services.history_query import HistoryQueryService
from modules.backend.services.project_context import ProjectContextManager

if TYPE_CHECKING:
    from modules.backend.services.code_map.loader import CodeMapLoader

logger = get_logger(__name__)

# Default token budget for context assembly
DEFAULT_TOKEN_BUDGET = 12_000  # ~48KB of JSON

# Domain tags that indicate a task needs codebase structural context
_CODING_TAGS = frozenset({
    "code", "implementation", "refactor", "bugfix",
    "feature", "migration", "testing",
})


class ContextAssembler:
    """Builds context packets for agents within token budgets.

    Four-layer assembly:
      Layer 0: PCD (always present, never trimmed)
      Layer 1: Task definition + resolved inputs
      Layer 3: Code Map Markdown (for coding tasks)
      Layer 2: Project history (failures, recent executions)
    """

    def __init__(
        self,
        context_manager: ProjectContextManager,
        history_service: HistoryQueryService,
        *,
        code_map_loader: CodeMapLoader | None = None,
    ) -> None:
        self._context_manager = context_manager
        self._history_service = history_service
        self._code_map_loader = code_map_loader

    async def build(
        self,
        project_id: str,
        task_definition: dict,
        resolved_inputs: dict,
        *,
        domain_tags: list[str] | None = None,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        code_map_max_tokens: int | None = None,
    ) -> dict:
        """Build the context packet for a task.

        Returns a dict with keys:
          - project_context: the PCD (Layer 0)
          - task: task definition (Layer 1)
          - inputs: resolved inputs (Layer 1)
          - code_map: Code Map Markdown (Layer 3, for coding tasks)
          - history: relevant past work (Layer 2, if budget allows)
        """
        packet: dict[str, Any] = {}
        remaining_budget = token_budget

        # Layer 0: PCD (always, never trimmed)
        pcd = await self._context_manager.get_context(project_id)
        pcd_tokens = estimate_tokens(pcd)
        packet["project_context"] = pcd
        remaining_budget -= pcd_tokens

        # Layer 1: Task definition (always, never trimmed)
        task_tokens = estimate_tokens(task_definition)
        packet["task"] = task_definition
        remaining_budget -= task_tokens

        # Layer 1: Resolved inputs (high priority, summarized if needed)
        input_tokens = estimate_tokens(resolved_inputs)
        if input_tokens <= remaining_budget:
            packet["inputs"] = resolved_inputs
            remaining_budget -= input_tokens
        else:
            summarized = {
                k: (
                    f"<{type(v).__name__}, {len(str(v))} chars>"
                    if not isinstance(v, (str, int, float, bool))
                    else v
                )
                for k, v in resolved_inputs.items()
            }
            packet["inputs"] = summarized
            remaining_budget -= estimate_tokens(summarized)

        # Layer 3: Code Map (for coding tasks, loaded before history)
        if self._is_coding_task(domain_tags):
            code_map_content = self._load_code_map_markdown(code_map_max_tokens)
            if code_map_content:
                packet["code_map"] = code_map_content
                remaining_budget -= estimate_tokens(code_map_content)

        # Layer 2: History (optional, trimmed first)
        if remaining_budget > 500 and domain_tags:
            history = await self._assemble_history(
                project_id, domain_tags, remaining_budget,
            )
            if history:
                packet["history"] = history

        logger.debug(
            "Context assembled",
            extra={
                "project_id": project_id,
                "budget": token_budget,
                "used": token_budget - remaining_budget,
                "layers": list(packet.keys()),
            },
        )

        return packet

    @staticmethod
    def _is_coding_task(domain_tags: list[str] | None) -> bool:
        """Determine if this task needs codebase structural context.

        Conservative: includes Code Map when domain_tags is empty or None.
        """
        if not domain_tags:
            return True
        return bool(set(domain_tags) & _CODING_TAGS)

    def _load_code_map_markdown(self, max_tokens: int | None = None) -> str | None:
        """Load the pre-rendered Code Map Markdown via the injected loader."""
        if self._code_map_loader is None:
            return None

        content = self._code_map_loader.get_markdown()

        if content and max_tokens:
            token_count = estimate_tokens(content)
            if token_count > max_tokens:
                code_map_json = self._code_map_loader.get_json()
                if code_map_json:
                    from modules.backend.services.code_map.assembler import render_for_agent
                    content = render_for_agent(code_map_json, max_tokens)

        return content

    async def _assemble_history(
        self,
        project_id: str,
        domain_tags: list[str],
        remaining_budget: int,
    ) -> dict[str, Any]:
        """Assemble Layer 2 history within remaining token budget."""
        history: dict[str, Any] = {}

        # Recent failures first — agents must not repeat mistakes
        failures = await self._history_service.get_recent_failures(
            project_id, domain_tags=domain_tags, limit=3,
        )
        if failures:
            failure_tokens = estimate_tokens(failures)
            if failure_tokens <= remaining_budget:
                history["recent_failures"] = failures
                remaining_budget -= failure_tokens

        # Recent executions in same domain
        if remaining_budget > 200:
            executions = await self._history_service.get_recent_task_executions(
                project_id, domain_tags=domain_tags, limit=5,
            )
            if executions:
                exec_tokens = estimate_tokens(executions)
                if exec_tokens <= remaining_budget:
                    history["recent_executions"] = executions

        return history
