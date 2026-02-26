"""
QA Compliance Agent (code.qa.agent).

Audits the codebase for rule violations, fixes auto-fixable issues,
and escalates design decisions to the human. Uses deterministic
scanner tools for detection and PydanticAI for reasoning about findings.

Usage:
    from modules.backend.agents.vertical.code.qa.agent import run_qa_agent
    result = await run_qa_agent("run compliance audit")
"""

import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from collections.abc import AsyncGenerator
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a QA compliance agent for a Python codebase. "
    "You find rule violations, fix them, and verify the fixes.\n\n"
    "Workflow:\n"
    "1. Use list_python_files to discover files in scope\n"
    "2. Run all scan_* tools to detect violations\n"
    "3. For each violation, classify as auto_fixable or needs_human_decision\n"
    "4. For auto_fixable violations: use apply_fix to fix them immediately\n"
    "5. For violations needing a design decision: set needs_human_decision=True, "
    "describe the question and options clearly in human_question\n"
    "6. After applying fixes, use run_tests to verify nothing broke\n"
    "7. Return a QaAuditResult with all violations and their fix status\n\n"
    "Rules:\n"
    "- Fix auto_fixable violations directly — do not ask the human\n"
    "- When a fix requires choosing where config goes or how to restructure, "
    "that is a human decision — present clear options\n"
    "- After fixing, always run tests\n"
    "- If tests fail after a fix, report the failure — do not attempt to fix the test\n"
    "- Be precise about file paths and line numbers\n"
    "- When uncertain whether something is a true violation, use read_source_file "
    "to examine the context before classifying"
)
# NOTE: This constant is in the agent system prompt.
# Moving it to config/agents/code/qa/agent.yaml would require
# significant refactoring of the agent initialization. It is kept here
# because it represents the core behavioral instructions for the agent,
# not a configurable system parameter.


# =============================================================================
# Output Schemas
# =============================================================================


class Violation(BaseModel):
    """A single compliance violation found during audit."""

    rule_id: str
    file: str
    line: int | None = None
    message: str
    severity: str
    auto_fixable: bool = False
    fix_description: str | None = None
    fixed: bool = False
    needs_human_decision: bool = False
    human_question: str | None = None


class QaAuditResult(BaseModel):
    """Structured output from the QA compliance agent."""

    summary: str
    total_violations: int
    error_count: int
    warning_count: int
    fixed_count: int
    needs_human_count: int
    violations: list[Violation]
    tests_passed: bool | None = None
    scanned_files_count: int


# =============================================================================
# Dependencies
# =============================================================================


@dataclass
class QaAgentDeps:
    """Dependencies injected into the QA agent at runtime."""

    config: dict[str, Any]
    on_progress: Any = None

    def emit(self, event: dict) -> None:
        """Emit a progress event if a callback is registered."""
        if self.on_progress is not None:
            self.on_progress(event)


# =============================================================================
# Config Loading
# =============================================================================


def _load_agent_config() -> dict[str, Any]:
    """Load QA agent configuration from YAML."""
    project_root = find_project_root()
    config_path = project_root / "config" / "agents" / "code" / "qa" / "agent.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Agent config not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def _get_exclusion_paths(config: dict[str, Any]) -> set[str]:
    """Get the set of excluded path prefixes from config."""
    return set(config.get("exclusions", {}).get("paths", []))


def _is_excluded(file_path: str, exclusion_paths: set[str]) -> bool:
    """Check if a file path matches any exclusion prefix."""
    for excl in exclusion_paths:
        if file_path.startswith(excl) or file_path.startswith(excl.rstrip("/")):
            return True
    return False


def _get_enabled_rule_ids(config: dict[str, Any]) -> set[str]:
    """Get the set of enabled rule IDs from config."""
    return {
        rule["id"]
        for rule in config.get("rules", [])
        if rule.get("enabled", True)
    }


def _get_rule_severity(config: dict[str, Any], rule_id: str) -> str:
    """Get severity for a rule from config."""
    for rule in config.get("rules", []):
        if rule["id"] == rule_id:
            return rule.get("severity", "warning")
    return "warning"


# =============================================================================
# Scanner Helpers
# =============================================================================


def _collect_python_files(project_root: Path, exclusion_paths: set[str]) -> list[str]:
    """Walk the project and collect .py files, respecting exclusions."""
    files: list[str] = []
    for py_file in sorted(project_root.rglob("*.py")):
        rel = str(py_file.relative_to(project_root))
        if not _is_excluded(rel, exclusion_paths):
            files.append(rel)
    return files


def _scan_file_lines(project_root: Path, rel_path: str) -> list[str]:
    """Read a file and return its lines."""
    full_path = project_root / rel_path
    if not full_path.is_file():
        return []
    return full_path.read_text(encoding="utf-8").splitlines()


# =============================================================================
# Agent Definition
# =============================================================================


_agent: Agent[QaAgentDeps, QaAuditResult] | None = None


def _get_agent() -> Agent[QaAgentDeps, QaAuditResult]:
    """Lazy initialization — only creates the agent when first called."""
    global _agent
    if _agent is not None:
        return _agent

    import os

    from modules.backend.core.config import get_settings

    settings = get_settings()
    os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)

    config = _load_agent_config()
    model = config["model"]

    agent = Agent(
        model,
        deps_type=QaAgentDeps,
        output_type=QaAuditResult,
        instructions=SYSTEM_PROMPT,
    )

    # =========================================================================
    # Scanner Tools
    # =========================================================================

    @agent.tool
    async def list_python_files(ctx: RunContext[QaAgentDeps]) -> list[str]:
        """List all Python files in scope, respecting exclusion patterns.

        Returns a list of file paths relative to project root.
        """
        ctx.deps.emit({"type": "tool_start", "tool": "list_python_files"})
        project_root = find_project_root()
        exclusions = _get_exclusion_paths(ctx.deps.config)
        files = _collect_python_files(project_root, exclusions)
        ctx.deps.emit({"type": "tool_done", "tool": "list_python_files", "detail": f"{len(files)} files"})
        return files

    @agent.tool
    async def scan_import_violations(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan for import violations: relative imports, direct 'import logging'
        in modules/, and os.getenv() with hardcoded fallback defaults.

        Returns a list of findings with file, line, and message.
        """
        ctx.deps.emit({"type": "tool_start", "tool": "scan_import_violations"})
        project_root = find_project_root()
        exclusions = _get_exclusion_paths(ctx.deps.config)
        enabled = _get_enabled_rule_ids(ctx.deps.config)
        findings: list[dict] = []

        for rel_path in _collect_python_files(project_root, exclusions):
            lines = _scan_file_lines(project_root, rel_path)
            in_modules = rel_path.startswith("modules/")
            is_core_logging = rel_path == "modules/backend/core/logging.py"

            for i, line in enumerate(lines, 1):
                stripped = line.strip()

                if "no_relative_imports" in enabled and re.match(r"^from\s+\.", stripped):
                    findings.append({
                        "rule_id": "no_relative_imports",
                        "file": rel_path, "line": i,
                        "message": stripped,
                    })

                if (
                    "no_direct_logging" in enabled
                    and in_modules
                    and not is_core_logging
                    and stripped == "import logging"
                ):
                    findings.append({
                        "rule_id": "no_direct_logging",
                        "file": rel_path, "line": i,
                        "message": "Direct 'import logging' — use get_logger() from core.logging",
                    })

                if "no_os_getenv_fallback" in enabled:
                    if re.search(r"os\.(getenv|environ\.get)\s*\(.+,\s*.+\)", stripped):
                        findings.append({
                            "rule_id": "no_os_getenv_fallback",
                            "file": rel_path, "line": i,
                            "message": stripped,
                        })

        ctx.deps.emit({"type": "tool_done", "tool": "scan_import_violations", "detail": f"{len(findings)} findings"})
        return findings

    @agent.tool
    async def scan_datetime_violations(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan for datetime.now() and datetime.utcnow() usage.

        Returns a list of findings with file, line, and message.
        """
        ctx.deps.emit({"type": "tool_start", "tool": "scan_datetime_violations"})
        project_root = find_project_root()
        exclusions = _get_exclusion_paths(ctx.deps.config)
        enabled = _get_enabled_rule_ids(ctx.deps.config)
        findings: list[dict] = []

        if "no_datetime_now" not in enabled:
            return findings

        pattern = re.compile(r"datetime\.(now|utcnow)\s*\(")

        for rel_path in _collect_python_files(project_root, exclusions):
            lines = _scan_file_lines(project_root, rel_path)
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    findings.append({
                        "rule_id": "no_datetime_now",
                        "file": rel_path, "line": i,
                        "message": line.strip(),
                    })

        ctx.deps.emit({"type": "tool_done", "tool": "scan_datetime_violations", "detail": f"{len(findings)} findings"})
        return findings

    @agent.tool
    async def scan_hardcoded_values(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan for module-level UPPER_CASE constants with literal values
        that likely should be in YAML config.

        Skips __all__, __version__, and similar dunder names.
        Returns a list of findings with file, line, and message.
        """
        ctx.deps.emit({"type": "tool_start", "tool": "scan_hardcoded_values"})
        project_root = find_project_root()
        exclusions = _get_exclusion_paths(ctx.deps.config)
        enabled = _get_enabled_rule_ids(ctx.deps.config)
        findings: list[dict] = []

        if "no_hardcoded_values" not in enabled:
            return findings

        skip_names = {"__all__", "__version__", "__tablename__", "__abstract__"}

        for rel_path in _collect_python_files(project_root, exclusions):
            full_path = project_root / rel_path
            try:
                source = full_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError):
                continue

            for node in ast.iter_child_nodes(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    name = target.id
                    if name in skip_names:
                        continue
                    if not re.match(r"^[A-Z][A-Z0-9_]+$", name):
                        continue
                    if not isinstance(node.value, ast.Constant):
                        continue
                    val = node.value.value
                    if isinstance(val, (int, float, str)) and not isinstance(val, bool):
                        findings.append({
                            "rule_id": "no_hardcoded_values",
                            "file": rel_path, "line": node.lineno,
                            "message": f"{name} = {val!r}",
                        })

        ctx.deps.emit({"type": "tool_done", "tool": "scan_hardcoded_values", "detail": f"{len(findings)} findings"})
        return findings

    @agent.tool
    async def scan_file_sizes(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan for Python files exceeding the configured line limit.

        Returns a list of findings with file, line count, and limit.
        """
        ctx.deps.emit({"type": "tool_start", "tool": "scan_file_sizes"})
        project_root = find_project_root()
        exclusions = _get_exclusion_paths(ctx.deps.config)
        enabled = _get_enabled_rule_ids(ctx.deps.config)
        findings: list[dict] = []

        if "file_size_limit" not in enabled:
            return findings

        limit = ctx.deps.config.get("file_size_limit", 1000)

        for rel_path in _collect_python_files(project_root, exclusions):
            lines = _scan_file_lines(project_root, rel_path)
            count = len(lines)
            if count > limit:
                findings.append({
                    "rule_id": "file_size_limit",
                    "file": rel_path, "line": None,
                    "message": f"{count} lines (limit: {limit})",
                })

        ctx.deps.emit({"type": "tool_done", "tool": "scan_file_sizes", "detail": f"{len(findings)} findings"})
        return findings

    @agent.tool
    async def scan_cli_options(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan root-level CLI scripts for positional arguments
        (should use --options) and missing --verbose/--debug flags.

        Returns a list of findings with file and message.
        """
        ctx.deps.emit({"type": "tool_start", "tool": "scan_cli_options"})
        project_root = find_project_root()
        enabled = _get_enabled_rule_ids(ctx.deps.config)
        findings: list[dict] = []

        root_py_files = sorted(project_root.glob("*.py"))

        for full_path in root_py_files:
            rel_path = str(full_path.relative_to(project_root))
            try:
                source = full_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            if "cli_options_not_positional" in enabled:
                if "add_argument" in source:
                    try:
                        tree = ast.parse(source)
                        for node in ast.walk(tree):
                            if (
                                isinstance(node, ast.Call)
                                and isinstance(node.func, ast.Attribute)
                                and node.func.attr == "add_argument"
                                and node.args
                            ):
                                first_arg = node.args[0]
                                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                                    if not first_arg.value.startswith("-"):
                                        findings.append({
                                            "rule_id": "cli_options_not_positional",
                                            "file": rel_path, "line": node.lineno,
                                            "message": f"Positional argument: {first_arg.value!r}",
                                        })
                    except SyntaxError:
                        pass

            if "cli_verbose_debug" in enabled:
                has_verbose = "--verbose" in source
                has_debug = "--debug" in source
                if not has_verbose or not has_debug:
                    missing = []
                    if not has_verbose:
                        missing.append("--verbose")
                    if not has_debug:
                        missing.append("--debug")
                    findings.append({
                        "rule_id": "cli_verbose_debug",
                        "file": rel_path, "line": None,
                        "message": f"Missing CLI options: {', '.join(missing)}",
                    })

        ctx.deps.emit({"type": "tool_done", "tool": "scan_cli_options", "detail": f"{len(findings)} findings"})
        return findings

    @agent.tool
    async def scan_config_files(ctx: RunContext[QaAgentDeps]) -> list[dict]:
        """Scan YAML config files for missing option header comments.

        Checks config/settings/*.yaml and config/agents/**/*.yaml.
        Returns a list of findings with file and message.
        """
        ctx.deps.emit({"type": "tool_start", "tool": "scan_config_files"})
        project_root = find_project_root()
        enabled = _get_enabled_rule_ids(ctx.deps.config)
        findings: list[dict] = []

        if "yaml_header_comment" not in enabled:
            return findings

        yaml_dirs = [
            project_root / "config" / "settings",
            project_root / "config" / "agents",
        ]

        for yaml_dir in yaml_dirs:
            if not yaml_dir.exists():
                continue
            for yaml_path in sorted(yaml_dir.rglob("*.yaml")):
                rel_path = str(yaml_path.relative_to(project_root))
                try:
                    head = yaml_path.read_text(encoding="utf-8")[:500]
                except (OSError, UnicodeDecodeError):
                    continue

                if "# =====" not in head:
                    findings.append({
                        "rule_id": "yaml_header_comment",
                        "file": rel_path, "line": 1,
                        "message": "YAML file missing commented option header",
                    })

        ctx.deps.emit({"type": "tool_done", "tool": "scan_config_files", "detail": f"{len(findings)} findings"})
        return findings

    # =========================================================================
    # Action Tools
    # =========================================================================

    @agent.tool
    async def read_source_file(ctx: RunContext[QaAgentDeps], file_path: str) -> str:
        """Read a source file and return its contents with line numbers.

        Args:
            file_path: Path relative to project root
        """
        ctx.deps.emit({"type": "tool_start", "tool": "read_source_file", "detail": file_path})
        project_root = find_project_root()
        full_path = project_root / file_path

        if not full_path.is_file():
            return f"Error: file not found: {file_path}"

        lines = full_path.read_text(encoding="utf-8").splitlines()
        numbered = [f"{i:4d}| {line}" for i, line in enumerate(lines, 1)]
        return "\n".join(numbered)

    @agent.tool
    async def apply_fix(
        ctx: RunContext[QaAgentDeps],
        file_path: str,
        old_text: str,
        new_text: str,
    ) -> dict:
        """Replace exact text in a file. Returns success status.

        Args:
            file_path: Path relative to project root
            old_text: Exact text to find (must appear exactly once)
            new_text: Replacement text
        """
        ctx.deps.emit({"type": "tool_start", "tool": "apply_fix", "detail": file_path})
        project_root = find_project_root()
        full_path = project_root / file_path

        if not full_path.is_file():
            return {"success": False, "error": f"File not found: {file_path}"}

        content = full_path.read_text(encoding="utf-8")
        count = content.count(old_text)

        if count == 0:
            return {"success": False, "error": "old_text not found in file"}
        if count > 1:
            return {"success": False, "error": f"old_text found {count} times — must be unique"}

        new_content = content.replace(old_text, new_text, 1)
        full_path.write_text(new_content, encoding="utf-8")

        ctx.deps.emit({"type": "tool_done", "tool": "apply_fix", "detail": f"fixed {file_path}"})
        return {"success": True, "file": file_path}

    @agent.tool
    async def run_tests(ctx: RunContext[QaAgentDeps]) -> dict:
        """Run the unit test suite and return results.

        Returns pass/fail status and failure details if any.
        """
        ctx.deps.emit({"type": "tool_start", "tool": "run_tests"})
        project_root = find_project_root()
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/unit", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
        )

        output_lines = result.stdout.splitlines()
        tail = "\n".join(output_lines[-50:]) if len(output_lines) > 50 else result.stdout
        passed = result.returncode == 0

        ctx.deps.emit({"type": "tool_done", "tool": "run_tests", "detail": "passed" if passed else "FAILED"})
        return {
            "passed": passed,
            "exit_code": result.returncode,
            "output": tail,
        }

    _agent = agent
    logger.info("QA compliance agent initialized", extra={"model": model})
    return _agent


# =============================================================================
# Entry Point
# =============================================================================


async def run_qa_agent(user_message: str) -> QaAuditResult:
    """
    Run the QA compliance agent.

    Args:
        user_message: The user's request (e.g., "run compliance audit")

    Returns:
        QaAuditResult with all violations and their fix status
    """
    agent = _get_agent()
    config = _load_agent_config()
    deps = QaAgentDeps(config=config)

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
    """
    Run the QA agent with streaming progress events and conversation memory.

    On first call (no conversation_id), starts a new conversation.
    On follow-up calls (with conversation_id), continues with full history
    so the agent remembers what it found and what the human decided.

    Yields SSE-compatible dicts:
        {"type": "tool_start", "tool": "scan_import_violations"}
        {"type": "tool_done", "tool": "scan_import_violations", "detail": "3 findings"}
        {"type": "complete", "result": {...}, "conversation_id": "..."}

    Args:
        user_message: The user's message
        conversation_id: ID from a previous turn to continue the conversation
    """
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
        config = _load_agent_config()
        deps = QaAgentDeps(config=config, on_progress=on_progress)
        logger.info(
            "QA agent invoked (stream)",
            extra={"message": user_message, "conversation_id": conversation_id},
        )
        result = await agent.run(
            user_message,
            deps=deps,
            message_history=message_history,
        )
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
        extra={
            "summary": result.summary,
            "total_violations": result.total_violations,
            "fixed_count": result.fixed_count,
            "conversation_id": conversation_id,
        },
    )
    yield {
        "type": "complete",
        "result": result.model_dump(),
        "conversation_id": conversation_id,
    }
