#!/usr/bin/env python3
"""Score codebase quality using the PyQuality Index (PQI).

Produces a composite 0-100 score across 7 dimensions:
Maintainability, Security, Modularity, Testability, Robustness,
Elegance, and Reusability.

Usage:
    python scripts/score_quality.py                           # Score modules/
    python scripts/score_quality.py --scope modules/backend/  # Specific directory
    python scripts/score_quality.py --profile library          # Library weights
    python scripts/score_quality.py --json                     # JSON output
    python scripts/score_quality.py --recommendations          # Show improvement tips
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.services.pqi.scorer import score_project
from modules.backend.services.pqi.types import PQIResult


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score codebase quality using the PyQuality Index (PQI).",
    )
    parser.add_argument(
        "--scope",
        nargs="*",
        default=["modules/"],
        help="Directories or files to include (default: modules/)",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=None,
        help="Patterns to exclude",
    )
    parser.add_argument(
        "--profile",
        choices=["production", "library", "data_science", "safety_critical"],
        default="production",
        help="Weight profile (default: production)",
    )
    parser.add_argument(
        "--with-code-map",
        action="store_true",
        help="Generate code map for modularity scoring (recommended)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    parser.add_argument(
        "--recommendations",
        action="store_true",
        help="Show actionable recommendations",
    )
    parser.add_argument(
        "--use-bandit",
        action="store_true",
        help="Run Bandit security linter (requires: pip install bandit)",
    )
    parser.add_argument(
        "--use-radon",
        action="store_true",
        help="Run Radon complexity analyzer (requires: pip install radon)",
    )

    args = parser.parse_args()

    exclude = args.exclude or [
        ".venv/",
        "__pycache__/",
        ".git/",
        "node_modules/",
        ".mypy_cache/",
        ".pytest_cache/",
        ".ruff_cache/",
    ]

    # Generate code map if requested
    code_map = None
    if args.with_code_map:
        from modules.backend.services.code_map.generator import generate_code_map
        code_map = generate_code_map(
            repo_root=PROJECT_ROOT,
            scope=args.scope,
            exclude=exclude,
        )

    # Build tool list from flags
    tools = []
    if args.use_bandit:
        tools.append("bandit")
    if args.use_radon:
        tools.append("radon")

    result = score_project(
        repo_root=PROJECT_ROOT,
        scope=args.scope,
        exclude=exclude,
        code_map=code_map,
        profile=args.profile,
        tools=tools,
    )

    if args.json_output:
        _print_json(result)
    else:
        _print_report(result, show_recommendations=args.recommendations)


def _print_report(result: PQIResult, show_recommendations: bool = False) -> None:
    """Print a human-readable quality report."""
    band = result.quality_band.value
    bar = _score_bar(result.composite)

    print(f"\n{'=' * 60}")
    print(f"  PyQuality Index (PQI)")
    print(f"{'=' * 60}")
    print(f"\n  Composite Score:  {result.composite:.1f} / 100  [{band}]")
    print(f"  {bar}")
    print(f"\n  Files: {result.file_count}    Lines: {result.line_count:,}")
    if result.floor_penalty < 1.0:
        print(f"  Floor penalty: {result.floor_penalty:.3f} (dimension below critical threshold)")
    print(f"\n{'─' * 60}")
    print(f"  {'Dimension':<20} {'Score':>6}  {'Bar'}")
    print(f"{'─' * 60}")

    # Sort dimensions by weight (highest first)
    for name, dim in sorted(
        result.dimensions.items(),
        key=lambda x: x[1].score,
        reverse=True,
    ):
        bar = _mini_bar(dim.score)
        confidence = f" (confidence: {dim.confidence:.0%})" if dim.confidence < 1.0 else ""
        print(f"  {dim.name:<20} {dim.score:>5.1f}  {bar}{confidence}")

        if show_recommendations:
            for sub_name, sub_score in dim.sub_scores.items():
                print(f"    {sub_name:<22} {sub_score:>5.1f}")

    if show_recommendations:
        print(f"\n{'─' * 60}")
        print("  Recommendations")
        print(f"{'─' * 60}")
        for name, dim in sorted(result.dimensions.items(), key=lambda x: x[1].score):
            if dim.recommendations:
                print(f"\n  [{dim.name}]")
                for rec in dim.recommendations:
                    print(f"    - {rec}")

    print(f"\n{'=' * 60}\n")


def _print_json(result: PQIResult) -> None:
    """Print the result as JSON."""
    output = {
        "composite": result.composite,
        "quality_band": result.quality_band.value,
        "floor_penalty": result.floor_penalty,
        "file_count": result.file_count,
        "line_count": result.line_count,
        "dimensions": {
            name: {
                "name": dim.name,
                "score": round(dim.score, 1),
                "sub_scores": {k: round(v, 1) for k, v in dim.sub_scores.items()},
                "confidence": dim.confidence,
                "recommendations": dim.recommendations,
            }
            for name, dim in result.dimensions.items()
        },
    }
    print(json.dumps(output, indent=2))


def _score_bar(score: float, width: int = 40) -> str:
    """Create a visual score bar."""
    filled = int(score / 100 * width)
    empty = width - filled
    return f"  [{'█' * filled}{'░' * empty}] {score:.1f}%"


def _mini_bar(score: float, width: int = 20) -> str:
    """Create a compact visual score bar."""
    filled = int(score / 100 * width)
    empty = width - filled
    return f"{'█' * filled}{'░' * empty}"


if __name__ == "__main__":
    main()
