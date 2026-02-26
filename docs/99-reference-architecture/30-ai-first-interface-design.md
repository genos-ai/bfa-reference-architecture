# 30 - AI-First Interface Design (Optional Module)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-02-26*

---

## Summary

Extend the existing BFF architecture so that AI agents (Cursor, Claude Code, external orchestrators) are first-class consumers alongside CLI, TUI, and web clients. The service layer defined in `03-backend-architecture.md` already enforces business logic centralization — this module adds the interface adapters, discovery endpoints, content negotiation, and structured error extensions that make those services consumable by machines without duplicating code. All client types — human and AI — call the same service methods through thin adapters.

**Dependencies**: `03-backend-architecture.md` (service layer), `04-module-structure.md` (module boundaries), `14-error-codes.md` (error registry), `27-agent-first-infrastructure.md` (MCP, A2A, agent identity). Composes with `25-agentic-architecture.md` and `26-agentic-pydanticai.md` for internal agents, and `29-multi-channel-gateway.md` for channel delivery.

---

## Core Principle: One Service, Many Adapters

### The Problem

Your architecture already mandates P1 (Backend Owns All Business Logic) and P2 (Clients Are Stateless Presentation Layers). The risk is that as you add consumer types — REST API, MCP tools, A2A executors, CLI commands, TUI screens, PydanticAI agent tools — each one reimplements service access patterns, input parsing, and error translation. The code duplication isn't in business logic; it's in the wiring between the consumer interface and the service layer.

### The Solution: Adapter Registry Pattern

Every consumer type is a thin adapter that performs exactly three operations:

1. **Parse** — translate consumer-specific input into a service-layer call (Pydantic schema)
2. **Invoke** — call the service method
3. **Format** — translate the service-layer return value into consumer-specific output

```
┌─────────────────────────────────────────────────────────┐
│                    Consumer Adapters                     │
│  (parse input → call service → format output)          │
├──────────┬──────────┬──────────┬──────────┬────────────┤
│ REST API │ MCP Tool │ A2A Exec │ CLI Cmd  │ Agent Tool │
│ (FastAPI)│(FastMCP) │ (a2a-sdk)│ (Click)  │(PydanticAI)│
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴─────┬──────┘
     │          │          │          │           │
     ▼          ▼          ▼          ▼           ▼
┌─────────────────────────────────────────────────────────┐
│              Service Layer (single source)               │
│         modules/backend/services/note.py                │
│         modules/backend/services/project.py             │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              Repository Layer                            │
│         modules/backend/repositories/note.py            │
└─────────────────────────────────────────────────────────┘
```

### Service Method as the Universal Contract

Every operation in the platform has exactly one service method. All adapters call it. The service method signature is the contract:

```python
# modules/backend/services/note.py — THE source of truth
class NoteService(BaseService):
    async def create_note(self, data: NoteCreate) -> NoteResponse:
        """Create a new note. Raises ValidationError if title empty."""
        ...

    async def archive_old_notes(self, older_than_days: int) -> ArchiveResult:
        """Archive notes older than threshold. Returns count affected."""
        ...
```

Every adapter calls `NoteService.create_note()`. No adapter contains business logic. No adapter validates business rules.

---

## Adapter Implementations

### Adapter 1: REST API (existing)

Already implemented per `03-backend-architecture.md`. Thin FastAPI endpoint handler:

```python
# modules/backend/api/v1/endpoints/notes.py
from modules.backend.core.dependencies import DbSession
from modules.backend.schemas.note import NoteCreate, NoteResponse
from modules.backend.services.note import NoteService

@router.post("/notes", response_model=ApiResponse[NoteResponse], status_code=201)
async def create_note(data: NoteCreate, db: DbSession) -> ApiResponse[NoteResponse]:
    service = NoteService(db)
    note = await service.create_note(data)
    return ApiResponse(success=True, data=note)
```

### Adapter 2: MCP Tool (doc 27)

Already defined in `27-agent-first-infrastructure.md`. The MCP tool function is a thin adapter:

```python
# modules/mcp/notes.py
from mcp.server.fastmcp import FastMCP
from modules.backend.core.database import get_db_session
from modules.backend.services.note import NoteService
from modules.backend.schemas.note import NoteCreate

mcp = FastMCP("NotesService", stateless_http=True, json_response=True)

@mcp.tool()
async def create_note(title: str, content: str | None = None) -> dict:
    """Create a new note with a title and optional content."""
    async for session in get_db_session():
        service = NoteService(session)
        note = await service.create_note(NoteCreate(title=title, content=content))
        return note.model_dump(mode="json")
```

### Adapter 3: PydanticAI Agent Tool (doc 26)

The PydanticAI tool function registered on an agent is a thin adapter:

```python
# modules/backend/agents/vertical/notes_agent.py
from pydantic_ai import Agent, RunContext
from modules.backend.agents.dependencies import AgentDeps
from modules.backend.schemas.note import NoteCreate

notes_agent = Agent(
    "anthropic:claude-sonnet-4-5-20250929",
    deps_type=AgentDeps,
    output_type=str,
    system_prompt="You manage notes for the user.",
)

@notes_agent.tool
async def create_note(ctx: RunContext[AgentDeps], title: str, content: str | None = None) -> str:
    """Create a new note with a title and optional content."""
    service = ctx.deps.note_service  # Injected via AgentDeps
    note = await service.create_note(NoteCreate(title=title, content=content))
    return f"Created note '{note.title}' with ID {note.id}"
```

### Adapter 4: CLI Command

Click commands are thin adapters that call service methods:

```python
# cli.py or modules/cli/notes.py
import asyncio
import click
import json
from modules.backend.core.database import get_db_session
from modules.backend.services.note import NoteService
from modules.backend.schemas.note import NoteCreate

@cli.command()
@click.argument("title")
@click.option("--content", default=None, help="Note content")
@click.option("--format", "output_format", type=click.Choice(["json", "text"]),
              default="text", help="Output format")
def create_note(title: str, content: str | None, output_format: str) -> None:
    """Create a new note."""
    async def _run():
        async for session in get_db_session():
            service = NoteService(session)
            return await service.create_note(NoteCreate(title=title, content=content))

    note = asyncio.run(_run())

    if output_format == "json":
        click.echo(json.dumps(note.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Created note '{note.title}' (ID: {note.id})")
```

### Adapter 5: A2A Task Executor

The A2A executor delegates to service methods:

```python
# modules/a2a/executor.py
from a2a.server.agent_execution import AgentExecutor
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message
from modules.backend.core.database import get_db_session
from modules.backend.services.note import NoteService
from modules.backend.schemas.note import NoteCreate

class NoteAgentExecutor(AgentExecutor):
    async def execute(self, context, event_queue: EventQueue):
        user_msg = context.get_user_input()
        async for session in get_db_session():
            service = NoteService(session)
            # Parse intent from user message, call service
            note = await service.create_note(NoteCreate(title=user_msg))
            await event_queue.enqueue_event(
                new_agent_text_message(f"Created note: {note.title}")
            )
```

### Pattern Summary

| Adapter | Input format | Output format | Location | Lines of adapter code |
|---------|-------------|---------------|----------|----------------------|
| REST API | Pydantic schema (JSON body) | `ApiResponse[T]` JSON envelope | `modules/backend/api/v1/endpoints/` | 5-10 per endpoint |
| MCP Tool | Function args (auto-generated from docstring) | `dict` or Pydantic model | `modules/mcp/` | 5-8 per tool |
| PydanticAI Tool | Function args via `RunContext` | `str` (natural language for LLM) | `modules/backend/agents/` | 5-8 per tool |
| CLI Command | Click args/options | JSON or formatted text | `cli.py` or `modules/cli/` | 8-15 per command |
| A2A Executor | JSON-RPC task input | A2A message artifacts | `modules/a2a/` | 10-15 per skill |

---

## Self-Describing API Surface

### OpenAPI Enhancement

FastAPI already generates OpenAPI 3.0 docs from Pydantic models. Enhance for AI consumption:

**1. Rich field descriptions on all schemas:**

```python
# modules/backend/schemas/note.py
from pydantic import BaseModel, Field

class NoteCreate(BaseModel):
    """Schema for creating a new note. Title is required, content is optional."""
    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="The note title. Must be unique per user.",
        examples=["Meeting notes 2026-02-26"],
    )
    content: str | None = Field(
        None,
        max_length=50000,
        description="Note body in plain text or markdown. Null for empty notes.",
    )
```

Rationale: AI agents use `description` and `examples` fields to decide which parameters to pass and how to format them — missing descriptions force the agent to guess.

**2. Rich operation descriptions on all endpoints:**

```python
@router.post(
    "/notes",
    response_model=ApiResponse[NoteResponse],
    status_code=201,
    summary="Create a new note",
    description="Creates a note with a title and optional content. "
                "Returns the created note with generated ID and timestamps. "
                "Fails with 400 if title is empty or exceeds 200 characters.",
    responses={
        400: {"description": "Validation failed — title empty or too long"},
        409: {"description": "Note with this title already exists for user"},
    },
)
async def create_note(data: NoteCreate, db: DbSession) -> ApiResponse[NoteResponse]:
    ...
```

**3. OpenAPI tags with descriptions:**

```python
# modules/backend/api/v1/__init__.py
tags_metadata = [
    {
        "name": "notes",
        "description": "CRUD operations for notes. Supports create, read, update, delete, archive, and search.",
    },
    {
        "name": "health",
        "description": "Health check endpoints for liveness, readiness, and component-level status.",
    },
]
```

### Discovery Endpoints

Implement the three discovery layers from `27-agent-first-infrastructure.md`:

| Endpoint | Purpose | Consumer | Implementation |
|----------|---------|----------|---------------|
| `/docs` (OpenAPI UI) | Interactive API docs | Human developers | FastAPI built-in |
| `/openapi.json` | Machine-readable API spec | AI agents, SDK generators | FastAPI built-in |
| `/llms.txt` | Curated AI-readable overview | LLM agents (Cursor, Claude Code) | New endpoint |
| `/llms-full.txt` | Complete API docs as plain text | LLM agents needing full detail | Build-time generated |
| `/.well-known/agent.json` | A2A Agent Card | External agents (A2A protocol) | New endpoint (doc 27) |
| `AGENTS.md` | Coding agent instructions | Cursor, Claude Code, Copilot | Existing file (enhance) |

### `/llms.txt` Implementation

```python
# modules/backend/api/discovery.py
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from modules.backend.core.config import get_app_config

router = APIRouter(tags=["discovery"])


@router.get("/llms.txt", response_class=PlainTextResponse,
            include_in_schema=False)
async def llms_txt() -> str:
    """LLM-consumable overview of this platform's API surface."""
    config = get_app_config()
    app = config.application
    return f"""# {app.name}

> {app.description}

## API Documentation
- [OpenAPI Spec](/openapi.json): Full machine-readable API specification
- [Interactive Docs](/docs): Swagger UI for exploration

## REST Endpoints (JSON, versioned)
- POST /api/v1/notes — Create a note
- GET  /api/v1/notes — List notes (cursor-paginated)
- GET  /api/v1/notes/{{id}} — Get note by ID
- PATCH /api/v1/notes/{{id}} — Update note
- DELETE /api/v1/notes/{{id}} — Delete note
- POST /api/v1/notes/{{id}}/archive — Archive note

## MCP Servers (tool access for AI agents)
- /mcp/notes — Note management tools (create, read, update, archive, search)
- /mcp/health — Health check tools

## A2A (agent-to-agent collaboration)
- /.well-known/agent.json — Agent Card with capabilities and auth

## Authentication
- Bearer JWT token in Authorization header
- MCP: OAuth 2.1 with PKCE
- A2A: OAuth 2.0 client_credentials

## Response Envelope
All responses: {{"success": bool, "data": T, "error": ErrorDetail | null, "metadata": {{...}}}}

## Error Codes
See /api/v1/error-codes for the full registry.
"""
```

### `/llms-full.txt` Generation (Build-Time)

Generate from OpenAPI spec at build time, not at runtime:

```python
# scripts/generate_llms_full.py
"""Generate /llms-full.txt from OpenAPI spec. Run at build time."""
import json
from pathlib import Path
from modules.backend.main import get_app

app = get_app()
spec = app.openapi()

lines = [f"# {spec['info']['title']} — Full API Reference\n"]
for path, methods in spec.get("paths", {}).items():
    for method, details in methods.items():
        summary = details.get("summary", "")
        desc = details.get("description", "")
        lines.append(f"## {method.upper()} {path}")
        lines.append(f"{summary}. {desc}\n")
        # Add request body schema if present
        if "requestBody" in details:
            lines.append("### Request Body")
            # ... render schema fields with descriptions
        # Add response schemas
        lines.append("")

Path("static/llms-full.txt").write_text("\n".join(lines))
```

Mount the static file:

```python
# modules/backend/main.py — in create_app()
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")
```

### Files Involved

```
modules/backend/api/discovery.py          # NEW — /llms.txt, /llms-full.txt
modules/backend/api/v1/endpoints/notes.py # MODIFY — add rich descriptions
modules/backend/schemas/note.py           # MODIFY — add Field descriptions
modules/backend/main.py                   # MODIFY — include discovery router
scripts/generate_llms_full.py             # NEW — build-time generation
AGENTS.md                                 # MODIFY — add MCP/A2A sections
```

---

## Structured Errors with Recovery Hints

### Current State

The existing `ErrorDetail` in `modules/backend/schemas/base.py` has `code`, `message`, and optional `details`. This is sufficient for human-driven clients but opaque to AI agents that need to decide what to do next programmatically.

### Extension: Agent-Consumable Error Fields

Extend `ErrorDetail` with three optional fields. Rationale: existing consumers ignore fields they don't use; new fields are additive and backward-compatible.

```python
# modules/backend/schemas/base.py — extend ErrorDetail
class ErrorDetail(BaseModel):
    """Error detail with optional agent-recovery fields."""
    code: str
    message: str
    details: dict[str, Any] | None = None

    # Agent-consumable recovery fields (optional, backward-compatible)
    suggestions: list[str] | None = Field(
        None,
        description="Valid alternatives when the request target is wrong. "
                    "E.g., similar note IDs when a note is not found.",
    )
    retry_strategy: RetryStrategy | None = Field(
        None,
        description="Machine-readable instructions for what to try next.",
    )
    doc_uri: str | None = Field(
        None,
        description="URI to machine-readable documentation about this error.",
    )


class RetryStrategy(BaseModel):
    """Machine-readable retry/recovery instruction for AI agents."""
    action: str = Field(
        ..., description="What the agent should do: 'retry', 'search', 'authenticate', 'wait'"
    )
    endpoint: str | None = Field(
        None, description="The endpoint to call for recovery"
    )
    wait_seconds: int | None = Field(
        None, description="How long to wait before retrying"
    )
    method: str | None = Field(
        None, description="HTTP method for the recovery endpoint"
    )
```

### Service-Layer Error Enrichment

Services raise domain exceptions. The exception handler translates them. Add recovery hints in the exception handler, not in the service:

```python
# modules/backend/core/exception_handlers.py — extend application_error_handler

async def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    status_code = EXCEPTION_STATUS_MAP.get(type(exc), 500)
    request_id = _get_request_id(request)

    error_detail = ErrorDetail(code=exc.code, message=exc.message)

    # Enrich with recovery hints based on error type
    error_detail = _enrich_with_recovery_hints(error_detail, exc, request)

    if isinstance(exc, ValidationError) and exc.details:
        error_detail.details = exc.details

    metadata = ResponseMetadata(request_id=request_id)
    response = ErrorResponse(error=error_detail, metadata=metadata)

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json", exclude_none=True),
    )


def _enrich_with_recovery_hints(
    error: ErrorDetail,
    exc: ApplicationError,
    request: Request,
) -> ErrorDetail:
    """Add agent-consumable recovery hints to error responses."""
    if isinstance(exc, NotFoundError):
        # Suggest search endpoint for the resource type
        resource_path = request.url.path.rsplit("/", 1)[0]
        error.retry_strategy = RetryStrategy(
            action="search",
            endpoint=f"{resource_path}/search",
            method="GET",
        )
        error.doc_uri = f"/docs#/default/search_{resource_path.split('/')[-1]}"

    elif isinstance(exc, RateLimitError):
        error.retry_strategy = RetryStrategy(
            action="wait",
            wait_seconds=60,
        )

    elif isinstance(exc, ValidationError):
        error.doc_uri = f"/docs#/schemas/{request.url.path.split('/')[-1]}"

    return error
```

### Anti-Patterns

- Do not put recovery hints in service methods. Services raise domain exceptions; error formatting is the API layer's concern.
- Do not make `suggestions` or `retry_strategy` required fields. Existing clients must not break.
- Do not return internal implementation details (stack traces, SQL queries) in `details` even for agent consumers.

### Files Involved

```
modules/backend/schemas/base.py               # MODIFY — add RetryStrategy, extend ErrorDetail
modules/backend/core/exception_handlers.py     # MODIFY — add _enrich_with_recovery_hints
```

---

## CLI Design for AI Consumption

### Current State

`cli.py` uses Click. The TUI (`tui.py`) uses Textual for interactive sessions. Both are functional for human users but hostile to AI agents: interactive prompts block, spinners corrupt stdout, and rich formatting breaks parsing.

### AI-Native CLI Patterns

**1. Universal `--format json` flag on every command:**

```python
# modules/cli/output.py — shared output formatter
import json
import click
from pydantic import BaseModel


def output_result(data: BaseModel | dict | list, format: str = "text") -> None:
    """Format and output result based on requested format."""
    if format == "json":
        if isinstance(data, BaseModel):
            click.echo(data.model_dump_json(indent=2))
        else:
            click.echo(json.dumps(data, indent=2, default=str))
    else:
        # Human-readable text format
        if isinstance(data, BaseModel):
            _print_model_as_text(data)
        else:
            click.echo(str(data))


def _print_model_as_text(model: BaseModel) -> None:
    """Render Pydantic model as human-readable text."""
    for field_name, value in model.model_dump().items():
        click.echo(f"  {field_name}: {value}")
```

**2. `--non-interactive` flag to suppress all prompts:**

```python
# cli.py — global option
@click.group()
@click.option("--format", "output_format", type=click.Choice(["json", "text"]),
              default="text", envvar="BFF_OUTPUT_FORMAT",
              help="Output format. Set BFF_OUTPUT_FORMAT=json for AI agents.")
@click.option("--non-interactive", is_flag=True, envvar="BFF_NON_INTERACTIVE",
              help="Suppress all prompts. Fail if input required.")
@click.option("--verbose", is_flag=True, help="Verbose output")
@click.option("--debug", is_flag=True, help="Debug output")
@click.pass_context
def cli(ctx, output_format, non_interactive, verbose, debug):
    ctx.ensure_object(dict)
    ctx.obj["format"] = output_format
    ctx.obj["non_interactive"] = non_interactive
```

**3. Deterministic exit codes:**

| Exit Code | Meaning | Agent Action |
|-----------|---------|-------------|
| 0 | Success | Continue |
| 1 | Invalid input (correctable) | Fix arguments, retry |
| 2 | Resource not found | Search or create |
| 3 | Authentication failure | Re-authenticate |
| 4 | Permission denied | Escalate |
| 5 | Conflict (duplicate, version mismatch) | Fetch current state, resolve |
| 10-99 | Application-specific errors | Consult `--help` |
| 100+ | Internal errors | Report, do not retry |

**4. Structured error output in JSON mode:**

```python
# modules/cli/output.py
import sys

def output_error(code: str, message: str, format: str = "text", exit_code: int = 1) -> None:
    """Output error in requested format and exit."""
    if format == "json":
        error = {"success": False, "error": {"code": code, "message": message}}
        click.echo(json.dumps(error), err=True)
    else:
        click.echo(f"Error [{code}]: {message}", err=True)
    sys.exit(exit_code)
```

### Environment Variable Convention

AI agents set environment variables instead of passing flags:

```bash
# AI agent environment
export BFF_OUTPUT_FORMAT=json
export BFF_NON_INTERACTIVE=1

# Now all CLI commands output JSON with no prompts
python cli.py --service notes --action create --title "Meeting notes"
```

### Anti-Patterns

- Do not use `click.confirm()` or `click.prompt()` without checking `--non-interactive`. If the flag is set and input is required, fail with exit code 1 and a message explaining what argument was missing.
- Do not use `rich` progress bars or spinners when `--format json` is set. They corrupt stdout.
- Do not mix stdout and stderr. All data goes to stdout; all errors and logs go to stderr.
- Do not use ANSI color codes when output is piped (check `sys.stdout.isatty()`).

### Files Involved

```
modules/cli/__init__.py     # NEW — CLI module
modules/cli/output.py       # NEW — shared output formatting
cli.py                      # MODIFY — add --format, --non-interactive globals
```

---

## Intent and Planning APIs

### When CRUD Is Not Enough

CRUD APIs require agents to orchestrate multi-step workflows. Intent APIs collapse intent into a single call. Planning APIs add a preview step before destructive operations.

### Implementation: Intent Endpoints

Add intent endpoints alongside existing CRUD routes in the same router:

```python
# modules/backend/api/v1/endpoints/notes.py — add to existing router

class ArchiveIntentRequest(BaseModel):
    """Intent: archive notes matching criteria."""
    criteria: ArchiveCriteria
    dry_run: bool = Field(
        False,
        description="If true, return what would be archived without executing.",
    )


class ArchiveCriteria(BaseModel):
    older_than_days: int = Field(..., ge=1, le=365)
    is_archived: bool = Field(False, description="Current archive status to filter on")


class ArchiveIntentResponse(BaseModel):
    affected_count: int
    note_ids: list[str]
    executed: bool


@router.post(
    "/notes/intents/archive-old",
    response_model=ApiResponse[ArchiveIntentResponse],
    summary="Archive notes older than a threshold",
    description="Intent API: archives all notes matching criteria in a single call. "
                "Use dry_run=true to preview without executing.",
)
async def archive_old_notes_intent(
    data: ArchiveIntentRequest,
    db: DbSession,
) -> ApiResponse[ArchiveIntentResponse]:
    service = NoteService(db)
    result = await service.archive_old_notes(
        older_than_days=data.criteria.older_than_days,
        dry_run=data.dry_run,
    )
    return ApiResponse(success=True, data=result)
```

### Implementation: Planning APIs

For destructive multi-step operations, return a reviewable plan:

```python
# modules/backend/api/v1/endpoints/plans.py
from uuid import uuid4

class PlanStep(BaseModel):
    step: str
    description: str
    status: str  # "computed" | "pending_confirmation"
    affected_count: int | None = None


class ExecutionPlan(BaseModel):
    plan_id: str
    steps: list[PlanStep]
    warnings: list[str]
    confirm_url: str
    expires_at: str  # ISO 8601 — plans expire after 15 minutes


@router.post("/plans/bulk-archive", response_model=ApiResponse[ExecutionPlan])
async def create_bulk_archive_plan(
    criteria: ArchiveCriteria,
    db: DbSession,
) -> ApiResponse[ExecutionPlan]:
    service = NoteService(db)
    preview = await service.archive_old_notes(
        older_than_days=criteria.older_than_days,
        dry_run=True,
    )
    plan_id = str(uuid4())
    # Store plan in cache (Redis) with 15-min TTL
    plan = ExecutionPlan(
        plan_id=plan_id,
        steps=[
            PlanStep(step="identify_notes", description="Find matching notes",
                     status="computed", affected_count=preview.affected_count),
            PlanStep(step="archive_notes", description="Archive matched notes",
                     status="pending_confirmation"),
        ],
        warnings=[f"This will archive {preview.affected_count} notes"],
        confirm_url=f"/api/v1/plans/{plan_id}/confirm",
        expires_at=(utc_now() + timedelta(minutes=15)).isoformat(),
    )
    # Store plan in Redis for retrieval on confirm
    return ApiResponse(success=True, data=plan)


@router.post("/plans/{plan_id}/confirm", response_model=ApiResponse[ArchiveIntentResponse])
async def confirm_plan(plan_id: str, db: DbSession) -> ApiResponse[ArchiveIntentResponse]:
    # Retrieve plan from Redis, execute, delete plan
    ...
```

### When to Use Each Pattern

| Pattern | Use When | Example |
|---------|----------|---------|
| CRUD endpoints | Single-resource operations, human-driven UIs | `POST /notes`, `GET /notes/{id}` |
| Intent endpoints | Multi-step operations an agent would need to orchestrate | `POST /notes/intents/archive-old` |
| Planning APIs | Destructive operations where preview is critical | `POST /plans/bulk-archive` → confirm |

### Anti-Patterns

- Do not replace CRUD endpoints with intent endpoints. Keep both. Human-driven clients use CRUD; agent-driven clients prefer intents.
- Do not make plans permanent. Plans expire (15 minutes default). Stale plans with stale counts are worse than no plan.
- Do not put intent/planning logic in the API handler. The service method does the work; the handler is a thin adapter.

### Files Involved

```
modules/backend/api/v1/endpoints/notes.py   # MODIFY — add intent endpoints
modules/backend/api/v1/endpoints/plans.py   # NEW — planning API
modules/backend/services/note.py            # MODIFY — add archive_old_notes(dry_run=True)
modules/backend/schemas/note.py             # MODIFY — add ArchiveCriteria, ArchiveIntentResponse
```

---

## Content Negotiation (Single Endpoint, Multiple Formats)

### Strategy: Accept Header

Use HTTP `Accept` header to return different representations from the same endpoint. Rationale: this is the HTTP standard mechanism, avoids duplicate routes, and works with existing clients that already send `Accept: application/json`.

```python
# modules/backend/core/content_negotiation.py
from fastapi import Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Any


def negotiate_response(
    request: Request,
    data: BaseModel | dict,
    template_name: str | None = None,
) -> JSONResponse | HTMLResponse:
    """Return JSON or HTML based on Accept header."""
    accept = request.headers.get("accept", "application/json")

    if "text/html" in accept and template_name:
        # Render HTML template for browser clients
        from modules.backend.core.templates import templates
        context = data.model_dump() if isinstance(data, BaseModel) else data
        return templates.TemplateResponse(template_name, {"request": request, **context})

    # Default: JSON for AI agents and API consumers
    if isinstance(data, BaseModel):
        return JSONResponse(content=data.model_dump(mode="json"))
    return JSONResponse(content=data)
```

### When to Use

Use content negotiation only for endpoints where both humans and agents consume the same data. For most API endpoints (JSON-only), the existing pattern is correct. Content negotiation applies primarily to dashboards, reports, and status pages where a human might view the same data in a browser.

For pure API routes (`/api/v1/*`), always return JSON. Content negotiation adds complexity that isn't needed for typed API endpoints.

### Files Involved

```
modules/backend/core/content_negotiation.py  # NEW — negotiate_response helper
```

---

## Service Layer Factory for Shared Initialization

### The Problem

Every adapter creates service instances slightly differently. REST endpoints use `Depends(DbSession)`. CLI commands use `async for session in get_db_session()`. MCP tools use the same pattern as CLI. This initialization code is duplicated across adapters.

### The Solution: Service Factory

Create a shared factory that provides initialized services regardless of the adapter:

```python
# modules/backend/core/service_factory.py
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from modules.backend.core.database import get_db_session
from modules.backend.services.note import NoteService


@asynccontextmanager
async def get_note_service() -> AsyncGenerator[NoteService, None]:
    """Provide an initialized NoteService with database session.

    Usage (CLI, MCP, A2A, PydanticAI tools):
        async with get_note_service() as service:
            result = await service.create_note(data)

    Usage (FastAPI — use dependency injection instead):
        See modules/backend/core/dependencies.py
    """
    async for session in get_db_session():
        yield NoteService(session)
```

### Adapter Usage

All non-FastAPI adapters use the factory:

```python
# MCP tool
@mcp.tool()
async def create_note(title: str, content: str | None = None) -> dict:
    """Create a new note."""
    async with get_note_service() as service:
        note = await service.create_note(NoteCreate(title=title, content=content))
        return note.model_dump(mode="json")

# CLI command
async def _create_note(title: str, content: str | None) -> NoteResponse:
    async with get_note_service() as service:
        return await service.create_note(NoteCreate(title=title, content=content))

# PydanticAI tool
@notes_agent.tool
async def create_note(ctx: RunContext[AgentDeps], title: str, content: str | None = None) -> str:
    """Create a new note."""
    async with get_note_service() as service:
        note = await service.create_note(NoteCreate(title=title, content=content))
        return f"Created note '{note.title}' with ID {note.id}"
```

FastAPI endpoints continue to use dependency injection (`Depends(DbSession)`) per existing patterns. The factory is for adapters outside the FastAPI request lifecycle.

### Session-Aware Factory (Doc 31)

When the project adopts `31-event-session-architecture.md`, the service factory can optionally accept a session context:

```python
@asynccontextmanager
async def get_note_service(session: Session | None = None) -> AsyncGenerator[NoteService, None]:
    async for db_session in get_db_session():
        service = NoteService(db_session)
        if session:
            service.set_session_context(session)  # Enables cost tracking, audit trail
        yield service
```

The `session` parameter is optional. Non-session callers (CLI, background tasks) pass `None` and the factory behaves identically to the base pattern. Session-aware callers (coordinator, channel adapters) pass the active session for cost tracking and audit trail integration.

See `31-event-session-architecture.md`, Section 1 (Session Model — SessionService) for the `Session` entity and lifecycle management.

### Files Involved

```
modules/backend/core/service_factory.py  # NEW — shared service initialization
modules/mcp/notes.py                     # MODIFY — use factory
modules/backend/agents/vertical/         # MODIFY — use factory
cli.py                                   # MODIFY — use factory
```

---

## Module Structure After Adoption

```
modules/
├── backend/
│   ├── api/
│   │   ├── discovery.py              # NEW — /llms.txt, discovery endpoints
│   │   └── v1/
│   │       └── endpoints/
│   │           ├── notes.py          # MODIFY — intent endpoints, rich descriptions
│   │           └── plans.py          # NEW — planning API
│   ├── core/
│   │   ├── content_negotiation.py    # NEW — Accept header negotiation
│   │   ├── exception_handlers.py     # MODIFY — recovery hints
│   │   └── service_factory.py        # NEW — shared service initialization
│   ├── schemas/
│   │   ├── base.py                   # MODIFY — RetryStrategy, extended ErrorDetail
│   │   └── note.py                   # MODIFY — rich Field descriptions
│   ├── services/                     # UNCHANGED — single source of truth
│   ├── agents/                       # MODIFY — use service factory
│   └── main.py                       # MODIFY — mount discovery router
├── mcp/                              # EXISTS (doc 27) — use service factory
├── a2a/                              # EXISTS (doc 27) — use service factory
├── cli/
│   ├── __init__.py                   # NEW — CLI module
│   └── output.py                     # NEW — shared output formatting
├── telegram/                         # UNCHANGED
└── frontend/                         # UNCHANGED
```

---

## Adoption Checklist

### Phase 1: Self-Describing APIs (Start Here)

- [ ] Add `description`, `examples` to all Pydantic schema fields in `modules/backend/schemas/`
- [ ] Add `summary`, `description`, `responses` to all FastAPI endpoint decorators
- [ ] Add OpenAPI `tags_metadata` with tag descriptions
- [ ] Create `modules/backend/api/discovery.py` with `/llms.txt`
- [ ] Mount discovery router in `modules/backend/main.py`
- [ ] Create `scripts/generate_llms_full.py` and run in CI build step

### Phase 2: Error Recovery Hints

- [ ] Add `RetryStrategy` model to `modules/backend/schemas/base.py`
- [ ] Extend `ErrorDetail` with `suggestions`, `retry_strategy`, `doc_uri`
- [ ] Add `_enrich_with_recovery_hints` to `modules/backend/core/exception_handlers.py`
- [ ] Test that existing clients are unaffected (fields are optional, excluded when None)

### Phase 3: Service Factory + Adapter Standardization

- [ ] Create `modules/backend/core/service_factory.py`
- [ ] Refactor MCP tools (`modules/mcp/`) to use factory
- [ ] Refactor PydanticAI agent tools to use factory
- [ ] Refactor CLI commands to use factory

### Phase 4: AI-Native CLI

- [ ] Create `modules/cli/output.py` with `output_result` and `output_error`
- [ ] Add `--format` and `--non-interactive` global options to `cli.py`
- [ ] Implement deterministic exit codes across all CLI commands
- [ ] Verify all commands work with `BFF_OUTPUT_FORMAT=json BFF_NON_INTERACTIVE=1`

### Phase 5: Intent and Planning APIs

- [ ] Identify top 3-5 multi-step operations agents need to perform
- [ ] Implement intent endpoints for each
- [ ] Implement planning API for destructive operations
- [ ] Add `dry_run` parameter to relevant service methods

---

## Testing

### Unit Tests

- Service factory: test that `get_note_service()` yields a working service with a mocked session
- Recovery hints: test that each exception type produces the correct recovery hint fields
- Output formatting: test that `output_result(model, "json")` produces valid JSON matching the model schema
- Content negotiation: test that `Accept: text/html` returns HTML and `Accept: application/json` returns JSON

### Integration Tests

- `/llms.txt`: assert response is `text/plain`, contains all endpoint paths
- `/openapi.json`: assert all endpoints have `description` and `summary`
- Intent endpoints: test full flow (dry_run → execute)
- Planning APIs: test create plan → confirm plan → verify execution
- CLI JSON mode: run CLI commands with `--format json`, parse stdout as JSON, verify schema

### Adapter Parity Tests

Write a shared test suite that verifies all adapters produce equivalent results for the same operation:

```python
# tests/integration/test_adapter_parity.py
import pytest
from modules.backend.schemas.note import NoteCreate

ADAPTERS = ["rest", "mcp", "cli", "agent_tool"]

@pytest.mark.parametrize("adapter", ADAPTERS)
async def test_create_note_parity(adapter, note_data):
    """All adapters must produce the same result for create_note."""
    result = await invoke_adapter(adapter, "create_note", note_data)
    assert result["title"] == note_data["title"]
    assert "id" in result
    assert "created_at" in result
```

---

## Glossary

| Term | Definition |
|------|-----------|
| **Adapter** | A thin translation layer between a consumer interface (REST, MCP, CLI, etc.) and the service layer. Contains no business logic. |
| **BFA (Backend for Agents)** | Extension of the BFF pattern where the backend includes adapters specifically designed for AI agent consumption (MCP tools, A2A executors, intent APIs). |
| **Intent API** | An endpoint that accepts a declarative description of a desired outcome rather than a specific CRUD operation. |
| **Planning API** | An endpoint that returns a preview of what an operation would do before executing it, with a separate confirmation step. |
| **Recovery Hint** | Machine-readable fields on error responses (`suggestions`, `retry_strategy`, `doc_uri`) that tell an AI agent what to try next. |
| **Service Factory** | A context manager that provides initialized service instances for use outside the FastAPI request lifecycle (CLI, MCP, agents). |

---

## Related Documentation

- [31-event-session-architecture.md](31-event-session-architecture.md) — Session context for service factory, event-driven interaction model

---

## Out of Scope

- Internal agent orchestration (covered by `25-agentic-architecture.md` and `26-agentic-pydanticai.md`)
- MCP server setup and A2A protocol integration (covered by `27-agent-first-infrastructure.md`)
- Human-in-the-loop approval flows within agent workflows (covered by `25-agentic-architecture.md` — durable execution section)
- Multi-channel gateway and session management (covered by `29-multi-channel-gateway.md`)
- Frontend architecture (covered by `07-frontend-architecture.md`)
- TUI architecture (covered by `28-tui-architecture.md`)
