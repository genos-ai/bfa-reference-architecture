#!/usr/bin/env python3
"""Score codebase quality using the PyQuality Index (PQI).

Produces a composite 0-100 score across 7 dimensions:
Maintainability, Security, Modularity, Testability, Robustness,
Elegance, and Reusability.

Usage:
    python scripts/code_quality.py                           # Score modules/
    python scripts/code_quality.py --scope modules/          # Specific directory
    python scripts/code_quality.py --profile library          # Library weights
    python scripts/code_quality.py --json                     # JSON output
    python scripts/code_quality.py --recommendations          # Show improvement tips
    python scripts/code_quality.py --use-bandit               # Run Bandit security linter
    python scripts/code_quality.py --use-radon                # Run Radon complexity analyzer
    python scripts/code_quality.py --with-code-map            # Include modularity scoring
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── Types ─────────────────────────────────────────────────────────────────


class QualityBand(str, Enum):
    POOR = "Poor"              # 0-30
    ACCEPTABLE = "Acceptable"  # 31-54
    ADEQUATE = "Adequate"      # 55-64
    GOOD = "Good"              # 65-79
    EXCELLENT = "Excellent"    # 80-100


@dataclass
class DimensionScore:
    name: str
    score: float
    sub_scores: dict[str, float] = field(default_factory=dict)
    confidence: float = 1.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class QualityIssue:
    """A specific, actionable quality issue with location and context."""

    file: str
    line: int
    dimension: str
    severity: str  # HIGH, MEDIUM, LOW
    category: str  # e.g. "broad-except", "long-function", "missing-annotation"
    message: str
    tool: str = "ast"  # ast, bandit, radon
    entity: str = ""  # function/class name when applicable
    value: float = 0  # measured value (lines, complexity, depth, etc.)
    threshold: float = 0  # threshold that was exceeded

    @property
    def priority(self) -> int:
        """Sort key: HIGH=0, MEDIUM=1, LOW=2."""
        return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(self.severity, 3)


@dataclass
class PQIResult:
    composite: float
    dimensions: dict[str, DimensionScore] = field(default_factory=dict)
    quality_band: QualityBand = QualityBand.POOR
    floor_penalty: float = 1.0
    file_count: int = 0
    line_count: int = 0
    issues: list[QualityIssue] = field(default_factory=list)


WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "production": {
        "maintainability": 0.20,
        "security": 0.15,
        "modularity": 0.15,
        "testability": 0.15,
        "robustness": 0.13,
        "elegance": 0.12,
        "reusability": 0.10,
    },
    "library": {
        "maintainability": 0.15,
        "security": 0.10,
        "modularity": 0.20,
        "testability": 0.15,
        "robustness": 0.10,
        "elegance": 0.15,
        "reusability": 0.15,
    },
    "data_science": {
        "maintainability": 0.15,
        "security": 0.10,
        "modularity": 0.10,
        "testability": 0.20,
        "robustness": 0.15,
        "elegance": 0.15,
        "reusability": 0.15,
    },
    "safety_critical": {
        "maintainability": 0.15,
        "security": 0.25,
        "modularity": 0.10,
        "testability": 0.20,
        "robustness": 0.15,
        "elegance": 0.05,
        "reusability": 0.10,
    },
}


def classify_band(score: float) -> QualityBand:
    if score >= 80:
        return QualityBand.EXCELLENT
    if score >= 65:
        return QualityBand.GOOD
    if score >= 55:
        return QualityBand.ADEQUATE
    if score >= 31:
        return QualityBand.ACCEPTABLE
    return QualityBand.POOR


# ── Tool Types ────────────────────────────────────────────────────────────


@dataclass
class Finding:
    rule_id: str
    severity: str
    confidence: str
    message: str
    file: str
    line: int
    tool: str


@dataclass
class ToolResult:
    tool: str
    available: bool
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    raw_output: str = ""
    error: str = ""

    @property
    def success(self) -> bool:
        return self.available and not self.error


# ── Normalizers ───────────────────────────────────────────────────────────


def sigmoid(x: float, midpoint: float, k: float = 0.5) -> float:
    return 100.0 / (1.0 + math.exp(k * (x - midpoint)))


def exp_decay(count: float, rate: float = 0.5) -> float:
    return 100.0 * math.exp(-rate * count)


def linear(value: float, max_value: float = 100.0) -> float:
    return max(0.0, min(100.0, (value / max_value) * 100.0)) if max_value > 0 else 0.0


def inverse_linear(value: float, good: float, bad: float) -> float:
    if bad == good:
        return 100.0 if value <= good else 0.0
    score = 100.0 * (bad - value) / (bad - good)
    return max(0.0, min(100.0, score))


def ratio_score(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 100.0
    return max(0.0, min(100.0, (numerator / denominator) * 100.0))


# ── AST Analysis ──────────────────────────────────────────────────────────


@dataclass
class FileAnalysis:
    path: str
    lines: int = 0
    functions: int = 0
    classes: int = 0
    methods: int = 0

    # Maintainability
    documented_callables: int = 0
    total_callables: int = 0

    # Robustness
    annotated_params: int = 0
    total_params: int = 0
    annotated_returns: int = 0
    total_returns: int = 0
    exception_handlers: int = 0
    bare_excepts: int = 0
    broad_excepts: int = 0

    # Elegance
    max_nesting: int = 0
    function_lengths: list[int] = field(default_factory=list)
    naming_violations: int = 0

    # Security
    unsafe_calls: list[str] = field(default_factory=list)

    # Reusability
    public_definitions: int = 0
    private_definitions: int = 0


@dataclass
class ProjectAnalysis:
    files: list[FileAnalysis] = field(default_factory=list)
    test_files: int = 0
    test_lines: int = 0
    source_files: int = 0
    source_lines: int = 0


UNSAFE_PATTERNS = {
    "eval": "eval() can execute arbitrary code",
    "exec": "exec() can execute arbitrary code",
    "compile": "compile() with exec mode is dangerous",
    "__import__": "dynamic import can be exploited",
}

UNSAFE_ATTR_PATTERNS = {
    ("os", "system"): "os.system() is vulnerable to shell injection",
    ("os", "popen"): "os.popen() is vulnerable to shell injection",
    ("subprocess", "call"): "subprocess.call(shell=True) is dangerous",
    ("pickle", "loads"): "pickle.loads() can execute arbitrary code",
    ("pickle", "load"): "pickle.load() can execute arbitrary code",
    ("yaml", "load"): "yaml.load() without SafeLoader is dangerous",
}


def _collect_files(
    repo_root: Path,
    scope: list[str] | None,
    exclude: list[str] | None,
) -> list[Path]:
    exclude = exclude or []
    exclude_set = set(exclude)

    if scope:
        files: list[Path] = []
        for pattern in scope:
            if pattern.endswith("/"):
                files.extend(repo_root.glob(f"{pattern}**/*.py"))
            elif "*" in pattern:
                files.extend(repo_root.glob(pattern))
            else:
                candidate = repo_root / pattern
                if candidate.is_file() and candidate.suffix == ".py":
                    files.append(candidate)
                elif candidate.is_dir():
                    files.extend(candidate.rglob("*.py"))
        files = list(set(files))
    else:
        files = list(repo_root.rglob("*.py"))

    result = []
    for f in files:
        rel = str(f.relative_to(repo_root))
        if any(_matches_exclude(rel, exc) for exc in exclude_set):
            continue
        result.append(f)
    return result


def _matches_exclude(rel_path: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        return rel_path.startswith(pattern) or rel_path.startswith(pattern.rstrip("/"))
    if "*" in pattern or "?" in pattern or "[" in pattern:
        from fnmatch import fnmatch
        return fnmatch(rel_path, pattern)
    return rel_path.startswith(pattern)


def analyze_file(file_path: Path, rel_path: str) -> FileAnalysis | None:
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return None

    line_count = source.count("\n") + (1 if source and not source.endswith("\n") else 0)
    analysis = FileAnalysis(path=rel_path, lines=line_count)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            analysis.classes += 1
            _analyze_callable(node, analysis, is_class=True)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            analysis.functions += 1
            _analyze_callable(node, analysis, is_class=False)
        elif isinstance(node, ast.ExceptHandler):
            _analyze_except_handler(node, analysis)

    analysis.max_nesting = _compute_max_nesting(tree)
    analysis.unsafe_calls = _detect_unsafe_patterns(tree)
    analysis.naming_violations = _count_naming_violations(tree)

    return analysis


def analyze_project(
    repo_root: Path,
    scope: list[str] | None = None,
    exclude: list[str] | None = None,
) -> ProjectAnalysis:
    files = _collect_files(repo_root, scope, exclude)
    result = ProjectAnalysis()

    for file_path in sorted(files):
        rel_path = str(file_path.relative_to(repo_root))
        analysis = analyze_file(file_path, rel_path)
        if analysis is None:
            continue

        result.files.append(analysis)

        is_test = (
            "/tests/" in rel_path
            or rel_path.startswith("tests/")
            or rel_path.startswith("test_")
            or "/test_" in rel_path
        )
        if is_test:
            result.test_files += 1
            result.test_lines += analysis.lines
        else:
            result.source_files += 1
            result.source_lines += analysis.lines

    return result


def _analyze_callable(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    analysis: FileAnalysis,
    is_class: bool,
) -> None:
    if isinstance(node, ast.ClassDef):
        analysis.total_callables += 1
        if ast.get_docstring(node):
            analysis.documented_callables += 1
        if node.name.startswith("_"):
            analysis.private_definitions += 1
        else:
            analysis.public_definitions += 1
        return

    analysis.total_callables += 1
    if ast.get_docstring(node):
        analysis.documented_callables += 1

    if node.end_lineno and node.lineno:
        length = node.end_lineno - node.lineno + 1
        analysis.function_lengths.append(length)

    for arg in node.args.args:
        if is_class and arg.arg in ("self", "cls"):
            continue
        analysis.total_params += 1
        if arg.annotation is not None:
            analysis.annotated_params += 1

    analysis.total_returns += 1
    if node.returns is not None:
        analysis.annotated_returns += 1

    if node.name.startswith("_") and not node.name.startswith("__"):
        analysis.private_definitions += 1
    else:
        analysis.public_definitions += 1


def _analyze_except_handler(node: ast.ExceptHandler, analysis: FileAnalysis) -> None:
    analysis.exception_handlers += 1
    if node.type is None:
        analysis.bare_excepts += 1
    elif isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"):
        analysis.broad_excepts += 1
    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
        analysis.bare_excepts += 1


def _compute_max_nesting(tree: ast.Module) -> int:
    max_depth = 0

    def walk(node: ast.AST, depth: int) -> None:
        nonlocal max_depth
        nesting_types = (
            ast.If, ast.For, ast.While, ast.With,
            ast.Try, ast.AsyncFor, ast.AsyncWith,
        )
        if isinstance(node, nesting_types):
            depth += 1
            max_depth = max(max_depth, depth)
        for child in ast.iter_child_nodes(node):
            walk(child, depth)

    walk(tree, 0)
    return max_depth


def _detect_unsafe_patterns(tree: ast.Module) -> list[str]:
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in UNSAFE_PATTERNS:
                findings.append(
                    f"line {node.lineno}: {UNSAFE_PATTERNS[node.func.id]}"
                )
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    key = (node.func.value.id, node.func.attr)
                    if key in UNSAFE_ATTR_PATTERNS:
                        findings.append(
                            f"line {node.lineno}: {UNSAFE_ATTR_PATTERNS[key]}"
                        )
                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                ):
                    for kw in node.keywords:
                        if (
                            kw.arg == "shell"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value is True
                        ):
                            findings.append(
                                f"line {node.lineno}: subprocess with shell=True"
                            )
    return findings


def _count_naming_violations(tree: ast.Module) -> int:
    violations = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if node.name[0].islower() and not node.name.startswith("_"):
                violations += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if not name.startswith("__") and not name.islower() and name != name.lower():
                if any(c.isupper() for c in name[1:]) and "_" not in name:
                    violations += 1
    return violations


# ── External Tools ────────────────────────────────────────────────────────


def _check_installed(command: str) -> bool:
    return shutil.which(command) is not None


def _run_command(
    args: list[str], cwd: Path, timeout: int = 120,
) -> tuple[str, str, int]:
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout}s", -1
    except OSError as e:
        return "", str(e), -1


def run_bandit(
    repo_root: Path,
    scope: list[str] | None = None,
    exclude: list[str] | None = None,
) -> ToolResult:
    if not _check_installed("bandit"):
        return ToolResult(tool="bandit", available=False)

    args = ["bandit", "-f", "json", "-r"]
    if scope:
        for s in scope:
            target = repo_root / s
            if target.exists():
                args.append(str(target))
    else:
        args.append(str(repo_root))

    exclude_dirs = exclude or []
    bandit_excludes = []
    for exc in exclude_dirs:
        exc_path = repo_root / exc.rstrip("/")
        if exc_path.is_dir():
            bandit_excludes.append(str(exc_path))
    if bandit_excludes:
        args.extend(["--exclude", ",".join(bandit_excludes)])

    stdout, stderr, returncode = _run_command(args, cwd=repo_root)

    if returncode not in (0, 1):
        return ToolResult(
            tool="bandit", available=True,
            error=stderr or f"bandit exited with code {returncode}",
        )

    # Strip progress bar from stdout
    idx = stdout.find("{")
    raw_json = stdout[idx:] if idx >= 0 else stdout

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return ToolResult(
            tool="bandit", available=True,
            error=f"Failed to parse bandit JSON: {e}",
            raw_output=raw_json[:500],
        )

    findings: list[Finding] = []
    severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    _TEST_NOISE_RULES = {"B101"}

    def _is_test_file(path: str) -> bool:
        parts = Path(path).parts
        return "tests" in parts or any(p.startswith("test_") for p in parts)

    for result in data.get("results", []):
        sev = result.get("issue_severity", "LOW")
        conf = result.get("issue_confidence", "LOW")
        rule_id = result.get("test_id", "")
        filename = result.get("filename", "")

        if rule_id in _TEST_NOISE_RULES and _is_test_file(filename):
            continue

        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

        findings.append(Finding(
            rule_id=rule_id, severity=sev, confidence=conf,
            message=result.get("issue_text", ""),
            file=filename, line=result.get("line_number", 0),
            tool="bandit",
        ))

    metrics = data.get("metrics", {})
    total_loc = sum(
        v.get("loc", 0) for v in metrics.values() if isinstance(v, dict)
    )
    weighted_findings = (
        severity_counts["HIGH"] * 3
        + severity_counts["MEDIUM"] * 2
        + severity_counts["LOW"] * 1
    )
    kloc = max(total_loc / 1000, 0.1)

    return ToolResult(
        tool="bandit", available=True, findings=findings,
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


def run_radon(
    repo_root: Path,
    scope: list[str] | None = None,
    exclude: list[str] | None = None,
) -> ToolResult:
    if not _check_installed("radon"):
        return ToolResult(tool="radon", available=False)

    targets = []
    if scope:
        for s in scope:
            target = repo_root / s
            if target.exists():
                targets.append(str(target))
    targets = targets or [str(repo_root)]

    exclude_args: list[str] = []
    if exclude:
        patterns = [exc.rstrip("/") + "/*" for exc in exclude]
        exclude_args = ["-e", ",".join(patterns)]

    # Run cyclomatic complexity
    cc_args = ["radon", "cc", "-j", "-s", "-a"] + exclude_args + targets
    cc_stdout, cc_stderr, cc_rc = _run_command(cc_args, cwd=repo_root)
    cc_data: dict | str = cc_stderr or f"radon cc exited with code {cc_rc}" if cc_rc != 0 else cc_stdout
    if isinstance(cc_data, str) and cc_rc == 0:
        try:
            cc_data = json.loads(cc_data)
        except json.JSONDecodeError as e:
            cc_data = f"Failed to parse radon cc JSON: {e}"

    # Run maintainability index
    mi_args = ["radon", "mi", "-j", "-s"] + exclude_args + targets
    mi_stdout, mi_stderr, mi_rc = _run_command(mi_args, cwd=repo_root)
    mi_data: dict | str = mi_stderr or f"radon mi exited with code {mi_rc}" if mi_rc != 0 else mi_stdout
    if isinstance(mi_data, str) and mi_rc == 0:
        try:
            mi_data = json.loads(mi_data)
        except json.JSONDecodeError as e:
            mi_data = f"Failed to parse radon mi JSON: {e}"

    # Merge results
    errors = []
    if isinstance(cc_data, str):
        errors.append(cc_data)
        cc_data = {}
    if isinstance(mi_data, str):
        errors.append(mi_data)
        mi_data = {}

    if errors and not cc_data and not mi_data:
        return ToolResult(tool="radon", available=True, error="; ".join(errors))

    findings: list[Finding] = []
    complexities: list[int] = []
    rank_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}

    def _rank_to_severity(rank: str) -> str:
        if rank in ("E", "F"):
            return "HIGH"
        if rank in ("C", "D"):
            return "MEDIUM"
        return "LOW"

    for file_path, functions in cc_data.items():
        if not isinstance(functions, list):
            continue
        for func in functions:
            complexity = func.get("complexity", 0)
            rank = func.get("rank", "A")
            complexities.append(complexity)
            rank_counts[rank] = rank_counts.get(rank, 0) + 1

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
                    tool="radon",
                ))

    mi_scores: list[float] = []
    for file_path, mi_info in mi_data.items():
        if isinstance(mi_info, dict):
            mi_scores.append(mi_info.get("mi", 0.0))

    radon_metrics: dict[str, float] = {"total_functions": len(complexities)}

    if complexities:
        sorted_cc = sorted(complexities)
        p90_idx = min(int(len(sorted_cc) * 0.9), len(sorted_cc) - 1)
        radon_metrics["avg_complexity"] = sum(complexities) / len(complexities)
        radon_metrics["max_complexity"] = max(complexities)
        radon_metrics["p90_complexity"] = sorted_cc[p90_idx]
        radon_metrics["median_complexity"] = sorted_cc[len(sorted_cc) // 2]

    for rank, count in rank_counts.items():
        radon_metrics[f"rank_{rank}"] = count

    simple = rank_counts.get("A", 0) + rank_counts.get("B", 0)
    radon_metrics["simple_ratio"] = simple / len(complexities) if complexities else 1.0

    if mi_scores:
        radon_metrics["avg_mi"] = sum(mi_scores) / len(mi_scores)
        radon_metrics["min_mi"] = min(mi_scores)
        radon_metrics["files_analyzed_mi"] = len(mi_scores)

    error = "; ".join(errors) if errors else ""

    return ToolResult(
        tool="radon", available=True, findings=findings,
        metrics=radon_metrics, error=error,
    )


# ── Dimension Scorers ─────────────────────────────────────────────────────


def _source_files(project: ProjectAnalysis) -> list[FileAnalysis]:
    return [f for f in project.files if "/tests/" not in f.path and not f.path.startswith("tests/")]


def score_maintainability(
    project: ProjectAnalysis,
    tool_results: dict[str, ToolResult] | None = None,
) -> DimensionScore:
    tool_results = tool_results or {}
    source = _source_files(project)

    total_callables = sum(f.total_callables for f in source)
    documented = sum(f.documented_callables for f in source)
    doc_coverage = ratio_score(documented, total_callables)

    if source:
        sizes = sorted(f.lines for f in source)
        p90_idx = int(len(sizes) * 0.9)
        p90_size = sizes[min(p90_idx, len(sizes) - 1)]
        file_size_score = inverse_linear(p90_size, good=200, bad=800)
    else:
        p90_size = 0
        file_size_score = 100.0

    all_lengths: list[int] = []
    for f in source:
        all_lengths.extend(f.function_lengths)
    if all_lengths:
        sorted_lengths = sorted(all_lengths)
        p90_idx = int(len(sorted_lengths) * 0.9)
        p90_length = sorted_lengths[min(p90_idx, len(sorted_lengths) - 1)]
        func_length_score = inverse_linear(p90_length, good=30, bad=100)
    else:
        p90_length = 0
        func_length_score = 100.0

    sub_scores: dict[str, float] = {
        "doc_coverage": doc_coverage,
        "file_size_p90": file_size_score,
        "function_length_p90": func_length_score,
    }
    recommendations: list[str] = []

    radon = tool_results.get("radon")
    if radon and radon.success:
        avg_mi = radon.metrics.get("avg_mi", 50.0)
        mi_score = min(100.0, max(0.0, avg_mi))
        sub_scores["radon_mi"] = mi_score
        score = (
            doc_coverage * 0.25 + file_size_score * 0.20
            + func_length_score * 0.25 + mi_score * 0.30
        )
        if avg_mi < 40:
            recommendations.append(f"Average maintainability index is {avg_mi:.0f} — refactor complex modules")
    else:
        if source:
            avg_funcs = statistics.mean(f.functions for f in source)
            cohesion_score = sigmoid(avg_funcs, midpoint=15, k=0.2)
        else:
            cohesion_score = 100.0
        sub_scores["cohesion"] = cohesion_score
        score = (
            doc_coverage * 0.30 + file_size_score * 0.25
            + func_length_score * 0.25 + cohesion_score * 0.20
        )

    if doc_coverage < 50:
        recommendations.append(f"Documentation coverage is {doc_coverage:.0f}% — add docstrings to public functions and classes")
    if p90_size > 500:
        recommendations.append(f"P90 file size is {p90_size} lines — split large files")
    if p90_length > 50:
        recommendations.append(f"P90 function length is {p90_length} lines — extract helper functions")

    return DimensionScore(name="Maintainability", score=score, sub_scores=sub_scores, recommendations=recommendations)


def score_security(
    project: ProjectAnalysis,
    tool_results: dict[str, ToolResult] | None = None,
) -> DimensionScore:
    tool_results = tool_results or {}
    source = _source_files(project)
    kloc = max(project.source_lines / 1000, 0.1)

    total_unsafe = sum(len(f.unsafe_calls) for f in source)
    unsafe_per_kloc = total_unsafe / kloc
    ast_unsafe_score = exp_decay(unsafe_per_kloc, rate=1.0)

    files_with_unsafe = sum(1 for f in source if f.unsafe_calls)
    ast_clean_ratio = ratio_score(len(source) - files_with_unsafe, len(source)) if source else 100.0

    sub_scores: dict[str, float] = {
        "ast_unsafe_patterns": ast_unsafe_score,
        "ast_clean_file_ratio": ast_clean_ratio,
    }
    recommendations: list[str] = []
    confidence = 0.5

    bandit = tool_results.get("bandit")
    if bandit and bandit.success:
        confidence = 0.9
        metrics = bandit.metrics
        weighted_per_kloc = metrics.get("weighted_per_kloc", 0)
        high_count = int(metrics.get("high_severity", 0))
        medium_count = int(metrics.get("medium_severity", 0))
        low_count = int(metrics.get("low_severity", 0))

        bandit_density_score = exp_decay(weighted_per_kloc, rate=0.3)
        bandit_high_score = exp_decay(high_count, rate=1.5)
        bandit_medium_score = exp_decay(medium_count, rate=0.5)

        sub_scores["bandit_severity_density"] = bandit_density_score
        sub_scores["bandit_high_severity"] = bandit_high_score
        sub_scores["bandit_medium_severity"] = bandit_medium_score

        score = (
            bandit_density_score * 0.30 + bandit_high_score * 0.25
            + bandit_medium_score * 0.15 + ast_unsafe_score * 0.15
            + ast_clean_ratio * 0.15
        )

        if high_count > 0:
            recommendations.append(f"{high_count} HIGH severity finding(s) — fix immediately")
        if medium_count > 0:
            recommendations.append(f"{medium_count} MEDIUM severity finding(s) — review and remediate")
        if low_count > 0:
            recommendations.append(f"{low_count} LOW severity finding(s)")

        for finding in bandit.findings[:5]:
            if finding.severity in ("HIGH", "MEDIUM"):
                short_path = finding.file.split("/modules/")[-1] if "/modules/" in finding.file else finding.file
                recommendations.append(
                    f"[{finding.severity}] {short_path}:{finding.line} — "
                    f"{finding.message} ({finding.rule_id})"
                )
    else:
        score = ast_unsafe_score * 0.60 + ast_clean_ratio * 0.40
        if total_unsafe > 0:
            for f in source:
                for finding in f.unsafe_calls[:3]:
                    recommendations.append(f"{f.path}: {finding}")
            if total_unsafe > 3:
                recommendations.append(f"... and {total_unsafe - 3} more unsafe patterns")
        if bandit and not bandit.success:
            recommendations.append(f"Bandit error: {bandit.error}")
        elif not bandit:
            recommendations.append("Install bandit for deeper security analysis: pip install bandit")

    return DimensionScore(
        name="Security", score=score, sub_scores=sub_scores,
        confidence=confidence, recommendations=recommendations,
    )


def score_modularity(
    project: ProjectAnalysis,
    code_map: dict | None = None,
) -> DimensionScore:
    if not code_map:
        return DimensionScore(
            name="Modularity", score=50.0, confidence=0.3,
            recommendations=["Run with --with-code-map for accurate modularity scoring"],
        )

    graph = code_map.get("import_graph", {})
    ce = {m: len(deps) for m, deps in graph.items()}
    ca: dict[str, int] = {}
    for targets in graph.values():
        for t in targets:
            ca[t] = ca.get(t, 0) + 1

    all_modules = set(ce.keys()) | set(ca.keys())

    instabilities = []
    for m in all_modules:
        c_e = ce.get(m, 0)
        c_a = ca.get(m, 0)
        if c_e + c_a > 0:
            instabilities.append(c_e / (c_e + c_a))

    if instabilities:
        avg_instability = statistics.mean(instabilities)
        instability_score = 100.0 * (1.0 - abs(avg_instability - 0.5) * 2)
    else:
        instability_score = 50.0

    max_ce = max(ce.values()) if ce else 0
    coupling_score = sigmoid(max_ce, midpoint=15, k=0.3)

    cycle_count = _count_cycles(graph)
    cycle_score = exp_decay(cycle_count, rate=1.0)

    modules_data = code_map.get("modules", {})
    sizes = [m.get("lines", 0) for m in modules_data.values()]
    if len(sizes) > 1:
        gini = _gini_coefficient(sizes)
        gini_score = (1.0 - gini) * 100.0
    else:
        gini = 0.0
        gini_score = 100.0

    score = (
        instability_score * 0.25 + coupling_score * 0.30
        + cycle_score * 0.25 + gini_score * 0.20
    )

    recommendations = []
    if max_ce > 15:
        worst = max(ce, key=ce.get)
        recommendations.append(f"{worst} has Ce={max_ce} — too many dependencies, consider splitting")
    if cycle_count > 0:
        recommendations.append(f"{cycle_count} circular dependency(ies) detected — break with protocols or restructure")
    if gini > 0.6:
        recommendations.append(f"Module size Gini={gini:.2f} — sizes are very uneven, split large modules")

    return DimensionScore(
        name="Modularity", score=score,
        sub_scores={
            "instability_balance": instability_score,
            "coupling_max_ce": coupling_score,
            "circular_deps": cycle_score,
            "size_gini": gini_score,
        },
        recommendations=recommendations,
    )


def score_testability(
    project: ProjectAnalysis,
    tool_results: dict[str, ToolResult] | None = None,
) -> DimensionScore:
    tool_results = tool_results or {}

    if project.source_lines > 0:
        test_ratio = project.test_lines / project.source_lines
        ratio_score_val = sigmoid(abs(test_ratio - 1.0), midpoint=0.8, k=3.0)
    else:
        test_ratio = 0.0
        ratio_score_val = 0.0

    if project.source_files > 0:
        file_ratio = project.test_files / project.source_files
        file_ratio_score = min(100.0, file_ratio * 100.0)
    else:
        file_ratio = 0.0
        file_ratio_score = 0.0

    source = _source_files(project)
    max_nestings = [f.max_nesting for f in source if f.max_nesting > 0]
    if max_nestings:
        avg_nesting = statistics.mean(max_nestings)
        nesting_score = sigmoid(avg_nesting, midpoint=4, k=1.0)
    else:
        nesting_score = 100.0

    sub_scores: dict[str, float] = {
        "test_code_ratio": ratio_score_val,
        "test_file_ratio": file_ratio_score,
        "avg_nesting_depth": nesting_score,
    }
    recommendations: list[str] = []

    radon = tool_results.get("radon")
    if radon and radon.success:
        avg_cc = radon.metrics.get("avg_complexity", 5.0)
        complexity_score = sigmoid(avg_cc, midpoint=10, k=0.3)
        sub_scores["radon_avg_complexity"] = complexity_score

        simple_ratio_val = radon.metrics.get("simple_ratio", 1.0)
        simple_score = simple_ratio_val * 100.0
        sub_scores["simple_function_ratio"] = simple_score

        score = (
            ratio_score_val * 0.30 + file_ratio_score * 0.15
            + complexity_score * 0.25 + simple_score * 0.15
            + nesting_score * 0.15
        )

        if avg_cc > 10:
            recommendations.append(f"Average cyclomatic complexity is {avg_cc:.1f} — simplify branching logic")
        complex_count = sum(
            int(radon.metrics.get(f"rank_{r}", 0)) for r in ("D", "E", "F")
        )
        if complex_count > 0:
            recommendations.append(f"{complex_count} function(s) with complexity rank D+ — refactor or split")
    else:
        all_lengths: list[int] = []
        for f in source:
            all_lengths.extend(f.function_lengths)
        if all_lengths:
            avg_length = statistics.mean(all_lengths)
            length_score = sigmoid(avg_length, midpoint=25, k=0.15)
        else:
            length_score = 100.0
        sub_scores["avg_function_length"] = length_score

        score = (
            ratio_score_val * 0.35 + file_ratio_score * 0.20
            + length_score * 0.25 + nesting_score * 0.20
        )

    if test_ratio < 0.5:
        recommendations.append(f"Test-to-code ratio is {test_ratio:.2f} — aim for 0.8-1.2")
    if project.test_files == 0:
        recommendations.append("No test files found")

    return DimensionScore(
        name="Testability", score=score, sub_scores=sub_scores,
        recommendations=recommendations,
    )


def score_robustness(project: ProjectAnalysis) -> DimensionScore:
    source = _source_files(project)

    total_params = sum(f.total_params for f in source)
    annotated_params = sum(f.annotated_params for f in source)
    param_coverage = ratio_score(annotated_params, total_params)

    total_returns = sum(f.total_returns for f in source)
    annotated_returns = sum(f.annotated_returns for f in source)
    return_coverage = ratio_score(annotated_returns, total_returns)

    total_handlers = sum(f.exception_handlers for f in source)
    bare_excepts = sum(f.bare_excepts for f in source)
    broad_excepts = sum(f.broad_excepts for f in source)
    bad_handlers = bare_excepts + broad_excepts
    if total_handlers > 0:
        handler_quality = (1.0 - bad_handlers / total_handlers) * 100.0
    else:
        handler_quality = 100.0

    score = (
        param_coverage * 0.35 + return_coverage * 0.30 + handler_quality * 0.35
    )

    recommendations = []
    if param_coverage < 70:
        recommendations.append(f"Parameter type coverage is {param_coverage:.0f}% — add type annotations")
    if return_coverage < 70:
        recommendations.append(f"Return type coverage is {return_coverage:.0f}% — add return type annotations")
    if bare_excepts > 0:
        recommendations.append(f"{bare_excepts} bare/swallowed except clause(s) — catch specific exceptions")
    if broad_excepts > 0:
        recommendations.append(f"{broad_excepts} broad except(Exception) clause(s) — narrow the exception type")

    return DimensionScore(
        name="Robustness", score=score,
        sub_scores={
            "param_type_coverage": param_coverage,
            "return_type_coverage": return_coverage,
            "exception_handling_quality": handler_quality,
        },
        recommendations=recommendations,
    )


def score_elegance(
    project: ProjectAnalysis,
    tool_results: dict[str, ToolResult] | None = None,
) -> DimensionScore:
    tool_results = tool_results or {}
    source = _source_files(project)

    nestings = [f.max_nesting for f in source]
    if nestings:
        p90_idx = int(len(nestings) * 0.9)
        p90_nesting = sorted(nestings)[min(p90_idx, len(nestings) - 1)]
        nesting_score = sigmoid(p90_nesting, midpoint=4, k=1.5)
    else:
        p90_nesting = 0
        nesting_score = 100.0

    all_lengths: list[int] = []
    for f in source:
        all_lengths.extend(f.function_lengths)
    if all_lengths:
        sorted_lengths = sorted(all_lengths)
        p90_idx = int(len(sorted_lengths) * 0.9)
        p90_length = sorted_lengths[min(p90_idx, len(sorted_lengths) - 1)]
        length_score = inverse_linear(p90_length, good=30, bad=100)
    else:
        p90_length = 0
        length_score = 100.0

    total_defs = sum(f.functions + f.classes for f in source)
    total_violations = sum(f.naming_violations for f in source)
    if total_defs > 0:
        naming_score = (1.0 - total_violations / total_defs) * 100.0
    else:
        naming_score = 100.0

    sub_scores: dict[str, float] = {
        "nesting_depth_p90": nesting_score,
        "function_length_p90": length_score,
        "naming_conventions": naming_score,
    }
    recommendations: list[str] = []

    radon = tool_results.get("radon")
    if radon and radon.success:
        p90_cc = radon.metrics.get("p90_complexity", 5)
        cc_score = sigmoid(p90_cc, midpoint=10, k=0.4)
        sub_scores["radon_complexity_p90"] = cc_score
        score = (
            nesting_score * 0.25 + length_score * 0.25
            + naming_score * 0.25 + cc_score * 0.25
        )
        if p90_cc > 15:
            recommendations.append(f"P90 cyclomatic complexity is {p90_cc} — simplify complex functions")
    else:
        score = nesting_score * 0.35 + length_score * 0.35 + naming_score * 0.30

    if p90_nesting > 4:
        recommendations.append(f"P90 nesting depth is {p90_nesting} — extract nested logic into helper functions")
    if p90_length > 50:
        recommendations.append(f"P90 function length is {p90_length} lines — break into smaller functions")
    if total_violations > 0:
        recommendations.append(f"{total_violations} naming convention violation(s) — use PEP 8 conventions")

    return DimensionScore(
        name="Elegance", score=score, sub_scores=sub_scores,
        recommendations=recommendations,
    )


def score_reusability(
    project: ProjectAnalysis,
    code_map: dict | None = None,
) -> DimensionScore:
    source = _source_files(project)

    total_public = sum(f.public_definitions for f in source)
    total_private = sum(f.private_definitions for f in source)
    total_defs = total_public + total_private
    if total_defs > 0:
        api_ratio = total_public / total_defs
        if 0.3 <= api_ratio <= 0.6:
            api_score = 100.0
        elif api_ratio < 0.3:
            api_score = api_ratio / 0.3 * 100.0
        else:
            api_score = max(0.0, 100.0 - (api_ratio - 0.6) / 0.4 * 100.0)
    else:
        api_ratio = 0.0
        api_score = 50.0

    if code_map:
        graph = code_map.get("import_graph", {})
        ce_values = [len(deps) for deps in graph.values()]
        if ce_values:
            avg_ce = statistics.mean(ce_values)
            coupling_score = sigmoid(avg_ce, midpoint=8, k=0.4)
        else:
            coupling_score = 100.0
    else:
        coupling_score = 50.0

    if source:
        avg_lines = statistics.mean(f.lines for f in source)
        size_score = sigmoid(avg_lines, midpoint=200, k=0.02)
    else:
        size_score = 50.0

    score = api_score * 0.35 + coupling_score * 0.35 + size_score * 0.30

    recommendations = []
    if api_ratio > 0.7:
        recommendations.append(f"API surface is {api_ratio:.0%} public — consider making more internals private")
    if api_ratio < 0.2:
        recommendations.append(f"API surface is {api_ratio:.0%} public — very little is reusable")

    return DimensionScore(
        name="Reusability", score=score,
        sub_scores={
            "api_surface_ratio": api_score,
            "coupling": coupling_score,
            "module_size": size_score,
        },
        recommendations=recommendations,
    )


# ── Composite PQI ─────────────────────────────────────────────────────────

CRITICAL_FLOOR = 20


def compute_pqi(
    dimensions: dict[str, DimensionScore],
    profile: str = "production",
    file_count: int = 0,
    line_count: int = 0,
) -> PQIResult:
    weights = WEIGHT_PROFILES.get(profile, WEIGHT_PROFILES["production"])

    scores = {k: max(1.0, v.score) for k, v in dimensions.items()}

    log_sum = 0.0
    for dim_name, weight in weights.items():
        s = scores.get(dim_name, 50.0)
        log_sum += weight * math.log(s)

    geometric_mean = math.exp(log_sum)

    penalty = _floor_penalty(scores)
    composite = min(100.0, geometric_mean * penalty)

    return PQIResult(
        composite=round(composite, 1),
        dimensions=dimensions,
        quality_band=classify_band(composite),
        floor_penalty=round(penalty, 3),
        file_count=file_count,
        line_count=line_count,
    )


def _floor_penalty(dimension_scores: dict[str, float]) -> float:
    violations = [s for s in dimension_scores.values() if s < CRITICAL_FLOOR]
    if not violations:
        return 1.0
    penalty = 1.0
    for s in violations:
        deficit = (CRITICAL_FLOOR - s) / CRITICAL_FLOOR
        penalty *= (1.0 - 0.3 * deficit)
    return max(0.3, penalty)


# ── Helpers ───────────────────────────────────────────────────────────────


def _count_cycles(graph: dict[str, list[str]]) -> int:
    visited: set[str] = set()
    rec_stack: set[str] = set()
    cycles = 0

    def dfs(node: str) -> None:
        nonlocal cycles
        visited.add(node)
        rec_stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in rec_stack:
                cycles += 1
        rec_stack.discard(node)

    for node in graph:
        if node not in visited:
            dfs(node)
    return cycles


def _gini_coefficient(values: list[int | float]) -> float:
    if not values or len(values) < 2:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    if total == 0:
        return 0.0
    cumulative = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(sorted_vals))
    return cumulative / (n * total)


# ── Issue Collector ───────────────────────────────────────────────────────


def _collect_issues(
    project: ProjectAnalysis,
    tool_results: dict[str, ToolResult],
) -> list[QualityIssue]:
    """Collect all actionable quality issues with file/line detail."""
    issues: list[QualityIssue] = []
    source_files = [f for f in project.files
                    if "/tests/" not in f.path and not f.path.startswith("tests/")]

    for fa in source_files:
        # Robustness: broad/bare excepts — need line-level detail from re-parse
        # We'll collect file-level counts here; line detail comes from AST walk below

        # Elegance: long functions — need line-level detail from re-parse
        # Elegance: deep nesting
        if fa.max_nesting > 4:
            issues.append(QualityIssue(
                file=fa.path, line=0, dimension="Elegance", severity="MEDIUM",
                category="deep-nesting",
                message=f"Max nesting depth {fa.max_nesting} (threshold: 4)",
                value=fa.max_nesting, threshold=4,
            ))

        # Security: unsafe patterns (already have line info in the string)
        for finding in fa.unsafe_calls:
            line_num = 0
            if finding.startswith("line "):
                try:
                    line_num = int(finding.split(":")[0].split(" ")[1])
                except (IndexError, ValueError):
                    pass
            msg = finding.split(": ", 1)[-1] if ": " in finding else finding
            issues.append(QualityIssue(
                file=fa.path, line=line_num, dimension="Security", severity="HIGH",
                category="unsafe-pattern", message=msg,
            ))

    # Detailed AST walk for line-level issues (broad excepts, long functions, missing annotations)
    for fa in source_files:
        file_path = PROJECT_ROOT / fa.path
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue

        # Large files
        if fa.lines > 500:
            sev = "HIGH" if fa.lines > 800 else "MEDIUM"
            issues.append(QualityIssue(
                file=fa.path, line=0, dimension="Maintainability",
                severity=sev, category="large-file",
                message=f"File is {fa.lines} lines (threshold: 500)",
                value=fa.lines, threshold=500,
            ))

        for node in ast.walk(tree):
            # Broad/bare excepts with line numbers
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    issues.append(QualityIssue(
                        file=fa.path, line=node.lineno, dimension="Robustness",
                        severity="MEDIUM", category="bare-except",
                        message="Bare except clause — catch specific exceptions",
                    ))
                elif isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"):
                    issues.append(QualityIssue(
                        file=fa.path, line=node.lineno, dimension="Robustness",
                        severity="LOW", category="broad-except",
                        message=f"Broad except({node.type.id}) — narrow the exception type",
                    ))
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    issues.append(QualityIssue(
                        file=fa.path, line=node.lineno, dimension="Robustness",
                        severity="HIGH", category="swallowed-exception",
                        message="Exception swallowed (except: pass) — log or re-raise",
                    ))

            # Long functions with line numbers
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.end_lineno and node.lineno:
                    length = node.end_lineno - node.lineno + 1
                    if length > 60:
                        sev = "HIGH" if length > 100 else "MEDIUM"
                        issues.append(QualityIssue(
                            file=fa.path, line=node.lineno, dimension="Elegance",
                            severity=sev, category="long-function",
                            message=f"Function '{node.name}' is {length} lines (threshold: 60)",
                            entity=node.name, value=length, threshold=60,
                        ))

                # Missing return type annotation
                if node.returns is None and not node.name.startswith("_"):
                    issues.append(QualityIssue(
                        file=fa.path, line=node.lineno, dimension="Robustness",
                        severity="LOW", category="missing-return-type",
                        message=f"Public function '{node.name}' missing return type annotation",
                        entity=node.name,
                    ))

            # Missing docstrings on public classes/functions
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_") and not ast.get_docstring(node):
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    issues.append(QualityIssue(
                        file=fa.path, line=node.lineno, dimension="Maintainability",
                        severity="LOW", category="missing-docstring",
                        message=f"Public {kind} '{node.name}' missing docstring",
                        entity=node.name,
                    ))

    # Bandit findings (already structured)
    bandit = tool_results.get("bandit")
    if bandit and bandit.success:
        for f in bandit.findings:
            short_path = f.file
            if str(PROJECT_ROOT) in short_path:
                short_path = str(Path(short_path).relative_to(PROJECT_ROOT))
            issues.append(QualityIssue(
                file=short_path, line=f.line, dimension="Security",
                severity=f.severity, category=f.rule_id,
                message=f"{f.message} ({f.rule_id})", tool="bandit",
            ))

    # Radon findings (already structured)
    radon = tool_results.get("radon")
    if radon and radon.success:
        for f in radon.findings:
            short_path = f.file
            if str(PROJECT_ROOT) in short_path:
                short_path = str(Path(short_path).relative_to(PROJECT_ROOT))
            # Extract entity name and complexity value from message
            entity = ""
            value = 0.0
            name_match = re.search(r"'([^']+)'", f.message)
            if name_match:
                entity = name_match.group(1)
            cc_match = re.search(r"complexity (\d+)", f.message)
            if cc_match:
                value = float(cc_match.group(1))
            issues.append(QualityIssue(
                file=short_path, line=f.line, dimension="Testability",
                severity=f.severity, category=f.rule_id,
                message=f.message, tool="radon",
                entity=entity, value=value,
            ))

    # Sort by severity (HIGH first), then file, then line
    issues.sort(key=lambda i: (i.priority, i.file, i.line))

    return issues


# ── Scorer (orchestrator) ─────────────────────────────────────────────────


def score_project(
    repo_root: Path,
    scope: list[str] | None = None,
    exclude: list[str] | None = None,
    code_map: dict | None = None,
    profile: str = "production",
    tools: list[str] | None = None,
) -> PQIResult:
    project = analyze_project(repo_root, scope=scope, exclude=exclude)

    tool_results: dict[str, ToolResult] = {}
    for name in (tools or []):
        if name == "bandit":
            tool_results["bandit"] = run_bandit(repo_root, scope, exclude)
        elif name == "radon":
            tool_results["radon"] = run_radon(repo_root, scope, exclude)

    dimensions = {
        "maintainability": score_maintainability(project, tool_results),
        "security": score_security(project, tool_results),
        "modularity": score_modularity(project, code_map),
        "testability": score_testability(project, tool_results),
        "robustness": score_robustness(project),
        "elegance": score_elegance(project, tool_results),
        "reusability": score_reusability(project, code_map),
    }

    issues = _collect_issues(project, tool_results)

    result = compute_pqi(
        dimensions, profile=profile,
        file_count=project.source_files,
        line_count=project.source_lines,
    )
    result.issues = issues
    return result


# ── CLI ───────────────────────────────────────────────────────────────────


def _print_report(result: PQIResult, show_recommendations: bool = False) -> None:
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

    # Issue summary
    if result.issues:
        high = sum(1 for i in result.issues if i.severity == "HIGH")
        medium = sum(1 for i in result.issues if i.severity == "MEDIUM")
        low = sum(1 for i in result.issues if i.severity == "LOW")
        print(f"\n{'─' * 60}")
        print(f"  Issues: {len(result.issues)} total ({high} HIGH, {medium} MEDIUM, {low} LOW)")
        print(f"{'─' * 60}")

        if high > 0:
            high_issues = [i for i in result.issues if i.severity == "HIGH"]
            for issue in high_issues[:5]:
                loc = f"{issue.file}:{issue.line}" if issue.line else issue.file
                print(f"  HIGH  {loc}")
                print(f"        {issue.message}")
            if high > 5:
                print(f"  ... and {high - 5} more HIGH issues (see .codemap/quality.md)")

    print(f"\n{'=' * 60}\n")


def _result_to_dict(result: PQIResult) -> dict:
    return {
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
        "issues": [
            {
                "file": i.file,
                "line": i.line,
                "dimension": i.dimension,
                "severity": i.severity,
                "category": i.category,
                "message": i.message,
                "tool": i.tool,
                "entity": i.entity,
                "value": i.value,
                "threshold": i.threshold,
            }
            for i in result.issues
        ],
    }


def _print_json(result: PQIResult) -> None:
    print(json.dumps(_result_to_dict(result), indent=2))


def _score_bar(score: float, width: int = 40) -> str:
    filled = int(score / 100 * width)
    empty = width - filled
    return f"  [{'█' * filled}{'░' * empty}] {score:.1f}%"


def _mini_bar(score: float, width: int = 20) -> str:
    filled = int(score / 100 * width)
    empty = width - filled
    return f"{'█' * filled}{'░' * empty}"


def _render_markdown_report(result: PQIResult) -> str:
    """Render PQI result as structured Markdown optimized for LLM consumption.

    Design: tables over bullets, numeric columns over prose, thresholds
    stated once per section header, no ASCII bar decorations.
    """
    lines: list[str] = []
    band = result.quality_band.value

    lines.append("# PyQuality Index (PQI)")
    lines.append("")
    lines.append(f"**Score: {result.composite:.1f} / 100 — {band}**")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|------:|")
    lines.append(f"| Files | {result.file_count} |")
    lines.append(f"| Lines | {result.line_count:,} |")
    if result.floor_penalty < 1.0:
        lines.append(f"| Floor penalty | {result.floor_penalty:.3f} |")
    lines.append("")

    # ── Dimensions table ──
    lines.append("## Dimensions")
    lines.append("")
    lines.append("| Dimension | Score | Confidence |")
    lines.append("|-----------|------:|-----------:|")

    for _name, dim in sorted(
        result.dimensions.items(),
        key=lambda x: x[1].score,
        reverse=True,
    ):
        conf = f"{dim.confidence:.0%}" if dim.confidence < 1.0 else "100%"
        lines.append(f"| {dim.name} | {dim.score:.1f} | {conf} |")

    lines.append("")

    # ── Sub-scores as tables ──
    lines.append("## Sub-Scores")
    lines.append("")
    lines.append("| Dimension | Sub-Score | Value |")
    lines.append("|-----------|-----------|------:|")
    for _name, dim in sorted(
        result.dimensions.items(),
        key=lambda x: x[1].score,
        reverse=True,
    ):
        for sub_name, sub_score in sorted(dim.sub_scores.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {dim.name} | {sub_name} | {sub_score:.1f} |")
    lines.append("")

    # ── Recommendations ──
    has_recs = any(dim.recommendations for dim in result.dimensions.values())
    if has_recs:
        lines.append("## Recommendations")
        lines.append("")
        for _name, dim in sorted(result.dimensions.items(), key=lambda x: x[1].score):
            if dim.recommendations:
                lines.append(f"### {dim.name}")
                lines.append("")
                for rec in dim.recommendations:
                    lines.append(f"- {rec}")
                lines.append("")

    # ── Issues ──
    if result.issues:
        high = sum(1 for i in result.issues if i.severity == "HIGH")
        medium = sum(1 for i in result.issues if i.severity == "MEDIUM")
        low = sum(1 for i in result.issues if i.severity == "LOW")

        lines.append("## Issues")
        lines.append("")
        lines.append(f"| Severity | Count |")
        lines.append(f"|----------|------:|")
        lines.append(f"| HIGH | {high} |")
        lines.append(f"| MEDIUM | {medium} |")
        lines.append(f"| LOW | {low} |")
        lines.append(f"| **Total** | **{len(result.issues)}** |")
        lines.append("")

        # Group by dimension
        dim_issues: dict[str, list[QualityIssue]] = {}
        for issue in result.issues:
            dim_issues.setdefault(issue.dimension, []).append(issue)

        sorted_dims = sorted(
            dim_issues.items(),
            key=lambda x: (
                -sum(1 for i in x[1] if i.severity == "HIGH"),
                -len(x[1]),
            ),
        )

        for dim_name, dim_iss in sorted_dims:
            dim_high = sum(1 for i in dim_iss if i.severity == "HIGH")
            dim_med = sum(1 for i in dim_iss if i.severity == "MEDIUM")
            dim_low = sum(1 for i in dim_iss if i.severity == "LOW")
            lines.append(f"### {dim_name} — {len(dim_iss)} issues ({dim_high}H / {dim_med}M / {dim_low}L)")
            lines.append("")

            # Group by category, render each as a typed table
            categories: dict[str, list[QualityIssue]] = {}
            for issue in dim_iss:
                categories.setdefault(issue.category, []).append(issue)

            for cat, cat_issues in sorted(
                categories.items(),
                key=lambda x: (x[1][0].priority, -len(x[1])),
            ):
                cat_issues_sorted = sorted(cat_issues, key=lambda i: (i.priority, -i.value, i.file, i.line))
                sev = cat_issues[0].severity
                has_entity = any(i.entity for i in cat_issues)
                has_value = any(i.value for i in cat_issues)
                threshold = cat_issues[0].threshold

                # Section header with threshold stated once
                header_parts = [f"#### {cat} — {len(cat_issues)} {sev}"]
                if threshold:
                    header_parts.append(f"(threshold: {threshold:g})")
                lines.append(" ".join(header_parts))
                lines.append("")

                # Build table columns based on available data
                if has_value and has_entity:
                    lines.append("| Sev | File | Line | Entity | Value | Tool |")
                    lines.append("|-----|------|-----:|--------|------:|------|")
                    for issue in cat_issues_sorted:
                        lines.append(
                            f"| {issue.severity} | {issue.file} | {issue.line or ''} "
                            f"| {issue.entity} | {issue.value:g} | {issue.tool} |"
                        )
                elif has_value:
                    lines.append("| Sev | File | Line | Value | Tool |")
                    lines.append("|-----|------|-----:|------:|------|")
                    for issue in cat_issues_sorted:
                        lines.append(
                            f"| {issue.severity} | {issue.file} | {issue.line or ''} "
                            f"| {issue.value:g} | {issue.tool} |"
                        )
                elif has_entity:
                    lines.append("| Sev | File | Line | Entity | Message | Tool |")
                    lines.append("|-----|------|-----:|--------|---------|------|")
                    for issue in cat_issues_sorted:
                        lines.append(
                            f"| {issue.severity} | {issue.file} | {issue.line or ''} "
                            f"| {issue.entity} | {issue.message} | {issue.tool} |"
                        )
                else:
                    lines.append("| Sev | File | Line | Message | Tool |")
                    lines.append("|-----|------|-----:|---------|------|")
                    for issue in cat_issues_sorted:
                        lines.append(
                            f"| {issue.severity} | {issue.file} | {issue.line or ''} "
                            f"| {issue.message} | {issue.tool} |"
                        )
                lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score codebase quality using the PyQuality Index (PQI).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Debug logging",
    )
    parser.add_argument(
        "--scope",
        nargs="*",
        default=["modules/", "tests/"],
        help="Directories or files to include (default: modules/ tests/)",
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
        "--no-code-map",
        action="store_true",
        help="Skip code map generation for modularity scoring",
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
        "--include-low",
        action="store_true",
        help="Include LOW severity issues (excluded by default)",
    )
    parser.add_argument(
        "--no-bandit",
        action="store_true",
        help="Skip Bandit security linter",
    )
    parser.add_argument(
        "--no-radon",
        action="store_true",
        help="Skip Radon complexity analyzer",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Write output to file instead of default (.codemap/ folder)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print to stdout instead of writing to .codemap/",
    )

    args = parser.parse_args()

    sys.path.insert(0, str(PROJECT_ROOT))
    from config.project_setup import setup_logging
    setup_logging(debug=args.debug, verbose=args.verbose)

    exclude = args.exclude or [
        ".venv/",
        "__pycache__/",
        ".git/",
        "node_modules/",
        ".mypy_cache/",
        ".pytest_cache/",
        ".ruff_cache/",
    ]

    code_map = None
    if not args.no_code_map:
        # Import from sibling script
        sys.path.insert(0, str(PROJECT_ROOT))
        from scripts.code_map import generate_code_map
        code_map = generate_code_map(
            repo_root=PROJECT_ROOT,
            scope=args.scope,
            exclude=exclude,
        )

    tools = []
    if not args.no_bandit:
        tools.append("bandit")
    if not args.no_radon:
        tools.append("radon")

    result = score_project(
        repo_root=PROJECT_ROOT,
        scope=args.scope,
        exclude=exclude,
        code_map=code_map,
        profile=args.profile,
        tools=tools,
    )

    # Filter out LOW severity issues unless --include-low
    if not args.include_low:
        result.issues = [i for i in result.issues if i.severity != "LOW"]

    # Always print the report to terminal
    _print_report(result, show_recommendations=args.recommendations)

    # Write structured output to file
    if args.stdout:
        if args.json_output:
            _print_json(result)
        else:
            print(_render_markdown_report(result))
        return

    if args.json_output:
        output = json.dumps(_result_to_dict(result), indent=2)
        ext = "json"
    else:
        output = _render_markdown_report(result)
        ext = "md"

    if args.output:
        out_path = Path(args.output)
    else:
        codemap_dir = PROJECT_ROOT / ".codemap"
        codemap_dir.mkdir(exist_ok=True)
        out_path = codemap_dir / f"quality.{ext}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    print(f"Quality report written to {out_path}")


if __name__ == "__main__":
    main()
