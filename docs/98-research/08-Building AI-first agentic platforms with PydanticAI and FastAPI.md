# Building AI-first agentic platforms with PydanticAI and FastAPI

**AI agents are now primary API consumers, yet only 24% of developers design APIs with agents in mind.** The emerging architecture for AI-first platforms centers on a three-protocol stack — MCP for tool access, A2A for agent collaboration, and AGENTS.md for discovery — unified through a shared service layer that serves both machines and humans without duplicating business logic. PydanticAI v1.0 (released September 2025) provides the type-safe orchestration backbone, while durable execution frameworks like Temporal handle the hard problems of long-running, interruptible agent workflows. This report synthesizes the current state of the art across interface design, orchestration, human-in-the-loop patterns, DRY architecture, communication standards, and real-world implementations.

---

## Designing interfaces that AI agents can actually use

The fundamental shift in AI-first platform design is treating machine legibility as the primary concern. The 2025 Postman State of the API Report found that **89% of developers use generative AI daily**, but most APIs remain optimized for human consumption — vague descriptions, inconsistent error formats, and interactive prompts that break agent workflows entirely.

**Self-describing APIs via OpenAPI 3.0+** form the foundation. Every endpoint, parameter, request body, and response format must be fully defined with `description` fields that explain not just *what* an endpoint does but *why* — helping agents decide which endpoint to use. Structured error responses following RFC 7807/9457 should include machine-readable error codes (`INVALID_TOKEN`, `RATE_LIMIT_EXCEEDED`), a `retryable` boolean, explicit recovery hints, and `retry_after` headers. AI agents cannot infer missing context the way human developers do.

Two new discovery standards have emerged. **`llms.txt`**, proposed by Jeremy Howard in September 2024, is a Markdown file at `/llms.txt` that curates documentation with plain-text links and one-sentence descriptions — agents fetch it once to understand a platform's shape. **`AGENTS.md`**, launched by OpenAI in August 2025, provides project-specific instructions and context for AI coding agents; it has been adopted by over **60,000 open-source projects** and every major coding agent (Cursor, Claude Code, Copilot, Gemini CLI, Devin).

For CLIs, Nikola Balić's nine principles of AI-native CLI design (February 2026) capture the consensus: default to structured JSON output via a universal envelope (`schema_version`, `command`, `status`, `data`, `errors`, `warnings`), make success and failure unambiguous through deterministic exit codes (0 = success, 1-2 = correctable errors, 3-125 = application-specific), and avoid interaction traps by providing `--yes`, `--non-interactive`, and `--quiet` flags. The **AWS CLI v2 pager incident** — where changing the default pager to `less` broke thousands of CI jobs — remains a cautionary tale about interactive defaults. Every mandatory prompt, spinner, or browser redirect is a potential breakpoint for an AI agent.

Security deserves explicit attention: 51% of developers cite unauthorized agent calls as their top concern, with 49% worried about agents accessing sensitive data. The recommendations are agent identification and segmentation, behavioral-aware rate limiting, least-privilege API keys with short lifetimes, and real-time anomaly detection.

---

## The three-protocol stack converging under Linux Foundation governance

The agent communication ecosystem has converged rapidly around a complementary three-layer architecture, with all major standards now governed by the Linux Foundation's **Agentic AI Foundation (AAIF)**, co-founded in December 2025 by Anthropic, OpenAI, and Block, with AWS, Google, Microsoft, Cloudflare, and Bloomberg as supporting members.

**Model Context Protocol (MCP)** handles the agent-to-tool layer. Launched by Anthropic in November 2024, MCP has become the de facto standard for connecting AI agents to external tools and data sources. It uses JSON-RPC 2.0 over stdio, SSE, or HTTP transports. By late 2025, the ecosystem reached **97 million monthly SDK downloads**, over **10,000 published MCP servers**, and adoption across Claude, ChatGPT, Copilot, Gemini, Cursor, VS Code, and JetBrains IDEs. The November 2025 spec update added OAuth 2.1 authorization, async operations, and a community registry. In Python, **FastMCP** (by Prefect's Jeremiah Lowin) powers roughly 70% of MCP servers across all languages and offers one-line FastAPI integration: `FastMCP.from_fastapi(app)`. The alternative **fastapi-mcp** package auto-generates an MCP server from existing FastAPI endpoints with `FastApiMCP(app).mount()`.

**Google's Agent2Agent (A2A) protocol** covers agent-to-agent collaboration. Unveiled at Google Cloud Next in April 2025 with 50+ launch partners and contributed to the Linux Foundation in June 2025, A2A enables agents to discover each other via **Agent Cards** (JSON capability manifests), negotiate capabilities, and collaborate without revealing internal state. It uses JSON-RPC 2.0 over HTTP with SSE streaming. Version 0.3 added gRPC support and signed security cards. Over **150 organizations** now support A2A. The official recommendation is clear: use MCP for tools, A2A for agents.

**Agent Client Protocol (ACP)** by Zed Industries standardizes how AI coding agents communicate with editors and IDEs — analogous to what LSP did for language servers. Launched in August 2025, it uses newline-delimited JSON over stdin/stdout for bidirectional, streaming, stateful sessions. Claude Code, Codex CLI, Gemini CLI, and many other agents support it, with editor integration in Zed, Neovim, and Marimo. The relationship to MCP: "MCP handles the *what* (tools/data), ACP handles the *where* (where the agent lives in your workflow)."

IBM's Agent Communication Protocol (also abbreviated ACP) has been **merged into A2A** under the Linux Foundation, with users advised to migrate. OpenAI has adopted a multi-standard strategy rather than creating a competing protocol — supporting MCP across its Agents SDK, co-founding the AAIF, and releasing AGENTS.md for discovery.

| Protocol | Primary use | Traction | Governance |
|----------|------------|----------|------------|
| **MCP** | Agent → tools/data | De facto standard; 97M monthly downloads | AAIF / Linux Foundation |
| **A2A** | Agent → agent | Rapidly growing; 150+ orgs | Linux Foundation |
| **ACP (Zed)** | Agent → editor/IDE | Growing fast in coding tools | Zed Industries |
| **AGENTS.md** | Agent discovery/context | 60K+ projects | AAIF / Linux Foundation |

For an AI-first platform built with PydanticAI and FastAPI, the practical recommendation is: **expose capabilities via MCP first** (using FastMCP or fastapi-mcp), **add A2A Agent Cards** if other agents need to discover and collaborate with your platform, and **include AGENTS.md and llms.txt** for coding agent discovery.

---

## PydanticAI orchestration from simple delegation to durable graphs

PydanticAI v1.0, released September 2025, brings the "FastAPI feeling" to agent development. Built by the same team behind Pydantic (used by the OpenAI SDK, Anthropic SDK, and LangChain), it provides fully generic `Agent[DepsType, OutputType]` with IDE autocompletion, static type checking, and automatic structured output validation. The framework supports 15+ LLM providers and has native MCP, A2A, and AG-UI protocol support.

The official documentation defines **five escalating levels of multi-agent complexity**, and the core advice is to start simple and escalate only when needed:

**Level 1 — Single agent** handles everything. **Level 2 — Agent delegation** uses tools to call other agents. This is PydanticAI's primary recommended pattern: a parent agent invokes a child agent within a `@agent.tool` function, optionally using different models for each and sharing usage tracking via `ctx.usage`. **Level 3 — Programmatic hand-off** lets application code route between agents based on structured output (e.g., a triage agent returns a route enum, and Python `if/elif` logic dispatches to the appropriate specialist). **Level 4 — Graph-based control flow** uses `pydantic-graph`, a standalone async graph/FSM library where nodes define edges via return type hints. This is reserved for complex cases where standard control flow becomes spaghetti. **Level 5 — Deep Agents** provide autonomous planning, file operations, task delegation, and sandboxed execution.

For parallel fan-out/fan-in, the pattern is straightforward — `asyncio.gather` over multiple agent runs:

```python
tasks = [worker.run(f"Write section {s.name}") for s in sections]
completed = await asyncio.gather(*tasks)
```

The dependency injection system mirrors FastAPI's: a `RunContext[DepsType]` provides typed access to dependencies (database connections, HTTP clients, configuration) across tools, system prompts, and validators. Dependencies are provided at runtime via `agent.run('prompt', deps=my_deps)`.

**Compared to alternatives**, PydanticAI is the fastest in execution benchmarks (ahead of OpenAI Agents SDK, LlamaIndex, AutoGen, LangGraph, and Google ADK per NextBuild 2025 tests). LangGraph offers more mature graph-based orchestration with built-in checkpointing, but is heavier and has a steeper learning curve. CrewAI provides richer out-of-the-box multi-agent collaboration (roles, tasks, memory), but PydanticAI offers stronger type safety and structured output guarantees. The OpenAI Agents SDK is lightweight and tightly integrated with OpenAI's ecosystem, but PydanticAI is model-agnostic with broader provider support.

The integration with FastAPI is natural — shared Pydantic models serve as the contract between API endpoints and agent output types. A `SupportOutput(BaseModel)` defined once becomes both the agent's `output_type` and the FastAPI endpoint's `response_model`. PydanticAI provides `AGUIApp` and `VercelAIAdapter` classes for streaming agent responses through FastAPI via SSE.

---

## Pausing agents to ask humans (or smarter AIs) for decisions

Long-running agentic workflows inevitably need to stop and wait — for human approval, for a smarter model's judgment, or for an external event. The architectural challenge is making the pause/resume mechanism agnostic to *who* responds.

PydanticAI provides **deferred tool calls**: tools flagged for approval pause execution and return a `DeferredToolRequest`. The caller decides whether to approve (`ToolApproved`) or deny (`ToolDenied`) before execution continues. The `agent.iter()` method enables stepping through execution node-by-node for manual control. For graph-based workflows, `pydantic_graph` supports `FullStatePersistence` for interrupt/resume at any node.

The key abstraction for responder-agnostic design is a **structured decision protocol**:

```python
@dataclass
class DecisionRequest:
    action: str                    # What the agent wants to do
    parameters: dict               # Tool call arguments
    context: str                   # Why it's asking
    allowed_decisions: list[str]   # ["approve", "reject", "edit"]

@dataclass
class DecisionResponse:
    decision: str                  # "approve" | "reject" | "edit"
    modified_params: dict | None   # For "edit" decisions
    reason: str | None
```

This same interface works identically whether a human responds (via Slack interactive message buttons, a web UI POST, or email approve/reject links) or another AI agent responds (treating the `DecisionRequest` as a prompt with structured output). The transport layer — Temporal Signals, DBOS `send/recv`, Hatchet `UserEventCondition`, or a plain FastAPI webhook — carries the response without caring about its origin.

For durable execution, PydanticAI has **native integrations with three frameworks**:

- **Temporal** (`TemporalAgent`): The most battle-tested option, used by OpenAI for Codex. Wraps all agent I/O as Activities with deterministic replay from crash points. Supports workflows that "sleep for a week" or "pause until approval" via Signals. Requires running Temporal Server — higher operational complexity but unmatched durability for workflows spanning days or months.

- **DBOS** (`DBOSAgent`): Minimal infrastructure — backed only by Postgres, no separate orchestration server. Uses `DBOS.recv()` / `DBOS.send()` for inter-workflow communication and human-in-the-loop. Ideal for teams that want durable execution without Temporal's operational overhead.

- **Prefect** (`PrefectAgent`): Wraps agent runs as Prefect flows with task caching that prevents re-running completed LLM calls on retry. Best monitoring dashboard of the three, familiar to data engineering teams.

A practical escalation ladder for risk-based approval: auto-approve read-only operations, require approval for state-modifying operations, and escalate high-risk actions (e.g., payments over a threshold) to human review regardless. This mirrors Microsoft Agent Framework's recommended phased rollout approach.

---

## One codebase, many consumers: the DRY architecture

The central DRY principle for an AI-first platform: **business logic lives exclusively in a service layer, never in handlers, CLI commands, or BFF layers**. This architecture, battle-tested at Rubin Observatory's SQuaRE team across multiple production FastAPI applications, follows a strict layering:

```
[Human Browser]  →  [Web BFF / HTML]     →
[AI Agent]       →  [Agent BFF / JSON]   →  [Service Layer]  →  [Storage]  →  [DB]
[CLI User/AI]    →  [CLI Layer / text+json] →
```

The **service layer** contains all validation, authorization, business rules, and orchestration. Handlers are thin — they parse requests, call services, and format responses. Storage contains zero business logic, only data translation. **Pydantic models serve as the universal contract** between all layers: they auto-serialize to JSON for AI agents and provide template context dictionaries for human-rendered views.

Content negotiation determines response format without duplicating logic. Three strategies work with FastAPI:

- **Accept header** (HTTP standard): `if "application/json" in request.headers.get("accept", "")` returns JSON; otherwise returns HTML via Jinja2 templates
- **Query parameter**: `?format=json` for explicit format selection
- **Separate router prefixes**: `/api/v1/projects/{id}` for JSON, `/web/projects/{id}` for HTML — both calling the same service method

Michael Douglas Barbosa Araujo's **Backend-for-Agents (BFA) pattern** extends the classic BFF specifically for AI consumers. The BFA introduces an intermediate layer that encapsulates APIs, enforces policies, translates data between formats, and exposes stable operations via MCP. This prevents agents from coupling directly to domain APIs and duplicating business rules.

For CLIs, the same service layer is called directly from Typer/Click commands with a `--format json` flag for structured output and a human-readable table (via Rich) as the default. The critical implementation detail: CLI commands and FastAPI endpoints share identical service initialization via factory functions or dependency injection.

```python
# Both API handler and CLI command call this
service = ProjectService(storage=ProjectStorage(session), notifier=NotificationService())
project = await service.create_project(ProjectCreate(name=name))
```

FastAPI's dependency injection naturally supports this via `Depends()` chains: Settings → Repository → Service → Handler. The same chain can be replicated in CLI commands using a factory function.

---

## Practical implementations proving these patterns work

Several production-quality open-source projects demonstrate these patterns concretely:

**PydanticAI + Temporal dinner bot** (github.com/pydantic/pydantic-ai-temporal-example) shows durable multi-agent coordination with a Slack bot: a dispatcher agent classifies intent, a researcher agent performs deep analysis, and Temporal workflows orchestrate the handoff with automatic retry and state preservation. This is the reference implementation for durable AI agents.

**FastAPI Agents** (github.com/blairhudson/fastapi-agents) provides a drop-in extension for serving PydanticAI, LlamaIndex, CrewAI, or Smolagents as REST APIs with minimal code — `agents.register("pydanticai", agent)` and `app.include_router(agents)`.

**FastMCP** (gofastmcp.com) powers ~70% of MCP servers across all languages. Its `FastMCP.from_fastapi(app)` method converts existing FastAPI applications into MCP servers in one line — the most practical path for exposing existing Python platforms to AI agents.

The Appunite Tech Blog's detailed walkthrough ("Building an API for Your Pydantic-AI Agent with FastAPI") demonstrates thread-based conversation management with both blocking and streaming endpoints, API key auth, and modular architecture. The Gel Blog's "Missing Piece" article shows a three-agent system (talker, extractor, summarizer) with database-triggered orchestration and long-term memory management.

For A2A integration, a DEV Community tutorial demonstrates FastAPI + PydanticAI + A2A using JSON-RPC endpoints, with a grammar correction agent as the example. CopilotKit's full-stack stock portfolio agent shows PydanticAI backend + Next.js frontend connected via AG-UI protocol with human-in-the-loop approval.

Notable conference talks from 2025 include Jason Kim (Anthropic) on "MCP as a Foundational Protocol for Agents" and Chitra Venkatesh (Google) on "A2A: The Future of AI Agent Collaboration" at the Berkeley Agentic AI Summit (August 2025, sold out), plus the AI Engineer Summit's "Agents at Work" theme.

---

## Conclusion: a concrete architecture for AI-first platforms

The architecture crystallizing in early 2026 is remarkably coherent. PydanticAI provides the typed, model-agnostic agent layer with five levels of orchestration complexity to choose from. FastAPI serves as the unified backend, using content negotiation and the BFA pattern to serve both AI and human consumers from a single service layer. MCP exposes platform capabilities to any AI agent via FastMCP's one-line integration. A2A enables agent-to-agent discovery and collaboration. Temporal (or DBOS for lighter infrastructure) provides durable execution for long-running workflows with responder-agnostic human-in-the-loop via structured decision protocols.

The most actionable insight is architectural: **start with agent delegation via PydanticAI tools, expose capabilities via MCP, and keep business logic in a shared service layer with thin adapters for each consumer type.** Escalate to graph-based orchestration and durable execution only when workflow complexity demands it. The standards ecosystem has converged enough that betting on MCP + A2A under Linux Foundation governance is a safe choice. The biggest risk is over-engineering — the frameworks now handle enough complexity that simple patterns (delegation, `asyncio.gather`, content negotiation) solve most real-world cases without reaching for heavy abstractions.