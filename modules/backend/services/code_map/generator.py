"""Code Map generator — top-level orchestrator.

Composes the four pipeline stages into a single ``generate_code_map()``
call. This is the primary public entry point for the code map service.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from modules.backend.services.code_map.assembler import assemble_code_map
from modules.backend.services.code_map.graph import build_reference_graph
from modules.backend.services.code_map.parser import parse_modules
from modules.backend.services.code_map.ranker import rank_symbols


def generate_code_map(
    repo_root: Path,
    scope: list[str] | None = None,
    exclude: list[str] | None = None,
    max_tokens: int | None = None,
    project_id: str = "",
) -> dict:
    """Generate a Code Map for the given repository.

    Orchestrates the full pipeline:
        1. parse_modules()          — AST extraction
        2. build_reference_graph()  — cross-reference edges
        3. rank_symbols()           — PageRank importance scoring
        4. assemble_code_map()      — JSON output

    Args:
        repo_root: Path to the repository root.
        scope: Directories/files to include. Defaults to entire repo.
        exclude: Patterns to exclude (e.g. tests/, .venv/).
        max_tokens: If set, trim output to fit this token budget.
        project_id: Identifier for the project in the output.

    Returns:
        JSON-serializable Code Map dictionary matching the schema
        defined in doc 49 (agentic-codebase-intelligence).
    """
    # Stage 1: Parse
    modules = parse_modules(repo_root, scope=scope, exclude=exclude)

    # Stage 2: Build reference graph
    graph = build_reference_graph(modules)

    # Stage 3: Rank symbols
    ranks = rank_symbols(graph)

    # Stage 4: Assemble output
    commit = _get_git_commit(repo_root)
    code_map = assemble_code_map(
        modules, ranks,
        repo_root_name=project_id or repo_root.name,
        commit=commit,
    )

    # Optional: trim to token budget
    if max_tokens is not None:
        from modules.backend.services.code_map.assembler import trim_by_rank
        code_map = trim_by_rank(code_map, max_tokens)

    return code_map


def _get_git_commit(repo_root: Path) -> str:
    """Get the current git commit hash, or empty string if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""
