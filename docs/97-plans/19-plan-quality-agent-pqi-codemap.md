# Implementation Plan: Integrate PQI & Code Map into Code Quality Agent

*Created: 2026-03-13*
*Status: Not Started*
*Depends on: Code Map service (done), PQI service (done), Code Quality Agent (done)*

---

## Summary

Add three new tools to the `code.quality.agent` that give it access to the PQI scorer and Code Map generator. The agent currently audits for compliance violations using deterministic scanners. After this change, it will also produce a quantitative quality assessment (PQI composite + 7 dimension scores) and structural analysis (dependency graph, circular dependencies, coupling hotspots). The output schema expands to include quality metrics alongside violations.

**Dev mode: breaking changes allowed.**

## Context

- PQI scorer: `modules/backend/services/pqi/scorer.py` — `score_project()` returns `PQIResult` with 7 dimensions, composite score, recommendations
- Code Map generator: `modules/backend/services/code_map/generator.py` — `generate_code_map()` returns JSON with modules, import graph, PageRank ranks, stats
- Code Map assembler: `modules/backend/services/code_map/assembler.py` — `render_markdown_tree()` renders enhanced markdown with header, dependency graph (with `[circular]` markers), and layer-grouped modules
- Current quality agent: `modules/backend/agents/vertical/code/quality/agent.py` — 8 compliance scanners + 1 read tool, outputs `QaAuditResult`
- Agent tool pattern: thin async wrappers in `modules/backend/agents/tools/`, no PydanticAI dependency, enforce `FileScope.check_read()` before delegating to service
- Agent config: `config/agents/code/quality/agent.yaml`
- Agent system prompt: `config/prompts/agents/code/qa/system.md`

## What to Build

### New files

- `modules/backend/agents/tools/quality.py` — Tool implementations for PQI and Code Map (~80 lines)
- `tests/unit/backend/agents/tools/test_quality_tools.py` — Unit tests for the new tools (~100 lines)

### Modified files

- `modules/backend/agents/vertical/code/quality/agent.py` — Register 3 new tools on the agent
- `modules/backend/agents/schemas.py` — Add `QualityMetrics` and `DependencyIssue` schemas, extend `QaAuditResult`
- `config/agents/code/quality/agent.yaml` — Add new tool names, add `CODEMAP.md` and `scripts/` to read scope
- `config/prompts/agents/code/qa/system.md` — Add workflow steps for quality scoring and dependency analysis

## Key Design Decisions

### 1. Three new tools, not one monolith

Split into focused tools that the agent calls independently:

| Tool | Service call | Returns | When to use |
|------|-------------|---------|-------------|
| `run_quality_score` | `score_project()` | PQI composite, 7 dimension scores, sub-scores, recommendations | Always — quantitative quality baseline |
| `get_dependency_analysis` | `generate_code_map()` + `_find_circular_deps()` | Dependency graph, circular deps, coupling hotspots (top N by efferent coupling) | Always — structural health check |
| `load_code_map_summary` | Reads `CODEMAP.md` from disk | Markdown string with header, deps, layer-grouped modules | Only when agent needs structural context for principle-based reviews |

**Rationale:** The agent can run `run_quality_score` and `get_dependency_analysis` unconditionally (they're fast, deterministic, high-value). `load_code_map_summary` is ~31K tokens so the agent should only call it when investigating structural issues flagged by the other tools.

### 2. Tool implementations are pure functions in `modules/backend/agents/tools/quality.py`

Follow the existing pattern from `compliance.py`: thin async wrappers that enforce `FileScope`, call the service, and return plain dicts. No PydanticAI dependency in the tool module.

### 3. Output schema extends `QaAuditResult` with optional quality metrics

Add optional fields to `QaAuditResult` so the schema is backwards-compatible. When the agent runs quality tools, it populates these fields. When it runs compliance-only (e.g., under tight token budget), they remain `None`.

### 4. PQI scope matches agent scope

The `run_quality_score` tool uses the agent's configured `scope.read` paths and `exclusions.paths` to determine what to scan. This ensures the quality score covers the same files the compliance scanners check.

### 5. Code map is read from disk, not regenerated

`load_code_map_summary` reads the existing `CODEMAP.md` (kept fresh by the pre-commit hook). This avoids the cost of regenerating during agent runs. `get_dependency_analysis` does regenerate because the dependency graph is small and must be current.

## Step-by-Step Implementation

### Step 1: Add quality metrics to output schema

**File:** `modules/backend/agents/schemas.py`

Add these models:

```python
class DimensionScore(BaseModel):
    """A single PQI dimension score."""
    name: str
    score: float
    sub_scores: dict[str, float] = {}
    recommendations: list[str] = []

class DependencyIssue(BaseModel):
    """A structural issue found in the dependency graph."""
    issue_type: str          # circular_dependency, high_coupling
    module: str
    detail: str
    severity: str            # error, warning

class QualityMetrics(BaseModel):
    """Quantitative quality assessment from PQI."""
    composite_score: float
    quality_band: str        # Excellent, Good, Acceptable, Poor, Critical
    file_count: int
    line_count: int
    dimensions: list[DimensionScore]
    dependency_issues: list[DependencyIssue] = []
```

Extend `QaAuditResult`:

```python
class QaAuditResult(BaseModel):
    # ... existing fields unchanged ...
    summary: str
    total_violations: int
    error_count: int
    warning_count: int
    violations: list[Violation]
    scanned_files_count: int
    # --- new fields (optional for backwards compat) ---
    quality_metrics: QualityMetrics | None = None
```

### Step 2: Create tool implementations

**File:** `modules/backend/agents/tools/quality.py`

```python
"""
Shared quality assessment tool implementations.

Thin async wrappers over PQI scorer and Code Map generator.
No PydanticAI dependency.
"""

from pathlib import Path

from modules.backend.agents.deps.base import FileScope


async def run_quality_score(
    project_root: Path,
    scope: FileScope,
    scan_scope: list[str] | None = None,
    exclude: list[str] | None = None,
) -> dict:
    """Run PQI scorer and return quality metrics.

    Returns dict with composite score, quality band, dimension scores,
    sub-scores, and recommendations per dimension.
    """
    scope.check_read("modules/")

    from modules.backend.services.pqi.scorer import score_project
    from modules.backend.services.code_map.generator import generate_code_map

    # Generate code map for modularity/reusability scoring
    code_map = generate_code_map(
        repo_root=project_root,
        scope=scan_scope,
        exclude=exclude,
    )

    result = score_project(
        repo_root=project_root,
        scope=scan_scope,
        exclude=exclude,
        code_map=code_map,
    )

    return {
        "composite_score": result.composite,
        "quality_band": result.quality_band.value,
        "file_count": result.file_count,
        "line_count": result.line_count,
        "dimensions": {
            name: {
                "score": dim.score,
                "sub_scores": dim.sub_scores,
                "recommendations": dim.recommendations,
            }
            for name, dim in result.dimensions.items()
        },
    }


async def get_dependency_analysis(
    project_root: Path,
    scope: FileScope,
    scan_scope: list[str] | None = None,
    exclude: list[str] | None = None,
    top_n_coupled: int = 10,
) -> dict:
    """Analyze dependency graph for structural issues.

    Returns dependency edges, circular dependencies, and top N modules
    by efferent coupling (most outbound dependencies).
    """
    scope.check_read("modules/")

    from modules.backend.services.code_map.generator import generate_code_map
    from modules.backend.services.code_map.assembler import _find_circular_deps

    code_map = generate_code_map(
        repo_root=project_root,
        scope=scan_scope,
        exclude=exclude,
    )

    import_graph = code_map.get("import_graph", {})
    circular = _find_circular_deps(import_graph)

    # Top N by efferent coupling (number of outbound dependencies)
    coupling_sorted = sorted(
        import_graph.items(),
        key=lambda x: len(x[1]),
        reverse=True,
    )[:top_n_coupled]

    return {
        "total_modules": len(code_map.get("modules", {})),
        "total_edges": sum(len(v) for v in import_graph.values()),
        "circular_dependencies": [
            {
                "cycle": cycle,
                "length": len(cycle) - 1,
            }
            for cycle in circular
        ],
        "top_coupled_modules": [
            {
                "module": module,
                "efferent_coupling": len(deps),
                "dependencies": deps,
            }
            for module, deps in coupling_sorted
        ],
    }


async def load_code_map_summary(
    project_root: Path,
    scope: FileScope,
) -> str:
    """Load the pre-generated CODEMAP.md for structural context.

    Returns the full markdown content. This is a large document (~31K tokens)
    — only call this when you need structural context for principle-based
    reviews or to investigate coupling/dependency issues.

    If CODEMAP.md does not exist, generates it on the fly.
    """
    scope.check_read("CODEMAP.md")

    codemap_path = project_root / "CODEMAP.md"
    if codemap_path.exists():
        return codemap_path.read_text(encoding="utf-8")

    # Fallback: generate on the fly
    from modules.backend.services.code_map.generator import generate_code_map
    from modules.backend.services.code_map.assembler import render_markdown_tree

    code_map = generate_code_map(
        repo_root=project_root,
        scope=["modules/"],
    )
    return render_markdown_tree(code_map)
```

**Important:** The `_find_circular_deps` function must be made importable. It is currently a private function in `assembler.py`. Either:
- (a) Rename it to `find_circular_deps` (remove leading underscore) and export it, OR
- (b) Import it as a private function (acceptable since both modules are in the same service package)

**Decision:** Option (a) — rename to `find_circular_deps` in `assembler.py` since it's now used by two consumers. Update the one call site in `render_markdown_tree()` accordingly.

### Step 3: Register tools on the agent

**File:** `modules/backend/agents/vertical/code/quality/agent.py`

Add three new `@agent.tool` registrations following the existing pattern. Each tool:
1. Emits `{"type": "tool_start", "tool": name}` via `ctx.deps.emit()`
2. Calls the shared tool implementation from `modules/backend/agents/tools/quality.py`
3. Emits `{"type": "tool_done", "tool": name, "detail": ...}`
4. Returns the result

```python
from modules.backend.agents.tools.quality import (
    run_quality_score as _run_quality_score,
    get_dependency_analysis as _get_dependency_analysis,
    load_code_map_summary as _load_code_map_summary,
)
```

Tool registrations (add after existing tool registrations in `create_agent()`):

```python
@agent.tool
async def run_quality_score(ctx: RunContext[QaAgentDeps]) -> dict:
    """Run PQI quality scorer. Returns composite score (0-100), 7 dimension
    scores with sub-scores, and actionable recommendations per dimension."""
    ctx.deps.emit({"type": "tool_start", "tool": "run_quality_score"})
    # Derive scope/exclude from agent config
    scan_scope = ["modules/", "tests/"]
    exclude_paths = []
    if ctx.deps.config and ctx.deps.config.exclusions:
        exclude_paths = list(ctx.deps.config.exclusions.paths or [])
    result = await _run_quality_score(
        ctx.deps.project_root, ctx.deps.scope,
        scan_scope=scan_scope, exclude=exclude_paths,
    )
    ctx.deps.emit({
        "type": "tool_done", "tool": "run_quality_score",
        "detail": f"PQI: {result['composite_score']}/100 ({result['quality_band']})",
    })
    return result

@agent.tool
async def get_dependency_analysis(ctx: RunContext[QaAgentDeps]) -> dict:
    """Analyze the dependency graph. Returns circular dependencies,
    top coupled modules, and edge counts."""
    ctx.deps.emit({"type": "tool_start", "tool": "get_dependency_analysis"})
    scan_scope = ["modules/"]
    exclude_paths = []
    if ctx.deps.config and ctx.deps.config.exclusions:
        exclude_paths = list(ctx.deps.config.exclusions.paths or [])
    result = await _get_dependency_analysis(
        ctx.deps.project_root, ctx.deps.scope,
        scan_scope=scan_scope, exclude=exclude_paths,
    )
    circular_count = len(result["circular_dependencies"])
    ctx.deps.emit({
        "type": "tool_done", "tool": "get_dependency_analysis",
        "detail": f"{result['total_modules']} modules, {result['total_edges']} edges, {circular_count} circular",
    })
    return result

@agent.tool
async def load_code_map_summary(ctx: RunContext[QaAgentDeps]) -> str:
    """Load structural code map (~31K tokens). Only call this when you need
    full structural context — e.g., to investigate coupling issues or
    review module organization for principle violations."""
    ctx.deps.emit({"type": "tool_start", "tool": "load_code_map_summary"})
    result = await _load_code_map_summary(ctx.deps.project_root, ctx.deps.scope)
    token_estimate = len(result) // 4
    ctx.deps.emit({
        "type": "tool_done", "tool": "load_code_map_summary",
        "detail": f"Loaded CODEMAP.md (~{token_estimate} tokens)",
    })
    return result
```

### Step 4: Update agent config YAML

**File:** `config/agents/code/quality/agent.yaml`

Add the three new tools to the `tools` list:

```yaml
tools:
  # ... existing tools ...
  - compliance.load_project_standards
  - filesystem.read_file
  - filesystem.list_files
  - compliance.scan_imports
  - compliance.scan_datetime
  - compliance.scan_hardcoded
  - compliance.scan_file_sizes
  - compliance.scan_cli_options
  - compliance.scan_config_files
  # --- new tools ---
  - quality.run_quality_score
  - quality.get_dependency_analysis
  - quality.load_code_map_summary
```

Add `CODEMAP.md` to read scope:

```yaml
scope:
  read:
    - "modules/"
    - "config/"
    - "docs/"
    - "*.py"
    - "*.md"
    - "requirements.txt"
    - "CODEMAP.md"
  write: []
```

Add quality-related keywords:

```yaml
keywords:
  # ... existing ...
  - code quality
  - quality score
  - pqi
  - dependencies
  - coupling
  - architecture quality
```

Increase `max_requests` from 25 to 35 (the three new tools add ~3-5 extra LLM round-trips):

```yaml
max_requests: 35
```

### Step 5: Update system prompt

**File:** `config/prompts/agents/code/qa/system.md`

Replace the current workflow with the expanded version. The new steps are marked with `[NEW]`:

```markdown
## QA Compliance Agent

You audit the codebase for compliance violations and code quality. You are read-only — you report findings but never modify files.

### Workflow

**Phase 1: Compliance Audit**
1. **Load project rules first** — call `load_project_standards` to read all rules from `docs/*-rules/*.jsonl`. This is your source of truth for what the codebase must conform to.
2. Use `list_python_files` to discover files in scope
3. Run all `scan_*` tools to detect violations
4. For each violation, provide a clear recommendation for how to fix it
5. If you need more context to classify a finding, use `read_source_file` to examine the surrounding code
6. After scanning, use `read_source_file` to review key modules for principle violations (rules with `check: "review"`) — these require your judgment and cannot be detected by `scan_*` tools. Evaluate against the principles loaded in step 1.
7. **Audit root documentation and dependencies** — use `read_source_file` to check root `.md` files (`README.md`, `AGENTS.md`, `USAGE.md`, etc.) and `requirements.txt` for accuracy and completeness. Flag stale references, missing sections, instructions that no longer match the codebase, unused or missing dependencies, and version pins that are outdated or inconsistent.

**Phase 2: Quality Assessment** [NEW]
8. **Run quality score** — call `run_quality_score` to get the PQI composite score and 7 dimension breakdowns. Record the composite score, quality band, and any dimension scoring below 50 as a concern.
9. **Analyze dependencies** — call `get_dependency_analysis` to check for circular dependencies and high coupling. Flag any module with efferent coupling > 15 and all circular dependencies.
10. **Investigate structural issues** (conditional) — if step 9 reveals circular dependencies or step 8 shows Modularity < 50, call `load_code_map_summary` to get full structural context. Use it to provide specific recommendations for breaking cycles and reducing coupling.

**Phase 3: Report** [NEW]
11. Return a `QaAuditResult` with:
    - All violations from Phase 1 (scan-detected, principle-based, documentation)
    - `quality_metrics` populated from Phase 2 results (composite score, dimension scores, dependency issues)
    - A summary that covers both compliance findings AND quality assessment

### Rules

Your `load_project_standards` tool returns all rules from `docs/*-rules/*.jsonl`. There are two kinds:

- **Deterministic rules** (`check` contains a shell command, `expect` defines pass criteria) — your `scan_*` tools enforce some of these automatically. Cross-reference scan results against the full rule set to identify gaps.
- **Principle rules** (`check: "review"`) — architectural principles that require your judgment. Use `read_source_file` to examine code before flagging. Only flag when you are confident it is a true violation.

Classify severity from the rule's `severity` field. For principle rules, report as "warning" with a clear recommendation.

### Quality Score Interpretation

- **Excellent (90-100):** No action needed
- **Good (70-89):** Address recommendations in lowest-scoring dimensions
- **Acceptable (50-69):** Dimensions below 50 need attention — flag as warnings
- **Poor (30-49):** Dimensions below 30 are critical — flag as errors
- **Critical (0-29):** Systemic issues — escalate in summary

### Constraints
- You MUST NOT modify any files — you are an auditor, not a fixer (P13)
- Be precise about file paths and line numbers
- When uncertain whether something is a true violation, read the file context before classifying
- Include a recommendation field explaining what the correct fix would be
- Classify severity accurately: "error" for rule violations, "warning" for principle/style issues
- Only call `load_code_map_summary` when you have a specific reason — it consumes ~31K tokens
```

### Step 6: Rename `_find_circular_deps` to public

**File:** `modules/backend/services/code_map/assembler.py`

Rename `_find_circular_deps` to `find_circular_deps` (remove leading underscore). Update the two call sites in the same file:
- Line in `render_markdown_tree()`: `circular = _find_circular_deps(import_graph)` → `circular = find_circular_deps(import_graph)`
- The function definition itself

### Step 7: Write tests

**File:** `tests/unit/backend/agents/tools/test_quality_tools.py`

Test the three tool implementations directly (no PydanticAI, no LLM). Use the real project root and file system.

```python
"""Tests for quality assessment tools."""

import pytest
from pathlib import Path
from modules.backend.agents.deps.base import FileScope
from modules.backend.agents.tools.quality import (
    run_quality_score,
    get_dependency_analysis,
    load_code_map_summary,
)

PROJECT_ROOT = Path(__file__).resolve().parents[5]  # up to repo root


@pytest.fixture
def read_scope() -> FileScope:
    return FileScope(read_paths=["modules/", "*.md"], write_paths=[])


@pytest.fixture
def restricted_scope() -> FileScope:
    return FileScope(read_paths=[], write_paths=[])


class TestRunQualityScore:
    async def test_returns_composite_and_dimensions(self, read_scope):
        result = await run_quality_score(
            PROJECT_ROOT, read_scope,
            scan_scope=["modules/"], exclude=["__pycache__/"],
        )
        assert 0 <= result["composite_score"] <= 100
        assert result["quality_band"] in ("Excellent", "Good", "Acceptable", "Poor", "Critical")
        assert "maintainability" in result["dimensions"]
        assert "modularity" in result["dimensions"]
        assert len(result["dimensions"]) == 7

    async def test_dimension_has_sub_scores(self, read_scope):
        result = await run_quality_score(
            PROJECT_ROOT, read_scope, scan_scope=["modules/"],
        )
        for dim_name, dim_data in result["dimensions"].items():
            assert "score" in dim_data
            assert "sub_scores" in dim_data
            assert "recommendations" in dim_data

    async def test_respects_file_scope(self, restricted_scope):
        with pytest.raises(PermissionError):
            await run_quality_score(
                PROJECT_ROOT, restricted_scope, scan_scope=["modules/"],
            )


class TestGetDependencyAnalysis:
    async def test_returns_graph_stats(self, read_scope):
        result = await get_dependency_analysis(
            PROJECT_ROOT, read_scope, scan_scope=["modules/"],
        )
        assert result["total_modules"] > 0
        assert result["total_edges"] > 0
        assert isinstance(result["circular_dependencies"], list)
        assert isinstance(result["top_coupled_modules"], list)

    async def test_top_coupled_is_sorted(self, read_scope):
        result = await get_dependency_analysis(
            PROJECT_ROOT, read_scope, scan_scope=["modules/"],
        )
        couplings = [m["efferent_coupling"] for m in result["top_coupled_modules"]]
        assert couplings == sorted(couplings, reverse=True)

    async def test_respects_file_scope(self, restricted_scope):
        with pytest.raises(PermissionError):
            await get_dependency_analysis(
                PROJECT_ROOT, restricted_scope, scan_scope=["modules/"],
            )


class TestLoadCodeMapSummary:
    async def test_returns_markdown(self, read_scope):
        result = await load_code_map_summary(PROJECT_ROOT, read_scope)
        assert "# Code Map" in result
        assert "## Dependencies" in result

    async def test_respects_file_scope(self, restricted_scope):
        with pytest.raises(PermissionError):
            await load_code_map_summary(PROJECT_ROOT, restricted_scope)
```

All tests use `pytest-asyncio` with real filesystem (no mocks). Tests run the actual PQI scorer and code map generator against the repo.

## File Inventory

| File | Action | Lines (est.) |
|------|--------|-------------|
| `modules/backend/agents/tools/quality.py` | CREATE | ~80 |
| `modules/backend/agents/schemas.py` | MODIFY | +25 |
| `modules/backend/agents/vertical/code/quality/agent.py` | MODIFY | +45 |
| `modules/backend/services/code_map/assembler.py` | MODIFY | rename 1 function, update 1 call site |
| `config/agents/code/quality/agent.yaml` | MODIFY | +8 |
| `config/prompts/agents/code/qa/system.md` | MODIFY | rewrite (~55 lines) |
| `tests/unit/backend/agents/tools/test_quality_tools.py` | CREATE | ~100 |

## Success Criteria

1. `run_quality_score` tool returns a valid PQI result with all 7 dimensions when called by the agent
2. `get_dependency_analysis` detects the known circular dependency (`backend.agents.mission_control.checks -> backend.agents.mission_control.checks`)
3. `load_code_map_summary` returns the CODEMAP.md content (or generates it if missing)
4. `QaAuditResult` includes `quality_metrics` when the agent runs the quality tools
5. All 3 tools enforce `FileScope` — calling with restricted scope raises `PermissionError`
6. Agent system prompt guides the agent through both phases (compliance + quality) in correct order
7. All tests pass: `pytest tests/unit/backend/agents/tools/test_quality_tools.py -v`
8. Agent runs end-to-end without exceeding `max_requests: 35`

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| PQI + code map generation is slow (~3-5s each) | Agent timeout | Both tools are I/O-bound, not LLM-bound. 3-5s is well within the 5min task timeout. Can cache code_map dict across the two tools that both generate it. |
| `load_code_map_summary` consumes ~31K tokens | Blows token budget | System prompt instructs agent to only call it conditionally. `max_tokens` increased to 500K (already set). |
| Two tools both call `generate_code_map()` | Redundant work | Accept for now. If profiling shows it matters, add a simple module-level cache keyed on repo root + scope. |
| Output schema change breaks downstream consumers | API breakage | New fields are optional (`None` default). Existing consumers ignore them. |

## Out of Scope

- Running external tools (Bandit, Radon) from the agent — these require subprocess execution and should stay as optional CLI flags
- Writing a new agent — we're extending the existing `code.quality.agent`
- Caching or persistence of PQI results — the agent runs on-demand and results are part of the mission outcome
- Quality trend tracking over time — future work, requires database storage of PQI snapshots
