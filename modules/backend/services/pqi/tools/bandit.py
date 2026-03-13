"""Bandit integration — Python security linter.

Bandit finds common security issues in Python code: SQL injection,
shell injection, hardcoded passwords, weak crypto, unsafe deserialization,
and more. It produces severity-weighted findings (HIGH/MEDIUM/LOW)
with confidence levels.

Feeds: Security dimension (primary), Robustness dimension (secondary).
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

TOOL_NAME = "bandit"


def is_available() -> bool:
    """Check if bandit is installed."""
    return check_installed(TOOL_NAME)


def run(
    repo_root: Path,
    scope: list[str] | None = None,
    exclude: list[str] | None = None,
) -> ToolResult:
    """Run bandit and return parsed findings.

    Args:
        repo_root: Repository root directory.
        scope: Directories to scan.
        exclude: Directories to exclude.

    Returns:
        ToolResult with severity-classified findings.
    """
    if not is_available():
        return ToolResult(tool=TOOL_NAME, available=False)

    args = [TOOL_NAME, "-f", "json", "-r"]

    # Add scope directories
    if scope:
        for s in scope:
            target = repo_root / s
            if target.exists():
                args.append(str(target))
    else:
        args.append(str(repo_root))

    # Add exclusions
    exclude_dirs = exclude or []
    # Bandit uses comma-separated exclude dirs
    bandit_excludes = []
    for exc in exclude_dirs:
        exc_path = repo_root / exc.rstrip("/")
        if exc_path.is_dir():
            bandit_excludes.append(str(exc_path))
    if bandit_excludes:
        args.extend(["--exclude", ",".join(bandit_excludes)])

    stdout, stderr, returncode = run_command(args, cwd=repo_root)

    # Bandit returns 1 when findings exist (not an error)
    if returncode not in (0, 1):
        return ToolResult(
            tool=TOOL_NAME,
            available=True,
            error=stderr or f"bandit exited with code {returncode}",
        )

    return _parse_output(_strip_progress(stdout))


def _strip_progress(raw: str) -> str:
    """Strip bandit's Rich progress bar from stdout.

    Bandit 1.8+ writes a progress bar to stdout before the JSON.
    We find the first '{' to locate the JSON start.
    """
    idx = raw.find("{")
    return raw[idx:] if idx >= 0 else raw


def _parse_output(raw_json: str) -> ToolResult:
    """Parse bandit JSON output into structured findings."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return ToolResult(
            tool=TOOL_NAME,
            available=True,
            error=f"Failed to parse bandit JSON: {e}",
            raw_output=raw_json[:500],
        )

    findings: list[Finding] = []
    severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    for result in data.get("results", []):
        severity = result.get("issue_severity", "LOW")
        confidence = result.get("issue_confidence", "LOW")

        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1

        findings.append(Finding(
            rule_id=result.get("test_id", ""),
            severity=severity,
            confidence=confidence,
            message=result.get("issue_text", ""),
            file=result.get("filename", ""),
            line=result.get("line_number", 0),
            tool=TOOL_NAME,
        ))

    # Compute severity-weighted density
    metrics = data.get("metrics", {})
    total_loc = sum(
        v.get("loc", 0) for v in metrics.values() if isinstance(v, dict)
    )

    # Weighted score: High×3 + Medium×2 + Low×1
    weighted_findings = (
        severity_counts["HIGH"] * 3
        + severity_counts["MEDIUM"] * 2
        + severity_counts["LOW"] * 1
    )
    kloc = max(total_loc / 1000, 0.1)

    return ToolResult(
        tool=TOOL_NAME,
        available=True,
        findings=findings,
        metrics={
            "total_findings": len(findings),
            "high_severity": severity_counts["HIGH"],
            "medium_severity": severity_counts["MEDIUM"],
            "low_severity": severity_counts["LOW"],
            "high_confidence": confidence_counts["HIGH"],
            "medium_confidence": confidence_counts["MEDIUM"],
            "low_confidence": confidence_counts["LOW"],
            "weighted_findings": weighted_findings,
            "weighted_per_kloc": weighted_findings / kloc,
            "total_loc": total_loc,
        },
    )
