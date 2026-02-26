"""
QA Compliance Agent (code.qa.agent).

Thin wrapper over shared tool implementations and ComplianceScannerService.
All scanning logic lives in services/compliance.py. All tool implementations
live in agents/tools/. This file registers tools, assembles prompts, and
exposes run_qa_agent() and run_qa_agent_stream() entry points.
"""

from collections.abc import AsyncGenerator
from typing import Any

from pydantic_ai import Agent, RunContext

from modules.backend.agents.coordinator.coordinator import assemble_instructions, build_deps_from_config
from modules.backend.agents.deps.base import QaAgentDeps
from modules.backend.agents.schemas import QaAuditResult
from modules.backend.agents.tools import compliance, code, filesystem
from modules.backend.core.logging import get_logger
from modules.backend.services.compliance import load_config

logger = get_logger(__name__)

_agent: Agent[QaAgentDeps, QaAuditResult] | None = None


def _get_agent() -> Agent[QaAgentDeps, QaAuditResult]:
    """Lazy initialization — creates the agent on first call."""
    global _agent
    if _agent is not None:
        return _agent

    import os
    from modules.backend.core.config import get_settings
    settings = get_settings()
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)

    config = load_config()
    model = config["model"]
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
        exclusions = set(ctx.deps.config.get("exclusions", {}).get("paths", []))
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

    _agent = agent
    logger.info("QA compliance agent initialized", extra={"model": model})
    return _agent


async def run_qa_agent(user_message: str) -> QaAuditResult:
    """Run the QA compliance agent. Returns structured audit result."""
    agent = _get_agent()
    config = load_config()
    deps = QaAgentDeps(**build_deps_from_config(config))

    logger.info("QA agent invoked", extra={"message": user_message})
    result = await agent.run(user_message, deps=deps)

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


_conversations: dict[str, list] = {}


async def run_qa_agent_stream(
    user_message: str,
    conversation_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Run the QA agent with streaming progress events and conversation memory."""
    import asyncio
    import uuid

    if conversation_id is None:
        conversation_id = str(uuid.uuid4())
    message_history = _conversations.get(conversation_id)

    queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_progress(event: dict) -> None:
        queue.put_nowait(event)

    async def _run():
        agent = _get_agent()
        config = load_config()
        deps = QaAgentDeps(**build_deps_from_config(config), on_progress=on_progress)
        logger.info("QA agent invoked (stream)", extra={"message": user_message, "conversation_id": conversation_id})
        result = await agent.run(user_message, deps=deps, message_history=message_history)
        _conversations[conversation_id] = result.all_messages()
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

    result = task.result()
    logger.info(
        "QA agent completed (stream)",
        extra={"summary": result.summary, "conversation_id": conversation_id},
    )
    yield {"type": "complete", "result": result.model_dump(), "conversation_id": conversation_id}
