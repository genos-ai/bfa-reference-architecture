"""
Architecture Review Agent (code.architecture.agent).

Deep architectural analysis using Opus. Reads source code and evaluates
against six engineering principles: unnecessary complexity, unsafe concurrency,
brittle coupling, leaky boundaries, silent failures, and duplication.

Unlike the QA compliance agent (regex scanners), this agent READS code and
REASONS about it. No deterministic scanners — pure AI judgment.
"""

import json
from collections.abc import AsyncGenerator
from pathlib import Path

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.models import Model

from modules.backend.agents.mission_control.helpers import assemble_instructions
from modules.backend.agents.deps.base import QaAgentDeps
from modules.backend.agents.schemas import ArchitectureReviewResult
from modules.backend.agents.tools import filesystem
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

_BASELINE_PATH = "config/qa-baseline.json"


def create_agent(model: str | Model) -> Agent[QaAgentDeps, ArchitectureReviewResult]:
    """Factory: create an architecture review agent with file reading tools.

    Called by AgentRegistry.get_instance() on first use.
    The registry caches the result — this function is not called again
    unless registry.reset() is called.
    """

    instructions = assemble_instructions("code", "architecture")

    agent = Agent(
        model,
        deps_type=QaAgentDeps,
        output_type=ArchitectureReviewResult,
        instructions=instructions,
        output_retries=3,
    )

    @agent.tool
    async def list_python_files(ctx: RunContext[QaAgentDeps]) -> list[str]:
        """List all Python files in scope, respecting exclusion patterns."""
        ctx.deps.emit({"type": "tool_start", "tool": "list_python_files"})
        exclusions = set(ctx.deps.config.exclusions.paths) if ctx.deps.config and ctx.deps.config.exclusions else set()
        files = await filesystem.list_files(ctx.deps.project_root, ctx.deps.scope, exclusions)
        ctx.deps.emit({"type": "tool_done", "tool": "list_python_files", "detail": f"{len(files)} files"})
        return files

    @agent.tool
    async def read_source_file(ctx: RunContext[QaAgentDeps], file_path: str) -> str:
        """Read a source file and return its contents with line numbers."""
        ctx.deps.emit({"type": "tool_start", "tool": "read_source_file", "detail": file_path})
        return await filesystem.read_file(ctx.deps.project_root, file_path, ctx.deps.scope)

    @agent.tool
    async def read_baseline(ctx: RunContext[QaAgentDeps]) -> str:
        """Read the QA baseline file containing known/accepted violations.

        Returns JSON array of known violations, or empty array if no baseline exists.
        Each entry has: principle, file, line, message.
        """
        ctx.deps.emit({"type": "tool_start", "tool": "read_baseline"})
        baseline_file = ctx.deps.project_root / _BASELINE_PATH
        if not baseline_file.is_file():
            ctx.deps.emit({"type": "tool_done", "tool": "read_baseline", "detail": "no baseline"})
            return "[]"
        content = baseline_file.read_text(encoding="utf-8")
        ctx.deps.emit({"type": "tool_done", "tool": "read_baseline", "detail": "loaded"})
        return content

    logger.info("Architecture review agent created (read-only)", extra={"model": str(model)})
    return agent


async def run_agent(
    user_message: str,
    deps: QaAgentDeps,
    agent: Agent[QaAgentDeps, ArchitectureReviewResult],
    usage_limits: UsageLimits | None = None,
) -> ArchitectureReviewResult:
    """Standard agent entry point. Called by mission control."""

    logger.info("Architecture review agent invoked", extra={"message": user_message})
    result = await agent.run(user_message, deps=deps, usage_limits=usage_limits)

    logger.info(
        "Architecture review agent completed",
        extra={
            "summary": result.output.summary,
            "total_findings": result.output.total_findings,
            "new_findings": result.output.new_findings,
            "files_reviewed": result.output.files_reviewed,
            "usage": {
                "requests": result.usage().requests,
                "input_tokens": result.usage().input_tokens,
                "output_tokens": result.usage().output_tokens,
            },
        },
    )
    return result.output


async def run_agent_stream(
    user_message: str,
    deps: QaAgentDeps,
    agent: Agent[QaAgentDeps, ArchitectureReviewResult],
    conversation_id: str | None = None,
    usage_limits: UsageLimits | None = None,
) -> AsyncGenerator[dict, None]:
    """Standard streaming entry point. Called by mission control."""
    import asyncio
    import uuid

    if conversation_id is None:
        conversation_id = str(uuid.uuid4())

    queue: asyncio.Queue[dict] = asyncio.Queue()

    original_progress = deps.on_progress
    deps.on_progress = lambda event: queue.put_nowait(event)

    async def _run():
        logger.info("Architecture review agent invoked (stream)", extra={"message": user_message, "conversation_id": conversation_id})
        result = await agent.run(user_message, deps=deps, usage_limits=usage_limits)
        return result.output

    task = asyncio.create_task(_run())

    while not task.done():
        try:
            event = await asyncio.wait_for(queue.get(), timeout=0.5)
            yield event
        except asyncio.TimeoutError:
            continue

    while not queue.empty():
        yield queue.get_nowait()

    deps.on_progress = original_progress

    result = task.result()
    logger.info(
        "Architecture review agent completed (stream)",
        extra={"summary": result.summary, "conversation_id": conversation_id},
    )
    yield {"type": "complete", "result": result.model_dump(), "conversation_id": conversation_id}
