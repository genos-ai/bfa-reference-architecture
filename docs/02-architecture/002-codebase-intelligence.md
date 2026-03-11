# Codebase Intelligence

*Version: 1.2.0*
*Author: Architecture Team*
*Created: 2026-03-10*

## Changelog

- 1.2.0 (2026-03-10): Internal decomposition — typed stage interfaces, cross-reference resolution boundary, separated trim/render, incremental update API, moved exemplar validation to PCD layer
- 1.1.0 (2026-03-10): tree-sitter as primary parser, PageRank symbol ranking, Markdown tree presentation format — informed by research on AI-readable code maps (doc 14)
- 1.0.0 (2026-03-10): Initial architecture — Code Map, Exemplar Registry, Task File Manifest, Code Map Generator tool, integration with Context Assembler and Planning Agent

---

## Purpose

This document defines the architecture for **codebase intelligence** — the system that gives ephemeral coding agents fast, precise structural awareness of a codebase without requiring exploration, embedding-based retrieval, or full-codebase loading.

An ephemeral coding agent spins up, executes one task, and exits. Without codebase intelligence, it must explore the file tree, read files speculatively, and discover patterns through trial and error. This exploration burns tokens, adds latency, produces non-deterministic results, and scales poorly as codebases grow.

Codebase intelligence eliminates exploration. It gives every coding agent three things that a senior developer has internalized:

1. **Spatial memory** — knowing what exists and where, without looking
2. **Pattern memory** — knowing how things are done, without re-reading
3. **Scope intuition** — knowing which files matter for a given task, without searching

These are provided by three components: the **Code Map**, the **Exemplar Registry**, and the **Task File Manifest**. Together they replace undirected exploration with targeted, pre-computed navigation.

---

## The Problem

A coding agent receives a task: "Add a `project_id` column to the Mission model and wire it through the repository and service layers."

The Project Context Document (PCD) tells the agent *about* the architecture: "Models use SQLAlchemy with `mapped_column`, services extend `BaseService`, repositories extend `BaseRepository`." This is necessary but insufficient. To write correct code, the agent needs:

| Need | What the PCD provides | What's missing |
|------|----------------------|----------------|
| Exact field syntax | "Uses SQLAlchemy mapped_column" | `mapped_column(String(36), nullable=True, index=True)` |
| Import paths | "Absolute imports only" | `from modules.backend.models.base import Base, UUIDMixin, TimestampMixin` |
| Base class interface | "Services extend BaseService" | `__init__(self, session: AsyncSession)`, `factory()` classmethod pattern |
| File locations | "Models in modules/backend/models/" | Which model files exist, what classes they contain |
| Related files | "Layered architecture" | The import graph showing mission.py depends on base.py |
| Naming conventions | "snake_case" | That repositories use `list_by_x()` not `find_x()` or `query_x()` |

The PCD is a map. The agent needs the terrain. But loading the entire terrain (full codebase) is impractical — a 50,000-line codebase won't fit in a context window, and 95% of it is irrelevant to any given task.

### Why Not Embeddings/RAG for Code?

The semantic retrieval approach (embed the codebase, vector-search for relevant chunks) solves a different problem. It is designed for finding relevant passages across large corpora of unstructured text (documents, knowledge bases). Code has properties that make structured approaches superior:

| Property | Implication |
|----------|-------------|
| Code has explicit structure | A function signature tells you its interface exactly. You don't need similarity search to find `BaseService.__init__` — you need to know it exists and where it is. |
| Code has exact patterns | A coding agent doesn't need "files similar to a service." It needs the exact service pattern to replicate. One exemplar is worth 100 retrieved snippets. |
| Code has dependency graphs | "What imports what" is a deterministic fact derivable from tree-sitter/AST parsing, not a similarity search result. |
| Precision is absolute | A 90% relevant code snippet produces broken code. An exact pattern from an exemplar produces working code. There is no tolerance for noise. |
| Code changes constantly | Re-embedding after every commit is expensive (minutes, dollars). Regenerating a tree-sitter map takes milliseconds (incremental), costs nothing. |

Embeddings may have a role for very large codebases (100K+ lines) where the Code Map alone is insufficient to find distant relationships. But for the primary use case — giving a coding agent enough context to execute a well-defined task — structured approaches are faster, cheaper, more precise, and more maintainable.

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
│  │  Import graph. File sizes. Updated on every commit.          │    │
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
Planning Agent (Opus, runs once per mission)
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
    │    Layer 0: PCD                      ~4K tokens
    │    Layer 1: Task definition           ~2K tokens
    │    Layer 3: Code Map (Markdown tree)  ~3K tokens (ranked, elided)
    │    Layer 2: History (if budget)       ~2K tokens
    │
    ▼
Coding Agent (Sonnet/Haiku, runs per-task)
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

The intelligence is **front-loaded into the Planning Agent**. It runs once per mission on an expensive model (Opus) with full architectural context. It produces task instructions so precise that the coding agent barely needs to explore. This is more cost-effective and more reliable than having every coding agent independently discover the codebase.

---

## Component 1: Code Map

### What It Is

A deterministic, auto-generated structural skeleton of the codebase. It contains every module, class, and function — with signatures, types, and relationships — but no implementation bodies, no comments, no docstrings. Symbols are **ranked by importance** using PageRank on the dependency graph, so the most-referenced symbols survive token budget cuts. It is a table of contents, not a textbook.

### What It Is Not

- Not embeddings. No vector store. No similarity search.
- Not LLM-generated. No AI calls. Pure tree-sitter parsing (Python `ast` fallback).
- Not a full dump of the codebase. Signatures only, ranked by importance.
- Not manually maintained. Auto-generated on every commit (incrementally).

### Storage Schema (JSON)

The Code Map is **stored** as JSON for programmatic access by the Context Assembler, Planning Agent, and CLI tooling. This is the internal representation — agents receive a more token-efficient Markdown tree format (see [Presentation Format](#presentation-format) below).

```json
{
  "project_id": "<string>",
  "commit": "<git commit hash>",
  "generated_at": "<ISO 8601 timestamp>",
  "generator_version": "1.1.0",

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

### Presentation Format (Markdown Tree)

When the Code Map is included in an agent's context window, it is rendered as a **Markdown tree** — not raw JSON. This format is ~15% more token-efficient than JSON (empirically validated: structured Markdown uses ~11,600 tokens where equivalent JSON uses ~13,900) and matches LLM training distributions (GitHub READMEs, documentation).

Symbols are ordered by PageRank score (highest first). Low-ranked symbols that exceed the token budget are elided with `⋮...` markers, signaling to the agent that more exists but was trimmed for budget.

```
modules/backend/models/mission.py (186 lines):
│class MissionState(str, Enum):
│    PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
│class Mission(UUIDMixin, TimestampMixin, Base):
│    playbook_run_id: Mapped[str | None]
│    project_id: Mapped[str | None]
│    objective: Mapped[str]
│    status: Mapped[str]
│    roster_ref: Mapped[str]
⋮...
│    def __repr__() -> str
│class PlaybookRun(UUIDMixin, TimestampMixin, Base):
│    playbook_name: Mapped[str]
│    status: Mapped[str]
⋮...

modules/backend/services/mission.py (422 lines):
│class MissionService(BaseService):
│    def __init__(session: AsyncSession, ...) -> None
│    def factory() -> AsyncGenerator[MissionService, None]
│    def create_mission(objective: str, roster_ref: str, ...) -> Mission
│    def execute_mission(mission_id: str, ...) -> dict
│    def get_mission(mission_id: str) -> Mission
│    def list_missions(limit: int, offset: int, ...) -> list[Mission]
│    def extract_outputs(mission: Mission, ...) -> dict[str, Any]

modules/backend/repositories/base.py (117 lines):
│class BaseRepository(Generic[ModelType]):
│    model: type[ModelType]
│    def __init__(session: AsyncSession) -> None
│    def get_by_id(id: str | UUID) -> ModelType
│    def create(**kwargs: Any) -> ModelType
│    def update(id: str | UUID, **kwargs: Any) -> ModelType
│    def delete(id: str | UUID) -> None
⋮...

modules/backend/models/base.py (50 lines):
│class Base(DeclarativeBase):
│class UUIDMixin:
│    id: Mapped[str]
│class TimestampMixin:
│    created_at: Mapped[datetime]
│    updated_at: Mapped[datetime]
```

**Rendering rules:**

1. Files are ordered by PageRank (most-connected files first)
2. Within a file, classes are ordered by rank, then methods by rank
3. `⋮...` indicates elided content (low-rank symbols trimmed for budget)
4. `self` parameter is omitted from method signatures (agents know it's there)
5. Long parameter lists show the first 3 params then `...`
6. The import graph is NOT rendered in the Markdown tree — it exists only in the stored JSON for the Planning Agent's file manifest generation

The `render_for_agent()` function converts the stored JSON to this format within a token budget:

```python
def render_for_agent(code_map: dict, max_tokens: int = 4000) -> str:
    """Render the Code Map as a Markdown tree for agent context.

    Symbols are ordered by PageRank score. Low-ranked symbols are
    elided with ⋮... markers when the token budget is exceeded.

    Args:
        code_map: The stored JSON Code Map.
        max_tokens: Target token budget for the rendered output.

    Returns:
        Markdown tree string ready for inclusion in agent context.
    """
    ...
```

### Example (Partial)

```json
{
  "commit": "b3e0a6f",
  "generated_at": "2026-03-10T14:00:00Z",
  "generator_version": "1.0.0",

  "modules": {
    "modules/backend/models/base.py": {
      "lines": 50,
      "imports": [
        "sqlalchemy.orm.DeclarativeBase",
        "sqlalchemy.orm.Mapped",
        "sqlalchemy.orm.mapped_column"
      ],
      "classes": {
        "Base": {
          "bases": ["DeclarativeBase"],
          "fields": [],
          "methods": []
        },
        "UUIDMixin": {
          "bases": [],
          "fields": ["id: Mapped[str]"],
          "methods": []
        },
        "TimestampMixin": {
          "bases": [],
          "fields": [
            "created_at: Mapped[datetime]",
            "updated_at: Mapped[datetime]"
          ],
          "methods": []
        }
      },
      "functions": {},
      "constants": []
    },

    "modules/backend/models/mission.py": {
      "lines": 186,
      "imports": [
        "sqlalchemy.Enum",
        "sqlalchemy.Float",
        "sqlalchemy.Integer",
        "sqlalchemy.String",
        "sqlalchemy.Text",
        "sqlalchemy.dialects.sqlite.JSON",
        "modules.backend.models.base.Base",
        "modules.backend.models.base.TimestampMixin",
        "modules.backend.models.base.UUIDMixin"
      ],
      "classes": {
        "MissionState": {
          "bases": ["str", "enum.Enum"],
          "fields": [
            "PENDING: str",
            "RUNNING: str",
            "COMPLETED: str",
            "FAILED: str",
            "CANCELLED: str"
          ],
          "methods": []
        },
        "PlaybookRun": {
          "bases": ["UUIDMixin", "TimestampMixin", "Base"],
          "fields": [
            "playbook_name: Mapped[str]",
            "playbook_version: Mapped[int]",
            "project_id: Mapped[str | None]",
            "status: Mapped[str]",
            "session_id: Mapped[str]",
            "trigger_type: Mapped[str]",
            "triggered_by: Mapped[str]",
            "context: Mapped[dict]",
            "total_cost_usd: Mapped[float]",
            "budget_usd: Mapped[float | None]",
            "started_at: Mapped[str | None]",
            "completed_at: Mapped[str | None]",
            "error_data: Mapped[dict | None]",
            "result_summary: Mapped[str | None]"
          ],
          "methods": ["__repr__() -> str"]
        },
        "Mission": {
          "bases": ["UUIDMixin", "TimestampMixin", "Base"],
          "fields": [
            "playbook_run_id: Mapped[str | None]",
            "playbook_step_id: Mapped[str | None]",
            "project_id: Mapped[str | None]",
            "objective: Mapped[str]",
            "roster_ref: Mapped[str]",
            "complexity_tier: Mapped[str]",
            "status: Mapped[str]",
            "session_id: Mapped[str]",
            "trigger_type: Mapped[str]",
            "triggered_by: Mapped[str]",
            "upstream_context: Mapped[dict]",
            "context: Mapped[dict]",
            "total_cost_usd: Mapped[float]",
            "cost_ceiling_usd: Mapped[float | None]",
            "started_at: Mapped[str | None]",
            "completed_at: Mapped[str | None]",
            "error_data: Mapped[dict | None]",
            "mission_outcome: Mapped[dict | None]",
            "result_summary: Mapped[str | None]"
          ],
          "methods": ["__repr__() -> str"]
        }
      },
      "functions": {},
      "constants": ["VALID_MISSION_TRANSITIONS: dict[MissionState, set[MissionState]]"]
    },

    "modules/backend/services/mission.py": {
      "lines": 422,
      "imports": [
        "modules.backend.services.base.BaseService",
        "modules.backend.repositories.mission.MissionRepository",
        "modules.backend.models.mission.Mission"
      ],
      "classes": {
        "MissionService": {
          "bases": ["BaseService"],
          "fields": [],
          "methods": [
            "__init__(self, session: AsyncSession, mission_control_dispatch: Any | None, session_service: Any | None, event_bus: Any | None) -> None",
            "factory() -> AsyncGenerator[MissionService, None]",
            "create_mission(objective: str, roster_ref: str, ...) -> Mission",
            "execute_mission(mission_id: str, ...) -> dict",
            "get_mission(mission_id: str) -> Mission",
            "list_missions(limit: int, offset: int, status: str | None) -> list[Mission]",
            "extract_outputs(mission: Mission, output_mapping: dict | None) -> dict[str, Any]"
          ]
        }
      },
      "functions": {},
      "constants": []
    },

    "modules/backend/repositories/base.py": {
      "lines": 117,
      "imports": [
        "sqlalchemy.select",
        "sqlalchemy.func",
        "sqlalchemy.ext.asyncio.AsyncSession",
        "modules.backend.models.base.Base"
      ],
      "classes": {
        "BaseRepository": {
          "bases": ["Generic[ModelType]"],
          "fields": ["model: type[ModelType]"],
          "methods": [
            "__init__(self, session: AsyncSession) -> None",
            "get_by_id(id: str | UUID) -> ModelType",
            "get_by_id_or_none(id: str | UUID) -> ModelType | None",
            "get_all(limit: int, offset: int) -> list[ModelType]",
            "create(**kwargs: Any) -> ModelType",
            "update(id: str | UUID, **kwargs: Any) -> ModelType",
            "delete(id: str | UUID) -> None",
            "exists(id: str | UUID) -> bool",
            "count() -> int"
          ]
        }
      },
      "functions": {},
      "constants": []
    }
  },

  "import_graph": {
    "modules/backend/services/mission.py": [
      "modules/backend/repositories/mission.py",
      "modules/backend/models/mission.py",
      "modules/backend/services/base.py",
      "modules/backend/core/database.py"
    ],
    "modules/backend/repositories/mission.py": [
      "modules/backend/models/mission.py",
      "modules/backend/repositories/base.py"
    ],
    "modules/backend/models/mission.py": [
      "modules/backend/models/base.py"
    ]
  },

  "stats": {
    "total_files": 47,
    "total_lines": 8923,
    "total_classes": 62,
    "total_functions": 184
  }
}
```

### Properties

| Property | Value |
|----------|-------|
| Size | Target 3-5K tokens (rendered Markdown). Hard cap 8K tokens. |
| Parser | **tree-sitter** (primary) via `py-tree-sitter` with Python grammar. Python `ast` module as fallback when tree-sitter is unavailable. |
| Ranking | PageRank on the cross-reference graph. Symbols referenced more frequently from more files rank higher. |
| Storage format | JSON (for programmatic access by Context Assembler, Planning Agent, CLI). |
| Presentation format | Markdown tree (for agent context windows). ~15% more token-efficient than JSON. |
| Generation | Deterministic. No LLM calls. tree-sitter for parsing, PageRank for ranking. |
| Update trigger | Git post-commit hook, or on-demand before mission planning. tree-sitter incremental parsing means only changed files are re-parsed. |
| Generation time | <1 second for a typical project (<100 files). <5 seconds for large projects (<1000 files). Incremental updates: <100ms. |
| Storage | `project_contexts.code_map_data` (JSON column), or a separate `project_code_maps` table. Versioned by commit hash. |
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

This naturally keeps the most important symbols — `BaseService`, `BaseRepository`, `Mission`, `TaskPlan` — and drops obscure utilities that nothing references.

#### Fallback: Mechanical Passes

If PageRank trimming alone cannot meet the budget (e.g., many equally-ranked symbols), apply these passes in order:

1. **Scope filtering** — Only include modules within the PCD's `identity.repo_structure` paths. If the PCD says the project lives in `modules/backend/`, only parse that subtree.

2. **Depth limiting** — For files with many methods, include only public methods (no leading underscore). Private/internal methods are omitted.

3. **Signature truncation** — For methods with many parameters, include only the first 3 parameters followed by `...`. Full signatures are available by reading the actual file.

4. **Layered maps** — For very large codebases (1000+ files), produce a two-level map:
   - **Summary map** (~3K tokens): one entry per module directory, listing classes and their public methods
   - **Detail maps** (~2K tokens each): one per directory, with full signatures
   - The Context Assembler includes the summary map always and the relevant detail map for the task's target directory

---

## Component 2: Exemplar Registry

### What It Is

A curated set of references to canonical files that demonstrate the correct pattern for each component type. Stored in the PCD's `architecture.components` section. Not the file contents — just the file path, the component type, and a one-line pattern description.

When a coding agent needs to create a new service, it reads exactly one file — the exemplar — and has a complete, working pattern to follow. No exploration. No guessing. No inconsistency.

### Schema

The Exemplar Registry is embedded in the PCD. Each entry in `architecture.components` gains two optional fields:

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

### Example

```json
{
  "architecture": {
    "components": {
      "models": {
        "purpose": "SQLAlchemy ORM entities with mapped_column style",
        "key_files": ["modules/backend/models/"],
        "interfaces": ["Base", "UUIDMixin", "TimestampMixin"],
        "exemplar": "modules/backend/models/mission.py",
        "pattern": "UUIDMixin + TimestampMixin + Base, mapped_column with explicit types, Enum for status fields, __repr__ method"
      },
      "repositories": {
        "purpose": "Data access layer with typed queries",
        "key_files": ["modules/backend/repositories/"],
        "interfaces": ["BaseRepository"],
        "exemplar": "modules/backend/repositories/mission.py",
        "pattern": "BaseRepository[Model], set model class attr, custom query methods return list[Model], use select() with where/order_by/limit"
      },
      "services": {
        "purpose": "Business logic and orchestration",
        "key_files": ["modules/backend/services/"],
        "interfaces": ["BaseService"],
        "exemplar": "modules/backend/services/mission.py",
        "pattern": "BaseService(session), factory() classmethod with get_async_session + commit, inject repos in __init__, _log_operation for audit"
      },
      "schemas": {
        "purpose": "Pydantic request/response models",
        "key_files": ["modules/backend/schemas/"],
        "interfaces": [],
        "exemplar": "modules/backend/schemas/mission.py",
        "pattern": "ConfigDict(extra='forbid') for input schemas, ConfigDict(from_attributes=True) for response, Field with constraints"
      },
      "cli_handlers": {
        "purpose": "CLI action dispatchers with Rich output",
        "key_files": ["modules/backend/cli/"],
        "interfaces": [],
        "exemplar": "modules/backend/cli/mission.py",
        "pattern": "run_X() dispatcher with actions dict, async action functions, asyncio.run(), get_console() + build_table() from report module"
      },
      "cli_commands": {
        "purpose": "Click command group definitions",
        "key_files": ["cli.py"],
        "interfaces": ["CliContext"],
        "exemplar": "cli.py",
        "pattern": "@group.command with @click.pass_obj for CliContext, lazy import handler in command body, pass ctx.output_format"
      },
      "agents": {
        "purpose": "PydanticAI agent definitions",
        "key_files": ["modules/backend/agents/"],
        "interfaces": [],
        "exemplar": "modules/backend/agents/horizontal/planning/agent.py",
        "pattern": "Agent(model, output_type, system_prompt from file), RunContext with deps, @agent.tool decorators"
      },
      "agent_config": {
        "purpose": "Agent YAML configuration",
        "key_files": ["config/agents/"],
        "interfaces": [],
        "exemplar": "config/agents/horizontal/planning/agent.yaml",
        "pattern": "agent_name, version, description, category, model block with name/temperature/max_tokens"
      }
    }
  }
}
```

### Properties

| Property | Value |
|----------|-------|
| Storage | Inside the PCD (`architecture.components` entries) |
| Size | ~1K tokens for references. The files themselves are read on-demand by the agent. |
| Maintenance | Agent-maintained. When a coding agent creates a particularly clean implementation, it proposes updating the exemplar reference via context_updates. |
| Selection criteria | The exemplar should be a real, working file in the codebase that best demonstrates the standard pattern. It should be complete (not a stub), readable (not too complex), and representative (not an edge case). |
| Validation | The **PCD validation layer** verifies that all exemplar paths exist on disk. Missing or stale exemplars are flagged as warnings during PCD validation (not during Code Map generation — the generator has no knowledge of exemplars). Validation is triggered on PCD load and before mission planning. |

### How the Agent Uses Exemplars

When a coding agent receives a task to create a new component:

1. The task instructions reference the exemplar: "Create `modules/backend/services/project.py` following the pattern in `modules/backend/services/mission.py` (see exemplar for services in PCD)."

2. The agent reads the exemplar file. It now sees the exact imports, class structure, method signatures, factory pattern, and naming conventions.

3. The agent writes the new file following the same pattern, adapted for the new domain.

This produces **consistent code** across the codebase without relying on the agent to infer patterns from descriptions.

### Exemplar Evolution

Exemplars are not static. They evolve as the codebase improves:

1. **Initial population** — The first "project discovery" mission (or a human) sets the initial exemplars when populating the PCD.

2. **Agent updates** — A coding agent that creates a cleaner implementation than the current exemplar can propose an update via context_updates:
   ```json
   {
     "op": "replace",
     "path": "architecture.components.services.exemplar",
     "value": "modules/backend/services/project.py",
     "reason": "project.py demonstrates the factory+context_manager pattern more cleanly than mission.py"
   }
   ```

3. **Staleness detection** — If the Code Map shows an exemplar file has been deleted or significantly refactored (line count changed by >50%), the system flags it for review.

---

## Component 3: Task File Manifest

### What It Is

A per-task list of files the coding agent needs, pre-computed by the Planning Agent during task plan generation. It tells the agent exactly which files to read and which to modify — eliminating exploration entirely.

### Schema

The file manifest is embedded in the task's `inputs.static` field within the TaskPlan:

```json
{
  "task_id": "task_003",
  "agent": "code.engineer.agent",
  "description": "Add project_id column to Mission model and update repository",
  "instructions": "...",
  "inputs": {
    "static": {
      "file_manifest": {
        "read_for_pattern": [
          {
            "path": "modules/backend/models/mission.py",
            "reason": "Exemplar for model pattern (UUIDMixin + TimestampMixin + Base, mapped_column)"
          }
        ],
        "read_first": [
          {
            "path": "modules/backend/models/mission.py",
            "reason": "Target file — understand current Mission and PlaybookRun field list"
          },
          {
            "path": "modules/backend/models/project.py",
            "reason": "See Project.id field type (String(36)) to match FK type"
          },
          {
            "path": "modules/backend/repositories/mission.py",
            "reason": "Understand existing query methods that may need project_id filtering"
          }
        ],
        "modify": [
          {
            "path": "modules/backend/models/mission.py",
            "reason": "Add project_id field to Mission and PlaybookRun classes"
          },
          {
            "path": "modules/backend/repositories/mission.py",
            "reason": "Add list_by_project_id query method"
          }
        ]
      }
    },
    "from_upstream": {}
  }
}
```

### File Manifest Fields

| Field | Purpose | Required |
|-------|---------|----------|
| `read_for_pattern` | Files to read to understand the coding pattern. Typically the exemplar or a closely related file. Read these first to internalize the pattern before starting work. | Optional. Omit if the task doesn't involve creating new code (e.g., config change). |
| `read_first` | Files to read to understand the current state of the code that will be changed. These give the agent the specific context it needs for this task. | Required for all coding tasks. |
| `modify` | Files that the agent will create or modify. This is the agent's work scope. The agent should not modify files outside this list unless the task explicitly requires it. | Required for all coding tasks. |

Each entry has:
- `path` — relative file path from repo root
- `reason` — why this file is in the manifest (helps the agent prioritize and understand)

### How the Planning Agent Generates File Manifests

The Planning Agent has access to the PCD (architecture, exemplars) and the Code Map (structure, import graph). It uses these to derive the file manifest for each task:

1. **Identify the target component type** — from the task description, determine which architecture component is being created/modified (model, service, repository, etc.)

2. **Look up the exemplar** — from `PCD.architecture.components[type].exemplar`, get the canonical pattern file. This goes in `read_for_pattern`.

3. **Identify target files** — from the Code Map, find the specific files that the task will modify. These go in `modify`.

4. **Trace dependencies** — from the Code Map's `import_graph`, find files that the target files depend on or that depend on the target files. Files that import the modified file may need to be read to understand downstream impact. These go in `read_first`.

5. **Minimize the list** — remove duplicates. If a file appears in both `read_for_pattern` and `read_first`, keep it in `read_first` only (it serves both purposes). Target: 3-8 files total across all three lists.

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

A deterministic Python tool that parses the codebase using **tree-sitter** (with Python `ast` fallback), builds a cross-reference graph, ranks symbols by PageRank, and produces the Code Map JSON. No LLM calls. Runs in milliseconds to seconds. Supports incremental re-parsing — only changed files are re-processed.

### Location

```
modules/backend/tools/code_map.py
```

### Dependencies

```
py-tree-sitter        # tree-sitter Python bindings
tree-sitter-python    # Python grammar for tree-sitter
```

If tree-sitter is unavailable (missing native dependency), the generator falls back to Python's built-in `ast` module. The fallback produces identical output but without incremental parsing or error tolerance.

### Interface

The generator is decomposed into **five public functions** — one per pipeline stage plus the top-level orchestrator. Each stage has a typed input and output, so stages can be tested, reused, and composed independently.

```python
"""
Code Map Generator.

Parses a Python codebase using tree-sitter and produces a structural
skeleton: every module, class, function with signatures and type annotations.
No method bodies, no comments, no docstrings. Symbols are ranked by PageRank
on the cross-reference graph. Deterministic, fast, cheap.

The generator is decomposed into four stages, each a pure function:

    parse_modules()          → list[ModuleInfo]
    build_reference_graph()  → ReferenceGraph
    rank_symbols()           → dict[str, float]
    assemble_code_map()      → dict  (the JSON Code Map)

generate_code_map() orchestrates all four stages. Each stage can be
called independently for testing, debugging, or reuse.

Presentation is handled by two separate functions:

    trim_by_rank()           → dict  (trimmed Code Map JSON)
    render_markdown_tree()   → str   (Markdown tree output)

Usage:
    from modules.backend.tools.code_map import generate_code_map

    code_map = generate_code_map(
        repo_root=Path("/path/to/repo"),
        scope=["modules/backend/"],
        exclude=["**/tests/**", "**/__pycache__/**", "**/migrations/**"],
    )

    # Trim and render for agent consumption
    from modules.backend.tools.code_map import trim_by_rank, render_markdown_tree

    trimmed = trim_by_rank(code_map, max_tokens=4000)
    markdown = render_markdown_tree(trimmed)

    # Or use the convenience wrapper (trims + renders in one call)
    from modules.backend.tools.code_map import render_for_agent

    markdown = render_for_agent(code_map, max_tokens=4000)

    # Incremental update (re-parses only changed files)
    from modules.backend.tools.code_map import generate_code_map

    updated = generate_code_map(
        repo_root=Path("/path/to/repo"),
        scope=["modules/backend/"],
        previous_map=code_map,  # provides cached parse results
    )
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Data types passed between stages ──────────────────────────────────


@dataclass
class SymbolInfo:
    """A single symbol (class, function, method, constant) extracted from source."""

    name: str
    kind: str  # "class" | "function" | "method" | "constant"
    qualified_name: str  # e.g. "modules.backend.services.base.BaseService"
    params: list[str] = field(default_factory=list)  # ["session: AsyncSession"]
    returns: str | None = None
    bases: list[str] = field(default_factory=list)  # class bases
    fields: list[str] = field(default_factory=list)  # class fields
    methods: list["SymbolInfo"] = field(default_factory=list)  # class methods
    decorators: list[str] = field(default_factory=list)


@dataclass
class ModuleInfo:
    """Parsed structure of a single Python module."""

    path: str  # relative to repo root
    lines: int
    imports: list[str]  # resolved dotted module paths
    classes: list[SymbolInfo] = field(default_factory=list)
    functions: list[SymbolInfo] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)  # "NAME: Type"


@dataclass
class ReferenceEdge:
    """A directed reference from one symbol to another."""

    source: str  # qualified name of the referencing symbol
    target: str  # qualified name of the referenced symbol
    kind: str  # "import" | "call" | "inherit" | "type_annotation"


@dataclass
class ReferenceGraph:
    """Directed graph of cross-references between symbols."""

    nodes: list[str]  # qualified symbol names
    edges: list[ReferenceEdge]


# ── Stage functions ───────────────────────────────────────────────────


def parse_modules(
    repo_root: Path,
    scope: list[str],
    exclude: list[str] | None = None,
    previous_modules: list[ModuleInfo] | None = None,
) -> list[ModuleInfo]:
    """Stage 1: Parse all Python files in scope into ModuleInfo structures.

    Uses tree-sitter with Python grammar (falls back to ast if unavailable).
    Extracts classes, functions, constants, imports, and cross-references.

    If previous_modules is provided, only re-parses files whose mtime has
    changed since the previous run. Unchanged files reuse cached ModuleInfo.

    Args:
        repo_root: Absolute path to the repository root.
        scope: Relative directory paths to include (e.g., ["modules/backend/"]).
        exclude: Glob patterns to exclude. Defaults to tests, __pycache__,
                 migrations, node_modules, .venv.
        previous_modules: Cached parse results from a prior run. Files with
                          unchanged mtime reuse these instead of re-parsing.

    Returns:
        List of ModuleInfo, one per parsed file.
    """
    ...


def build_reference_graph(modules: list[ModuleInfo]) -> ReferenceGraph:
    """Stage 2: Build a cross-reference graph from parsed modules.

    Constructs a directed graph where nodes are symbols and edges are
    references. See 'Cross-Reference Resolution Boundary' below for
    what is and is not resolved.

    Args:
        modules: Output of parse_modules().

    Returns:
        ReferenceGraph with nodes and typed edges.
    """
    ...


def rank_symbols(graph: ReferenceGraph, damping: float = 0.85) -> dict[str, float]:
    """Stage 3: Run PageRank on the reference graph.

    Args:
        graph: Output of build_reference_graph().
        damping: PageRank damping factor (standard: 0.85).

    Returns:
        Dict mapping qualified symbol name → rank score (0.0 to 1.0,
        normalized so the highest-ranked symbol is 1.0).
    """
    ...


def assemble_code_map(
    modules: list[ModuleInfo],
    ranks: dict[str, float],
    repo_root: Path,
) -> dict:
    """Stage 4: Assemble the final Code Map JSON from parsed modules and ranks.

    Merges ModuleInfo structures with rank scores and produces the storage
    schema defined in this document. Includes import_graph and stats.

    Args:
        modules: Output of parse_modules().
        ranks: Output of rank_symbols().
        repo_root: Repo root (for commit hash and metadata).

    Returns:
        Code Map dict matching the storage schema.
    """
    ...


# ── Orchestrator ──────────────────────────────────────────────────────


def generate_code_map(
    repo_root: Path,
    scope: list[str],
    exclude: list[str] | None = None,
    max_tokens: int = 5000,
    previous_map: dict | None = None,
) -> dict:
    """Generate a Code Map for the given repository.

    Orchestrates all four pipeline stages: parse → graph → rank → assemble.
    Applies token budgeting if the result exceeds max_tokens.

    For incremental updates, pass previous_map — the generator extracts
    cached ModuleInfo from it and only re-parses files with changed mtime.

    Args:
        repo_root: Absolute path to the repository root.
        scope: Relative directory paths to include (e.g., ["modules/backend/"]).
        exclude: Glob patterns to exclude. Defaults to tests, __pycache__,
                 migrations, node_modules, .venv.
        max_tokens: Target maximum token count for the stored JSON.
                    If exceeded, low-ranked symbols are trimmed first,
                    then mechanical passes are applied as fallback.
        previous_map: A previously generated Code Map dict. If provided,
                      enables incremental parsing — only files whose mtime
                      changed since the previous map are re-parsed.

    Returns:
        Code Map dict matching the storage schema defined in this document.
        Includes rank scores on modules, classes, and functions.
    """
    ...


# ── Presentation (separate from generation) ───────────────────────────


def trim_by_rank(code_map: dict, max_tokens: int = 4000) -> dict:
    """Trim a Code Map to fit within a token budget.

    Removes lowest-ranked symbols first. If rank-based trimming alone
    is insufficient, applies mechanical fallback passes (see Token
    Budgeting section). Returns a new dict — does not mutate the input.

    Useful independently of rendering — e.g., to produce a trimmed JSON
    for storage or for the Planning Agent at a reduced budget.

    Args:
        code_map: The full Code Map dict.
        max_tokens: Target token budget.

    Returns:
        A new Code Map dict with low-ranked symbols removed.
    """
    ...


def render_markdown_tree(code_map: dict) -> str:
    """Render a Code Map as a Markdown tree.

    Produces the presentation format defined in this document. Symbols
    are ordered by PageRank score within each file. Does NOT trim —
    renders whatever is in the input. Call trim_by_rank() first if
    budget enforcement is needed.

    Args:
        code_map: A Code Map dict (full or already trimmed).

    Returns:
        Markdown tree string.
    """
    ...


def render_for_agent(code_map: dict, max_tokens: int = 4000) -> str:
    """Convenience wrapper: trim by rank then render as Markdown tree.

    Equivalent to render_markdown_tree(trim_by_rank(code_map, max_tokens)).

    Args:
        code_map: The stored JSON Code Map.
        max_tokens: Target token budget for the rendered output.

    Returns:
        Markdown tree string ready for inclusion in agent context.
    """
    ...


def get_current_commit(repo_root: Path) -> str:
    """Get the current git HEAD commit hash."""
    ...
```

### Parsing Pipeline

The generator runs a four-stage pipeline:

#### Stage 1: Parse

For each `.py` file in scope:

1. **Parse with tree-sitter** using the Python grammar and `tags.scm` queries. tree-sitter is error-tolerant — files with syntax errors produce partial trees rather than failures. If tree-sitter is unavailable, fall back to `ast.parse()` (which raises on syntax errors — skip and log a warning).

2. **Extract definitions** using tree-sitter tag queries (`@definition.class`, `@definition.function`, `@definition.method`):
   - Class name, base classes (names only)
   - Class-level fields: assignments with type annotations (`field: Type = ...` → `"field: Type"`)
   - Methods: name, parameter list with types, return type, decorator names
   - For enum classes (inherits from `enum.Enum`): extract member names as fields

3. **Extract references** using tree-sitter tag queries (`@reference.call`, `@reference.class`):
   - Which symbols each file/class/function references
   - These references are used in Stage 2 for graph construction

4. **Extract top-level functions**, module-level constants, and imports (same as v1.0).

#### Stage 2: Build Cross-Reference Graph

Construct a directed graph where:
- **Nodes** are symbols (modules, classes, functions)
- **Edges** are references (file A's class calls file B's function → edge from A to B)

This graph captures not just import relationships (which module imports which) but **usage relationships** (which class actually calls which function). The import graph from v1.0 is a subset of this — it captures module-level dependencies. The cross-reference graph captures symbol-level dependencies.

Sources for edges:
- Import statements (module → module)
- Function/method calls (caller → callee, resolved via import context)
- Class inheritance (subclass → base class)
- Type annotations referencing other classes

External symbols (stdlib, third-party) are excluded from the graph.

##### Cross-Reference Resolution Boundary

tree-sitter gives us syntax, not semantics. The generator can resolve some references statically and cannot resolve others. This boundary is explicit — **unresolved references are dropped, not guessed**.

| Resolvable (static) | Not resolvable (requires type inference) |
|---------------------|------------------------------------------|
| `from x.y import Z` → Z is in module x.y | `self.repo.create()` → which class is `self.repo`? |
| `class Foo(BaseService)` → Foo inherits BaseService | `items = get_items(); items.filter()` → what type is `items`? |
| `field: Mapped[str]` → type annotation references Mapped | `callback(handler)` → what does `handler` resolve to? |
| `BaseRepository.create()` → explicit class reference | `getattr(obj, method_name)()` → dynamic dispatch |
| Top-level function calls: `validate_config(x)` | Closures, decorators that return different types |

**Resolution strategy:** For each reference extracted by tree-sitter, attempt to resolve it against the import table of the current module. If the reference matches an imported name (or a locally defined name), create an edge. If it cannot be resolved to an in-scope symbol, drop it silently. This is conservative — it under-counts references rather than creating false edges. Under-counting is safe: it slightly underweights some symbols in PageRank but never creates spurious importance.

This means `self.method()` calls within a class **are** resolved (the method is defined in the same class or a known base class), but `self.dependency.method()` calls are resolved **only if** the dependency's type is declared in an annotation (e.g., `self.repo: MissionRepository`). Unannotated dependencies produce no edge.

#### Stage 3: Rank with PageRank

Run PageRank on the cross-reference graph:
- Symbols referenced more frequently from more files get higher scores
- Symbols in highly-connected files (hubs) propagate their importance to what they reference
- The damping factor is 0.85 (standard PageRank default)
- Scores are normalized to 0.0–1.0 range

The result: every module, class, and function has a `rank` score in the stored JSON.

**Why PageRank over simpler metrics (reference count)?** Reference count would rank utility functions highest (called from everywhere) but miss architectural keystone classes. PageRank captures that `BaseService` is important not because it's called a lot, but because important things inherit from it. It's the same insight that makes Google's search ranking work — a link from an important page matters more than a link from an obscure page.

#### Stage 4: Output

Produce the JSON Code Map with rank scores on all symbols. Apply token budgeting if the result exceeds `max_tokens`.

### Extraction Rules

For each `.py` file in scope:

1. **Extract top-level classes**:
   - Class name
   - Base classes (names only, not fully qualified)
   - Class-level fields: assignments with type annotations (`field: Type = ...` → `"field: Type"`)
   - Methods: name, parameter list with types, return type, decorator names
   - For enum classes (inherits from `enum.Enum`): extract member names as fields

2. **Extract top-level functions**:
   - Function name
   - Parameter list with types
   - Return type
   - Decorator names (without arguments)

3. **Extract module-level constants**:
   - Assignments to ALL_CAPS names with type annotations

4. **Extract imports**:
   - All `import` and `from ... import` statements
   - Resolve to dotted module paths

5. **Build import graph**:
   - For each module, record which other modules in-scope it imports
   - External imports (stdlib, third-party) are excluded from the graph

### Token Budgeting

After initial generation, if the estimated token count exceeds `max_tokens`:

**Primary: Rank-based trimming** — Sort all symbols by PageRank score descending. Remove the lowest-ranked symbols until the budget is met. This ensures the most important symbols always survive.

**Fallback passes** (if rank-based trimming alone is insufficient):

1. **Pass 1**: Remove private methods (leading `_`) from all classes
2. **Pass 2**: Truncate method signatures with more than 3 parameters to `(param1: T1, param2: T2, param3: T3, ...)`
3. **Pass 3**: Remove `constants` arrays from all modules
4. **Pass 4**: Remove `imports` arrays (import_graph still preserved)
5. **Pass 5**: Remove modules with fewer than 20 lines (trivial files)

If still over budget after all passes, remove the lowest-ranked files.

### Triggering

| Trigger | Mechanism |
|---------|-----------|
| Git commit | Post-commit hook: `python -m modules.backend.tools.code_map --project <id>`. tree-sitter incremental parsing means only changed files are re-parsed (<100ms). |
| Before mission planning | The dispatch adapter checks if the code map commit matches HEAD. If not, regenerates. |
| CLI command | `python cli.py project code-map <project_id>` — regenerate and display (Markdown tree format) |
| On project creation | Generated as part of the initial project setup alongside the seed PCD |

### Storage

The Code Map is stored alongside the PCD. Two options (implementation chooses one):

**Option A**: Additional column on `project_contexts` table:
```python
code_map_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
code_map_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
```

**Option B**: Separate `project_code_maps` table:
```python
class ProjectCodeMap(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "project_code_maps"

    project_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    code_map_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    commit_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(20), nullable=False)
    total_files: Mapped[int] = mapped_column(Integer, nullable=False)
    total_lines: Mapped[int] = mapped_column(Integer, nullable=False)
    size_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
```

Option B is preferred. The Code Map updates more frequently than the PCD (every commit vs. every task), so separating them avoids unnecessary PCD version increments.

---

## Integration with Context Assembly

The Context Assembler (defined in [001-project-context-layer.md](001-project-context-layer.md)) gains a new layer:

```
Context Assembly Priority Order:

  Priority 1 (never trimmed):  Layer 0 — PCD                    ~4K tokens
  Priority 2 (never trimmed):  Layer 1 — Task definition         ~2K tokens
  Priority 3 (high):           Layer 3 — Code Map                ~3K tokens
  Priority 4 (high):           Layer 1 — Upstream outputs         ~2K tokens
  Priority 5 (normal):         Layer 2 — History                  ~2K tokens
```

The Code Map is loaded for all tasks with `domain_tags` that include code-related tags (`api`, `models`, `services`, `database`, `testing`, etc.). It is omitted for non-coding tasks (pure analysis, summarization, review).

### Assembly Logic

```python
# In ContextAssembler.build():

# Layer 3: Code Map (for coding tasks)
if self._is_coding_task(task_definition):
    code_map_json = await self._load_code_map(project_id)
    if code_map_json:
        # Trim by rank first, then render as Markdown tree.
        # These are separate operations — trim_by_rank produces a valid
        # Code Map dict that could also be used for JSON output.
        trimmed = trim_by_rank(code_map_json, max_tokens=remaining_budget)
        rendered = render_markdown_tree(trimmed)
        rendered_tokens = _estimate_tokens(rendered)
        packet["code_map"] = rendered
        remaining_budget -= rendered_tokens
```

The `_is_coding_task()` method checks whether the task's `domain_tags` or agent type indicate a code modification task. Non-coding tasks (analysis, summarization, review) skip the Code Map to save token budget.

The Planning Agent receives the **stored JSON** (not Markdown) — it needs programmatic access to the import graph and rank scores for generating file manifests. It may also use `trim_by_rank()` independently if the JSON exceeds its budget. Coding agents receive the **rendered Markdown tree** — they need spatial awareness, not programmatic access.

---

## Integration with Planning Agent

The Planning Agent's prompt is extended to include:

1. **The Code Map (JSON format)** — so it can access rank scores, import graph, and symbol data programmatically for generating precise file manifests. The Planning Agent receives JSON, not the Markdown tree — it needs structured access to the data.

2. **The Exemplar Registry** — so it can point coding agents to the right pattern files.

3. **Instruction to generate file manifests** — the Planning Agent prompt explicitly requires it to produce `file_manifest` in each task's `inputs.static` for coding tasks.

### Planning Agent Prompt Addition

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

The existing Agent Contract (defined in [001-project-context-layer.md](001-project-context-layer.md)) is extended for coding agents:

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

5. **Propose exemplar updates.** If the agent creates code that is cleaner or more complete than the current exemplar for that component type, include an exemplar update in context_updates.

---

## Comparison with Existing Approaches

| Approach | Token Cost | Freshness | Precision | Exploration Required | Our Assessment |
|----------|-----------|-----------|-----------|---------------------|----------------|
| CLAUDE.md / AGENTS.md (static docs) | Low | Goes stale quickly | Manual maintenance | Still needs exploration | PCD replaces this, agent-maintained |
| Codebase embeddings (RAG) | High to build, expensive to update | Minutes stale after changes | Fuzzy — 10%+ irrelevant results | Reduced but not eliminated | Wrong tool for agent coordination |
| Aider repo map (tree-sitter + PageRank) | Low (~3K tokens) | Auto-updated | Structural, ranked by importance | Reduced | We adopt tree-sitter + PageRank, extend with exemplars and manifests |
| MCP-based agentic exploration | Per-query cost | Always fresh (live queries) | High if queries are well-formed | Agent-driven exploration | Wrong model for autonomous dispatch (adds latency, non-deterministic) |
| Cursor codebase indexing | Medium | Background reindexing | Good for IDE but not autonomous agents | Built for interactive use | Not applicable to dispatch loop |
| File-by-file reading | High per-task | Always fresh | Exact when you find the right file | Maximum — agent must discover | Necessary but must be targeted |
| **Code Map + Exemplar + Manifest** | **Medium (~4K tokens, Markdown)** | **Auto-updated (incremental)** | **High — ranked signatures + exact patterns** | **Near zero — pre-computed** | **Best for autonomous dispatch** |

---

## Failure Modes and Mitigations

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Code Map is stale (commit mismatch) | Agent works with outdated structure | Dispatch adapter checks commit hash before planning. Regenerate if stale. |
| Exemplar file was deleted or refactored | Agent reads a nonexistent or changed file | PCD validation layer checks exemplar paths on load and before planning. Missing exemplars flagged as warnings. Agent falls back to Code Map for pattern inference. |
| File manifest is incomplete | Agent needs a file not in the manifest | Agent can use Code Map to find additional files and read them. Manifest is guidance, not a hard constraint. Agent reports unscoped reads in its output. |
| File manifest is wrong (Planning Agent hallucinated a path) | Agent tries to read a nonexistent file | Code Map is ground truth. Agent validates manifest paths against Code Map before reading. Invalid paths are skipped with a warning. |
| tree-sitter unavailable (missing native dep) | Cannot use primary parser | Fall back to Python `ast` module. Identical output but no incremental parsing or error tolerance. Log a warning recommending tree-sitter installation. |
| Codebase has no parsable Python files | Code Map is empty | Generator logs a warning. Agent falls back to PCD-only context. File manifest is omitted from task instructions. |
| Code Map exceeds token budget | Bloated context packet | PageRank-based trimming drops lowest-ranked symbols first. Mechanical passes as fallback. `render_for_agent()` applies independent budget on the Markdown output. |
| Agent modifies files outside manifest scope | Unintended side effects | Verification pipeline (Tier 1) checks that only manifest files were modified. Unscoped modifications are flagged. |

---

## Relationship to Other Architecture Components

| Component | Relationship |
|-----------|-------------|
| PCD (001-project-context-layer.md) | Exemplar Registry lives inside the PCD. Code Map is a companion data structure stored alongside the PCD. Exemplar path validation belongs to the PCD validation layer, not the Code Map generator. |
| Context Assembler (001-project-context-layer.md) | Extended with Layer 3 (Code Map) loading for coding tasks. |
| Planning Agent (Plan 13) | Extended to use Code Map for generating file manifests and to reference exemplars in task instructions. |
| Dispatch Loop (Plan 13) | No changes. Code Map is assembled by the Context Assembler before the dispatch loop calls the agent. |
| TaskPlan Schema (schemas/task_plan.py) | `file_manifest` is a new optional field in `TaskDefinition.inputs.static`. No schema change needed — static is already `dict`. |
| Verification Pipeline (Plan 14) | Tier 1 verification can check that agent modifications stayed within the `modify` scope. |
| Agent Module Organization (doc 47) | The Code Map Generator is a **tool** (not an agent). It lives in `modules/backend/tools/`, following the tool organization from doc 47. |

---

## Implementation Sequence

### Phase 1: Code Map Generator (tree-sitter + PageRank)

Build the four stage functions (`parse_modules()`, `build_reference_graph()`, `rank_symbols()`, `assemble_code_map()`) and the orchestrator (`generate_code_map()`). Include `ast` fallback for `parse_modules()`. Build the presentation layer (`trim_by_rank()`, `render_markdown_tree()`, `render_for_agent()`). Each stage function is independently testable. Test against the current codebase. Verify output matches expected structure. Add CLI command: `python cli.py project code-map <project_id>`.

**Deliverable:** Code Map can be generated (JSON), trimmed, rendered (Markdown tree), viewed, and stored. Each pipeline stage is testable in isolation. Not yet used by agents.

### Phase 2: Code Map Storage + Freshness

Add storage (table or column). Wire generation into git post-commit hook and dispatch adapter. Use `previous_map` parameter for incremental updates — only changed files are re-parsed. Ensure the Code Map is always fresh before mission planning.

**Deliverable:** Code Map is automatically maintained and always current. Incremental updates via `previous_map` in <100ms.

### Phase 3: Exemplar Registry

Populate the PCD with exemplar references for all existing component types. Add exemplar path validation to the PCD validation layer (not the Code Map generator — the generator has no knowledge of exemplars).

**Deliverable:** PCD has exemplar references. PCD validation warns on missing or stale exemplars.

### Phase 4: Planning Agent Integration

Extend the Planning Agent prompt to use Code Map (JSON format with rank scores and import graph) and exemplar registry. Generate file manifests for coding tasks. Validate manifests against Code Map.

**Deliverable:** TaskPlans include file manifests. Planning Agent references specific files using rank-informed selection.

### Phase 5: Context Assembler Integration

Add Code Map to Context Assembler. Use `trim_by_rank()` + `render_markdown_tree()` for coding agent context windows. Pass JSON (optionally trimmed via `trim_by_rank()`) to Planning Agent. Token budgeting via rank-ordered elision.

**Deliverable:** Coding agents receive the ranked Markdown tree Code Map in their context packet (~15% fewer tokens than JSON equivalent).

### Phase 6: Coding Agent Contract

Formalize the coding agent lifecycle. Enforce manifest-scoped modifications in Tier 1 verification. Enable exemplar updates via context_updates.

**Deliverable:** Coding agents follow the manifest, propose exemplar improvements.
