"""Shared AST analysis utilities for PQI dimension scoring.

Pure functions that walk Python AST trees to extract quality signals.
No external dependencies — uses only the stdlib ``ast`` module.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileAnalysis:
    """Aggregated AST analysis results for a single file."""

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
    """Aggregated analysis across all files in a project."""

    files: list[FileAnalysis] = field(default_factory=list)
    test_files: int = 0
    test_lines: int = 0
    source_files: int = 0
    source_lines: int = 0


def analyze_file(file_path: Path, rel_path: str) -> FileAnalysis | None:
    """Analyze a single Python file and return quality signals."""
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
            # Only count top-level and class-level functions
            analysis.functions += 1
            _analyze_callable(node, analysis, is_class=False)

        elif isinstance(node, ast.ExceptHandler):
            _analyze_except_handler(node, analysis)

    # Nesting depth
    analysis.max_nesting = _compute_max_nesting(tree)

    # Security patterns
    analysis.unsafe_calls = _detect_unsafe_patterns(tree)

    # Naming
    analysis.naming_violations = _count_naming_violations(tree)

    return analysis


def analyze_project(
    repo_root: Path,
    scope: list[str] | None = None,
    exclude: list[str] | None = None,
) -> ProjectAnalysis:
    """Analyze all Python files in a project."""
    from modules.backend.services.code_map.parser import _collect_files

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
    """Analyze a callable (function, method, or class) for quality signals."""
    # Documentation coverage
    if isinstance(node, ast.ClassDef):
        analysis.total_callables += 1
        if ast.get_docstring(node):
            analysis.documented_callables += 1
        # Public/private
        if node.name.startswith("_"):
            analysis.private_definitions += 1
        else:
            analysis.public_definitions += 1
        return

    # Function/method analysis
    is_method = is_class  # simplified: if parent is a class
    analysis.total_callables += 1

    if ast.get_docstring(node):
        analysis.documented_callables += 1

    # Function length
    if node.end_lineno and node.lineno:
        length = node.end_lineno - node.lineno + 1
        analysis.function_lengths.append(length)

    # Type annotation coverage
    for arg in node.args.args:
        if is_method and arg.arg in ("self", "cls"):
            continue
        analysis.total_params += 1
        if arg.annotation is not None:
            analysis.annotated_params += 1

    # Return type
    analysis.total_returns += 1
    if node.returns is not None:
        analysis.annotated_returns += 1

    # Public/private
    if node.name.startswith("_") and not node.name.startswith("__"):
        analysis.private_definitions += 1
    else:
        analysis.public_definitions += 1


def _analyze_except_handler(node: ast.ExceptHandler, analysis: FileAnalysis) -> None:
    """Analyze an except handler for anti-patterns."""
    analysis.exception_handlers += 1

    if node.type is None:
        analysis.bare_excepts += 1
    elif isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"):
        analysis.broad_excepts += 1

    # Check for exception swallowing (empty except body or just pass)
    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
        analysis.bare_excepts += 1


def _compute_max_nesting(tree: ast.Module) -> int:
    """Compute the maximum nesting depth of control flow structures."""
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


def _detect_unsafe_patterns(tree: ast.Module) -> list[str]:
    """Detect security anti-patterns in the AST."""
    findings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Direct calls: eval(), exec()
            if isinstance(node.func, ast.Name) and node.func.id in UNSAFE_PATTERNS:
                findings.append(
                    f"line {node.lineno}: {UNSAFE_PATTERNS[node.func.id]}"
                )

            # Attribute calls: os.system(), pickle.loads()
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    key = (node.func.value.id, node.func.attr)
                    if key in UNSAFE_ATTR_PATTERNS:
                        findings.append(
                            f"line {node.lineno}: {UNSAFE_ATTR_PATTERNS[key]}"
                        )

                # Check for shell=True in subprocess calls
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
    """Count naming convention violations (PEP 8)."""
    violations = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Classes should be CamelCase
            if node.name[0].islower() and not node.name.startswith("_"):
                violations += 1

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Functions should be snake_case (allow dunder methods)
            name = node.name
            if not name.startswith("__") and not name.islower() and name != name.lower():
                # Check for camelCase
                if any(c.isupper() for c in name[1:]) and "_" not in name:
                    violations += 1

    return violations
