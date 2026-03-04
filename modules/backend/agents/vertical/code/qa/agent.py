"""
QA Compliance Agent (code.qa.agent).

Thin wrapper over shared tool implementations and ComplianceScannerService.
All scanning logic lives in services/compliance.py. All tool implementations
live in agents/tools/. This file registers tools, receives config from the
mission control, and exposes the standard run_agent() / run_agent_stream() interface.
"""

from collections.abc import AsyncGenerator

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.models import Model

from modules.backend.agents.mission_control.mission_control import assemble_instructions
from modules.backend.agents.deps.base import QaAgentDeps
from modules.backend.agents.schemas import QaAuditResult
from modules.backend.agents.tools import code, compliance, filesystem
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def create_agent(model: str | Model) -> Agent[QaAgentDeps, QaAuditResult]:
    """Factory: create a QA compliance agent with all tools registered.

    Called by AgentRegistry.get_instance() on first use.
    The registry caches the result — this function is not called again
    unless registry.reset() is called.
    """

    instructions = assemble_instructions("code", "qa")

    agent = Agent(
        model,
        deps_type=QaAgentDeps,
        output_type=QaAuditResult,
        instructions=instructions,
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
    async def scan_import_violations(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan for import violations: relative imports, direct logging, os.getenv fallbacks."""
        ctx.deps.emit({"type": "tool_start", "tool": "scan_import_violations"})
        findings = await compliance.scan_imports(ctx.deps.project_root, ctx.deps.scope, ctx.deps.config)
        ctx.deps.emit({"type": "tool_done", "tool": "scan_import_violations", "detail": f"{len(findings)} findings"})
        return findings

    @agent.tool
    async def scan_datetime_violations(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan for datetime.now() and datetime.utcnow() usage."""
        ctx.deps.emit({"type": "tool_start", "tool": "scan_datetime_violations"})
        findings = await compliance.scan_datetime(ctx.deps.project_root, ctx.deps.scope, ctx.deps.config)
        ctx.deps.emit({"type": "tool_done", "tool": "scan_datetime_violations", "detail": f"{len(findings)} findings"})
        return findings

    @agent.tool
    async def scan_hardcoded_values(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan for module-level UPPER_CASE constants with literal values."""
        ctx.deps.emit({"type": "tool_start", "tool": "scan_hardcoded_values"})
        findings = await compliance.scan_hardcoded(ctx.deps.project_root, ctx.deps.scope, ctx.deps.config)
        ctx.deps.emit({"type": "tool_done", "tool": "scan_hardcoded_values", "detail": f"{len(findings)} findings"})
        return findings

    @agent.tool
    async def scan_file_sizes(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan for Python files exceeding the configured line limit."""
        ctx.deps.emit({"type": "tool_start", "tool": "scan_file_sizes"})
        findings = await compliance.scan_file_sizes(ctx.deps.project_root, ctx.deps.scope, ctx.deps.config)
        ctx.deps.emit({"type": "tool_done", "tool": "scan_file_sizes", "detail": f"{len(findings)} findings"})
        return findings

    @agent.tool
    async def scan_cli_options(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan root CLI scripts for positional args and missing --verbose/--debug."""
        ctx.deps.emit({"type": "tool_start", "tool": "scan_cli_options"})
        findings = await compliance.scan_cli_options(ctx.deps.project_root, ctx.deps.scope, ctx.deps.config)
        ctx.deps.emit({"type": "tool_done", "tool": "scan_cli_options", "detail": f"{len(findings)} findings"})
        return findings

    @agent.tool
    async def scan_config_files(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan YAML config files for missing option header comments."""
        ctx.deps.emit({"type": "tool_start", "tool": "scan_config_files"})
        findings = await compliance.scan_config_files(ctx.deps.project_root, ctx.deps.scope, ctx.deps.config)
        ctx.deps.emit({"type": "tool_done", "tool": "scan_config_files", "detail": f"{len(findings)} findings"})
        return findings

    @agent.tool
    async def read_source_file(ctx: RunContext[QaAgentDeps], file_path: str) -> str:
        """Read a source file and return its contents with line numbers."""
        ctx.deps.emit({"type": "tool_start", "tool": "read_source_file", "detail": file_path})
        return await filesystem.read_file(ctx.deps.project_root, file_path, ctx.deps.scope)

    @agent.tool
    async def apply_fix_tool(ctx: RunContext[QaAgentDeps], file_path: str, old_text: str, new_text: str) -> dict:
        """Replace exact text in a file. Returns success status."""
        ctx.deps.emit({"type": "tool_start", "tool": "apply_fix", "detail": file_path})
        result = await code.apply_fix(ctx.deps.project_root, file_path, old_text, new_text, ctx.deps.scope)
        ctx.deps.emit({"type": "tool_done", "tool": "apply_fix", "detail": f"{'fixed' if result['success'] else 'failed'} {file_path}"})
        return result

    @agent.tool
    async def run_tests_tool(ctx: RunContext[QaAgentDeps]) -> dict:
        """Run the unit test suite and return results."""
        ctx.deps.emit({"type": "tool_start", "tool": "run_tests"})
        result = await code.run_tests(ctx.deps.project_root)
        ctx.deps.emit({"type": "tool_done", "tool": "run_tests", "detail": "passed" if result["passed"] else "FAILED"})
        return result

    logger.info("QA compliance agent created", extra={"model": str(model)})
    return agent


async def run_agent(
    user_message: str,
    deps: QaAgentDeps,
    agent: Agent[QaAgentDeps, QaAuditResult],
    usage_limits: UsageLimits | None = None,
) -> QaAuditResult:
    """Standard agent entry point. Called by mission control.

    The agent instance is provided by mission control (from the registry).
    """

    logger.info("QA agent invoked", extra={"message": user_message})
    result = await agent.run(user_message, deps=deps, usage_limits=usage_limits)

    logger.info(
        "QA agent completed",
        extra={
            "summary": result.output.summary,
            "total_violations": result.output.total_violations,
            "fixed_count": result.output.fixed_count,
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
    agent: Agent[QaAgentDeps, QaAuditResult],
    conversation_id: str | None = None,
    usage_limits: UsageLimits | None = None,
) -> AsyncGenerator[dict, None]:
    """Standard streaming entry point. Called by mission control.

    Stateless — each call is a fresh conversation. Conversation
    persistence will be added when doc 46 session model is implemented.
    """
    import asyncio
    import uuid

    if conversation_id is None:
        conversation_id = str(uuid.uuid4())

    queue: asyncio.Queue[dict] = asyncio.Queue()

    original_progress = deps.on_progress
    deps.on_progress = lambda event: queue.put_nowait(event)

    async def _run():
        logger.info("QA agent invoked (stream)", extra={"message": user_message, "conversation_id": conversation_id})
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
        "QA agent completed (stream)",
        extra={"summary": result.summary, "conversation_id": conversation_id},
    )
    yield {"type": "complete", "result": result.model_dump(), "conversation_id": conversation_id}
