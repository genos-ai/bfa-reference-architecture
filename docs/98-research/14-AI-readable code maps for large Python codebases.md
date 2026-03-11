# AI-readable code maps for large Python codebases

**The best approach to mapping a 100k+ LOC Python codebase for both compliance enforcement and AI agent consumption is a layered pipeline combining tree-sitter-based structural extraction, import-graph-powered architectural enforcement, and graph-ranked context generation — not a single tool.** Aider's open-source RepoMap technique (tree-sitter + PageRank ranking) has emerged as the de facto standard for compact AI context, while `import-linter` with its Rust-powered `grimp` backend dominates architectural compliance. The most cutting-edge systems in 2026 layer these static approaches with vector embeddings and knowledge graphs exposed via MCP servers, enabling AI agents to dynamically query codebase structure rather than relying on a single static artifact.

This report covers the full landscape — from battle-tested CLI tools you can add to CI today to emerging graph-based knowledge systems — and concludes with a ranked recommendation for the optimal toolchain.

---

## The structural layer: tree-sitter and AST-based extraction

Every serious code mapping pipeline starts with fast, accurate parsing. Three tools form the foundation for Python codebases, each serving a distinct role.

**Tree-sitter** has become the universal parser for AI code tools. It generates incremental, error-tolerant concrete syntax trees in single-digit milliseconds per file, meaning a 100k LOC codebase parses in **2–5 seconds**. Aider, Continue.dev, GitHub Semantic, GitNexus, and dozens of other tools depend on it. Its `tags.scm` query system extracts definitions (`@definition.class`, `@definition.function`) and references (`@reference.call`) with structured S-expression queries, making it trivial to build cross-file dependency edges. Python bindings via `py-tree-sitter` give full access to parsing, tree walking, and query execution. Tree-sitter's key advantage over Python's built-in `ast` module is language-agnosticism and incremental re-parsing — only changed portions of files need re-processing, yielding sub-millisecond updates.

**Python's `ast` module** remains the fastest option for pure-Python analysis — it's C-implemented, requires zero dependencies, and handles 100k+ LOC in seconds. The `ast.dump()` function with `indent` parameter produces structured output serializable to JSON. Python 3.14 added `ast.compare()` for tree diffing. The limitation is that `ast` is lossy (discards comments and formatting) and Python-only. For custom compliance scripts that only need Python, it's unbeatable for speed.

**libcst** (Meta/Instagram) fills the gap between the two: a concrete syntax tree parser that preserves all formatting while providing visitor/transformer patterns. Its native Rust parser (via PyO3) runs within **2x of CPython's parser speed**. Instagram uses it on their multi-million-LOC server codebase for automated refactoring. The key differentiator is lossless round-tripping — parse, modify, write back with identical formatting — plus metadata providers for fully qualified name resolution and call graph generation. For AI agents that need to both *read* and *modify* code, libcst is essential.

| Parser | Speed (100k LOC) | Preserves formatting | JSON export | Best for |
|--------|-------------------|---------------------|-------------|----------|
| tree-sitter | ~2–5s (incremental: <100ms) | Yes (CST) | Via queries | Multi-language mapping, AI context |
| Python `ast` | ~1–3s | No (AST) | `ast.dump()` | Custom Python-only scripts |
| libcst | ~3–8s | Yes (lossless) | Custom serialization | Code modification, lint rules |

---

## Compliance enforcement: the proven toolkit

For detecting architectural violations, coupling issues, and dead code, the Python ecosystem offers mature, CI-ready tools that require minimal setup.

### Architectural boundary enforcement

**`import-linter`** is the single most important tool for Python architectural compliance. Built on `grimp` (a Rust-powered import graph library, v3.14 as of December 2025), it validates import dependencies against declarative "contracts" defined in `pyproject.toml`. Five built-in contract types cover most architectural patterns: **Layers** (enforce unidirectional dependency flow between tiers), **Forbidden** (block specific import paths like views importing directly from database models), **Independence** (ensure domain modules don't cross-depend), plus custom contracts via a Python ABC. It detects both direct and **transitive violations**, reporting full import chains. A typical configuration enforces clean architecture in under 20 lines:

```toml
[tool.importlinter]
root_package = "myproject"

[[tool.importlinter.contracts]]
name = "Layered architecture"
type = "layers"
layers = ["myproject.api", "myproject.service", "myproject.domain", "myproject.infrastructure"]

[[tool.importlinter.contracts]]
name = "Domain modules are independent"
type = "independence"
modules = ["myproject.domain.orders", "myproject.domain.users", "myproject.domain.billing"]
```

Running `lint-imports` takes seconds on large codebases, exits non-zero on violations, and integrates directly as a pre-commit hook. It's production-stable, BSD-licensed, and used by projects like Kedro.

**PyTestArch** (v4.0.1) and **pytest-archon** (v0.0.7) bring ArchUnit-style testing to Python. Both let you write architecture rules as pytest tests with fluent APIs. PyTestArch offers richer features (LayeredArchitecture support, matplotlib visualization), while pytest-archon is lighter-weight. A blog post from 2026 demonstrates pytest-archon enforcing layered Django architecture at **160k+ LOC** in production. Since they're pytest plugins, they run in any existing CI pipeline without additional infrastructure.

### Dead code detection

**`vulture`** (v2.15) remains the go-to dead code finder. It uses `ast` to find unused functions, classes, variables, and imports, assigning **confidence scores (60–100%)**. Running `vulture mypackage/ --min-confidence 80 --sort-by-size` on 100k+ LOC completes in seconds. The `--make-whitelist` flag auto-generates suppression files for framework magic (Flask routes, pytest fixtures). The main limitation is name-based matching — it can't track scope, producing false positives with dynamic dispatch.

**`deadcode`** (presented at EuroPython 2024) improves on vulture with **scope and namespace tracking**, structured error codes (DC01–DC04), and a `--fix` flag for automatic removal. Using both tools in combination yields the best results: vulture for broad, confidence-scored detection and deadcode for stricter, scope-aware analysis.

**Skylos** (2025–2026) represents the emerging hybrid approach — AST analysis plus optional LLM reasoning to distinguish framework magic from truly dead code, with MCP server integration and GitHub Actions CI workflow generation. Still early-stage but points to where dead code detection is heading.

---

## AI context generation: how the best tools represent codebases

The central challenge for AI agent context is compression: how to represent a 100k+ LOC codebase in a few thousand tokens without losing critical structural information. The approaches that work best in 2026 combine structural extraction with importance ranking.

### Aider's RepoMap: the proven standard

Aider pioneered **repository maps for LLMs**, and its approach remains the gold standard. The algorithm works in four steps: (1) tree-sitter parses all files to extract symbol definitions and references, (2) a dependency graph is built where files are nodes and cross-references are edges, (3) **PageRank** ranks symbols by importance — frequently-referenced symbols in highly-connected files score highest, (4) binary search optimally packs the most important context within a configurable token budget (default 1K tokens, expandable). The output uses a hierarchical tree format with elision markers:

```
src/auth/service.py:
⋮...
│class AuthService:
│    def login(self, username: str, password: str) -> Token:
⋮...
│    def validate_token(self, token: str) -> User:
```

A `diskcache` persistent cache avoids re-parsing unchanged files, making subsequent runs near-instant. For 100k+ LOC repos, the `--subtree-only` flag and `.aiderignore` files manage scope. The approach has been validated through extensive benchmarks and adopted by Continue.dev's `@repo-map` context provider and the standalone **RepoMapper MCP server** (pdavis68/RepoMapper).

### Token-efficient output formats

Empirical research on LLM format comprehension reveals significant differences in both token efficiency and accuracy:

**Structured Markdown** is the best default — it's **15–16% more token-efficient than JSON** (verified via tiktoken: 11,612 vs 13,869 tokens for equivalent data) and matches LLM training data distributions (GitHub READMEs, documentation). **YAML achieves 62% accuracy on nested data** versus JSON's 50%, making it superior for deeply hierarchical code structure representations while saving 20–35% tokens versus JSON for repeated structures. JSON is best reserved for automated pipelines requiring strict parsing. XML should be avoided entirely for code maps.

The practical recommendation is structured Markdown for human-readable code maps and AI chat context, YAML for programmatic code structure schemas, and Mermaid diagrams (natively rendered by GitHub, GitLab, Notion) for high-level architecture visualization.

### How commercial AI coding tools handle context

**Cursor** uses a RAG pipeline with Merkle tree-based incremental file tracking, AST-based semantic chunking, proprietary code embedding models, and Turbopuffer vector database — yielding ~60–80K tokens of effective code context. Performance reportedly degrades on monorepos exceeding 100k LOC.

**GitHub Copilot** builds remote code search indexes from the default branch (completing in seconds for most repos as of March 2025 GA), combines semantic embedding search with local file tracking for uncommitted changes, and uses GPT-4o-mini for fast query classification. Sub-second search times for multi-million-line codebases.

**Augment Code** claims the most advanced context engine: semantic indexing, cross-repo relationship awareness, commit history indexing with LLM-summarized diffs ("Context Lineage"), processing **400,000+ files** per codebase. Available as an MCP server for any agent.

**Sourcegraph Cody** Enterprise supports context windows up to **1M tokens**, combines code search with semantic embeddings, and has proven at 300K+ repos and 90GB+ monorepos. A new "Deep Search" feature uses sub-agents for file discovery.

All of these are proprietary and closed-source. For an open, self-hosted pipeline, the Aider RepoMap approach combined with vector embeddings is the closest equivalent.

---

## Graph-based representations for deep analysis

When you need more than import-level analysis — data-flow tracking, control-flow awareness, or complex vulnerability patterns — graph-based representations provide the deepest understanding.

### Code Property Graphs with Joern

**Joern** (Apache 2.0) generates Code Property Graphs that merge ASTs, control flow graphs, and program dependence graphs into a single queryable structure. Its Python support is rated "High" maturity via the `pysrc2cpg` frontend. For AI consumption, Joern offers multiple export paths: Neo4j CSV for graph database loading, GraphML, GraphSON, DOT, and a `--vectors` flag for ML-ready vector representations. CPG slicing (`--slice-mode=DataFlow`) produces focused subgraphs per function that fit well in LLM context windows.

The trade-off is setup complexity — Joern requires the JVM with significant heap allocation (users report needing `-J-Xmx128g` for large codebases), and analysis is slower than pure import-graph tools. For 100k+ LOC, excluding test files via `--ignore-paths` is essential. The Python library **cpggen** (AppThreat) wraps Joern frontends for easier CLI usage and GitHub Actions integration.

### CodeQL for compliance at scale

**CodeQL** (GitHub) has first-class Python support with no build step required — `codeql database create --language=python` just runs the extractor. Its QL query language can express sophisticated architectural constraints:

```ql
from Import i, Module source, Module target
where source.getName().matches("myproject.views%")
  and i.getAnImportedModuleName().matches("myproject.models.db%")
select i, "Views layer directly accesses database models"
```

CodeQL is proven at massive scale (GitHub runs it on millions of repositories) and outputs **SARIF JSON** — machine-parseable and usable as structured compliance reports. The limitation is licensing: free for open-source repos, but private repos require GitHub Code Security at **$19/month per active committer**. Custom queries require the CodeQL CLI, which is restricted to OSI-licensed codebases without a commercial license.

### Emerging knowledge graphs

Several tools released in 2025–2026 build knowledge graphs specifically designed for AI agent consumption:

**Axon** indexes codebases into structural knowledge graphs with Neo4j backend, MCP tools for AI agents (`query`, `context`, `impact` analysis), a web dashboard with force-directed graph visualization, and health scoring including coupling heatmaps and dead code reports. It analyzed 142 files in ~4.2 seconds.

**GitNexus** (1,200+ GitHub stars, trending February 2026) uses KuzuDB + tree-sitter to build knowledge graphs that run in-browser or via CLI, with 7 MCP tools including hybrid search and blast radius analysis. No server required.

**SCIP** (Sourcegraph's Code Intelligence Protocol) provides precise definition/reference maps via a Protobuf schema. The Python indexer (`scip-python`) is built on Pyright, producing type-aware navigation data. GitLab added Python SCIP support in v17.9 (2025).

---

## The 2026 landscape: MCP, AGENTS.md, and the shift to agentic exploration

Three developments in 2025–2026 have reshaped how AI agents interact with codebases.

**Model Context Protocol (MCP)**, launched by Anthropic in November 2024 and now under the Linux Foundation, has become the universal connector between AI agents and code analysis tools. Tens of thousands of MCP servers exist, with code-specific ones including RepoMapper (Aider-style maps), Augment Context Engine, Sourcegraph Deep Search, and graph-code (Memgraph-backed code graphs). The practical implication: any analysis tool that exposes an MCP interface can be consumed by Claude Code, Cursor, Cline, Codex, or any MCP-compatible agent.

**AGENTS.md** has emerged as the industry-standard format for providing persistent project context to AI agents, backed by Sourcegraph, OpenAI, Google, Cursor, and Factory under the Linux Foundation. It's a plain Markdown file at the repo root describing project structure, build commands, coding conventions, and architectural boundaries. **67% of AI coding teams** already use some variant (often as CLAUDE.md). Supported by Claude Code, Cursor, Copilot, Gemini CLI, Windsurf, Aider, Cline, and more. For compliance context, AGENTS.md can describe architectural rules that AI agents should follow, complementing programmatic enforcement.

**The shift from pre-indexed RAG to agentic exploration** is the most significant architectural trend. Continue.dev deprecated its `@Codebase` and `@Docs` context providers in favor of agent mode with MCP tools. Rather than pre-indexing everything into a vector database, agents dynamically explore codebases using search tools, file reading, and graph queries. This reduces stale-index problems and scales better to very large codebases, though it increases per-query latency.

---

## Ranked recommendations: the optimal toolchain

Based on maturity, scalability, AI readability, compliance capability, and ease of integration, here is the recommended layered approach — organized from quickest wins to deepest analysis.

### Tier 1 — Immediate CI integration (day one)

These tools are pip-installable, require minimal configuration, and run as pre-commit hooks or CI steps.

- **`import-linter`** for architectural boundary enforcement. Define layer contracts, forbidden dependencies, and module independence rules in `pyproject.toml`. Grimp's Rust engine handles 100k+ LOC in seconds. This alone catches the majority of modularity violations.
- **`vulture`** + **`deadcode`** for dead code detection. Run both: vulture for confidence-scored broad detection, deadcode for scope-aware precision. Combined false-positive rate is significantly lower than either alone.
- **`pydeps --show-deps`** for JSON dependency maps. The `--show-deps` flag outputs machine-readable JSON showing every module's imports and importers — directly consumable by AI agents or custom compliance scripts.

### Tier 2 — AI context generation (week one)

- **Aider RepoMap approach** (via Aider directly or RepoMapper MCP server) for generating compact, PageRank-ranked codebase summaries. The tree-sitter + graph ranking pipeline produces the most information-dense context format proven in LLM benchmarks. Configure `--map-tokens` based on your model's context window.
- **AGENTS.md** at repo root and per-package for persistent architectural context. Describe module boundaries, dependency rules, coding conventions, and domain terminology. This file is read by every major AI coding agent and costs nothing to maintain.
- **Structured Markdown or YAML** as the output format for any custom code map generation. Avoid JSON unless downstream tooling strictly requires it.

### Tier 3 — Deep analysis and knowledge graphs (month one)

- **PyTestArch** or **pytest-archon** for executable architecture tests that go beyond import-linter's declarative contracts — custom predicates, submodule-aware matching, and integration with existing pytest infrastructure.
- **CodeQL** for custom compliance queries with data-flow awareness. Write QL queries for patterns import-linter can't express (e.g., "no function in module X should call `os.system()` with user-provided arguments"). Free for open-source projects.
- **Axon** or **GitNexus** for AI-queryable knowledge graphs with MCP integration. These provide graph-based codebase exploration (blast radius analysis, coupling heatmaps, impact queries) that AI agents can use dynamically rather than requiring pre-computed maps.

### Tier 4 — Enterprise-scale or security-critical (quarter one)

- **Joern/cpggen → Neo4j** for full Code Property Graph analysis when you need data-flow tracking, taint analysis, or vulnerability detection alongside architectural compliance. Export CPG slices as JSON for AI consumption.
- **Sourcegraph Cody Enterprise** or **Augment Code Context Engine** (via MCP) for the most advanced commercial codebase understanding, supporting 300k+ repos and multi-million LOC monorepos.
- **Greptile** for graph-based AI code review with full repository context, processing ~1 billion LOC/month with an **82% bug catch rate** in benchmarks.

### The minimum viable pipeline

For a team that wants to start today with maximum impact and minimum overhead, this three-command pipeline covers both compliance and AI context:

```bash
# 1. Architectural compliance (CI gate)
lint-imports                                    # import-linter with contracts in pyproject.toml

# 2. Dead code detection (CI warning)  
vulture src/ --min-confidence 80 --sort-by-size # confidence-scored dead code

# 3. AI-readable code map (artifact)
# Use Aider's RepoMap or the RepoMapper MCP server
aider --map-tokens 4096 --show-repo-map         # generates PageRank-ranked code map
```

This pipeline runs in under 30 seconds on a 100k LOC codebase, integrates with any CI system, and produces both enforceable compliance gates and a compact AI-readable representation. From there, layer in graph-based analysis and knowledge graph tools based on the depth of analysis your team requires.

## Conclusion

The field has converged on a clear architectural pattern: **tree-sitter for parsing, graph algorithms for ranking, and MCP for AI agent access**. The most important insight from this research is that no single tool solves both compliance enforcement and AI context generation — but a surprisingly thin pipeline of three to four open-source tools covers 80% of use cases. `import-linter` is uniquely effective for Python architectural compliance because its Rust-powered import graph catches transitive violations that simpler tools miss. For AI context, Aider's PageRank-based RepoMap remains unmatched in information density per token. The fastest-moving frontier is knowledge graphs with MCP interfaces (Axon, GitNexus), which enable AI agents to *query* codebase structure on demand rather than consuming a static map — a paradigm shift from pre-computed artifacts to live, interactive code understanding.