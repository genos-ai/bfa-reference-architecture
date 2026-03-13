"""
Shared Code Map and PQI tool implementations.

Pure async functions — no PydanticAI dependency. Accept project_root
and scope, delegate to CodeMapLoader and PQI scorer.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from modules.backend.agents.deps.base import FileScope


async def generate_code_map(
    project_root: Path, scope: FileScope,
) -> dict:
    """Generate a fresh Code Map for the codebase.

    Runs the full pipeline (parse → graph → rank → assemble) and
    writes both JSON and Markdown to disk. Returns the JSON dict.
    Fast (~2-5s for typical projects).
    """
    scope.check_read("modules/")
    from modules.backend.services.code_map.loader import CodeMapLoader

    loader = CodeMapLoader(project_root)
    code_map = loader.regenerate()

    if code_map is None:
        return {"error": "Failed to generate Code Map"}

    stats = code_map.get("stats", {})
    return {
        "status": "generated",
        "files": stats.get("total_files", 0),
        "lines": stats.get("total_lines", 0),
        "classes": stats.get("total_classes", 0),
        "functions": stats.get("total_functions", 0),
        "commit": code_map.get("commit", "")[:12],
    }


async def load_code_map(
    project_root: Path, scope: FileScope,
) -> dict:
    """Load the Code Map JSON, generating if missing or stale.

    Returns the full Code Map dict (modules, import_graph, stats, ranks).
    The agent can use this to inspect dependencies, find files, and
    understand codebase structure.
    """
    scope.check_read("modules/")
    from modules.backend.services.code_map.loader import CodeMapLoader

    loader = CodeMapLoader(project_root)
    code_map = loader.ensure_fresh()

    if code_map is None:
        return {"error": "Code Map unavailable"}

    return code_map


async def get_dependency_analysis(
    project_root: Path, scope: FileScope,
) -> dict:
    """Analyze the import graph for circular dependencies and key modules.

    Returns circular dependency cycles and top-ranked modules by PageRank.
    """
    scope.check_read("modules/")
    from modules.backend.services.code_map.loader import CodeMapLoader
    from modules.backend.services.code_map.assembler import find_circular_deps

    loader = CodeMapLoader(project_root)
    code_map = loader.ensure_fresh()

    if code_map is None:
        return {"error": "Code Map unavailable"}

    import_graph = code_map.get("import_graph", {})
    cycles = find_circular_deps(import_graph)

    # Top modules by PageRank (highest rank = most referenced)
    modules = code_map.get("modules", {})
    ranked = sorted(
        modules.items(),
        key=lambda kv: kv[1].get("rank", 999),
    )
    top_modules = [
        {"path": path, "rank": data.get("rank", 0), "lines": data.get("lines", 0)}
        for path, data in ranked[:10]
    ]

    return {
        "total_modules": len(modules),
        "total_edges": sum(len(deps) for deps in import_graph.values()),
        "circular_dependencies": [
            " → ".join(cycle) for cycle in cycles
        ],
        "top_modules_by_importance": top_modules,
    }


async def run_quality_score(
    project_root: Path, scope: FileScope,
) -> dict:
    """Run the PyQuality Index (PQI) scorer on the codebase.

    Returns composite score (0-100), quality band, and per-dimension
    breakdowns with recommendations.
    """
    scope.check_read("modules/")
    from modules.backend.services.code_map.loader import CodeMapLoader
    from modules.backend.services.pqi.scorer import score_project

    # Load code map for modularity/reusability scoring
    loader = CodeMapLoader(project_root)
    code_map = loader.get_json()

    # Auto-detect available tools for deeper analysis
    tools = []
    from modules.backend.services.pqi.tools.bandit import is_available as bandit_available
    from modules.backend.services.pqi.tools.radon import is_available as radon_available
    if bandit_available():
        tools.append("bandit")
    if radon_available():
        tools.append("radon")

    result = score_project(
        repo_root=project_root,
        scope=["modules/"],
        code_map=code_map,
        tools=tools,
    )

    # Serialize dataclass to dict for the agent
    dimensions = {}
    for name, dim in result.dimensions.items():
        dimensions[name] = {
            "score": round(dim.score, 1),
            "confidence": round(dim.confidence, 2),
            "recommendations": dim.recommendations,
        }

    return {
        "composite_score": round(result.composite, 1),
        "quality_band": result.quality_band.value,
        "floor_penalty": round(result.floor_penalty, 3),
        "file_count": result.file_count,
        "line_count": result.line_count,
        "dimensions": dimensions,
    }
