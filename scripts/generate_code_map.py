#!/usr/bin/env python3
"""Generate a structural code map of the repository.

Produces a JSON or Markdown representation of the codebase's structure,
ranked by PageRank importance. Output can be piped to an LLM or saved
as an artifact.

Usage:
    python scripts/generate_code_map.py                          # Markdown to stdout
    python scripts/generate_code_map.py --format json            # JSON to stdout
    python scripts/generate_code_map.py --format json --pretty   # Pretty-printed JSON
    python scripts/generate_code_map.py --max-tokens 2048        # Token-budgeted
    python scripts/generate_code_map.py --scope modules/         # Specific directory
    python scripts/generate_code_map.py --stats                  # Summary statistics only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.services.code_map.generator import generate_code_map
from modules.backend.services.code_map.assembler import (
    render_for_agent,
    render_markdown_tree,
    trim_by_rank,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a structural code map of the repository.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Maximum token budget for the output",
    )
    parser.add_argument(
        "--scope",
        nargs="*",
        default=None,
        help="Directories or files to include (default: entire repo)",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=None,
        help="Patterns to exclude",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print summary statistics only",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Write output to file instead of stdout",
    )

    args = parser.parse_args()

    # Default exclusions
    exclude = args.exclude or [
        ".venv/",
        "__pycache__/",
        ".git/",
        "node_modules/",
        ".mypy_cache/",
        ".pytest_cache/",
        ".ruff_cache/",
    ]

    code_map = generate_code_map(
        repo_root=PROJECT_ROOT,
        scope=args.scope,
        exclude=exclude,
        project_id=PROJECT_ROOT.name,
    )

    if args.stats:
        _print_stats(code_map)
        return

    if args.format == "json":
        if args.max_tokens:
            code_map = trim_by_rank(code_map, args.max_tokens)
        indent = 2 if args.pretty else None
        output = json.dumps(code_map, indent=indent)
    else:
        if args.max_tokens:
            output = render_for_agent(code_map, args.max_tokens)
        else:
            output = render_markdown_tree(code_map)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        stats = code_map.get("stats", {})
        print(
            f"Code map written to {args.output} "
            f"({stats.get('total_files', 0)} files, "
            f"{stats.get('total_lines', 0)} lines, "
            f"~{len(output) // 4} tokens)",
        )
    else:
        print(output)


def _print_stats(code_map: dict) -> None:
    """Print summary statistics about the code map."""
    stats = code_map.get("stats", {})
    modules = code_map.get("modules", {})

    print(f"Project:    {code_map.get('project_id', 'unknown')}")
    print(f"Commit:     {code_map.get('commit', 'unknown')[:12]}")
    print(f"Files:      {stats.get('total_files', 0)}")
    print(f"Lines:      {stats.get('total_lines', 0):,}")
    print(f"Classes:    {stats.get('total_classes', 0)}")
    print(f"Functions:  {stats.get('total_functions', 0)}")
    print()

    # Top 10 files by rank
    ranked = sorted(
        modules.items(),
        key=lambda x: x[1].get("rank", 0),
        reverse=True,
    )[:10]

    print("Top 10 files by PageRank:")
    for path, mod in ranked:
        rank = mod.get("rank", 0)
        lines = mod.get("lines", 0)
        n_classes = len(mod.get("classes", {}))
        n_funcs = len(mod.get("functions", {}))
        print(f"  {rank:.4f}  {path} ({lines} lines, {n_classes}C {n_funcs}F)")

    # Import graph stats
    graph = code_map.get("import_graph", {})
    total_edges = sum(len(v) for v in graph.values())
    print(f"\nImport graph: {len(graph)} modules, {total_edges} edges")

    # Estimated token counts
    json_tokens = len(json.dumps(code_map)) // 4
    md_tokens = len(render_markdown_tree(code_map)) // 4
    print(f"\nEstimated tokens: ~{json_tokens:,} (JSON), ~{md_tokens:,} (Markdown)")


if __name__ == "__main__":
    main()
