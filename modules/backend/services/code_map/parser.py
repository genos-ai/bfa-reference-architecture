"""Stage 1: Parse — extract structural information from Python modules.

Uses Python's built-in ``ast`` module. tree-sitter can replace this later
for incremental parsing and multi-language support; the output types are
identical.
"""

from __future__ import annotations

import ast
from pathlib import Path

from modules.backend.services.code_map.types import ModuleInfo, SymbolInfo, SymbolKind


def parse_modules(
    repo_root: Path,
    scope: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[ModuleInfo]:
    """Parse all Python files in scope and return structural info.

    Args:
        repo_root: Repository root directory.
        scope: Glob patterns for directories/files to include.
            Defaults to the entire repo.
        exclude: Glob patterns to exclude (tests, migrations, etc.).

    Returns:
        List of ModuleInfo, one per parsed file.
    """
    files = _collect_files(repo_root, scope, exclude)
    modules: list[ModuleInfo] = []

    for file_path in sorted(files):
        module = _parse_file(repo_root, file_path)
        if module is not None:
            modules.append(module)

    return modules


def _collect_files(
    repo_root: Path,
    scope: list[str] | None,
    exclude: list[str] | None,
) -> list[Path]:
    """Collect Python files matching scope/exclude patterns."""
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
    """Check if a relative path matches an exclusion pattern.

    Supports three styles:
    - Directory prefix: ``tests/`` matches any path under tests/
    - Exact prefix: ``modules/backend/core/config.py`` matches that file
    - Glob/fnmatch: ``**/config_schema.py`` or ``*.generated.py``
    """
    if pattern.endswith("/"):
        return rel_path.startswith(pattern) or rel_path.startswith(pattern.rstrip("/"))
    if "*" in pattern or "?" in pattern or "[" in pattern:
        from fnmatch import fnmatch
        return fnmatch(rel_path, pattern)
    return rel_path.startswith(pattern)


def _parse_file(repo_root: Path, file_path: Path) -> ModuleInfo | None:
    """Parse a single Python file into ModuleInfo."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return None

    rel_path = str(file_path.relative_to(repo_root))
    line_count = source.count("\n") + (1 if source and not source.endswith("\n") else 0)

    imports = _extract_imports(tree)
    classes = _extract_classes(tree, rel_path)
    functions = _extract_functions(tree, rel_path)
    constants = _extract_constants(tree)
    references = _extract_references(tree)

    return ModuleInfo(
        path=rel_path,
        lines=line_count,
        imports=imports,
        classes=classes,
        functions=functions,
        constants=constants,
        references=references,
    )


def _extract_imports(tree: ast.Module) -> list[str]:
    """Extract import paths from top-level import statements."""
    imports: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _extract_classes(tree: ast.Module, module_path: str) -> list[SymbolInfo]:
    """Extract class definitions with methods and fields."""
    classes: list[SymbolInfo] = []
    module_qname = _path_to_module(module_path)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(_parse_class(node, module_qname))

    return classes


def _parse_class(node: ast.ClassDef, module_qname: str) -> SymbolInfo:
    """Parse a class definition into SymbolInfo."""
    bases = [_name_from_node(b) for b in node.bases if _name_from_node(b)]
    decorators = [_name_from_node(d) for d in node.decorator_list if _name_from_node(d)]
    class_qname = f"{module_qname}.{node.name}"

    fields: list[str] = []
    methods: list[SymbolInfo] = []

    for item in ast.iter_child_nodes(node):
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            annotation = _annotation_str(item.annotation)
            fields.append(f"{item.target.id}: {annotation}")
        elif isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            methods.append(_parse_function(item, class_qname, is_method=True))

    return SymbolInfo(
        name=node.name,
        kind=SymbolKind.CLASS,
        qualified_name=class_qname,
        line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        bases=bases,
        fields=fields,
        methods=methods,
        decorators=decorators,
    )


def _extract_functions(tree: ast.Module, module_path: str) -> list[SymbolInfo]:
    """Extract top-level function definitions."""
    functions: list[SymbolInfo] = []
    module_qname = _path_to_module(module_path)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(_parse_function(node, module_qname, is_method=False))

    return functions


def _parse_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parent_qname: str,
    is_method: bool,
) -> SymbolInfo:
    """Parse a function/method definition into SymbolInfo."""
    params: list[str] = []
    for arg in node.args.args:
        if is_method and arg.arg == "self":
            continue
        if is_method and arg.arg == "cls":
            continue
        annotation = _annotation_str(arg.annotation) if arg.annotation else ""
        param_str = f"{arg.arg}: {annotation}" if annotation else arg.arg
        params.append(param_str)

    return_type = _annotation_str(node.returns) if node.returns else ""
    decorators = [_name_from_node(d) for d in node.decorator_list if _name_from_node(d)]

    return SymbolInfo(
        name=node.name,
        kind=SymbolKind.METHOD if is_method else SymbolKind.FUNCTION,
        qualified_name=f"{parent_qname}.{node.name}",
        line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        params=params,
        return_type=return_type,
        decorators=decorators,
    )


def _extract_constants(tree: ast.Module) -> list[str]:
    """Extract module-level UPPER_CASE assignments with type annotations."""
    constants: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            if name.isupper() or (name.startswith("_") and name[1:].isupper()):
                annotation = _annotation_str(node.annotation)
                constants.append(f"{name}: {annotation}")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    constants.append(target.id)

    return constants


def _extract_references(tree: ast.Module) -> list[str]:
    """Extract all name references in the module for cross-referencing.

    Collects class names, function calls, and attribute accesses that
    may reference symbols in other modules.
    """
    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            refs.add(node.id)
        elif isinstance(node, ast.Attribute):
            chain = _attribute_chain(node)
            if chain:
                refs.add(chain)
    return sorted(refs)


def _attribute_chain(node: ast.Attribute) -> str:
    """Build a dotted name from nested Attribute nodes."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return ""


def _annotation_str(node: ast.expr | None) -> str:
    """Convert an annotation AST node to a string representation."""
    if node is None:
        return ""
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _attribute_chain(node)
    if isinstance(node, ast.Subscript):
        value = _annotation_str(node.value)
        slice_str = _annotation_str(node.slice)
        return f"{value}[{slice_str}]"
    if isinstance(node, ast.Tuple):
        elts = ", ".join(_annotation_str(e) for e in node.elts)
        return elts
    if isinstance(node, ast.List):
        elts = ", ".join(_annotation_str(e) for e in node.elts)
        return f"[{elts}]"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _annotation_str(node.left)
        right = _annotation_str(node.right)
        return f"{left} | {right}"
    return ast.dump(node)


def _name_from_node(node: ast.expr) -> str:
    """Extract a simple name from a Name or Attribute node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _attribute_chain(node)
    if isinstance(node, ast.Call):
        return _name_from_node(node.func)
    return ""


def _path_to_module(rel_path: str) -> str:
    """Convert a relative file path to a Python module path."""
    module = rel_path.replace("/", ".").replace("\\", ".")
    if module.endswith(".py"):
        module = module[:-3]
    if module.endswith(".__init__"):
        module = module[:-9]
    return module
