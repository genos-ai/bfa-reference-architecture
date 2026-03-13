"""Data types for the Code Map pipeline.

Each type corresponds to an intermediate or final result in the pipeline:
    parse_modules()          → list[ModuleInfo]
    build_reference_graph()  → ReferenceGraph
    rank_symbols()           → dict[str, float]
    assemble_code_map()      → dict  (JSON-serializable Code Map)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SymbolKind(str, Enum):
    """Kind of symbol extracted from source."""

    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    CONSTANT = "constant"


class ReferenceKind(str, Enum):
    """Kind of cross-reference edge."""

    IMPORT = "import"
    CALL = "call"
    INHERIT = "inherit"
    TYPE_ANNOTATION = "type_annotation"


@dataclass(frozen=True)
class SymbolInfo:
    """A single extracted symbol (class, function, method, constant)."""

    name: str
    kind: SymbolKind
    qualified_name: str
    line: int = 0
    params: list[str] = field(default_factory=list)
    return_type: str = ""
    bases: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    methods: list[SymbolInfo] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    end_line: int = 0


@dataclass
class ModuleInfo:
    """Parsed structure of a single Python module."""

    path: str
    lines: int
    imports: list[str] = field(default_factory=list)
    classes: list[SymbolInfo] = field(default_factory=list)
    functions: list[SymbolInfo] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReferenceEdge:
    """A directed reference from one symbol to another."""

    source: str
    target: str
    kind: ReferenceKind


@dataclass
class ReferenceGraph:
    """Directed graph of symbol cross-references."""

    nodes: list[str] = field(default_factory=list)
    edges: list[ReferenceEdge] = field(default_factory=list)
