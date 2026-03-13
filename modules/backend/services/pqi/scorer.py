"""PQI scorer — top-level orchestrator.

Composes AST analysis, external tool runs, code map analysis, and
all seven dimension scorers into a single ``score_project()`` call.

External tools are auto-discovered: if installed, they run and their
results are blended into the relevant dimensions. If missing, dimensions
gracefully degrade to AST-only scoring at lower confidence.
"""

from __future__ import annotations

from pathlib import Path

from modules.backend.services.pqi.ast_analysis import analyze_project
from modules.backend.services.pqi.composite import compute_pqi
from modules.backend.services.pqi.dimensions import (
    score_elegance,
    score_maintainability,
    score_modularity,
    score_reusability,
    score_robustness,
    score_security,
    score_testability,
)
from modules.backend.services.pqi.tools import ToolResult
from modules.backend.services.pqi.types import PQIResult


def score_project(
    repo_root: Path,
    scope: list[str] | None = None,
    exclude: list[str] | None = None,
    code_map: dict | None = None,
    profile: str = "production",
    tools: list[str] | None = None,
) -> PQIResult:
    """Score a Python project using the PyQuality Index.

    Orchestrates the full pipeline:
        1. AST analysis of all source files
        2. Run requested external tools (Bandit, etc.)
        3. Seven dimension scores computed (blending AST + tool results)
        4. Composite PQI via penalized weighted geometric mean

    Args:
        repo_root: Path to the repository root.
        scope: Directories/files to include.
        exclude: Patterns to exclude.
        code_map: Pre-generated code map dict (for modularity scoring).
            If None, modularity is scored with lower confidence.
        profile: Weight profile (production, library, data_science, safety_critical).
        tools: List of tool names to run (e.g. ["bandit"]).
            If None, no external tools are run (AST-only).

    Returns:
        PQIResult with composite score, dimension breakdowns, and recommendations.
    """
    # Stage 1: AST analysis
    project = analyze_project(repo_root, scope=scope, exclude=exclude)

    # Stage 2: Run requested external tools
    tool_results = _run_tools(repo_root, scope, exclude, tools or [])

    # Stage 3: Score all seven dimensions
    dimensions = {
        "maintainability": score_maintainability(project, tool_results),
        "security": score_security(project, tool_results),
        "modularity": score_modularity(project, code_map),
        "testability": score_testability(project, tool_results),
        "robustness": score_robustness(project),
        "elegance": score_elegance(project, tool_results),
        "reusability": score_reusability(project, code_map),
    }

    # Stage 4: Composite score
    return compute_pqi(
        dimensions,
        profile=profile,
        file_count=project.source_files,
        line_count=project.source_lines,
    )


_TOOL_REGISTRY: dict[str, str] = {
    "bandit": "modules.backend.services.pqi.tools.bandit",
    "radon": "modules.backend.services.pqi.tools.radon",
}


def _run_tools(
    repo_root: Path,
    scope: list[str] | None,
    exclude: list[str] | None,
    requested: list[str],
) -> dict[str, ToolResult]:
    """Run requested external tools.

    Each tool is independent — a failure in one does not affect others.
    Tools that are not installed return a ToolResult with available=False.
    """
    import importlib

    results: dict[str, ToolResult] = {}

    for name in requested:
        module_path = _TOOL_REGISTRY.get(name)
        if module_path is None:
            results[name] = ToolResult(
                tool=name, available=False, error=f"Unknown tool: {name}",
            )
            continue
        mod = importlib.import_module(module_path)
        results[name] = mod.run(repo_root, scope, exclude)

    return results
