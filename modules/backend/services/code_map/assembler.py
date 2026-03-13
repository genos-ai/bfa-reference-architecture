"""Stage 4: Assemble — produce the Code Map JSON and presentation formats.

Three independent functions (doc 49 requirement):
    assemble_code_map()     — produce JSON from parsed data + ranks
    trim_by_rank()          — reduce JSON to fit a token budget
    render_markdown_tree()  — convert JSON to Markdown tree for agents

Plus a convenience compositor:
    render_for_agent()      — trim + render in one call
"""

from __future__ import annotations

import datetime

from modules.backend.services.code_map.types import ModuleInfo, SymbolInfo, SymbolKind


def assemble_code_map(
    modules: list[ModuleInfo],
    ranks: dict[str, float],
    repo_root_name: str = "",
    commit: str = "",
) -> dict:
    """Assemble the Code Map JSON from parsed modules and rank scores.

    Produces the schema defined in doc 49 (agentic-codebase-intelligence).

    Args:
        modules: Parsed module info from parse_modules().
        ranks: PageRank scores from rank_symbols().
        repo_root_name: Project identifier for the output.
        commit: Git commit hash at generation time.

    Returns:
        JSON-serializable Code Map dictionary.
    """
    modules_dict: dict[str, dict] = {}
    import_graph: dict[str, list[str]] = {}

    # Build a set of internal module paths for import graph filtering
    internal_modules = {_path_to_qname(m.path) for m in modules}

    for module in modules:
        module_qname = _path_to_qname(module.path)
        module_rank = ranks.get(module_qname, 0.0)

        classes_dict: dict[str, dict] = {}
        for cls in module.classes:
            methods_list = [
                f"{m.name}({', '.join(m.params)}) -> {m.return_type}"
                if m.return_type else f"{m.name}({', '.join(m.params)})"
                for m in cls.methods
            ]
            classes_dict[cls.name] = {
                "bases": cls.bases,
                "fields": cls.fields,
                "methods": methods_list,
                "rank": round(ranks.get(cls.qualified_name, 0.0), 4),
            }

        functions_dict: dict[str, dict] = {}
        for func in module.functions:
            functions_dict[func.name] = {
                "params": func.params,
                "returns": func.return_type,
                "decorators": func.decorators,
                "rank": round(ranks.get(func.qualified_name, 0.0), 4),
            }

        modules_dict[module.path] = {
            "lines": module.lines,
            "rank": round(module_rank, 4),
            "imports": module.imports,
            "classes": classes_dict,
            "functions": functions_dict,
            "constants": module.constants,
        }

        # Build import graph (internal edges only)
        internal_imports = [
            imp for imp in module.imports
            if _is_internal_import(imp, internal_modules)
        ]
        if internal_imports:
            import_graph[module_qname] = internal_imports

    total_classes = sum(len(m.classes) for m in modules)
    total_functions = sum(len(m.functions) for m in modules)

    return {
        "project_id": repo_root_name,
        "commit": commit,
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "generator_version": "1.0.0",
        "modules": modules_dict,
        "import_graph": import_graph,
        "stats": {
            "total_files": len(modules),
            "total_lines": sum(m.lines for m in modules),
            "total_classes": total_classes,
            "total_functions": total_functions,
        },
    }


def trim_by_rank(
    code_map: dict,
    max_tokens: int = 4096,
) -> dict:
    """Trim the Code Map to fit within a token budget.

    Uses PageRank-based trimming first (remove lowest-ranked symbols),
    then mechanical passes as fallback per doc 49.

    Args:
        code_map: Full Code Map JSON from assemble_code_map().
        max_tokens: Target token budget.

    Returns:
        A new (trimmed) Code Map dict. The original is not modified.
    """
    import copy
    trimmed = copy.deepcopy(code_map)
    current_tokens = _estimate_tokens(trimmed)

    if current_tokens <= max_tokens:
        return trimmed

    # Pass 1: Remove lowest-ranked symbols (methods, then functions, then classes)
    all_symbols = _collect_ranked_symbols(trimmed)
    all_symbols.sort(key=lambda x: x[1])  # ascending by rank

    for path, rank, kind, name, parent in all_symbols:
        if _estimate_tokens(trimmed) <= max_tokens:
            break
        _remove_symbol(trimmed, path, kind, name, parent)

    if _estimate_tokens(trimmed) <= max_tokens:
        return trimmed

    # Pass 2: Remove private methods (leading _)
    for path, mod in list(trimmed["modules"].items()):
        for cls_name, cls_data in mod.get("classes", {}).items():
            cls_data["methods"] = [
                m for m in cls_data["methods"] if not _method_name(m).startswith("_")
            ]

    if _estimate_tokens(trimmed) <= max_tokens:
        return trimmed

    # Pass 3: Remove constants
    for mod in trimmed["modules"].values():
        mod["constants"] = []

    if _estimate_tokens(trimmed) <= max_tokens:
        return trimmed

    # Pass 4: Remove imports arrays (import_graph still preserved)
    for mod in trimmed["modules"].values():
        mod["imports"] = []

    if _estimate_tokens(trimmed) <= max_tokens:
        return trimmed

    # Pass 5: Remove modules with < 20 lines
    trimmed["modules"] = {
        p: m for p, m in trimmed["modules"].items() if m["lines"] >= 20
    }

    if _estimate_tokens(trimmed) <= max_tokens:
        return trimmed

    # Pass 6: Remove lowest-ranked entire modules
    ranked_modules = sorted(
        trimmed["modules"].items(), key=lambda x: x[1]["rank"],
    )
    while _estimate_tokens(trimmed) > max_tokens and ranked_modules:
        path, _ = ranked_modules.pop(0)
        del trimmed["modules"][path]

    return trimmed


def render_markdown_tree(code_map: dict) -> str:
    """Render a Code Map as a Markdown tree for agent context windows.

    Includes a project header with stats, a dependency graph section,
    and all symbols ordered by PageRank (most-connected first).
    Within files, classes by rank, then methods by rank.
    ``self`` is omitted. Elision markers (``...``) show trimmed content.

    Args:
        code_map: Code Map JSON (full or trimmed).

    Returns:
        Markdown-formatted tree string.
    """
    lines: list[str] = []

    # --- Header ---
    lines.append(f"# Code Map — {code_map.get('project_id', 'unknown')}")
    lines.append("")
    stats = code_map.get("stats", {})
    commit = code_map.get("commit", "")
    commit_short = commit[:12] if commit else "unknown"
    lines.append(
        f"**{stats.get('total_files', 0)} files** | "
        f"**{stats.get('total_lines', 0):,} lines** | "
        f"**{stats.get('total_classes', 0)} classes** | "
        f"**{stats.get('total_functions', 0)} functions** | "
        f"commit `{commit_short}`"
    )
    lines.append("")
    lines.append("Symbols ranked by PageRank (most-connected first).")
    lines.append("")

    # --- Import graph with circular dependency detection ---
    import_graph = code_map.get("import_graph", {})
    if import_graph:
        circular = _find_circular_deps(import_graph)
        lines.append("## Dependencies")
        lines.append("")
        if circular:
            lines.append(f"**Circular dependencies ({len(circular)}):**")
            for cycle in circular:
                lines.append(f"  ! {' -> '.join(_shorten_module(m) for m in cycle)}")
            lines.append("")
        # Sort by number of dependencies descending (most coupled first)
        sorted_deps = sorted(
            import_graph.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )
        # Build set of circular edges for marking
        circular_edges: set[tuple[str, str]] = set()
        for cycle in circular:
            for i in range(len(cycle) - 1):
                circular_edges.add((cycle[i], cycle[i + 1]))
        for module, deps in sorted_deps:
            short = _shorten_module(module)
            dep_strs = []
            for d in deps:
                short_d = _shorten_module(d)
                if (module, d) in circular_edges:
                    short_d += " [circular]"
                dep_strs.append(short_d)
            lines.append(f"  {short} -> {', '.join(dep_strs)}")
        lines.append("")

    # --- Module tree grouped by layer ---
    sorted_modules = sorted(
        code_map.get("modules", {}).items(),
        key=lambda x: x[1].get("rank", 0),
        reverse=True,
    )

    # Group modules by top-level package
    layers: dict[str, list[tuple[str, dict]]] = {}
    for path, mod in sorted_modules:
        layer = _get_layer(path)
        layers.setdefault(layer, []).append((path, mod))

    # Render each layer, ordered by total rank within layer
    sorted_layers = sorted(
        layers.items(),
        key=lambda x: sum(m.get("rank", 0) for _, m in x[1]),
        reverse=True,
    )

    for layer_name, layer_modules in sorted_layers:
        lines.append(f"## {layer_name}")
        lines.append("")
        for path, mod in layer_modules:
            _render_module(lines, path, mod)
        lines.append("")

    return "\n".join(lines)


def _render_module(lines: list[str], path: str, mod: dict) -> None:
    """Render a single module's symbols into the output lines."""
    line_count = mod.get("lines", 0)
    lines.append(f"{path} ({line_count} lines):")

    # Classes sorted by rank descending
    sorted_classes = sorted(
        mod.get("classes", {}).items(),
        key=lambda x: x[1].get("rank", 0),
        reverse=True,
    )

    for cls_name, cls_data in sorted_classes:
        bases_str = f"({', '.join(cls_data.get('bases', []))})" if cls_data.get("bases") else ""
        lines.append(f"\u2502class {cls_name}{bases_str}:")

        for field in cls_data.get("fields", []):
            lines.append(f"\u2502    {field}")

        for method_sig in cls_data.get("methods", []):
            lines.append(f"\u2502    def {method_sig}")

    # Functions sorted by rank descending
    sorted_functions = sorted(
        mod.get("functions", {}).items(),
        key=lambda x: x[1].get("rank", 0),
        reverse=True,
    )

    for func_name, func_data in sorted_functions:
        params = func_data.get("params", [])
        params_str = ", ".join(params[:3])
        if len(params) > 3:
            params_str += ", ..."
        returns = func_data.get("returns", "")
        ret_str = f" -> {returns}" if returns else ""
        decorators = func_data.get("decorators", [])
        for dec in decorators:
            lines.append(f"\u2502@{dec}")
        lines.append(f"\u2502def {func_name}({params_str}){ret_str}")

    lines.append("")


def _get_layer(path: str) -> str:
    """Extract the layer name from a module path for grouping.

    Groups by the second-level package under modules/backend/ or
    the top-level package under modules/ (e.g. telegram).
    Standalone files (e.g. modules/__init__.py, modules/backend/main.py)
    are grouped under their nearest package.
    """
    parts = path.replace("\\", "/").split("/")
    # modules/backend/core/... -> "backend.core"
    # modules/backend/agents/... -> "backend.agents"
    # modules/backend/main.py (standalone) -> "backend.core"
    # modules/telegram/... -> "telegram"
    # modules/__init__.py -> "root"
    if len(parts) >= 4 and parts[1] == "backend":
        return f"{parts[1]}.{parts[2]}"
    if len(parts) == 3 and parts[1] == "backend":
        # Standalone files like modules/backend/main.py
        return "backend.core"
    if len(parts) >= 3:
        return parts[1]
    # Top-level files like modules/__init__.py
    return "root"


def _find_circular_deps(import_graph: dict[str, list[str]]) -> list[list[str]]:
    """Detect circular dependencies in the import graph.

    Returns a list of cycles, each as a list of module names forming the loop.
    """
    visited: set[str] = set()
    in_stack: set[str] = set()
    stack: list[str] = []
    cycles: list[list[str]] = []

    def _dfs(node: str) -> None:
        if node in in_stack:
            # Found a cycle — extract it
            cycle_start = stack.index(node)
            cycle = stack[cycle_start:] + [node]
            cycles.append(cycle)
            return
        if node in visited:
            return
        visited.add(node)
        in_stack.add(node)
        stack.append(node)
        for dep in import_graph.get(node, []):
            _dfs(dep)
        stack.pop()
        in_stack.remove(node)

    for node in import_graph:
        if node not in visited:
            _dfs(node)

    return cycles


def _shorten_module(qname: str) -> str:
    """Shorten a qualified module name by removing the 'modules.' prefix."""
    if qname.startswith("modules."):
        return qname[8:]
    return qname


def render_for_agent(code_map: dict, max_tokens: int = 4096) -> str:
    """Convenience: trim by rank then render as Markdown tree.

    Trims based on the *rendered* Markdown size (not JSON size),
    since Markdown is roughly 50% smaller than JSON.

    Args:
        code_map: Full Code Map JSON.
        max_tokens: Token budget for the rendered output.

    Returns:
        Markdown tree string fitting within the token budget.
    """
    import copy

    rendered = render_markdown_tree(code_map)
    if _estimate_tokens(rendered) <= max_tokens:
        return rendered

    # Progressively remove lowest-ranked modules until budget is met
    working = copy.deepcopy(code_map)
    ranked_modules = sorted(
        working["modules"].items(),
        key=lambda x: x[1].get("rank", 0),
    )

    for path, _ in ranked_modules:
        del working["modules"][path]
        rendered = render_markdown_tree(working)
        if _estimate_tokens(rendered) <= max_tokens:
            return rendered

    return rendered


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _estimate_tokens(data: dict | str) -> int:
    """Estimate token count. Approximation: 1 token ≈ 4 characters."""
    if isinstance(data, str):
        text = data
    else:
        import json
        text = json.dumps(data)
    return len(text) // 4


def _collect_ranked_symbols(
    code_map: dict,
) -> list[tuple[str, float, str, str, str | None]]:
    """Collect all symbols with their ranks for trimming.

    Returns list of (file_path, rank, kind, name, parent_class).
    """
    symbols: list[tuple[str, float, str, str, str | None]] = []

    for path, mod in code_map.get("modules", {}).items():
        for cls_name, cls_data in mod.get("classes", {}).items():
            for method_sig in cls_data.get("methods", []):
                method_name = _method_name(method_sig)
                symbols.append((path, cls_data.get("rank", 0), "method", method_name, cls_name))
            symbols.append((path, cls_data.get("rank", 0), "class", cls_name, None))

        for func_name, func_data in mod.get("functions", {}).items():
            symbols.append((path, func_data.get("rank", 0), "function", func_name, None))

    return symbols


def _remove_symbol(
    code_map: dict,
    path: str,
    kind: str,
    name: str,
    parent: str | None,
) -> None:
    """Remove a single symbol from the code map."""
    mod = code_map["modules"].get(path)
    if mod is None:
        return

    if kind == "method" and parent:
        cls_data = mod.get("classes", {}).get(parent)
        if cls_data:
            cls_data["methods"] = [
                m for m in cls_data["methods"] if _method_name(m) != name
            ]
    elif kind == "function":
        mod.get("functions", {}).pop(name, None)
    elif kind == "class":
        mod.get("classes", {}).pop(name, None)


def _method_name(sig: str) -> str:
    """Extract method name from a signature string like 'foo(x: int) -> str'."""
    return sig.split("(", 1)[0].strip()


def _is_internal_import(imp: str, internal_modules: set[str]) -> bool:
    """Check if an import path refers to an internal module."""
    if imp in internal_modules:
        return True
    # Check if it's a symbol import from an internal module
    if "." in imp:
        parent = imp.rsplit(".", 1)[0]
        return parent in internal_modules
    return False


def _path_to_qname(rel_path: str) -> str:
    """Convert relative file path to module qualified name."""
    module = rel_path.replace("/", ".").replace("\\", ".")
    if module.endswith(".py"):
        module = module[:-3]
    if module.endswith(".__init__"):
        module = module[:-9]
    return module
