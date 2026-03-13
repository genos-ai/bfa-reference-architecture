"""Radon integration — cyclomatic complexity and maintainability index.

Radon measures two complementary signals:
    cc  — per-function cyclomatic complexity (decision path count)
    mi  — per-file maintainability index (0-100 composite)

Cyclomatic complexity captures branching density, which our AST analysis
(function length, nesting depth) cannot detect. A 20-line function with
15 if/elif branches is worse than a 50-line linear function — radon
quantifies this difference.

Feeds: Maintainability (mi), Testability (cc), Elegance (cc).
"""

from __future__ import annotations

import json
from pathlib import Path

from modules.backend.services.pqi.tools import (
    Finding,
    ToolResult,
    check_installed,
    run_command,
)

TOOL_NAME = "radon"


def is_available() -> bool:
    """Check if radon is installed."""
    return check_installed(TOOL_NAME)


def run(
    repo_root: Path,
    scope: list[str] | None = None,
    exclude: list[str] | None = None,
) -> ToolResult:
    """Run radon cc and mi, return merged findings and metrics.

    Runs two sub-commands:
        radon cc -j -s -a <paths>   — cyclomatic complexity per function
        radon mi -j -s <paths>      — maintainability index per file
    """
    if not is_available():
        return ToolResult(tool=TOOL_NAME, available=False)

    targets = _build_targets(repo_root, scope)
    exclude_args = _build_excludes(repo_root, exclude)

    cc_result = _run_cc(targets, exclude_args, repo_root)
    mi_result = _run_mi(targets, exclude_args, repo_root)

    return _merge_results(cc_result, mi_result)


def _build_targets(repo_root: Path, scope: list[str] | None) -> list[str]:
    """Build target path arguments."""
    if scope:
        targets = []
        for s in scope:
            target = repo_root / s
            if target.exists():
                targets.append(str(target))
        return targets or [str(repo_root)]
    return [str(repo_root)]


def _build_excludes(
    repo_root: Path, exclude: list[str] | None,
) -> list[str]:
    """Build radon exclude arguments."""
    if not exclude:
        return []
    # Radon uses -e with glob patterns
    patterns = []
    for exc in exclude:
        patterns.append(exc.rstrip("/") + "/*")
    return ["-e", ",".join(patterns)]


def _run_cc(
    targets: list[str], exclude_args: list[str], cwd: Path,
) -> dict | str:
    """Run radon cyclomatic complexity and return parsed JSON or error string."""
    args = [TOOL_NAME, "cc", "-j", "-s", "-a"] + exclude_args + targets
    stdout, stderr, returncode = run_command(args, cwd=cwd)

    if returncode != 0:
        return stderr or f"radon cc exited with code {returncode}"

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        return f"Failed to parse radon cc JSON: {e}"


def _run_mi(
    targets: list[str], exclude_args: list[str], cwd: Path,
) -> dict | str:
    """Run radon maintainability index and return parsed JSON or error string."""
    args = [TOOL_NAME, "mi", "-j", "-s"] + exclude_args + targets
    stdout, stderr, returncode = run_command(args, cwd=cwd)

    if returncode != 0:
        return stderr or f"radon mi exited with code {returncode}"

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        return f"Failed to parse radon mi JSON: {e}"


def _merge_results(
    cc_data: dict | str, mi_data: dict | str,
) -> ToolResult:
    """Merge cc and mi results into a single ToolResult."""
    errors = []
    if isinstance(cc_data, str):
        errors.append(cc_data)
        cc_data = {}
    if isinstance(mi_data, str):
        errors.append(mi_data)
        mi_data = {}

    if errors and not cc_data and not mi_data:
        return ToolResult(
            tool=TOOL_NAME, available=True, error="; ".join(errors),
        )

    # Parse cyclomatic complexity
    findings: list[Finding] = []
    complexities: list[int] = []
    rank_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}

    for file_path, functions in cc_data.items():
        if not isinstance(functions, list):
            continue
        for func in functions:
            complexity = func.get("complexity", 0)
            rank = func.get("rank", "A")
            complexities.append(complexity)
            rank_counts[rank] = rank_counts.get(rank, 0) + 1

            # Only create findings for C+ (complexity >= 11)
            if rank not in ("A", "B"):
                findings.append(Finding(
                    rule_id=f"CC:{rank}",
                    severity=_rank_to_severity(rank),
                    confidence="HIGH",
                    message=(
                        f"{func.get('type', 'function')} '{func.get('name', '?')}' "
                        f"has cyclomatic complexity {complexity} (rank {rank})"
                    ),
                    file=file_path,
                    line=func.get("lineno", 0),
                    tool=TOOL_NAME,
                ))

    # Parse maintainability index
    mi_scores: list[float] = []
    for file_path, mi_info in mi_data.items():
        if isinstance(mi_info, dict):
            mi_scores.append(mi_info.get("mi", 0.0))

    # Compute aggregate metrics
    metrics: dict[str, float] = {
        "total_functions": len(complexities),
    }

    if complexities:
        sorted_cc = sorted(complexities)
        p90_idx = min(int(len(sorted_cc) * 0.9), len(sorted_cc) - 1)
        metrics["avg_complexity"] = sum(complexities) / len(complexities)
        metrics["max_complexity"] = max(complexities)
        metrics["p90_complexity"] = sorted_cc[p90_idx]
        metrics["median_complexity"] = sorted_cc[len(sorted_cc) // 2]

    for rank, count in rank_counts.items():
        metrics[f"rank_{rank}"] = count

    # Percentage of functions at A or B (complexity ≤ 10)
    simple = rank_counts.get("A", 0) + rank_counts.get("B", 0)
    metrics["simple_ratio"] = simple / len(complexities) if complexities else 1.0

    if mi_scores:
        metrics["avg_mi"] = sum(mi_scores) / len(mi_scores)
        metrics["min_mi"] = min(mi_scores)
        metrics["files_analyzed_mi"] = len(mi_scores)

    error = "; ".join(errors) if errors else ""

    return ToolResult(
        tool=TOOL_NAME,
        available=True,
        findings=findings,
        metrics=metrics,
        error=error,
    )


def _rank_to_severity(rank: str) -> str:
    """Map radon rank to severity level."""
    if rank in ("E", "F"):
        return "HIGH"
    if rank in ("C", "D"):
        return "MEDIUM"
    return "LOW"
