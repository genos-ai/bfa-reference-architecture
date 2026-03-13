"""Stage 2: Build Cross-Reference Graph.

Constructs a directed graph where nodes are symbols (modules, classes,
functions) and edges are references (imports, calls, inheritance, type
annotations). External symbols (stdlib, third-party) are excluded.
"""

from __future__ import annotations

from modules.backend.services.code_map.types import (
    ModuleInfo,
    ReferenceEdge,
    ReferenceGraph,
    ReferenceKind,
    SymbolInfo,
    SymbolKind,
)


def build_reference_graph(modules: list[ModuleInfo]) -> ReferenceGraph:
    """Build a cross-reference graph from parsed modules.

    Resolution strategy (from doc 49): for each reference, attempt to
    resolve against the import table of the current module. If it matches
    an imported name or a locally defined name, create an edge. Otherwise
    drop it silently. Conservative — under-counts rather than guesses.

    Args:
        modules: Parsed module info from parse_modules().

    Returns:
        ReferenceGraph with module-level and symbol-level edges.
    """
    known_modules = _build_module_index(modules)
    known_symbols = _build_symbol_index(modules)
    import_tables = _build_import_tables(modules, known_modules)

    nodes = sorted(known_modules | known_symbols.keys())
    edges: list[ReferenceEdge] = []

    for module in modules:
        module_qname = _path_to_qname(module.path)

        # Import edges: module → imported module
        for imp in module.imports:
            target = _resolve_import(imp, known_modules)
            if target:
                edges.append(ReferenceEdge(
                    source=module_qname,
                    target=target,
                    kind=ReferenceKind.IMPORT,
                ))

        # Class inheritance edges
        for cls in module.classes:
            for base in cls.bases:
                target = _resolve_name(
                    base, module_qname, import_tables, known_symbols,
                )
                if target:
                    edges.append(ReferenceEdge(
                        source=cls.qualified_name,
                        target=target,
                        kind=ReferenceKind.INHERIT,
                    ))

            # Method-level references
            for method in cls.methods:
                _add_symbol_references(
                    method, module_qname, import_tables, known_symbols, edges,
                )

            # Field type annotation edges
            for field_str in cls.fields:
                if ": " in field_str:
                    type_str = field_str.split(": ", 1)[1]
                    target = _resolve_name(
                        type_str, module_qname, import_tables, known_symbols,
                    )
                    if target:
                        edges.append(ReferenceEdge(
                            source=cls.qualified_name,
                            target=target,
                            kind=ReferenceKind.TYPE_ANNOTATION,
                        ))

        # Top-level function references
        for func in module.functions:
            _add_symbol_references(
                func, module_qname, import_tables, known_symbols, edges,
            )

    # Deduplicate edges
    unique_edges = list(set(edges))

    return ReferenceGraph(nodes=nodes, edges=unique_edges)


def _add_symbol_references(
    symbol: SymbolInfo,
    module_qname: str,
    import_tables: dict[str, dict[str, str]],
    known_symbols: dict[str, str],
    edges: list[ReferenceEdge],
) -> None:
    """Add edges for parameter and return type annotations."""
    for param in symbol.params:
        if ": " in param:
            type_str = param.split(": ", 1)[1]
            target = _resolve_name(
                type_str, module_qname, import_tables, known_symbols,
            )
            if target:
                edges.append(ReferenceEdge(
                    source=symbol.qualified_name,
                    target=target,
                    kind=ReferenceKind.TYPE_ANNOTATION,
                ))

    if symbol.return_type:
        target = _resolve_name(
            symbol.return_type, module_qname, import_tables, known_symbols,
        )
        if target:
            edges.append(ReferenceEdge(
                source=symbol.qualified_name,
                target=target,
                kind=ReferenceKind.TYPE_ANNOTATION,
            ))


def _build_module_index(modules: list[ModuleInfo]) -> set[str]:
    """Build a set of known module qualified names."""
    index: set[str] = set()
    for module in modules:
        qname = _path_to_qname(module.path)
        index.add(qname)
        # Also add parent packages
        parts = qname.split(".")
        for i in range(1, len(parts)):
            index.add(".".join(parts[:i]))
    return index


def _build_symbol_index(modules: list[ModuleInfo]) -> dict[str, str]:
    """Build a mapping of qualified name → short name for all symbols."""
    index: dict[str, str] = {}
    for module in modules:
        for cls in module.classes:
            index[cls.qualified_name] = cls.name
            for method in cls.methods:
                index[method.qualified_name] = method.name
        for func in module.functions:
            index[func.qualified_name] = func.name
    return index


def _build_import_tables(
    modules: list[ModuleInfo],
    known_modules: set[str],
) -> dict[str, dict[str, str]]:
    """Build per-module import tables mapping local names to qualified names.

    Only includes imports that resolve to known (internal) modules.
    """
    tables: dict[str, dict[str, str]] = {}

    for module in modules:
        module_qname = _path_to_qname(module.path)
        table: dict[str, str] = {}

        for imp in module.imports:
            resolved = _resolve_import(imp, known_modules)
            if resolved:
                # Map the short name (last segment) to the full qualified name
                short = imp.rsplit(".", 1)[-1]
                table[short] = resolved

        tables[module_qname] = table

    return tables


def _resolve_import(imp: str, known_modules: set[str]) -> str | None:
    """Resolve an import string to a known module.

    Tries the full import path first, then progressively shorter
    prefixes (to handle ``from x.y import Z`` where Z is a symbol).
    """
    if imp in known_modules:
        return imp
    # Try parent (import is a symbol within a module)
    parent = imp.rsplit(".", 1)[0] if "." in imp else None
    if parent and parent in known_modules:
        return parent
    return None


def _resolve_name(
    name: str,
    module_qname: str,
    import_tables: dict[str, dict[str, str]],
    known_symbols: dict[str, str],
) -> str | None:
    """Resolve a name reference to a known symbol or module.

    Strips generic type wrappers (e.g. list[Foo] → Foo) and attempts
    resolution against the module's import table.
    """
    # Strip generic wrappers
    name = _strip_generics(name)
    if not name or name[0].islower():
        return None  # Skip builtins and lowercase names

    # Check import table for the current module
    table = import_tables.get(module_qname, {})
    if name in table:
        return table[name]

    # Check if it's a fully qualified known symbol
    for qname in known_symbols:
        if qname.endswith(f".{name}"):
            return qname

    return None


def _strip_generics(type_str: str) -> str:
    """Strip generic type wrappers to get the base type name.

    Examples:
        list[Foo]        → Foo
        dict[str, Foo]   → Foo  (last type arg)
        Optional[Foo]    → Foo
        Foo | None       → Foo
        Foo              → Foo
    """
    # Handle union types (Foo | None)
    if " | " in type_str:
        parts = [p.strip() for p in type_str.split(" | ") if p.strip() != "None"]
        if parts:
            return _strip_generics(parts[0])
        return ""

    # Handle subscript types (List[Foo], Optional[Foo])
    if "[" in type_str and "]" in type_str:
        inner = type_str[type_str.index("[") + 1 : type_str.rindex("]")]
        # For dict-like with multiple args, take the last
        parts = _split_type_args(inner)
        for part in reversed(parts):
            stripped = part.strip()
            if stripped and stripped[0].isupper():
                return stripped
        return ""

    return type_str


def _split_type_args(args_str: str) -> list[str]:
    """Split type arguments respecting nested brackets."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in args_str:
        if char == "[":
            depth += 1
            current.append(char)
        elif char == "]":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _path_to_qname(rel_path: str) -> str:
    """Convert relative file path to module qualified name."""
    module = rel_path.replace("/", ".").replace("\\", ".")
    if module.endswith(".py"):
        module = module[:-3]
    if module.endswith(".__init__"):
        module = module[:-9]
    return module
