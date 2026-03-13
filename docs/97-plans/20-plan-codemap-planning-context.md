# Implementation Plan: Wire Code Map into Planning Agent & Context Assembly

*Created: 2026-03-13*
*Status: Implemented*
*Depends on: Code Map Generator (done — Phase 1 of doc 49), Context Assembler (done — doc 48), Planning Agent (done — Plan 13)*
*Reference: docs/99-reference-architecture/49-agentic-codebase-intelligence.md*

---

## Summary

Wire the Code Map into the two places doc 49 says it belongs:

1. **Planning Agent** — receives the full Code Map **JSON** so it can use the import graph, PageRank ranks, and symbol data to generate precise file manifests and task instructions.
2. **Context Assembler** — injects the Code Map **Markdown tree** as Layer 3 for coding agents, giving them spatial awareness of the codebase without exploration.

Also add a **staleness check** so the Code Map is regenerated when it doesn't match HEAD, and extend the TaskPlan schema with `file_manifest` so the Planning Agent can tell coding agents exactly which files to read and modify.

**Philosophy: quality and accuracy over cost.** The full Code Map (~31K tokens Markdown, ~77K JSON) is used unless profiling proves a trimmed version produces equivalent results. We are not pre-optimizing token budgets — we want the Planning Agent to have complete structural awareness.

**Dev mode: breaking changes allowed.**

## Context

- Doc 49 (agentic-codebase-intelligence): defines Code Map as front-loaded into Planning Agent (JSON) and delivered to coding agents via Context Assembler (Markdown tree, Layer 3)
- Code Map generator: `modules/backend/services/code_map/generator.py` — `generate_code_map()` returns JSON dict
- Code Map assembler: `modules/backend/services/code_map/assembler.py` — `render_markdown_tree()` returns enhanced Markdown with header, dependency graph, circular dep markers, layer grouping
- Context Assembler: `modules/backend/services/context_assembler.py` — builds layered context packets (Layer 0: PCD, Layer 1: task+inputs, Layer 2: history). No Layer 3 exists yet.
- Planning Agent: `modules/backend/agents/horizontal/planning/agent.py` — receives mission brief, roster, upstream context via `PlanningAgentDeps`. No Code Map injected currently.
- Planning prompt: `config/prompts/agents/horizontal/planning/system.md` — TaskPlan schema has `inputs.static` but no `file_manifest` field.
- Dispatch adapter: `modules/backend/agents/mission_control/dispatch_adapter.py` — entry point that calls `handle_mission()`. No staleness check.
- Dispatch loop: `modules/backend/agents/mission_control/dispatch.py` — calls `context_assembler.build()` per-task before agent execution.
- Helpers: `modules/backend/agents/mission_control/helpers.py` — `_call_planning_agent()` creates PlanningAgentDeps and runs the agent. `_build_planning_prompt()` assembles the prompt with mission brief + roster + upstream context.

## What to Build

### New files

| File | Purpose |
|------|---------|
| `modules/backend/services/code_map/loader.py` | Reusable `CodeMapLoader` service — load, cache, staleness check, regenerate. Used by both Plan 20 (planning/context) and Plan 19 (quality agent). |

### Modified files

| File | Change |
|------|--------|
| `modules/backend/agents/horizontal/planning/agent.py` | Add `code_map` field to `PlanningAgentDeps`, inject into agent context |
| `modules/backend/agents/mission_control/helpers.py` | Load Code Map JSON in `_call_planning_agent()`, pass to PlanningAgentDeps. Add staleness check + regeneration. |
| `modules/backend/services/context_assembler.py` | Add Layer 3 (Code Map Markdown) for coding tasks |
| `modules/backend/schemas/task_plan.py` | Add `FileManifestEntry` and `FileManifest` models, add optional `file_manifest` to `TaskInputs` |
| `config/prompts/agents/horizontal/planning/system.md` | Add file manifest generation instructions and Code Map usage guidance |
| `config/agents/horizontal/planning/agent.yaml` | Add `CODEMAP.md` and `.codemap/` to read scope |
| `modules/backend/agents/mission_control/models.py` | Update `ContextAssemblerProtocol` signature if needed |

## Key Design Decisions

### 1. Planning Agent gets the full Code Map JSON — no trimming

The Planning Agent runs once per mission on Opus 4.6 with extended thinking. It needs the import graph, PageRank scores, and complete symbol data to generate accurate file manifests. Trimming removes low-ranked symbols that may be exactly the ones a specific task needs to modify.

The full JSON is ~77K tokens. The Planning Agent's token budget is already high (16K output, 200K+ input on Opus). The cost of one planning call is small compared to the cost of a coding agent exploring the wrong files because the manifest was incomplete.

If profiling later shows the full JSON causes issues (context window pressure, latency), we can add `trim_by_rank()` with a generous budget (e.g., 40K tokens). But we start with the full map.

### 2. Coding agents get the full Markdown tree via Context Assembler — no trimming

Doc 49 specifies ~3-5K tokens for the Markdown tree. Our enhanced Markdown is ~31K tokens because we include the dependency graph and layer grouping. This is more useful than a trimmed version because:

- The agent can see the full dependency graph (which module depends on which)
- Circular dependency markers are visible
- Layer grouping provides structural context

The Context Assembler's default `token_budget` is 12K. We increase it or make the Code Map layer exempt from budget trimming (like Layer 0/PCD). If the token budget becomes a problem in practice, we add `render_for_agent(code_map, max_tokens=N)` as a fallback — but only after measuring.

**Decision: Start with full Markdown. Add a `code_map_max_tokens` parameter to `ContextAssembler.build()` defaulting to `None` (no limit). If set, trim via `render_for_agent()`.**

### 3. Staleness check uses git commit hash comparison

The Code Map JSON includes a `commit` field. Before planning, compare it to `git rev-parse HEAD`. If they differ, regenerate. This is fast (<5s for the full codebase) and ensures the Planning Agent never works with outdated structure.

**Location:** In `_call_planning_agent()` in helpers.py, before building deps.

### 4. Code Map is loaded from `.codemap/map.json` (JSON) and `CODEMAP.md` (Markdown)

- Planning Agent: reads `.codemap/map.json` — structured data for programmatic use
- Context Assembler: reads `CODEMAP.md` — pre-rendered Markdown for agent context
- Both files are kept fresh by the pre-commit hook (already wired)
- Staleness check regenerates both if needed

### 5. File manifest is optional in TaskPlan

Not all tasks are coding tasks. The `file_manifest` field is added to `TaskInputs.static` as an optional typed field. The Planning Agent generates it only for tasks assigned to coding agents (agents with write scope). Non-coding tasks (analysis, health checks, summarization) skip it.

### 6. Context Assembler determines "coding task" by domain_tags

Doc 49 says the Code Map is loaded for tasks with code-related `domain_tags`. The Context Assembler checks if any of the task's `domain_tags` contain coding-related tags (e.g., `"code"`, `"implementation"`, `"refactor"`, `"bugfix"`). If none match, Layer 3 is skipped.

If `domain_tags` is empty or None, the Code Map is included by default (conservative — better to include than to miss).

## Step-by-Step Implementation

### Step 1: Add file manifest to TaskPlan schema

**File:** `modules/backend/schemas/task_plan.py`

Add models for file manifest entries:

```python
class FileManifestEntry(BaseModel, extra="forbid"):
    """A single file in the task file manifest."""
    path: str
    reason: str

class FileManifest(BaseModel, extra="forbid"):
    """Pre-computed file list for coding agents (doc 49)."""
    read_for_pattern: list[FileManifestEntry] = []
    read_first: list[FileManifestEntry] = []
    modify: list[FileManifestEntry] = []
```

Add `file_manifest` as an optional field to `TaskInputs`:

```python
class TaskInputs(BaseModel, extra="forbid"):
    static: dict[str, Any] = {}
    from_upstream: dict[str, FromUpstreamRef] = {}
    file_manifest: FileManifest | None = None
```

### Step 2: Load Code Map JSON into Planning Agent

**File:** `modules/backend/agents/horizontal/planning/agent.py`

Add `code_map` to `PlanningAgentDeps`:

```python
@dataclass
class PlanningAgentDeps:
    mission_brief: str
    roster_description: str
    upstream_context: dict[str, Any] | None = None
    code_map: dict | None = None  # NEW: Full Code Map JSON
```

The agent already receives all context via the user prompt (assembled in `_build_planning_prompt()`). The Code Map JSON will be appended to the prompt as a structured section, not passed through deps. Deps carries it for access in tool calls if needed later.

### Step 3: Inject Code Map into planning prompt

**File:** `modules/backend/agents/mission_control/helpers.py`

Modify `_build_planning_prompt()` to accept and include the Code Map:

```python
def _build_planning_prompt(
    mission_brief: str,
    mission_id: str,
    roster_description: str,
    upstream_context: dict | None = None,
    code_map: dict | None = None,  # NEW
) -> str:
```

Add a new section to the prompt output:

```python
if code_map:
    prompt += "\n\n## Code Map (Structural Overview)\n\n"
    prompt += "The following JSON contains the complete structural map of the codebase.\n"
    prompt += "Use it to:\n"
    prompt += "- Identify which files exist and what they contain\n"
    prompt += "- Trace dependencies via the import_graph\n"
    prompt += "- Generate file_manifest entries for coding tasks\n"
    prompt += "- Understand which modules are most important (highest PageRank rank)\n\n"
    prompt += "```json\n"
    prompt += json.dumps(code_map, indent=None)  # compact JSON to save tokens
    prompt += "\n```\n"
```

Modify `_call_planning_agent()` to load and pass the Code Map:

```python
async def _call_planning_agent(prompt, roster, upstream_context):
    # ... existing code ...

    # Load Code Map JSON
    code_map = _load_code_map_json()

    # Check staleness, regenerate if needed
    if code_map and _is_code_map_stale(code_map):
        code_map = _regenerate_code_map()

    # Build prompt with Code Map
    planning_prompt = _build_planning_prompt(
        mission_brief=prompt,
        mission_id=mission_id,
        roster_description=roster_desc,
        upstream_context=upstream_context,
        code_map=code_map,  # NEW
    )

    deps = PlanningAgentDeps(
        mission_brief=prompt,
        roster_description=roster_desc,
        upstream_context=upstream_context,
        code_map=code_map,  # NEW
    )

    # ... rest unchanged ...
```

Add helper functions for Code Map loading and staleness:

```python
def _load_code_map_json() -> dict | None:
    """Load the Code Map JSON from .codemap/map.json."""
    project_root = find_project_root()
    map_path = project_root / ".codemap" / "map.json"
    if not map_path.exists():
        logger.warning("Code Map not found at %s", map_path)
        return None
    try:
        return json.loads(map_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load Code Map: %s", exc)
        return None


def _is_code_map_stale(code_map: dict) -> bool:
    """Check if the Code Map commit matches HEAD."""
    map_commit = code_map.get("commit", "")
    if not map_commit:
        return True
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=find_project_root(),
            capture_output=True, text=True, timeout=5,
        )
        head_commit = result.stdout.strip() if result.returncode == 0 else ""
        return map_commit != head_commit
    except (OSError, subprocess.TimeoutExpired):
        return False  # Can't check, assume fresh


def _regenerate_code_map() -> dict | None:
    """Regenerate the Code Map from the current codebase."""
    from modules.backend.services.code_map.generator import generate_code_map
    from modules.backend.services.code_map.assembler import render_markdown_tree

    project_root = find_project_root()
    try:
        code_map = generate_code_map(
            repo_root=project_root,
            scope=["modules/"],
            project_id=project_root.name,
        )
        # Write JSON
        map_dir = project_root / ".codemap"
        map_dir.mkdir(exist_ok=True)
        (map_dir / "map.json").write_text(
            json.dumps(code_map, indent=2), encoding="utf-8",
        )
        # Write Markdown
        markdown = render_markdown_tree(code_map)
        (project_root / "CODEMAP.md").write_text(markdown, encoding="utf-8")

        logger.info("Regenerated Code Map (%d files)", code_map.get("stats", {}).get("total_files", 0))
        return code_map
    except Exception as exc:
        logger.warning("Failed to regenerate Code Map: %s", exc)
        return None
```

### Step 4: Add Layer 3 (Code Map) to Context Assembler

**File:** `modules/backend/services/context_assembler.py`

Add Code Map loading and injection between Layer 1 and Layer 2:

```python
async def build(
    self,
    project_id: str,
    task_definition: dict,
    resolved_inputs: dict,
    *,
    domain_tags: list[str] | None = None,
    token_budget: int = 12000,
    code_map_max_tokens: int | None = None,  # NEW: None = no limit
) -> dict:
    # ... Layer 0 (PCD) — unchanged ...
    # ... Layer 1 (Task + Inputs) — unchanged ...

    # Layer 3: Code Map (for coding tasks)
    code_map_content = None
    if self._is_coding_task(domain_tags):
        code_map_content = self._load_code_map_markdown(code_map_max_tokens)
        if code_map_content:
            code_map_tokens = self._estimate_tokens(code_map_content)
            remaining_budget -= code_map_tokens

    # ... Layer 2 (History) — unchanged, uses remaining_budget ...

    # Assemble final packet
    packet = {
        "project_context": pcd,
        "task": task_definition,
        "inputs": resolved_inputs_content,
        "history": history_content,
    }
    if code_map_content:
        packet["code_map"] = code_map_content

    return packet
```

Add helper methods:

```python
_CODING_TAGS = {"code", "implementation", "refactor", "bugfix", "feature", "migration"}

def _is_coding_task(self, domain_tags: list[str] | None) -> bool:
    """Determine if this task needs codebase structural context."""
    if not domain_tags:
        return True  # Conservative: include Code Map when unsure
    return bool(set(domain_tags) & self._CODING_TAGS)

def _load_code_map_markdown(self, max_tokens: int | None = None) -> str | None:
    """Load the pre-rendered Code Map Markdown."""
    from modules.backend.core.config import find_project_root

    codemap_path = find_project_root() / "CODEMAP.md"
    if not codemap_path.exists():
        return None
    try:
        content = codemap_path.read_text(encoding="utf-8")
        if max_tokens and self._estimate_tokens(content) > max_tokens:
            # Trim if budget specified
            from modules.backend.services.code_map.assembler import render_for_agent
            import json
            map_json_path = find_project_root() / ".codemap" / "map.json"
            if map_json_path.exists():
                code_map = json.loads(map_json_path.read_text(encoding="utf-8"))
                content = render_for_agent(code_map, max_tokens)
        return content
    except OSError:
        return None
```

### Step 5: Update Planning Agent system prompt

**File:** `config/prompts/agents/horizontal/planning/system.md`

Add a new section after the existing TaskPlan schema documentation:

```markdown
### Code Map Usage

You receive a Code Map JSON containing the full structural skeleton of the codebase:
modules, classes, functions, signatures, import graph, and PageRank importance scores.

Use the Code Map to:
- **Identify files to include in file_manifest** — look up exact file paths and understand what each module contains
- **Trace dependencies** — use the `import_graph` to find which files depend on the files being modified, and include them in `read_first`
- **Assess task complexity** — modules with high PageRank scores are architectural keystones; changes to them are higher risk
- **Generate precise instructions** — reference exact class names, method signatures, and import paths from the Code Map instead of guessing

### File Manifest (for coding tasks)

When generating tasks for coding agents (agents that create or modify files), you MUST include a `file_manifest` in `inputs`:

```json
{
  "inputs": {
    "file_manifest": {
      "read_for_pattern": [
        {"path": "modules/backend/services/note.py", "reason": "Exemplar for service layer pattern"}
      ],
      "read_first": [
        {"path": "modules/backend/services/base.py", "reason": "Base class the new service must extend"},
        {"path": "modules/backend/models/session.py", "reason": "Model this service will query"}
      ],
      "modify": [
        {"path": "modules/backend/services/session.py", "reason": "Add new query method"}
      ]
    },
    "static": { ... },
    "from_upstream": { ... }
  }
}
```

**File manifest rules:**
- `read_for_pattern`: Exemplar file(s) demonstrating the correct coding pattern. Maximum 2 files.
- `read_first`: Files the agent must read to understand current state. Include direct dependencies from the import graph. Maximum 5 files.
- `modify`: Files the agent will create or change. This is the work scope. Maximum 5 files.
- Every `path` must exist in the Code Map. Do not hallucinate file paths.
- The coding agent will read ONLY the files in the manifest. Do not assume it will explore the codebase.
- For non-coding tasks (analysis, health checks, summarization), omit the file_manifest entirely.
```

### Step 6: Update agent config

**File:** `config/agents/horizontal/planning/agent.yaml`

Add to read scope:

```yaml
scope:
  read:
    - "modules/"
    - "config/"
    - "docs/"
    - "CODEMAP.md"
    - ".codemap/"
  write: []
```

### Step 7: Update ContextAssemblerProtocol

**File:** `modules/backend/agents/mission_control/models.py`

Add `code_map_max_tokens` parameter to the protocol:

```python
class ContextAssemblerProtocol(Protocol):
    async def build(
        self,
        project_id: str,
        task_definition: dict,
        resolved_inputs: dict,
        *,
        domain_tags: list[str] | None = ...,
        token_budget: int = ...,
        code_map_max_tokens: int | None = ...,  # NEW
    ) -> dict: ...
```

### Step 8: Update dispatch loop to pass code_map through

**File:** `modules/backend/agents/mission_control/dispatch.py`

The dispatch loop already calls `context_assembler.build()`. The Code Map injection happens inside the Context Assembler (Step 4), so the dispatch loop itself needs minimal changes.

Ensure the assembled context packet's `code_map` key is passed through to the agent. In `_make_agent_executor()` in helpers.py, the resolved_inputs (which includes `project_context` from the assembler) are already serialized into the user message. The `code_map` field from the packet needs to be included:

In dispatch.py, where context is injected into resolved_inputs:

```python
# Existing: injects PCD
assembled_context = await context_assembler.build(
    project_id, task_def_dict, resolved_inputs,
    domain_tags=task.domain_tags,
)
resolved_inputs["project_context"] = assembled_context.get("project_context", {})

# NEW: inject Code Map separately so it's clearly labeled
code_map_content = assembled_context.get("code_map")
if code_map_content:
    resolved_inputs["code_map"] = code_map_content
```

## File Inventory

| File | Action | Change |
|------|--------|--------|
| `modules/backend/schemas/task_plan.py` | MODIFY | Add FileManifestEntry, FileManifest, file_manifest field on TaskInputs (~20 lines) |
| `modules/backend/agents/horizontal/planning/agent.py` | MODIFY | Add code_map to PlanningAgentDeps (~3 lines) |
| `modules/backend/agents/mission_control/helpers.py` | MODIFY | Load Code Map, staleness check, inject into planning prompt (~80 lines) |
| `modules/backend/services/context_assembler.py` | MODIFY | Add Layer 3 Code Map loading, _is_coding_task, _load_code_map_markdown (~40 lines) |
| `config/prompts/agents/horizontal/planning/system.md` | MODIFY | Add Code Map usage and file manifest instructions (~40 lines) |
| `config/agents/horizontal/planning/agent.yaml` | MODIFY | Add CODEMAP.md and .codemap/ to read scope (~3 lines) |
| `modules/backend/agents/mission_control/models.py` | MODIFY | Add code_map_max_tokens to ContextAssemblerProtocol (~1 line) |
| `modules/backend/agents/mission_control/dispatch.py` | MODIFY | Pass code_map from assembled context to resolved_inputs (~4 lines) |

## Execution Order

Steps 1-8 can largely be done in order because they build on each other:

1. **Step 1** (TaskPlan schema) — no dependencies, pure schema addition
2. **Step 5** (system prompt) — no code dependencies, can be written alongside Step 1
3. **Step 2** (PlanningAgentDeps) — depends on Step 1 conceptually
4. **Step 3** (helpers.py) — depends on Step 2, this is the main integration work
5. **Step 4** (Context Assembler) — independent of Steps 2-3, can be done in parallel
6. **Step 6** (agent config) — trivial, do anytime
7. **Step 7** (protocol) — do with Step 4
8. **Step 8** (dispatch loop) — depends on Steps 4 and 7

## Success Criteria

1. Planning Agent receives the full Code Map JSON in its prompt and uses it to generate file manifests
2. Context Assembler injects Code Map Markdown into coding agent context as Layer 3
3. Staleness check regenerates the Code Map when commit hash doesn't match HEAD
4. TaskPlan schema validates file_manifest entries (path + reason)
5. Non-coding tasks (domain_tags without code-related tags) do NOT receive the Code Map in context
6. File manifest paths reference real files from the Code Map (Planning Agent is instructed to validate)
7. Coding agent receives `code_map` and `project_context` in its resolved_inputs
8. End-to-end: a mission that includes a coding task produces a TaskPlan with file_manifest, and the coding agent receives both the file manifest and the Code Map Markdown

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Full Code Map JSON (~77K tokens) exceeds Planning Agent context | Planning fails or is truncated | Opus 4.6 has 200K input context. 77K is well within budget. Monitor and add trim_by_rank() only if needed. |
| Full Markdown (~31K tokens) crowds out other context for coding agents | History or inputs trimmed too aggressively | Context Assembler has layered priority. Code Map is Layer 3 (high priority). History (Layer 2) is trimmed first. If still an issue, add code_map_max_tokens parameter. |
| Staleness check adds latency | Slower mission dispatch | `git rev-parse HEAD` is <10ms. Code Map regeneration is <5s. Only happens when stale. |
| .codemap/map.json doesn't exist | Planning Agent runs without Code Map | Graceful fallback: log warning, skip Code Map injection. Planning still works, just without structural context. |
| Planning Agent generates invalid file_manifest paths | Coding agent reads nonexistent files | Agent instructions explicitly say paths must exist in Code Map. Verification pipeline can add a check. |
| Code Map JSON is too compact (no indent) to be readable by LLM | Planning Agent misinterprets structure | JSON without indent is fine for LLMs — they parse structure from braces/brackets, not whitespace. Saves ~30% tokens vs indented. |

## What This Does NOT Cover

- **Exemplar Registry** (Component 2 of doc 49) — separate concern, lives in PCD. Implement after this plan.
- **Coding Agent lifecycle enforcement** (doc 49 Phase 6) — the manifest-scoped modification checks belong in the verification pipeline. Separate plan.
- **Code Map storage in database** (doc 49 Phase 2) — file-based storage (`.codemap/map.json`, `CODEMAP.md`) is sufficient for single-repo operation. Database storage is needed for multi-project SaaS; defer until then.
- **Incremental Code Map updates** (doc 49, `previous_map` parameter) — the generator already supports this via file mtime comparison in `parse_modules()`. Not blocking this plan.
- **Quality agent integration** — covered in Plan 19. That plan adds PQI and Code Map as tools for the quality agent. Independent of this plan.
