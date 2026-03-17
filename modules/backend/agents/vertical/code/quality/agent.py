"""
QA Compliance Agent (code.quality.agent).

Thin wrapper over shared tool implementations and ComplianceScannerService.
All scanning logic lives in services/compliance.py. All tool implementations
live in agents/tools/. This file registers tools, receives config from the
mission control, and exposes the standard run_agent() / run_agent_stream() interface.
"""

from collections.abc import AsyncGenerator

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.models import Model

from modules.backend.agents.mission_control.helpers import assemble_instructions
from modules.backend.agents.deps.base import QaAgentDeps
from modules.backend.agents.schemas import PqiDimensionScore, PqiScore, QaAuditResult
from modules.backend.agents.tools import codemap, compliance, filesystem
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def create_agent(model: str | Model) -> Agent[QaAgentDeps, QaAuditResult]:
    """Factory: create a QA compliance agent with all tools registered.

    Called by AgentRegistry.get_instance() on first use.
    The registry caches the result — this function is not called again
    unless registry.reset() is called.
    """

    instructions = assemble_instructions("code", "quality")

    agent = Agent(
        model,
        deps_type=QaAgentDeps,
        output_type=QaAuditResult,
        instructions=instructions,
        output_retries=3,
    )

    @agent.tool
    async def load_project_standards(ctx: RunContext[QaAgentDeps]) -> dict:
        """Load project rules from docs/. Call this FIRST before scanning."""
        ctx.deps.emit({"type": "tool_start", "tool": "load_project_standards"})
        result = await compliance.load_project_standards(ctx.deps.project_root, ctx.deps.scope)
        ctx.deps.emit({
            "type": "tool_done", "tool": "load_project_standards",
            "detail": f"{len(result['rules'])} rules",
        })
        return result

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

    # ── Code Map & PQI tools ──────────────────────────────────────────

    @agent.tool
    async def generate_code_map_tool(ctx: RunContext[QaAgentDeps]) -> dict:
        """Generate a fresh Code Map for the codebase. Fast (~2-5s)."""
        ctx.deps.emit({"type": "tool_start", "tool": "generate_code_map"})
        result = await codemap.generate_code_map(ctx.deps.project_root, ctx.deps.scope)
        ctx.deps.emit({"type": "tool_done", "tool": "generate_code_map", "detail": f"{result.get('files', 0)} files"})
        return result

    @agent.tool
    async def load_code_map_tool(ctx: RunContext[QaAgentDeps]) -> dict:
        """Load the Code Map JSON (generates if missing or stale)."""
        ctx.deps.emit({"type": "tool_start", "tool": "load_code_map"})
        result = await codemap.load_code_map(ctx.deps.project_root, ctx.deps.scope)
        files = len(result.get("modules", {})) if "error" not in result else 0
        ctx.deps.emit({"type": "tool_done", "tool": "load_code_map", "detail": f"{files} modules"})
        return result

    @agent.tool
    async def get_dependency_analysis_tool(ctx: RunContext[QaAgentDeps]) -> dict:
        """Analyze import graph for circular deps and key modules."""
        ctx.deps.emit({"type": "tool_start", "tool": "get_dependency_analysis"})
        result = await codemap.get_dependency_analysis(ctx.deps.project_root, ctx.deps.scope)
        cycles = len(result.get("circular_dependencies", []))
        ctx.deps.emit({"type": "tool_done", "tool": "get_dependency_analysis", "detail": f"{cycles} cycles"})
        return result

    @agent.tool
    async def run_quality_score_tool(ctx: RunContext[QaAgentDeps]) -> dict:
        """Run the PyQuality Index (PQI) scorer. Returns composite 0-100 score."""
        ctx.deps.emit({"type": "tool_start", "tool": "run_quality_score"})
        result = await codemap.run_quality_score(ctx.deps.project_root, ctx.deps.scope)
        score = result.get("composite_score", "?")
        ctx.deps.emit({"type": "tool_done", "tool": "run_quality_score", "detail": f"PQI {score}"})
        return result

    logger.info("QA compliance agent created (read-only audit)", extra={"model": str(model)})
    return agent


async def _compute_pqi(deps: QaAgentDeps) -> PqiScore | None:
    """Compute PQI deterministically. Returns None on failure (non-fatal)."""
    try:
        raw = await codemap.run_quality_score(deps.project_root, deps.scope)
        if "error" in raw:
            logger.warning("PQI computation failed", extra={"error": raw["error"]})
            return None
        dimensions = {}
        for name, dim in raw.get("dimensions", {}).items():
            dimensions[name] = PqiDimensionScore(
                score=dim["score"],
                confidence=dim.get("confidence", 1.0),
                sub_scores=dim.get("sub_scores", {}),
            )
        return PqiScore(
            composite=raw["composite_score"],
            quality_band=raw["quality_band"],
            dimensions=dimensions,
            file_count=raw.get("file_count", 0),
            line_count=raw.get("line_count", 0),
        )
    except Exception:
        logger.exception("PQI computation failed")
        return None


def _format_pqi_for_llm(pqi: PqiScore) -> str:
    """Format PQI score as text the LLM can reference in its summary."""
    lines = [
        f"## PQI Score: {pqi.composite:.1f}/100 ({pqi.quality_band})",
        f"Files: {pqi.file_count} | Lines: {pqi.line_count}",
        "",
    ]
    for name, dim in sorted(pqi.dimensions.items(), key=lambda kv: -kv[1].score):
        lines.append(f"- {name}: {dim.score:.1f}/100 (confidence: {dim.confidence:.0%})")
        for sub, val in sorted(dim.sub_scores.items()):
            lines.append(f"    {sub}: {val:.1f}")
    return "\n".join(lines)


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

    # Compute PQI deterministically BEFORE the agent runs so the LLM
    # can reference the scores in its summary and recommendations.
    pqi = await _compute_pqi(deps)
    if pqi:
        pqi_text = _format_pqi_for_llm(pqi)
        user_message = (
            f"{user_message}\n\n"
            f"## Pre-computed PQI (PyQuality Index)\n\n"
            f"The following PQI score has been computed deterministically. "
            f"Reference it in your summary and recommendations — you do NOT "
            f"need to call run_quality_score_tool yourself.\n\n"
            f"{pqi_text}"
        )
        deps.emit({"type": "tool_done", "tool": "pqi_precompute", "detail": f"PQI {pqi.composite:.1f}"})

    result = await agent.run(user_message, deps=deps, usage_limits=usage_limits)

    # Inject PQI deterministically — overwrite whatever the LLM returned
    if pqi:
        result.output.pqi = pqi

    logger.info(
        "QA agent completed",
        extra={
            "summary": result.output.summary,
            "total_violations": result.output.total_violations,
            "pqi_composite": pqi.composite if pqi else None,
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

    # Compute PQI deterministically before agent runs
    pqi = await _compute_pqi(deps)
    enriched_message = user_message
    if pqi:
        pqi_text = _format_pqi_for_llm(pqi)
        enriched_message = (
            f"{user_message}\n\n"
            f"## Pre-computed PQI (PyQuality Index)\n\n"
            f"The following PQI score has been computed deterministically. "
            f"Reference it in your summary and recommendations — you do NOT "
            f"need to call run_quality_score_tool yourself.\n\n"
            f"{pqi_text}"
        )
        queue.put_nowait({"type": "tool_done", "tool": "pqi_precompute", "detail": f"PQI {pqi.composite:.1f}"})

    async def _run():
        logger.info("QA agent invoked (stream)", extra={"message": user_message, "conversation_id": conversation_id})
        result = await agent.run(enriched_message, deps=deps, usage_limits=usage_limits)
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

    output = task.result()
    # Inject PQI deterministically
    if pqi:
        output.pqi = pqi

    logger.info(
        "QA agent completed (stream)",
        extra={"summary": output.summary, "conversation_id": conversation_id},
    )
    yield {"type": "complete", "result": output.model_dump(), "conversation_id": conversation_id}
