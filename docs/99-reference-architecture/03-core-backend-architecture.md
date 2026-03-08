# 03 - Backend Architecture

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic backend architecture standard

---

## Context

The backend is the center of gravity for every project in this architecture. Per Core Principle P1, all business logic, validation, and data processing lives here, which means the backend framework choice, project structure, and API patterns affect everything downstream — from how modules communicate (04) to how clients consume data (22) to how tests are structured (11).

FastAPI was chosen because it is async-native (matching the I/O-bound nature of most web backends), generates OpenAPI documentation automatically, integrates Pydantic for request/response validation, and has extensive AI training data for code assistance. The layered architecture (API → Service → Repository → Model) enforces separation between HTTP handling, business logic, and data access, making each layer independently testable and replaceable.

This document standardizes the patterns that, left to individual choice, create the most friction: response envelope format, pagination strategy (cursor-based, never offset), error handling hierarchy, timeout values, configuration loading order, and health check endpoints. These are precisely the areas where "let each developer decide" leads to inconsistency across services and wasted integration time. Nearly every other standard — module structure (04), coding standards (08), error codes (09), testing (11), background tasks (14), and deployment (15, 16) — builds on the patterns defined here.

---

## Framework

### Standard: FastAPI

All backend services use FastAPI as the web framework.

Rationale:
- Async-native for I/O-bound operations (database, external APIs)
- Automatic OpenAPI documentation generation
- Pydantic integration for request/response validation
- Extensive AI training data for code assistance
- Strong typing support with Python type hints

### Python Version

Minimum: Python 3.12

All projects target the latest stable Python release at project inception. Upgrades occur during major version releases.

---

## Project Structure

All backend projects follow this directory structure:

```
project/
├── config/
│   ├── .env
│   ├── .env.example
│   └── settings/
│       └── *.yaml
├── modules/
│   ├── backend/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   └── v1/endpoints/
│   │   ├── core/                # Config, middleware, exceptions, logging, security
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── agents/              # PydanticAI agents (coordinator, verticals)
│   │   ├── gateway/             # Channel adapter registry, security
│   │   ├── tasks/               # Background tasks (Taskiq broker)
│   │   ├── cli/                 # CLI subcommands
│   │   └── migrations/          # Alembic database migrations
│   ├── telegram/                # Telegram bot (client module)
│   └── frontend/                # React + Vite web UI (client module)
├── tests/
├── data/
│   └── logs/
├── requirements.txt
└── .project_root
```

Domain separation within `modules/backend/` happens via file naming within layers (e.g., `services/user_service.py`, `services/note_service.py`). See doc 04 for the full module structure standard.

### Directory Purposes

| Directory | Purpose |
|-----------|---------|
| config/ | Environment variables (.env) and YAML configuration |
| modules/backend/api/ | HTTP endpoint handlers, versioned |
| modules/backend/core/ | Shared utilities, configuration loading, middleware, security |
| modules/backend/models/ | Database models (SQLAlchemy) |
| modules/backend/repositories/ | Data access layer, queries |
| modules/backend/schemas/ | Pydantic models for API request/response |
| modules/backend/services/ | Business logic, orchestration |
| modules/backend/agents/ | PydanticAI agent coordinator and vertical agents |
| modules/backend/gateway/ | Channel adapter registry and security |
| modules/backend/tasks/ | Background task broker and task definitions |
| modules/backend/cli/ | CLI subcommand modules |
| modules/telegram/ | Telegram bot — communicates with backend via HTTP API |
| modules/frontend/ | React web UI — communicates with backend via HTTP API |
| tests/ | All test files (unit, integration, e2e) |
| data/logs/ | Application logs |

---

## Configuration Loading

All configuration flows through two mechanisms — do not add a third.

### Secrets: `config/.env` via Pydantic Settings

Passwords, tokens, API keys, and other sensitive values live in `config/.env` and are loaded by a flat `Settings` class in `modules/backend/core/config.py`:

```python
from modules.backend.core.config import get_settings
settings = get_settings()  # Cached via @lru_cache
settings.anthropic_api_key
settings.db_password
```

`Settings` extends Pydantic's `BaseSettings`. Environment variables override `.env` values at runtime (for deployment).

### Application Config: `config/settings/*.yaml` via `get_app_config()`

Non-secret application settings (server, logging, agents, telegram, features) live in YAML files under `config/settings/` and are loaded by `get_app_config()`:

```python
from modules.backend.core.config import get_app_config
config = get_app_config()  # Returns validated dict from YAML
config.server["host"]
config.agents["coordinator"]
```

YAML files are organized by concern (`application.yaml`, `agents/*.yaml`, `logging.yaml`). The `ConfigSchema` in `core/config_schema.py` validates the merged YAML at load time.

### Precedence

```
Environment variables  >  config/.env  >  config/settings/*.yaml
```

### Rules

- **No hardcoded fallbacks.** If a value is missing, fail at startup — never silently default.
- **No `os.getenv()` with defaults.** Use `get_settings()` or `get_app_config()`.
- **Secrets never in YAML.** YAML is for application settings only.
- **YAML never in `.env`.** `.env` is for secrets only.

---

## Service Layer Pattern

### Responsibilities

Services contain all business logic. They:
- Validate business rules
- Orchestrate multi-step operations
- Call repositories for data access
- Call external services
- Emit events for async processing

Services do not:
- Handle HTTP concerns (status codes, headers)
- Access the database directly (use repositories)
- Know about request/response schemas

### Naming Convention

Services are named by domain: `UserService`, `OrderService`, `ProjectService`.

One service per domain concept. Services may call other services for cross-domain operations.

---

## Repository Layer Pattern

### Responsibilities

Repositories handle all database operations. They:
- Execute queries
- Handle database-specific concerns (transactions, connections)
- Map database results to domain models

Repositories do not:
- Contain business logic
- Call external services
- Validate business rules

### Naming Convention

Repositories are named by entity: `UserRepository`, `OrderRepository`, `ProjectRepository`.

One repository per database table or aggregate root.

---

## Async Patterns

### Parallel Calls with TaskGroup

Use `asyncio.TaskGroup` for parallel operations where all must succeed:

```python
import asyncio

async def get_dashboard(user_id: UUID) -> Dashboard:
    async with asyncio.timeout(10):  # Total timeout
        async with asyncio.TaskGroup() as tg:
            user_task = tg.create_task(user_api.get_user(user_id))
            projects_task = tg.create_task(project_api.get_projects(user_id))
    
    return Dashboard(
        user=user_task.result(),
        projects=projects_task.result()
    )
```

If any task fails, all others are automatically cancelled.

### TaskGroup vs gather()

| Pattern | Use When |
|---------|----------|
| `asyncio.TaskGroup` | All tasks must succeed; cancel others on first failure |
| `asyncio.gather(return_exceptions=True)` | Best-effort; continue even if some fail |

### Timeout Enforcement

All external calls must have timeouts:

```python
async def call_external_service(request: Request) -> Response:
    try:
        async with asyncio.timeout(30):
            return await external_client.call(request)
    except asyncio.TimeoutError:
        logger.warning("External call timed out")
        raise ExternalServiceError("Service did not respond in time")
```

### Timeout Guidelines

| Operation | Timeout |
|-----------|---------|
| Database query | 10 seconds |
| Internal API call | 10 seconds |
| External API call | 30 seconds |
| File operations | 30 seconds |
| Batch processing | 120 seconds |

Adjust based on known operation characteristics.

---

## API Design

### Versioning

All APIs are versioned with URL prefix: `/api/v1/`, `/api/v2/`.

Breaking changes require version increment. Non-breaking additions can occur within a version.

### Response Format

All API responses use consistent envelope:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "metadata": {
    "timestamp": "2025-01-27T12:00:00Z",
    "request_id": "uuid"
  }
}
```

Error responses:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "details": {}
  },
  "metadata": {
    "timestamp": "2025-01-27T12:00:00Z",
    "request_id": "uuid"
  }
}
```

### HTTP Methods

| Method | Purpose | Idempotent |
|--------|---------|------------|
| GET | Retrieve resource(s) | Yes |
| POST | Create resource or trigger action | No* |
| PUT | Replace resource entirely | Yes |
| PATCH | Partial update | Yes |
| DELETE | Remove resource | Yes |

*POST operations that modify state must accept idempotency keys.

### Status Codes

| Code | Usage |
|------|-------|
| 200 | Successful GET, PUT, PATCH, DELETE |
| 201 | Successful POST creating resource |
| 204 | Successful operation with no response body |
| 400 | Invalid request (validation failure) |
| 401 | Authentication required |
| 403 | Authenticated but not authorized |
| 404 | Resource not found |
| 409 | Conflict (duplicate, version mismatch) |
| 422 | Semantically invalid (business rule violation) |
| 429 | Rate limit exceeded |
| 500 | Server error |

### Pagination

All list endpoints support pagination:
- `limit` - Maximum items to return (default: 50, max: 100)
- `cursor` - Opaque cursor for next page

Cursor-based pagination is mandatory. Offset-based pagination is forbidden (performance degrades at scale).

### Cursor Implementation

Use keyset pagination with base64-encoded cursor containing the last record's sort key.

**Why not offset?**
```sql
-- Offset: Slow at page 100 (must skip 5000 rows)
SELECT * FROM items LIMIT 50 OFFSET 5000;

-- Cursor: Fast at any depth (uses index)
SELECT * FROM items WHERE created_at < '2025-01-27T10:30:00' LIMIT 50;
```

**Cursor encoding:**
```python
import base64
from datetime import datetime

def encode_cursor(last_item) -> str:
    """Encode cursor from last item in results."""
    value = f"{last_item.created_at.isoformat()}:{last_item.id}"
    return base64.urlsafe_b64encode(value.encode()).decode()

def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Decode cursor to (timestamp, id) tuple."""
    value = base64.urlsafe_b64decode(cursor.encode()).decode()
    timestamp_str, item_id = value.rsplit(":", 1)
    return datetime.fromisoformat(timestamp_str), item_id
```

**Query pattern:**
```sql
-- First page (no cursor)
SELECT * FROM items ORDER BY created_at DESC, id DESC LIMIT 50;

-- Subsequent pages (with cursor)
SELECT * FROM items 
WHERE (created_at, id) < (:cursor_timestamp, :cursor_id)
ORDER BY created_at DESC, id DESC 
LIMIT 50;
```

**Rules:**
- Cursor is opaque to clients (they never parse it)
- Always include a tiebreaker column (usually `id`)
- Sort order must be deterministic
- Cursor encodes position, not page number

### Interactive and Streaming Operations (AI-First Profile Only)

> **Skip this section if using the Traditional Backend profile.** See `00-overview.md` for profile definitions.

The request/response patterns above apply to stateless CRUD operations — the majority of API endpoints. For interactive operations involving conversations, agent streaming, multi-step plans, or approval gates, see `46-event-session-architecture.md` (AI-First Platform). That module introduces a session-and-event model where the coordinator returns `AsyncIterator[Event]` instead of a response object, and channels subscribe to session event streams. The service layer defined in this document remains the single source of business logic — the session model layers on top, it does not replace anything here.

---

## Background Tasks

For background task processing and scheduled jobs, see [14-background-tasks.md](14-background-tasks.md).

Summary:
- **Standard**: Taskiq with Redis
- **On-demand tasks**: Triggered by code via `.kiq()`
- **Scheduled tasks**: Cron-based via TaskiqScheduler
- **CLI**: `python cli.py worker` and `python cli.py scheduler`

---

## Configuration Management

### Environment Variables

Secrets and environment-specific values come from environment variables:
- Database credentials
- API keys
- JWT secrets
- External service URLs

### YAML Configuration

Application settings come from YAML files:
- Feature flags
- Rate limits
- Timeouts
- Business rules

### Loading Order

1. Load YAML configuration files
2. Override with environment variables where specified
3. Validate all required configuration present
4. Fail startup if configuration invalid

---

## Error Handling

### Exception Hierarchy

Define project-specific exceptions:
- `ApplicationError` - Base for all application errors
- `ValidationError` - Invalid input
- `NotFoundError` - Resource does not exist
- `AuthorizationError` - Not permitted
- `ConflictError` - State conflict
- `ExternalServiceError` - Third-party failure

### Error Propagation

- Repositories raise database-specific errors
- Services catch and translate to application errors
- API layer catches and translates to HTTP responses
- Unhandled exceptions return 500 with error ID for debugging

---

## Health Checks

All services expose health endpoints:

| Endpoint | Purpose |
|----------|---------|
| /health | Basic liveness (returns 200 if process running) |
| /health/ready | Readiness (database connected, dependencies available) |
| /health/detailed | Component-by-component status (authenticated) |

Health checks do not perform expensive operations. Database checks use simple queries, not full scans.
