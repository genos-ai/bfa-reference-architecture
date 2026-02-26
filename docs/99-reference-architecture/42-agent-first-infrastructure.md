# 42 - Agent-First Infrastructure (Optional Module)

*Version: 1.1.0*
*Author: Architecture Team*
*Created: 2026-02-20*

## Changelog

- 1.1.0 (2026-02-24): Added Secure by Default principle (startup invariants, fail-closed enforcement), DM pairing protocol for messaging channels, channel-level rate limiting; references 44-multi-channel-gateway.md
- 1.0.0 (2026-02-20): Initial agent-first infrastructure standard — MCP server integration, A2A protocol, agent identity, intent APIs, agent-discoverable endpoints, observability, testing, security

---

## Module Status: Optional

This module is **optional**. Adopt when your project:
- Needs to expose capabilities for consumption by external AI agents
- Requires interoperability with agents outside your system (A2A protocol)
- Needs agent-grade identity beyond API keys and JWT (delegation chains, workload identity)
- Wants to make its API surface agent-discoverable via standard protocols

**Dependencies**: This module requires **03-backend-architecture.md** (FastAPI app where MCP is mounted) and **05-authentication.md** (extended with agent identity layers).

**Relationship to 40/41**: This module is independent of 40-agentic-architecture.md and 41-agentic-pydanticai.md. Those documents define how to build and run internal agents. This document defines how external agents discover, authenticate with, and consume your platform — and how your agents interoperate with agents you don't control. Adopt 40+41 for internal agent orchestration. Adopt this module for external agent interoperability. Adopt both for a full agent-native platform.

---

## Context

Traditional APIs are designed for human-driven clients: browsers, mobile apps, CLIs. AI agents are fundamentally different consumers — they discover capabilities programmatically, delegate tasks across trust boundaries, operate at machine speed, and need structured recovery paths when operations fail. An API that works well for a React frontend may be unusable for an autonomous agent that cannot interpret a bare HTTP 400 or navigate a multi-step CRUD workflow.

The agent ecosystem is converging on two complementary open protocols, both now governed by the Linux Foundation's Agentic AI Foundation (AAIF): **MCP** (Model Context Protocol) for agent-to-tool communication, and **A2A** (Agent-to-Agent Protocol) for inter-agent collaboration. Together with agent-discoverable metadata (`/.well-known/agent.json`, `llms.txt`), intent-based API design, structured error recovery, and cryptographic agent identity, these form the infrastructure layer that makes a platform agent-native.

This module defines how to add that layer to the existing FastAPI architecture without restructuring the backend.

---

## Protocol Stack

Two protocols serve different axes of agent communication. Both are required for a complete agent-first platform; either can be adopted independently.

| Protocol | Purpose | Analogy | Specification |
|----------|---------|---------|---------------|
| **MCP** (Model Context Protocol) | Agent-to-tool communication (vertical) | USB-C for AI — universal tool connector | Anthropic, now AAIF. Python SDK `mcp` v1.26+. Pin `mcp>=1.25,<2` until v2.0 ships. |
| **A2A** (Agent-to-Agent Protocol) | Agent-to-agent collaboration (horizontal) | SMTP for agents — inter-agent messaging | Google, now AAIF. Python SDK `a2a-sdk`. Version 0.3, RC 1.0 in progress. |

**MCP** defines how an agent discovers and invokes your tools and reads your data. Your platform is the **MCP server**; the external agent's runtime is the **MCP client**.

**A2A** defines how agents discover each other via Agent Cards, delegate tasks with full lifecycle management, and exchange structured artifacts. Your platform publishes an **Agent Card** and accepts **A2A tasks** from external agents.

**MCP and A2A are complementary, not competing.** An agent uses MCP internally to access tools and data. It uses A2A externally to collaborate with other agents. In enterprise architecture, agents expose A2A interfaces to the outside world while using MCP internally.

---

## MCP Server Integration

### Core Concepts

MCP servers expose two primitive types:

| Primitive | HTTP Equivalent | Side Effects | Use When |
|-----------|----------------|--------------|----------|
| **Tool** | POST/PUT/DELETE | Yes | Agent needs to create, update, or delete data |
| **Resource** | GET | No | Agent needs to read data |

Tools map to service-layer methods that mutate state. Resources map to read-only queries. This aligns directly with the existing service layer in `modules/backend/services/`.

### Building an MCP Server

Use the **FastMCP** high-level API with `stateless_http=True` for horizontal scaling across replicas:

```python
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

mcp = FastMCP("NotesService", stateless_http=True, json_response=True)


@mcp.tool()
async def create_note(title: str, content: str | None = None) -> dict:
    """Create a new note with a title and optional content.
    Returns the created note with its generated ID."""
    from modules.backend.core.database import get_db_session
    from modules.backend.services.note import NoteService
    from modules.backend.schemas.note import NoteCreate

    async for session in get_db_session():
        service = NoteService(session)
        note = await service.create_note(NoteCreate(title=title, content=content))
        return {"id": note.id, "title": note.title, "created_at": note.created_at.isoformat()}


@mcp.resource("notes://{note_id}")
async def get_note(note_id: str) -> str:
    """Get a note by ID. Returns the note title and content."""
    from modules.backend.core.database import get_db_session
    from modules.backend.services.note import NoteService

    async for session in get_db_session():
        service = NoteService(session)
        note = await service.get_note(note_id)
        return f"Title: {note.title}\nContent: {note.content or '(empty)'}"
```

**Tools are thin adapters.** They call service methods. No business logic in MCP tool functions — the same rule as API endpoint handlers and PydanticAI tool functions (41-agentic-pydanticai.md).

### Structured Output via Pydantic

MCP supports structured output using Pydantic models (spec revision 2025-06-18). Reuse existing schemas from `modules/backend/schemas/`:

```python
from modules.backend.schemas.note import NoteResponse

@mcp.tool()
async def get_note_structured(note_id: str) -> NoteResponse:
    """Get a note by ID. Returns validated structured data."""
    from modules.backend.core.database import get_db_session
    from modules.backend.services.note import NoteService

    async for session in get_db_session():
        service = NoteService(session)
        note = await service.get_note(note_id)
        return NoteResponse.model_validate(note)
```

### Mounting on Existing FastAPI Application

Mount MCP servers on the existing FastAPI app in `modules/backend/main.py`. Each domain gets its own mount path:

```python
from modules.mcp.notes import mcp as notes_mcp
from modules.mcp.health import mcp as health_mcp

def create_app() -> FastAPI:
    app = FastAPI(...)

    # Existing REST routes
    app.include_router(health.router, tags=["health"])
    app.include_router(api_v1_router, prefix="/api/v1")

    # MCP servers — one per domain
    if app_config.features.get("mcp_enabled"):
        app.mount("/mcp/notes", notes_mcp.streamable_http_app())
        app.mount("/mcp/health", health_mcp.streamable_http_app())

    return app
```

**Streamable HTTP** (introduced March 2025) is the production transport — a single endpoint per mount supporting bidirectional communication, server-initiated notifications via SSE, and compatibility with standard load balancers.

### Wrapping Existing REST APIs as MCP Tools

For APIs that already exist as REST endpoints, wrap them using `httpx.AsyncClient` rather than duplicating service-layer calls:

```python
import httpx
from mcp.server.fastmcp import FastMCP
from modules.backend.core.config import get_app_config

mcp = FastMCP("LegacyBridge", stateless_http=True, json_response=True)


@mcp.tool()
async def list_notes(limit: int = 50, include_archived: bool = False) -> dict:
    """List notes with optional filtering. Returns paginated results."""
    server = get_app_config().application["server"]
    base_url = f"http://{server['host']}:{server['port']}"
    async with httpx.AsyncClient(base_url=base_url) as client:
        resp = await client.get(
            "/api/v1/notes",
            params={"limit": limit, "include_archived": include_archived},
        )
        resp.raise_for_status()
        return resp.json()
```

Use this pattern for rapid MCP exposure of existing endpoints. Prefer direct service-layer calls for new MCP tools (avoids the HTTP round-trip).

### MCP Authentication

The MCP authorization specification classifies MCP servers as **OAuth 2.0 Resource Servers**. Requirements:

- Mandatory PKCE for all clients
- RFC 9728 Protected Resource Metadata at `/.well-known/oauth-protected-resource`
- RFC 8707 Resource Indicators for audience binding
- Strict token audience validation
- MCP servers **must not** pass client tokens through to upstream APIs (prevents confused deputy attacks)

Extend the existing JWT authentication from **05-authentication.md** with MCP-specific audience validation:

```python
from modules.backend.core.security import decode_token
from modules.backend.core.exceptions import AuthenticationError


def validate_mcp_token(token: str, expected_audience: str) -> dict:
    """Validate an MCP request token with audience checking."""
    payload = decode_token(token)
    if payload.get("aud") != expected_audience:
        raise AuthenticationError("Token audience mismatch")
    return payload
```

---

## A2A Protocol Integration

### Agent Cards

Every A2A-capable service publishes a JSON metadata document at `/.well-known/agent.json`. This is how external agents discover your platform's capabilities:

```json
{
  "name": "BFF Application Agent",
  "version": "0.1.0",
  "url": "https://your-domain.com/a2a/",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false
  },
  "skills": [
    {
      "id": "note_management",
      "name": "Note Management",
      "description": "Create, read, update, delete, archive, and search notes",
      "tags": ["notes", "crud", "search"],
      "inputModes": ["application/json"],
      "outputModes": ["application/json"]
    }
  ],
  "securitySchemes": {
    "oauth2": {
      "type": "oauth2",
      "flows": {
        "clientCredentials": {
          "tokenUrl": "https://your-domain.com/auth/token",
          "scopes": {
            "notes:read": "Read notes",
            "notes:write": "Create and modify notes"
          }
        }
      }
    }
  }
}
```

Auto-generate the Agent Card from registered capabilities rather than maintaining it manually. Serve it from the FastAPI app:

```python
from fastapi import APIRouter
from modules.backend.core.config import get_app_config

router = APIRouter()


@router.get("/.well-known/agent.json")
async def agent_card() -> dict:
    """A2A Agent Card — auto-generated from registered capabilities."""
    config = get_app_config()
    app = config.application
    a2a = config.a2a

    return {
        "name": app["name"],
        "version": app["version"],
        "url": a2a["base_url"],
        "capabilities": a2a["capabilities"],
        "skills": a2a["skills"],
        "securitySchemes": a2a["security_schemes"],
    }
```

### Task Lifecycle

A2A tasks progress through **9 states**: `submitted → working → completed` for simple flows, with `input-required` and `auth-required` interrupt states for human-in-the-loop patterns. Terminal states (`completed`, `failed`, `canceled`, `rejected`) are immutable — critical for audit compliance.

This aligns with the AgentTask states in **40-agentic-architecture.md** if both modules are adopted.

### A2A Server Implementation

Use the official SDK mounted on the existing Starlette/FastAPI application:

```python
from a2a.server.agent_execution import AgentExecutor
from a2a.server.events import EventQueue
from a2a.server.apps.starlette import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill
from a2a.utils import new_agent_text_message


class NoteAgentExecutor(AgentExecutor):
    """Executes A2A tasks by delegating to the note service layer."""

    async def execute(self, context, event_queue: EventQueue):
        from modules.backend.core.database import get_db_session
        from modules.backend.services.note import NoteService

        async for session in get_db_session():
            service = NoteService(session)
            # Parse the task input and delegate to service
            result = await self._process_task(service, context)
            await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context, event_queue: EventQueue):
        await event_queue.enqueue_event(
            new_agent_text_message("Task cancelled")
        )
```

Mount the A2A application alongside the FastAPI app, gated by feature flag:

```python
if app_config.features.get("a2a_enabled"):
    a2a_app = build_a2a_application(agent_card, handler)
    app.mount("/a2a", a2a_app.build())
```

---

## Agent-Discoverable Endpoints

### `/.well-known/agent.json`

The A2A Agent Card (defined above). Auto-generated from configuration. This is the agent equivalent of DNS — it tells external agents what your platform can do and how to authenticate.

### `/llms.txt` and `/llms-full.txt`

Machine-readable documentation endpoints that reduce token usage by **90%+** compared to HTML crawling. Serve from the FastAPI app:

```python
@router.get("/llms.txt", response_class=PlainTextResponse)
async def llms_txt() -> str:
    """LLM-consumable site overview."""
    config = get_app_config()
    return f"""# {config.application['name']}

> {config.application['description']}

## API Documentation
- [REST API](/docs): OpenAPI documentation
- [MCP Tools](/mcp/notes): Note management tools (MCP protocol)

## Endpoints
- /api/v1/notes: Note CRUD operations
- /health: Health checks
- /mcp/notes: MCP server for note tools
- /.well-known/agent.json: A2A Agent Card
"""
```

`/llms-full.txt` contains the complete API documentation compiled into a single Markdown file. Generate it at build time from OpenAPI specs rather than maintaining manually.

### `AGENTS.md`

Already present at the project root per existing conventions. Formalize: every project adopting this module must maintain an `AGENTS.md` that includes MCP tool listings, A2A skill descriptions, and authentication instructions for agent consumers.

---

## Intent and Planning API Patterns

### When to Use Intent APIs

Traditional CRUD requires agents to orchestrate multiple calls to achieve a single business outcome. **Intent APIs** collapse this into a single declarative call:

```
# CRUD: agent must orchestrate 3 calls
POST /api/v1/notes         (create note)
PATCH /api/v1/notes/{id}   (update with content)
POST /api/v1/notes/{id}/archive  (archive)

# Intent: single call expressing desired outcome
POST /api/v1/intents/organize-notes
{
  "action": "archive_old_notes",
  "criteria": {"older_than_days": 30, "is_archived": false}
}
```

Add intent endpoints alongside existing CRUD routes, not as replacements. CRUD endpoints remain for human-driven clients; intent endpoints serve agent consumers.

### Planning APIs

For destructive or multi-step operations, **Planning APIs** propose an execution plan before committing:

```
POST /api/v1/plans/bulk-archive
{"criteria": {"older_than_days": 30}}

# Response: reviewable plan
{
  "plan_id": "PLAN-001",
  "steps": [
    {"step": "identify_notes", "count": 15, "status": "computed"},
    {"step": "archive_notes", "status": "pending_confirmation"}
  ],
  "warnings": ["This will archive 15 notes permanently"],
  "confirm_url": "/api/v1/plans/PLAN-001/confirm"
}
```

The agent inspects the plan, then confirms or abandons. This is the API equivalent of the HITL approval gates in **40-agentic-architecture.md**.

### Structured Errors with Recovery Hints

Standard HTTP errors are opaque to agents. Extend the existing `ErrorResponse` from **09-error-codes.md** with agent-consumable recovery fields:

```python
class AgentErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    suggestions: list[str] | None = None
    retry_strategy: dict[str, str] | None = None
    doc_uri: str | None = None
```

Example error response with recovery hints:

```json
{
  "success": false,
  "error": {
    "code": "RES_NOT_FOUND",
    "message": "Note not found",
    "detail": "Note ID 'abc-999' does not exist",
    "suggestions": ["abc-001", "abc-002", "abc-003"],
    "retry_strategy": {
      "action": "search_notes",
      "endpoint": "/api/v1/notes/search?q=abc"
    },
    "doc_uri": "https://docs.example.com/errors/RES_NOT_FOUND"
  }
}
```

The `suggestions` field provides valid alternatives. The `retry_strategy` tells the agent exactly what to try next. The `doc_uri` points to machine-readable documentation about the error. These fields are optional — they enhance existing error responses without breaking backward compatibility.

---

## Agent Identity Architecture

The existing authentication stack (**05-authentication.md**) covers human-era patterns: API keys, JWT, sessions. Agent identity requires three additional layers for autonomous, delegating, non-deterministic actors.

### Layer 1: Workload Identity (SPIFFE/SPIRE)

**SPIFFE** (CNCF graduated) provides every agent a cryptographic identity — a short-lived X.509 certificate (1-hour TTL, auto-rotated) tied to its runtime environment. No static secrets to manage.

Use when: agents run as workloads in Kubernetes, VMs, or multi-cloud and need zero-trust mutual authentication.

```bash
# Register an agent workload in SPIRE
spire-server entry create \
  -spiffeID spiffe://example.com/agents/note-processor \
  -parentID spiffe://example.com/k8s-node \
  -selector k8s:ns:ai-agents \
  -selector k8s:sa:note-processor-sa
```

### Layer 2: Token Delegation (Biscuit Tokens)

**Biscuit tokens** use Ed25519 public-key cryptography with Datalog-based authorization. The critical property: tokens can only be **attenuated** (narrowed), never expanded. An orchestrator mints a token and narrows its scope before passing to a sub-agent — offline, without contacting any server.

Use when: agents delegate tasks to sub-agents across trust boundaries and permissions must narrow at each hop.

```python
from biscuit_auth import BiscuitBuilder
from modules.backend.core.utils import utc_now
from datetime import timedelta

builder = BiscuitBuilder("""
    agent({agent_id});
    right({resource}, "read");
    check if time($time), $time < {expiration};
""", {
    'agent_id': 'note-processor-001',
    'resource': '/api/v1/notes',
    'expiration': utc_now() + timedelta(hours=1),
})
root_token = builder.build(private_key)

# Attenuate before delegating to sub-agent — read-only, specific prefix
attenuated = root_token.append("""
    check if resource($r), operation($op), ["read"].contains($op);
    check if resource($r), $r.starts_with("/api/v1/notes/active");
""")
```

### Layer 3: OAuth 2.1 Token Exchange (Delegation)

**RFC 8693 Token Exchange** enables agents to act on behalf of users with full delegation audit trails. The resulting JWT carries an `act` claim identifying the acting agent:

```json
{
  "sub": "user-12345",
  "aud": "https://api.example.com/notes",
  "scope": "notes:read notes:write",
  "act": {
    "sub": "agent:note-processor-001",
    "iss": "https://auth.example.com"
  }
}
```

Use when: an agent performs actions on behalf of a specific user and the audit trail must distinguish "user did this" from "agent did this on behalf of user."

### Adoption Guidance

| Scenario | Layers Needed |
|----------|---------------|
| Single-service, no delegation | Existing JWT from 05-authentication.md is sufficient |
| Multi-service agents in Kubernetes | Add Layer 1 (SPIFFE/SPIRE) |
| Agent delegation chains | Add Layer 2 (Biscuit) |
| Agent acting on behalf of users | Add Layer 3 (OAuth 2.1 Token Exchange) |
| Full enterprise agent platform | All three layers |

---

## Agent Gateway Patterns

An **agent gateway** is a reverse proxy that understands agentic protocols. Introduce a gateway when the platform runs multiple MCP servers, accepts external agent traffic, or needs protocol-level security enforcement.

### When to Introduce

- **Single MCP server, internal agents only**: no gateway needed — mount directly on FastAPI
- **Multiple MCP servers, mixed protocols**: gateway provides unified entry point
- **External agent traffic from untrusted sources**: gateway enforces authentication, rate limiting, DLP

### Core Capabilities

| Capability | Description |
|-----------|-------------|
| Protocol routing | Route MCP, A2A, and REST traffic to appropriate backends |
| Tool virtualization | Present a unified tool catalog from multiple MCP servers |
| Authentication enforcement | JWT/mTLS validation before requests reach MCP servers |
| Cost-aware rate limiting | Token-based budgets (1 unit = $0.001), not request counts |
| Policy engine | Fine-grained RBAC via Cedar or OPA |
| DLP enforcement | Prevent sensitive data exfiltration through agent workflows |

### Cost-Aware Rate Limiting

Traditional request-count limits fail for agents because one LLM-powered request can cost anywhere from $0.001 to $0.50. Implement **token-based rate limiting** using budget units:

| Tier | Per-Minute | Per-Hour | Per-Day |
|------|-----------|---------|---------|
| Free | 100 units | 1,000 units | 5,000 units |
| Standard | 1,000 units | 10,000 units | 50,000 units |
| Enterprise | 10,000 units | 100,000 units | 500,000 units |

Configure tiers in `config/settings/mcp.yaml` rather than hardcoding.

### Reference Implementation

Solo.io **agentgateway** (Rust, Linux Foundation, MIT license) is the leading open-source option:

```yaml
# agentgateway configuration
binds:
  - port: 3000
listeners:
  - routes:
    - backends:
      - mcp:
          targets:
            - name: notes-service
              sse:
                uri: http://localhost:8000/mcp/notes
            - name: health-service
              sse:
                uri: http://localhost:8000/mcp/health
```

Evaluate gateway introduction as traffic and security requirements grow. Do not introduce prematurely.

---

## Agent-Specific Observability

### OpenTelemetry GenAI Semantic Conventions

The **OpenTelemetry GenAI Semantic Conventions** (v1.37+, stable) provide standardized trace attributes for agent operations. These extend the existing structlog setup from **10-observability.md**.

```python
from opentelemetry import trace

tracer = trace.get_tracer("agents.infrastructure")


async def handle_mcp_tool_call(tool_name: str, params: dict):
    with tracer.start_as_current_span("agent.tool_call") as span:
        span.set_attribute("gen_ai.agent.id", params.get("agent_id", "unknown"))
        span.set_attribute("gen_ai.action.tool.name", tool_name)

        result = await execute_tool(tool_name, params)

        span.set_attribute("gen_ai.usage.input_tokens", result.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", result.output_tokens)
        return result
```

### Standard Attributes

| Attribute | Description | When Set |
|-----------|-------------|----------|
| `gen_ai.agent.id` | External agent identifier | Every MCP/A2A request |
| `gen_ai.request.model` | Model used by the calling agent | If provided in request metadata |
| `gen_ai.action.tool.name` | MCP tool being invoked | Every tool call |
| `gen_ai.usage.input_tokens` | Input tokens consumed | After tool execution |
| `gen_ai.usage.output_tokens` | Output tokens generated | After tool execution |
| `gen_ai.operation.name` | High-level operation type | Every span |

### Behavioral Baselining

Monitor agent consumers for anomalous behavior across three dimensions:

| Dimension | What to Baseline | Anomaly Signal |
|-----------|-----------------|----------------|
| API/tool usage patterns | Which tools each agent typically calls | Agent suddenly calling tools outside its normal set |
| Data access patterns | Volume and scope of data accessed | Agent accessing 10x normal data volume |
| Latency distributions | Typical response times per agent | Sudden latency changes suggesting different usage patterns |

AI agents move **16x more data** than human users (Obsidian Security, 2025). Behavioral monitoring is not optional for external agent traffic.

### Log Source

Agent infrastructure logs are written to `logs/system.jsonl` with `source="agents"` per **10-observability.md**.

---

## Agent-Specific Testing

### MCP Server Testing

Test MCP servers using the in-memory client — no HTTP, no network:

```python
import pytest
from mcp.client import Client
from modules.mcp.notes import mcp


@pytest.fixture
async def mcp_client():
    async with Client(transport=mcp) as client:
        yield client


@pytest.mark.asyncio
async def test_create_note_tool(mcp_client):
    result = await mcp_client.call_tool(
        "create_note",
        {"title": "Test Note", "content": "Test content"},
    )
    assert result.data["title"] == "Test Note"
    assert "id" in result.data


@pytest.mark.asyncio
async def test_get_note_resource(mcp_client):
    result = await mcp_client.read_resource("notes://note-id-123")
    assert "Title:" in result
```

### Behavioral Evaluation

Use **DeepEval** agentic metrics for evaluating agent interactions with your MCP tools:

| Metric | What It Measures |
|--------|-----------------|
| `TaskCompletionMetric` | Did the agent achieve the intended outcome? |
| `ToolCorrectnessMetric` | Did the agent call the right tools? |
| `ArgumentCorrectnessMetric` | Were the tool arguments valid? |
| `ToolCallOutputCorrectnessMetric` | Were tool outputs used correctly? |

### Red Teaming

Non-negotiable for any externally-exposed agent interface. Use **DeepTeam** (Apache 2.0) for automated adversarial testing covering agentic-specific vulnerabilities:

- DirectControlHijacking: attacker redirects agent to call unintended tools
- GoalRedirection: attacker changes the agent's objective via poisoned input
- MemoryPoisoning: attacker corrupts data that agents use for future decisions

Run red team evaluations as part of the CI/CD pipeline before deploying changes to MCP/A2A interfaces.

---

## Security

### OWASP Agentic Top 10 Mapping

The **OWASP Top 10 for Agentic Applications** (December 2025) defines the authoritative threat taxonomy. Map each risk to the platform's defenses:

| OWASP Risk | Platform Defense |
|-----------|-----------------|
| Agent Goal Hijacking | Guardrails decorator (41), input validation on MCP tools |
| Tool Misuse and Exploitation | Tool sandboxing — agents can only call explicitly registered tools |
| Identity and Privilege Abuse | Three-layer identity (this document), scope narrowing at each delegation hop |
| Excessive Agency | UsageLimits on every agent run (41), cost-aware rate limiting (this document) |
| Inadequate Guardrails | Prompt injection patterns in guardrails config, output validation |
| Poisoned Training Data | Not applicable at infrastructure level — model provider concern |
| Insufficient Monitoring | Behavioral baselining, OTel GenAI conventions (this document) |

### Confused Deputy Prevention

MCP servers **must not** forward client tokens to upstream APIs. The MCP server authenticates the client, then uses its own service credentials for backend calls. This prevents a compromised agent from leveraging MCP server authority to access backends it shouldn't reach.

### Agent Session Smuggling Prevention

Validate every A2A task message independently. Do not build accumulated trust based on conversation history — rogue agents exploit built-in trust relationships in multi-turn interactions.

### Secure by Default Principle

Every security boundary in the platform must **fail closed** when configuration is missing. The system must refuse to start rather than silently degrade to open access. This principle applies to all external interfaces — MCP endpoints, A2A endpoints, messaging channel webhooks, WebSocket connections, and REST APIs.

This addresses the most common vulnerability pattern in agent-first platforms (documented in [98-research/07](../98-research/07-Personal%20AI%20assistant%20architecture-%20lessons%20from%20OpenClaw%20for%20agent-first%20platforms.md)): when a security-relevant configuration value is missing or empty, the system defaults to allowing all access, and the developer never notices until the vulnerability is exploited.

**Startup invariants** (checked before the application accepts traffic):

| Invariant | Condition | Failure |
|-----------|-----------|---------|
| JWT secret strength | `JWT_SECRET` length ≥ `secrets_validation.jwt_secret_min_length` from `security.yaml` | Startup failure |
| API key salt strength | `API_KEY_SALT` length ≥ `secrets_validation.api_key_salt_min_length` from `security.yaml` | Startup failure |
| Webhook secrets | If a channel with webhooks is enabled, its secret must be non-empty | Startup failure |
| MCP authentication | If `mcp_enabled: true` in features, `authentication.required` must be `true` in `mcp.yaml` | Startup failure |
| A2A authentication | If `a2a_enabled: true` in features, `security_schemes` must be configured in `a2a.yaml` | Startup failure |
| Production safety | In `production` environment: `debug: false`, `api_detailed_errors: false`, `docs_enabled: false` | Startup failure |
| CORS origins | In `production` environment: CORS origins must not contain `localhost` when `cors.enforce_in_production: true` in `security.yaml` | Startup failure |
| Channel allowlists | If a channel is enabled with `default_policy: "allowlist"`, its allowlist must be non-empty | Startup failure |

These checks are implemented as a startup validation function called during FastAPI's lifespan initialization. Configuration for validation thresholds lives in `config/settings/security.yaml` under `secrets_validation`.

**Design rule**: No hardcoded fallback may weaken a security boundary. If a configuration value controls access (allowlists, secrets, rate limits), the absence of that value must result in denial, not permissiveness.

### DM Pairing for Messaging Channels

When the platform is exposed through messaging channels (Telegram, Slack, Discord, WhatsApp) via **[44-multi-channel-gateway.md](44-multi-channel-gateway.md)**, unknown senders must be authenticated before their messages reach the agent coordinator. Three policies are available, configured per channel in `config/settings/gateway.yaml`:

| Policy | Behavior | When to Use |
|--------|----------|-------------|
| `deny` | Unknown senders receive no response. Message logged and dropped silently. | Default. Production systems where all users are pre-configured. |
| `pairing` | Unknown senders receive a one-time code. Admin approves via CLI/API. Sender added to persistent allowlist. | Systems that need controlled onboarding of new users. |
| `allowlist` | Only senders in the configured allowlist can interact. All others denied. | Same as deny, but with explicit allowlist configuration. |

The **default policy is `deny`** — deploying with an empty allowlist results in a bot that responds to nobody. This is the correct posture for a system that has not been configured.

The pairing protocol:
1. Unknown sender messages through any channel
2. Gateway generates a short alphanumeric code with configurable TTL (stored in Redis)
3. Gateway responds: "Send this code to the admin to get access: `ABC123`"
4. Admin approves: `python cli.py --service approve-pairing --code ABC123`
5. Sender's channel-specific ID added to persistent allowlist
6. Subsequent messages processed normally

This pattern originates from messaging platform security practices and prevents the class of vulnerabilities where a public-facing bot processes messages from any sender — enabling prompt injection, resource exhaustion, and unauthorized access to agent capabilities.

For the full gateway security implementation, see **[44-multi-channel-gateway.md](44-multi-channel-gateway.md)**.

### Channel-Level Rate Limiting

In addition to the cost-aware rate limiting for MCP/A2A traffic (defined above in Agent Gateway Patterns), messaging channels require **per-user, per-channel rate limiting** to prevent abuse from authenticated users.

Rate limits are configured in `config/settings/security.yaml` under `rate_limiting`, with per-channel settings:

```yaml
rate_limiting:
  telegram:
    messages_per_minute: 30
    messages_per_hour: 500
  slack:
    messages_per_minute: 30
    messages_per_hour: 500
  websocket:
    messages_per_minute: 60
    messages_per_hour: 1000
```

Rate limiting is enforced at the gateway level (**[44-multi-channel-gateway.md](44-multi-channel-gateway.md)**) using Redis for distributed state. When a limit is exceeded, the gateway responds with a channel-appropriate cooldown message and does not forward the message to the agent coordinator. Rate-limited messages do not consume agent budget.

This is distinct from MCP/A2A rate limiting (token-based cost budgets) — channel rate limiting is message-count-based because messaging channel abuse is volumetric, not cost-based.

---

## Module Structure

```
modules/
├── mcp/
│   ├── __init__.py
│   ├── notes.py              # Notes MCP server (tools + resources)
│   └── health.py             # Health MCP server
├── a2a/
│   ├── __init__.py
│   ├── agent_card.py         # Agent Card generation and serving
│   ├── executor.py           # A2A task executor
│   └── skills.py             # Skill definitions
├── backend/
│   └── ...                   # Unchanged
config/
└── settings/
    ├── mcp.yaml              # MCP server configuration
    └── a2a.yaml              # A2A protocol configuration
tests/
├── mcp/
│   └── test_notes_mcp.py    # MCP in-memory client tests
└── a2a/
    └── test_agent_card.py   # Agent Card tests
```

### Configuration

**`config/settings/mcp.yaml`:**

```yaml
# =============================================================================
# MCP Server Configuration
# =============================================================================
# Available options:
#   enabled         - Enable MCP servers (boolean)
#   servers         - List of MCP server configurations (list)
#     name          - Server name (string)
#     mount_path    - FastAPI mount path (string)
#     module        - Python module path (string)
#   rate_limiting   - Rate limit settings (object)
#     enabled       - Enable rate limiting (boolean)
#     tiers         - Rate limit tiers (object)
#       free        - Free tier limits (object)
#       standard    - Standard tier limits (object)
#   authentication  - Auth settings (object)
#     required      - Require authentication (boolean)
#     audience      - Expected token audience (string)
# =============================================================================

enabled: true

servers:
  - name: notes
    mount_path: /mcp/notes
    module: modules.mcp.notes
  - name: health
    mount_path: /mcp/health
    module: modules.mcp.health

rate_limiting:
  enabled: true
  tiers:
    free:
      per_minute: 100
      per_hour: 1000
      per_day: 5000
    standard:
      per_minute: 1000
      per_hour: 10000
      per_day: 50000

authentication:
  required: true
  audience: "mcp://your-domain.com"
```

**`config/settings/a2a.yaml`:**

```yaml
# =============================================================================
# A2A Protocol Configuration
# =============================================================================
# Available options:
#   enabled         - Enable A2A protocol (boolean)
#   base_url        - Public base URL for A2A (string)
#   capabilities    - A2A capabilities (object)
#     streaming     - Support streaming responses (boolean)
#     pushNotifications - Support push notifications (boolean)
#   skills          - List of A2A skills (list)
#     id            - Skill identifier (string)
#     name          - Skill display name (string)
#     description   - Skill description (string)
#     tags          - Skill tags (list of strings)
#     inputModes    - Accepted input MIME types (list of strings)
#     outputModes   - Output MIME types (list of strings)
#   security_schemes - OAuth security schemes (object)
# =============================================================================

enabled: true
base_url: "https://your-domain.com/a2a/"

capabilities:
  streaming: true
  pushNotifications: false

skills:
  - id: note_management
    name: "Note Management"
    description: "Create, read, update, delete, archive, and search notes"
    tags: ["notes", "crud", "search"]
    inputModes: ["application/json"]
    outputModes: ["application/json"]

security_schemes:
  oauth2:
    type: oauth2
    flows:
      clientCredentials:
        tokenUrl: "https://your-domain.com/auth/token"
        scopes:
          "notes:read": "Read notes"
          "notes:write": "Create and modify notes"
```

---

## Adoption Checklist

### Phase 1: MCP Exposure (Start Here)

- [ ] Install `mcp` package (`pip install "mcp[cli]>=1.25,<2"`)
- [ ] Create `modules/mcp/` directory
- [ ] Implement MCP server for at least one domain (e.g., notes)
- [ ] Mount MCP server on FastAPI app, gated by feature flag
- [ ] Add `mcp.yaml` to `config/settings/`
- [ ] Create `features.yaml` entry: `mcp_enabled: true`
- [ ] Write MCP in-memory client tests
- [ ] Implement structured errors with recovery hints on existing endpoints
- [ ] Serve `/llms.txt` endpoint

### Phase 2: Agent Discovery

- [ ] Create `config/settings/a2a.yaml`
- [ ] Implement and serve `/.well-known/agent.json` (auto-generated from config)
- [ ] Add skill definitions for all exposed capabilities
- [ ] Document MCP tools and A2A skills in `AGENTS.md`

### Phase 3: A2A Protocol

- [ ] Install `a2a-sdk` package (`pip install "a2a-sdk[http-server]"`)
- [ ] Create `modules/a2a/` directory
- [ ] Implement A2A task executor
- [ ] Mount A2A application on FastAPI, gated by feature flag
- [ ] Write A2A integration tests

### Phase 4: Agent Identity

- [ ] Evaluate which identity layers are needed (see Adoption Guidance table)
- [ ] Implement MCP token audience validation
- [ ] Add `act` claim support to JWT decode for delegation tracking
- [ ] If needed: deploy SPIFFE/SPIRE for workload identity
- [ ] If needed: implement Biscuit token attenuation for delegation chains

### Phase 5: Observability and Security

- [ ] Add OpenTelemetry GenAI attributes to MCP/A2A request handling
- [ ] Implement behavioral baselining for external agent consumers
- [ ] Run DeepTeam red team evaluation on MCP/A2A interfaces
- [ ] Map platform defenses to OWASP Agentic Top 10

---

## Related Documentation

- [40-agentic-architecture.md](40-agentic-architecture.md) — Internal agent orchestration (conceptual)
- [41-agentic-pydanticai.md](41-agentic-pydanticai.md) — Internal agent implementation (PydanticAI)
- [44-multi-channel-gateway.md](44-multi-channel-gateway.md) — Multi-channel delivery, DM pairing, channel rate limiting, session management
- [03-backend-architecture.md](03-backend-architecture.md) — FastAPI application where MCP/A2A is mounted
- [05-authentication.md](05-authentication.md) — Base authentication (extended by agent identity layers)
- [10-observability.md](10-observability.md) — Logging standards (extended by OTel GenAI conventions)
- [09-error-codes.md](09-error-codes.md) — Error code registry (extended by recovery hints)
- [24-llm-integration.md](24-llm-integration.md) — LLM provider interface
- [06-security-standards.md](06-security-standards.md) — Application security standards
