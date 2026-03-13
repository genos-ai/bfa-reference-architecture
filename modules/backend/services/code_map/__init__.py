"""Code Map generator — structural codebase intelligence.

Deterministic pipeline that parses Python source, builds a cross-reference
graph, ranks symbols by PageRank, and produces a compact structural map
for AI agent context windows.

Public API:
    generate_code_map()     — full pipeline orchestrator
    render_for_agent()      — trim + render convenience
    render_markdown_tree()  — Markdown presentation
    trim_by_rank()          — token-budgeted trimming
    CodeMapLoader           — reusable load/cache/refresh service
"""

from modules.backend.services.code_map.generator import generate_code_map
from modules.backend.services.code_map.assembler import (
    find_circular_deps,
    render_for_agent,
    render_markdown_tree,
    trim_by_rank,
)
from modules.backend.services.code_map.loader import CodeMapLoader

__all__ = [
    "find_circular_deps",
    "generate_code_map",
    "render_for_agent",
    "render_markdown_tree",
    "trim_by_rank",
    "CodeMapLoader",
]
