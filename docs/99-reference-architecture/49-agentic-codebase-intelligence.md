# 49 - Agentic Codebase Intelligence

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-03-10*

## Changelog

- 1.0.0 (2026-03-10): Initial standard — Code Map (tree-sitter + PageRank), Exemplar Registry, Task File Manifest, decomposed generator pipeline, dual-format presentation, coding agent contract extension

---

## Module Status: Recommended (AI-First Profile)

This module is **recommended** for AI-First Platform (BFA) projects that include coding agents — agents that read, create, or modify source code as part of their task execution.

Adopt when your project:
- Uses agents that write or modify code in a repository
- Needs consistent code output without per-task codebase exploration
- Operates on codebases large enough that full-codebase loading is impractical (>20 files)
- Uses a Planning Agent that generates file-level task instructions

**Dependencies**: This module requires **48-agentic-project-context.md** (PCD, context assembly, agent contract), **47-agentic-module-organization.md** (tool architecture), and **40-agentic-architecture.md** (orchestration patterns). It extends doc 48's context assembly with a new layer and extends the agent contract with a coding-specific lifecycle.

---

## Purpose

This document defines the standard architecture for **codebase intelligence** — the system that gives ephemeral coding agents fast, precise structural awareness of a codebase without requiring exploration, embedding-based retrieval, or full-codebase loading.

An ephemeral coding agent spins up, executes one task, and exits. Without codebase intelligence, it must explore the file tree, read files speculatively, and discover patterns through trial and error. This exploration burns tokens, adds latency, produces non-deterministic results, and scales poorly as codebases grow.

Codebase intelligence eliminates exploration. It provides three capabilities that a senior developer has internalized:

1. **Spatial memory** — knowing what exists and where, without looking
2. **Pattern memory** — knowing how things are done, without re-reading
3. **Scope intuition** — knowing which files matter for a given task, without searching

These are provided by three components: the **Code Map**, the **Exemplar Registry**, and the **Task File Manifest**. Together they replace undirected exploration with targeted, pre-computed navigation.

---

## The Problem

The Project Context Document (PCD, defined in 48-agentic-project-context.md) tells an agent *about* the architecture — component purposes, conventions, file locations. This is necessary but insufficient for coding tasks. To write correct code, an agent needs:

| Need | What the PCD provides | What's missing |
|------|----------------------|----------------|
| Exact field syntax | Convention descriptions | Actual syntax from the codebase |
| Import paths | "Absolute imports only" | The real import paths to use |
| Base class interface | "Services extend BaseService" | BaseService's constructor signature, method patterns |
| File locations | "Models in modules/backend/models/" | Which model files exist, what classes they contain |
| Related files | "Layered architecture" | The dependency graph showing which files depend on which |
| Naming conventions | "snake_case" | That repositories use `list_by_x()` not `find_x()` |

The PCD is a map. The agent needs the terrain. But loading the entire terrain (full codebase) is impractical — a 50,000-line codebase won't fit in a context window, and 95% of it is irrelevant to any given task.

### Why Not Embeddings/RAG for Code?

Code has properties that make structured approaches superior to semantic retrieval:

| Property | Implication |
|----------|-------------|
| Code has explicit structure | A function signature tells you its interface exactly. You don't need similarity search — you need to know it exists and where it is. |
| Code has exact patterns | A coding agent needs the exact pattern to replicate, not "similar" files. One exemplar is worth 100 retrieved snippets. |
| Code has dependency graphs | "What imports what" is a deterministic fact derivable from AST parsing, not a similarity search result. |
| Precision is absolute | A 90% relevant code snippet produces broken code. An exact pattern from an exemplar produces working code. |
| Code changes constantly | Re-embedding after every commit is expensive. Regenerating a structural map takes milliseconds (incremental), costs nothing. |

Embeddings may have a role for very large codebases (100K+ lines) where the Code Map alone is insufficient. But for the primary use case — giving a coding agent enough context to execute a well-defined task — structured approaches are faster, cheaper, more precise, and more maintainable.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CODEBASE INTELLIGENCE                           │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  CODE MAP                                                    │    │
│  │  Auto-generated structural skeleton of the codebase.         │    │
│  │  Every module, class, function — with signatures, not bodies.│    │
│  │  Ranked by PageRank. Updated on every commit.                │    │
│  │  ~3-5K tokens.                                               │    │
│  │                                                              │    │
│  │  Gives: SPATIAL MEMORY                                       │    │
│  │  Answers: "What exists and where is it?"                     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  EXEMPLAR REGISTRY                                           │    │
│  │  For each component type: one canonical reference file.      │    │
│  │  Stored in PCD architecture.components section.              │    │
│  │  Agent-maintained — updated when better examples emerge.     │    │
│  │  ~1K tokens (references only, not file contents).            │    │
│  │                                                              │    │
│  │  Gives: PATTERN MEMORY                                       │    │
│  │  Answers: "What does correct code look like?"                │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  TASK FILE MANIFEST                                          │    │
│  │  Per-task list of files the agent needs, pre-computed by     │    │
│  │  the Planning Agent using Code Map + PCD.                    │    │
│  │  Embedded in task instructions as inputs.static.             │    │
│  │  ~500 tokens.                                                │    │
│  │                                                              │    │
│  │  Gives: SCOPE INTUITION                                      │    │
│  │  Answers: "Which files do I need for THIS task?"             │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### How They Work Together

```
Planning Agent (runs once per mission)
    │
    │  Inputs:
    │    - PCD (architecture, conventions, exemplars)
    │    - Code Map JSON (ranked skeleton, import graph, PageRank scores)
    │    - Mission objective
    │
    │  Outputs:
    │    - TaskPlan with precise instructions
    │    - file_manifest per task (which files to read, which to modify)
    │    - References to exemplars in task instructions
    │
    ▼
Context Assembler (deterministic, per-task)
    │
    │  Builds context packet:
    │    Layer 0: PCD                      ~4K tokens  (from doc 48)
    │    Layer 1: Task definition           ~2K tokens  (from doc 48)
    │    Layer 3: Code Map (Markdown tree)  ~3K tokens  (THIS STANDARD)
    │    Layer 2: History (if budget)       ~2K tokens  (from doc 48)
    │
    ▼
Coding Agent (runs per-task)
    │
    │  Step 1: Read file_manifest.read_for_pattern  → see the pattern
    │  Step 2: Read file_manifest.read_first         → understand current state
    │  Step 3: Write changes to file_manifest.modify → execute the task
    │  Step 4: Return output + context_updates
    │
    │  Total file reads: 3-5 (not 50)
    │  Exploration tokens: ~0 (everything pre-computed)
    │
    ▼
Result
```

The intelligence is **front-loaded into the Planning Agent**. It runs once per mission with full architectural context. It produces task instructions so precise that the coding agent barely needs to explore. This is more cost-effective and more reliable than having every coding agent independently discover the codebase.

---

## Component 1: Code Map

### What It Is

A deterministic, auto-generated structural skeleton of the codebase. It contains every module, class, and function — with signatures, types, and relationships — but no implementation bodies, no comments, no docstrings. Symbols are **ranked by importance** using PageRank on the dependency graph, so the most-referenced symbols survive token budget cuts. It is a table of contents, not a textbook.

### What It Is Not

- Not embeddings. No vector store. No similarity search.
- Not LLM-generated. No AI calls. Pure tree-sitter parsing (language-native `ast` fallback).
- Not a full dump of the codebase. Signatures only, ranked by importance.
- Not manually maintained. Auto-generated on every commit (incrementally).

### Storage Schema (JSON)

The Code Map is **stored** as JSON for programmatic access by the Context Assembler, Planning Agent, and CLI tooling. Agents receive a more token-efficient Markdown tree format (see Presentation Format below).

```json
{
  "project_id": "<string>",
  "commit": "<git commit hash>",
  "generated_at": "<ISO 8601 timestamp>",
  "generator_version": "<semver>",

  "modules": {
    "<relative file path>": {
      "lines": "<integer — total line count>",
      "rank": "<float — PageRank score, 0.0 to 1.0>",
      "imports": ["<module path>"],
      "classes": {
        "<ClassName>": {
          "bases": ["<base class names>"],
          "fields": ["<field_name>: <type annotation>"],
          "methods": ["<method_name>(<param>: <type>, ...) -> <return_type>"],
          "rank": "<float — PageRank score for this class>"
        }
      },
      "functions": {
        "<function_name>": {
          "params": ["<param>: <type>"],
          "returns": "<return type>",
          "decorators": ["<decorator name>"],
          "rank": "<float — PageRank score for this function>"
        }
      },
      "constants": ["<CONSTANT_NAME>: <type>"]
    }
  },

  "import_graph": {
    "<source module path>": ["<imported module path>"]
  },

  "stats": {
    "total_files": "<integer>",
    "total_lines": "<integer>",
    "total_classes": "<integer>",
    "total_functions": "<integer>"
  }
}
```

Implementations may extend this schema with language-specific fields but must not remove or rename the fields shown above.

### Presentation Format (Markdown Tree)

When the Code Map is included in an agent's context window, it is rendered as a **Markdown tree** — not raw JSON. This format is ~15% more token-efficient than JSON and matches LLM training distributions (GitHub READMEs, documentation).

Symbols are ordered by PageRank score (highest first). Low-ranked symbols that exceed the token budget are elided with `⋮...` markers, signaling to the agent that more exists but was trimmed for budget.

```
src/services/base.py (85 lines):
│class BaseService:
│    def __init__(session: AsyncSession) -> None
│    def factory() -> AsyncGenerator[BaseService, None]
⋮...

src/models/base.py (50 lines):
│class Base(DeclarativeBase):
│class UUIDMixin:
│    id: Mapped[str]
│class TimestampMixin:
│    created_at: Mapped[datetime]
│    updated_at: Mapped[datetime]

src/repositories/base.py (117 lines):
│class BaseRepository(Generic[ModelType]):
│    model: type[ModelType]
│    def __init__(session: AsyncSession) -> None
│    def get_by_id(id: str | UUID) -> ModelType
│    def create(**kwargs: Any) -> ModelType
│    def update(id: str | UUID, **kwargs: Any) -> ModelType
│    def delete(id: str | UUID) -> None
⋮...
```

**Rendering rules:**

1. Files are ordered by PageRank (most-connected files first)
2. Within a file, classes are ordered by rank, then methods by rank
3. `⋮...` indicates elided content (low-rank symbols trimmed for budget)
4. `self` parameter is omitted from method signatures (agents know it's there)
5. Long parameter lists show the first 3 params then `...`
6. The import graph is NOT rendered in the Markdown tree — it exists only in the stored JSON for the Planning Agent

### Dual-Format Strategy

The Code Map is stored once (JSON) and presented differently to different consumers:

| Consumer | Format | Reason |
|----------|--------|--------|
| Planning Agent | JSON | Needs programmatic access to import graph, rank scores, symbol data for generating file manifests |
| Coding Agent | Markdown tree | Needs spatial awareness, not programmatic access. ~15% fewer tokens. |
| CLI / scripts | Either | JSON for tooling, Markdown for human display |

### Properties

| Property | Value |
|----------|-------|
| Size | Target 3-5K tokens (rendered Markdown). Hard cap 8K tokens. |
| Parser | **tree-sitter** (primary). Language-native `ast` module as fallback when tree-sitter is unavailable. |
| Ranking | PageRank on the cross-reference graph. Symbols referenced more frequently from more files rank higher. |
| Storage format | JSON (for programmatic access). |
| Presentation format | Markdown tree (for agent context windows). |
| Generation | Deterministic. No LLM calls. tree-sitter for parsing, PageRank for ranking. |
| Update trigger | Git post-commit hook, or on-demand before mission planning. Incremental parsing means only changed files are re-parsed. |
| Generation time | <1 second for a typical project (<100 files). <5 seconds for large projects (<1000 files). Incremental updates: <100ms. |
| Scope | Only files within the PCD's `identity.repo_structure` paths. Excludes tests, migrations, config, vendored code by default. Scope is configurable per project. |
| Staleness | Maximum acceptable staleness: the current git commit. If the code map commit doesn't match HEAD, regenerate before planning. |

### What to Include

| Include | Exclude |
|---------|---------|
| Module file paths (relative to repo root) | File contents / method bodies |
| Class names and base classes | Docstrings and comments |
| Class field names with type annotations | Default values |
| Method/function names with full signatures (params + return types) | Method bodies / implementation logic |
| Decorators on functions (names only) | Decorator arguments |
| Module-level constants with types | Constant values |
| Import statements (for dependency graph) | Conditional imports inside functions |
| File line counts | File modification timestamps |
| Enum values (names only) | Enum value strings |

### Size Management

Size management uses **PageRank-based trimming first**, then mechanical passes as fallback. This ensures the most-referenced, most-connected symbols always survive budget cuts.

#### Primary: PageRank Trimming

After generating the full Code Map with rank scores:

1. **Sort all symbols** (classes, functions, methods) by their PageRank score, descending.
2. **Render the Markdown tree** starting from the highest-ranked symbols.
3. **Stop adding symbols** when the token budget is reached.
4. **Insert `⋮...` markers** where content was elided, preserving structural context (the file and class still appear, but low-ranked methods within them are omitted).

This naturally keeps the most important symbols — base classes, core models, primary services — and drops obscure utilities that nothing references.

#### Fallback: Mechanical Passes

If PageRank trimming alone cannot meet the budget (e.g., many equally-ranked symbols), apply these passes in order:

1. **Scope filtering** — Only include modules within the PCD's `identity.repo_structure` paths.
2. **Depth limiting** — Include only public methods (no leading underscore).
3. **Signature truncation** — For methods with many parameters, include only the first 3 followed by `...`.
4. **Layered maps** — For very large codebases (1000+ files), produce a two-level map:
   - **Summary map** (~3K tokens): one entry per module directory, listing classes and public methods
   - **Detail maps** (~2K tokens each): one per directory, with full signatures
   - The Context Assembler includes the summary map always and the relevant detail map for the task's target directory

### Storage

The Code Map is stored alongside the PCD (defined in 48-agentic-project-context.md). A separate table is recommended because the Code Map updates more frequently than the PCD (every commit vs. every task).

**Required columns:**

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| id | UUID | PK | Unique identifier |
| project_id | UUID | FK → projects, UNIQUE, NOT NULL | Owning project |
| code_map_data | JSON | NOT NULL | The Code Map content |
| commit_hash | VARCHAR(40) | NOT NULL | Git commit at generation time |
| generator_version | VARCHAR(20) | NOT NULL | Generator version for cache invalidation |
| total_files | INTEGER | NOT NULL | File count at generation |
| total_lines | INTEGER | NOT NULL | Line count at generation |
| size_tokens | INTEGER | NOT NULL | Estimated token count |
| created_at | TIMESTAMP | NOT NULL | Creation time |
| updated_at | TIMESTAMP | NOT NULL | Last regeneration time |

### Triggering

| Trigger | Mechanism |
|---------|-----------|
| Git commit | Post-commit hook. Incremental parsing means only changed files are re-parsed (<100ms). |
| Before mission planning | The dispatch adapter checks if the code map commit matches HEAD. If not, regenerates. |
| CLI command | CLI command to regenerate and display the Code Map (Markdown tree format). |
| On project creation | Generated as part of initial project setup alongside the seed PCD. |

---

## Component 2: Exemplar Registry

### What It Is

A curated set of references to canonical files that demonstrate the correct pattern for each component type. Stored in the PCD's `architecture.components` section. Not the file contents — just the file path, the component type, and a one-line pattern description.

When a coding agent needs to create a new component, it reads exactly one file — the exemplar — and has a complete, working pattern to follow. No exploration. No guessing. No inconsistency.

### Schema

The Exemplar Registry extends the PCD's `architecture.components` with two optional fields per component:

```json
{
  "architecture": {
    "components": {
      "<component_key>": {
        "purpose": "<string — what this component type does>",
        "key_files": ["<relative paths to important files>"],
        "interfaces": ["<key function/class names>"],
        "exemplar": "<relative path to the canonical example file>",
        "pattern": "<string — one-line description of the pattern to follow>"
      }
    }
  }
}
```

The `exemplar` and `pattern` fields are the additions from this standard. The other fields (`purpose`, `key_files`, `interfaces`) are defined in 48-agentic-project-context.md.

### Properties

| Property | Value |
|----------|-------|
| Storage | Inside the PCD (`architecture.components` entries) |
| Size | ~1K tokens for references. The files themselves are read on-demand by the agent. |
| Maintenance | Agent-maintained. When a coding agent creates a particularly clean implementation, it proposes updating the exemplar reference via context_updates. |
| Selection criteria | The exemplar should be a real, working file in the codebase that best demonstrates the standard pattern. Complete (not a stub), readable (not too complex), representative (not an edge case). |
| Validation | The **PCD validation layer** verifies that all exemplar paths exist on disk. Missing or stale exemplars are flagged as warnings during PCD validation (not during Code Map generation — the generator has no knowledge of exemplars). Validation is triggered on PCD load and before mission planning. |

### How the Agent Uses Exemplars

When a coding agent receives a task to create a new component:

1. The task instructions reference the exemplar: "Create a new service following the pattern in the services exemplar (see PCD)."
2. The agent reads the exemplar file. It sees the exact imports, class structure, method signatures, and conventions.
3. The agent writes the new file following the same pattern, adapted for the new domain.

This produces **consistent code** across the codebase without relying on the agent to infer patterns from descriptions.

### Exemplar Evolution

Exemplars are not static. They evolve as the codebase improves:

1. **Initial population** — The first "project discovery" mission (or a human) sets the initial exemplars when populating the PCD.
2. **Agent updates** — A coding agent that creates a cleaner implementation can propose an update via context_updates:
   ```json
   {
     "op": "replace",
     "path": "architecture.components.services.exemplar",
     "value": "src/services/project.py",
     "reason": "project.py demonstrates the pattern more cleanly"
   }
   ```
3. **Staleness detection** — If the Code Map shows an exemplar file has been deleted or significantly refactored (line count changed by >50%), the PCD validation layer flags it for review.

---

## Component 3: Task File Manifest

### What It Is

A per-task list of files the coding agent needs, pre-computed by the Planning Agent during task plan generation. It tells the agent exactly which files to read and which to modify — eliminating exploration entirely.

### Schema

The file manifest is embedded in the task's `inputs.static` field within the TaskPlan:

```json
{
  "inputs": {
    "static": {
      "file_manifest": {
        "read_for_pattern": [
          {
            "path": "<relative file path>",
            "reason": "<why this file is needed>"
          }
        ],
        "read_first": [
          {
            "path": "<relative file path>",
            "reason": "<why this file is needed>"
          }
        ],
        "modify": [
          {
            "path": "<relative file path>",
            "reason": "<what change is needed>"
          }
        ]
      }
    }
  }
}
```

### File Manifest Fields

| Field | Purpose | Required |
|-------|---------|----------|
| `read_for_pattern` | Files to read to understand the coding pattern. Typically the exemplar or a closely related file. Read first to internalize the pattern before starting work. | Optional. Omit if the task doesn't involve creating new code. |
| `read_first` | Files to read to understand the current state of the code that will be changed. | Required for all coding tasks. |
| `modify` | Files that the agent will create or modify. This is the agent's work scope. | Required for all coding tasks. |

Each entry has:
- `path` — relative file path from repo root
- `reason` — why this file is in the manifest (helps the agent prioritize)

### How the Planning Agent Generates File Manifests

The Planning Agent uses the PCD (architecture, exemplars) and the Code Map (structure, import graph) to derive the file manifest:

1. **Identify the target component type** — from the task description, determine which architecture component is involved.
2. **Look up the exemplar** — from `PCD.architecture.components[type].exemplar`. This goes in `read_for_pattern`.
3. **Identify target files** — from the Code Map, find the files to modify. These go in `modify`.
4. **Trace dependencies** — from the Code Map's `import_graph`, find files that the targets depend on or that depend on them. These go in `read_first`.
5. **Minimize the list** — remove duplicates. Target: 3-8 files total.

### Size Constraints

| Constraint | Value |
|------------|-------|
| Maximum files in `read_for_pattern` | 2 |
| Maximum files in `read_first` | 5 |
| Maximum files in `modify` | 5 |
| Maximum total files in manifest | 10 |
| Target total files | 3-6 |

If a task requires modifying more than 5 files, the Planning Agent should split it into multiple tasks.

---

## The Code Map Generator

### What It Is

A deterministic tool that parses the codebase using **tree-sitter** (with language-native `ast` fallback), builds a cross-reference graph, ranks symbols by PageRank, and produces the Code Map JSON. No LLM calls. Runs in milliseconds to seconds. Supports incremental re-parsing.

### Location

The generator is a **tool** (not an agent), following the tool organization defined in 47-agentic-module-organization.md. It lives alongside other shared tools.

### Dependencies

```
py-tree-sitter            # tree-sitter bindings
tree-sitter-<language>    # Language grammar (e.g., tree-sitter-python)
```

If tree-sitter is unavailable (missing native dependency), the generator falls back to the language's built-in AST module (e.g., Python's `ast`). The fallback produces identical output but without incremental parsing or error tolerance.

### Decomposed Interface

The generator is decomposed into **typed stage functions** — one per pipeline stage plus a top-level orchestrator. Each stage has a typed input and output, so stages can be tested, reused, and composed independently.

```
┌──────────────┐     ┌───────────────────────┐     ┌──────────────┐     ┌──────────────────┐
│ parse_modules │────▶│ build_reference_graph  │────▶│ rank_symbols │────▶│ assemble_code_map│
│               │     │                       │     │              │     │                  │
│ list[Module   │     │ ReferenceGraph        │     │ dict[str,    │     │ dict             │
│    Info]      │     │ (nodes + typed edges) │     │    float]    │     │ (Code Map JSON)  │
└──────────────┘     └───────────────────────┘     └──────────────┘     └──────────────────┘

generate_code_map() orchestrates all four stages.
```

**Required data types** between stages:

| Type | Purpose |
|------|---------|
| `SymbolInfo` | A single symbol (class, function, method, constant) with name, kind, qualified name, params, return type, bases, fields, methods, decorators |
| `ModuleInfo` | Parsed structure of a single module: path, lines, imports, classes, functions, constants |
| `ReferenceEdge` | A directed reference: source qualified name → target qualified name, with kind (import, call, inherit, type_annotation) |
| `ReferenceGraph` | Directed graph: list of node qualified names + list of ReferenceEdge |

**Required functions:**

| Function | Stage | Input | Output |
|----------|-------|-------|--------|
| `parse_modules()` | 1: Parse | repo_root, scope, exclude, previous_modules | list[ModuleInfo] |
| `build_reference_graph()` | 2: Graph | list[ModuleInfo] | ReferenceGraph |
| `rank_symbols()` | 3: Rank | ReferenceGraph, damping | dict[str, float] |
| `assemble_code_map()` | 4: Output | list[ModuleInfo], ranks, repo_root | dict (Code Map) |
| `generate_code_map()` | Orchestrator | repo_root, scope, exclude, max_tokens, previous_map | dict (Code Map) |
| `trim_by_rank()` | Presentation | code_map, max_tokens | dict (trimmed Code Map) |
| `render_markdown_tree()` | Presentation | code_map | str (Markdown tree) |
| `render_for_agent()` | Convenience | code_map, max_tokens | str (trimmed + rendered) |

**Key design constraint:** `trim_by_rank()` and `render_markdown_tree()` are separate functions. Trimming (deciding what to keep) is independent of rendering (formatting the output). This allows:
- Trimming without rendering (e.g., producing reduced JSON for the Planning Agent)
- Rendering without trimming (e.g., full output for debugging or CLI display)
- `render_for_agent()` composes both as a convenience

**Incremental updates:** `generate_code_map()` accepts an optional `previous_map` parameter. When provided, `parse_modules()` reuses cached ModuleInfo for files whose mtime has not changed. This enables <100ms post-commit updates.

### Parsing Pipeline

#### Stage 1: Parse

For each source file in scope:

1. **Parse with tree-sitter** using the language grammar. tree-sitter is error-tolerant — files with syntax errors produce partial trees rather than failures. If unavailable, fall back to the language's built-in AST parser.

2. **Extract definitions** (classes, functions, methods, fields, constants, enums).

3. **Extract references** (which symbols each file/class/function references — used in Stage 2).

4. **Extract imports** for the dependency graph.

#### Stage 2: Build Cross-Reference Graph

Construct a directed graph where:
- **Nodes** are symbols (modules, classes, functions)
- **Edges** are references (file A's class calls file B's function → edge from A to B)

This graph captures not just import relationships but **usage relationships**. The import graph is a subset — it captures module-level dependencies. The cross-reference graph captures symbol-level dependencies.

Sources for edges:
- Import statements (module → module)
- Function/method calls (caller → callee, resolved via import context)
- Class inheritance (subclass → base class)
- Type annotations referencing other classes

External symbols (stdlib, third-party) are excluded from the graph.

##### Cross-Reference Resolution Boundary

tree-sitter provides syntax, not semantics. The generator can resolve some references statically and cannot resolve others. This boundary is explicit — **unresolved references are dropped, not guessed**.

| Resolvable (static) | Not resolvable (requires type inference) |
|---------------------|------------------------------------------|
| `from x.y import Z` → Z is in module x.y | `self.repo.create()` → which class is `self.repo`? |
| `class Foo(Base)` → Foo inherits Base | `items = get_items(); items.filter()` → what type is `items`? |
| `field: SomeType` → type annotation references SomeType | `callback(handler)` → what does `handler` resolve to? |
| `ClassName.method()` → explicit class reference | `getattr(obj, name)()` → dynamic dispatch |
| Top-level function calls: `validate(x)` | Closures, decorators that return different types |

**Resolution strategy:** For each reference, attempt to resolve against the import table of the current module. If it matches an imported name (or a locally defined name), create an edge. Otherwise, drop it silently. This is conservative — it under-counts references rather than creating false edges. Under-counting is safe: it slightly underweights some symbols in PageRank but never creates spurious importance.

#### Stage 3: Rank with PageRank

Run PageRank on the cross-reference graph:
- Symbols referenced more frequently from more files get higher scores
- Symbols in highly-connected files propagate their importance to what they reference
- Damping factor: 0.85 (standard PageRank default)
- Scores are normalized to 0.0–1.0 range

**Why PageRank over reference count?** Reference count ranks utility functions highest (called everywhere) but misses architectural keystones. PageRank captures that a base class is important not because it's called a lot, but because important things inherit from it. A reference from an important symbol matters more than a reference from an obscure one.

#### Stage 4: Output

Produce the JSON Code Map with rank scores on all symbols. Apply token budgeting via `trim_by_rank()` if the result exceeds `max_tokens`.

### Token Budgeting

**Primary: Rank-based trimming** — Sort all symbols by PageRank descending. Remove lowest-ranked until budget is met.

**Fallback passes** (if rank-based trimming alone is insufficient):

1. Remove private methods (leading `_`) from all classes
2. Truncate method signatures with >3 parameters to `(p1: T1, p2: T2, p3: T3, ...)`
3. Remove `constants` arrays from all modules
4. Remove `imports` arrays (import_graph still preserved)
5. Remove modules with fewer than 20 lines (trivial files)

If still over budget after all passes, remove the lowest-ranked files.

---

## Integration with Context Assembly

This standard extends doc 48's Context Assembly with a new layer:

```
Context Assembly Priority Order:

  Priority 1 (never trimmed):  Layer 0 — PCD                    ~4K tokens  (doc 48)
  Priority 2 (never trimmed):  Layer 1 — Task definition         ~2K tokens  (doc 48)
  Priority 3 (high):           Layer 3 — Code Map                ~3K tokens  (THIS STANDARD)
  Priority 4 (high):           Layer 1 — Upstream outputs         ~2K tokens  (doc 48)
  Priority 5 (normal):         Layer 2 — History                  ~2K tokens  (doc 48)
```

The Code Map is loaded for tasks with code-related `domain_tags`. It is omitted for non-coding tasks (analysis, summarization, review).

### Assembly Logic

```python
# Extension to ContextAssembler.build() from doc 48:

# Layer 3: Code Map (for coding tasks)
if self._is_coding_task(task_definition):
    code_map_json = await self._load_code_map(project_id)
    if code_map_json:
        trimmed = trim_by_rank(code_map_json, max_tokens=remaining_budget)
        rendered = render_markdown_tree(trimmed)
        rendered_tokens = _estimate_tokens(rendered)
        packet["code_map"] = rendered
        remaining_budget -= rendered_tokens
```

The Planning Agent receives the **stored JSON** (not Markdown) — it needs programmatic access to the import graph and rank scores. It may also use `trim_by_rank()` independently if the JSON exceeds its budget.

---

## Integration with Planning Agent

The Planning Agent's prompt is extended to include:

1. **The Code Map (JSON)** — for file manifests generation using import graph and rank scores.
2. **The Exemplar Registry** — for pointing coding agents to pattern files.
3. **Instruction to generate file manifests** — the prompt explicitly requires `file_manifest` in `inputs.static` for coding tasks.

### Required Planning Agent Prompt Addition

```
When generating tasks for coding agents, you MUST include a file_manifest
in inputs.static with three sections:

- read_for_pattern: The exemplar file(s) from the PCD that demonstrate
  the correct coding pattern. Maximum 2 files.

- read_first: Files the agent must read to understand the current state
  of the code it will modify. Include direct dependencies from the
  import graph. Maximum 5 files.

- modify: Files the agent will create or change. This defines the work
  scope. Maximum 5 files.

Each entry must have a path and a reason explaining why it's needed.

Use the Code Map to identify file paths, class names, and method signatures.
Use the PCD exemplar registry to find the correct pattern file for each
component type.

The coding agent will read ONLY the files in the manifest. Do not assume
it will explore the codebase. Every file it needs must be listed.
```

---

## Coding Agent Contract Extension

This standard extends the Agent Contract from doc 48 with a coding-specific lifecycle.

### Coding Agent Lifecycle

```
┌──────────────────────────────────────────────────────────────────┐
│              CODING AGENT LIFECYCLE                               │
│                                                                  │
│  1. RECEIVE CONTEXT                                              │
│     ├── PCD (always — Layer 0)                                   │
│     ├── Task definition with file_manifest (Layer 1)             │
│     ├── Code Map (Layer 3 — ranked Markdown tree)                │
│     └── History (Layer 2 — if budget allows)                     │
│                                                                  │
│  2. READ PATTERN                                                 │
│     └── Read file_manifest.read_for_pattern files                │
│         Internalize the coding pattern before writing anything.  │
│                                                                  │
│  3. READ CONTEXT                                                 │
│     └── Read file_manifest.read_first files                      │
│         Understand the current state of the code to be changed.  │
│                                                                  │
│  4. EXECUTE                                                      │
│     └── Create or modify file_manifest.modify files              │
│         Follow the pattern from step 2.                          │
│         Stay within the modify list — no unscoped changes.       │
│                                                                  │
│  5. RETURN RESULTS                                               │
│     ├── output_reference (files created/modified, diffs)         │
│     └── context_updates (PCD patches — may include exemplar      │
│         updates if the new code is a better pattern example)     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Coding Agent Rules

1. **Read the manifest files before writing any code.** The agent must not start writing until it has read all `read_for_pattern` and `read_first` files.

2. **Stay within the modify scope.** The agent should only create or modify files listed in `file_manifest.modify`. If the task requires changes to additional files, the agent should report this in its output rather than making unscoped changes.

3. **Follow the exemplar pattern exactly.** Import style, class structure, method naming, error handling — all should match the exemplar. Consistency is more valuable than local optimization.

4. **Use the Code Map for navigation.** If the agent needs to understand a class or function not in the manifest, check the Code Map first. Only read additional files if the Code Map's signature information is insufficient.

5. **Propose exemplar updates.** If the agent creates code that is cleaner or more complete than the current exemplar, include an exemplar update in context_updates.

---

## Comparison with Existing Approaches

| Approach | Token Cost | Freshness | Precision | Exploration Required | Assessment |
|----------|-----------|-----------|-----------|---------------------|------------|
| CLAUDE.md / AGENTS.md | Low | Goes stale quickly | Manual maintenance | Still needs exploration | PCD replaces this |
| Codebase embeddings (RAG) | High to build | Minutes stale | Fuzzy — 10%+ irrelevant | Reduced but not eliminated | Wrong tool for code structure |
| Aider repo map (tree-sitter + PageRank) | Low (~3K tokens) | Auto-updated | Structural, ranked | Reduced | We adopt tree-sitter + PageRank, extend with exemplars and manifests |
| MCP-based exploration | Per-query cost | Always fresh | High if queries are good | Agent-driven | Wrong model for autonomous dispatch (latency, non-determinism) |
| Full codebase loading | Very high | Always fresh | Exact | None | Doesn't scale beyond ~20K lines |
| File-by-file reading | High per-task | Always fresh | Exact per-file | Maximum | Necessary but must be targeted |
| **Code Map + Exemplar + Manifest** | **Medium (~4K tokens)** | **Auto-updated (incremental)** | **High — ranked signatures + exact patterns** | **Near zero — pre-computed** | **Best for autonomous dispatch** |

---

## Failure Modes and Mitigations

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Code Map is stale (commit mismatch) | Agent works with outdated structure | Dispatch adapter checks commit hash before planning. Regenerate if stale. |
| Exemplar file was deleted or refactored | Agent reads a nonexistent or changed file | PCD validation layer checks exemplar paths. Missing exemplars flagged. Agent falls back to Code Map for pattern inference. |
| File manifest is incomplete | Agent needs a file not in the manifest | Agent uses Code Map to find additional files. Manifest is guidance, not a hard constraint. Agent reports unscoped reads. |
| File manifest is wrong (hallucinated path) | Agent tries to read a nonexistent file | Agent validates manifest paths against Code Map. Invalid paths skipped with warning. |
| tree-sitter unavailable | Cannot use primary parser | Fall back to language-native AST module. Identical output but no incremental parsing or error tolerance. |
| Code Map exceeds token budget | Bloated context packet | PageRank trimming drops lowest-ranked symbols first. Mechanical passes as fallback. `render_for_agent()` applies independent budget. |
| Agent modifies files outside manifest | Unintended side effects | Verification pipeline checks that only manifest files were modified. Unscoped modifications flagged. |
| Codebase has no parsable files | Code Map is empty | Generator logs a warning. Agent falls back to PCD-only context. File manifest is omitted. |

---

## Relationship to Other Standards

| Standard | Relationship |
|----------|-------------|
| 48-agentic-project-context.md | Exemplar Registry extends the PCD's `architecture.components` schema. Code Map is a companion data structure stored alongside the PCD. Context Assembly gains Layer 3. Agent Contract gains coding-specific lifecycle. Exemplar validation belongs to the PCD validation layer. |
| 47-agentic-module-organization.md | The Code Map Generator is a **tool** (not an agent), following the shared tool architecture defined there. |
| 40-agentic-architecture.md | The Planning Agent and Coding Agent roles extend the orchestration model. File manifests extend TaskPlan's `inputs.static`. |
| 41-agentic-pydanticai.md | Generator functions are pure (no PydanticAI dependency), callable from agent tools, scripts, and tests. |
| 03-core-backend-architecture.md | Code Map storage table follows the standard data model patterns (service → repository → model). |
| 20-opt-data-layer.md | Storage table uses mapped_column style. Migrations via standard tooling. |

---

## Implementation Sequence

### Phase 1: Code Map Generator

Build the four stage functions (`parse_modules()`, `build_reference_graph()`, `rank_symbols()`, `assemble_code_map()`) and the orchestrator (`generate_code_map()`). Include language-native `ast` fallback. Build the presentation layer (`trim_by_rank()`, `render_markdown_tree()`, `render_for_agent()`). Each stage function is independently testable. Test against the project's own codebase. Add CLI command for generation and display.

**Deliverable:** Code Map can be generated, trimmed, rendered, and stored. Each stage testable in isolation.

**Test:** Does the generator produce valid JSON matching the schema? Does the Markdown tree render correctly with PageRank ordering?

### Phase 2: Storage + Freshness

Add storage table. Wire generation into git post-commit hook and dispatch adapter. Use `previous_map` for incremental updates. Ensure the Code Map is fresh before mission planning.

**Deliverable:** Code Map is automatically maintained. Incremental updates via `previous_map` in <100ms.

**Test:** Does changing one file and regenerating take <100ms? Does the dispatch adapter reject a stale code map?

### Phase 3: Exemplar Registry

Populate the PCD with exemplar references for all component types. Add exemplar path validation to the PCD validation layer.

**Deliverable:** PCD has exemplar references. PCD validation warns on missing or stale exemplars.

**Test:** Does PCD validation flag a deleted exemplar file?

### Phase 4: Planning Agent Integration

Extend the Planning Agent prompt with Code Map (JSON) and exemplar registry. Generate file manifests. Validate manifests against Code Map.

**Deliverable:** TaskPlans include file manifests with rank-informed file selection.

**Test:** Does the Planning Agent produce a valid file_manifest for a coding task?

### Phase 5: Context Assembler Integration

Add Code Map to Context Assembler as Layer 3. Use `trim_by_rank()` + `render_markdown_tree()` for coding agents. Pass JSON to Planning Agent. Token budgeting via rank-ordered elision.

**Deliverable:** Coding agents receive ranked Markdown tree in context (~15% fewer tokens than JSON).

**Test:** Does the context packet include a Code Map for coding tasks and omit it for non-coding tasks?

### Phase 6: Coding Agent Contract

Formalize the coding agent lifecycle. Enforce manifest-scoped modifications in verification. Enable exemplar updates via context_updates.

**Deliverable:** Coding agents follow the manifest, propose exemplar improvements.

**Test:** Is an out-of-scope file modification flagged by verification?

---

## Compliance

This standard is recommended for all AI-First Platform (BFA) projects that include coding agents. Projects with only non-coding agents (analysis, conversation, orchestration) may defer adoption.

When adopted, all six phases should be implemented in order. Phase 1 (generator) is independently valuable even without agent integration — it provides a CLI-accessible structural overview of the codebase.
