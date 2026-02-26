# AGENTS.md — AI Assistant Instructions

This file tells AI coding assistants how to work with this codebase.
For full details, see `docs/99-reference-architecture/`.

## Project Overview

BFF (Backend-for-Frontend) Python web application skeleton.
FastAPI backend, React frontend, PostgreSQL, Redis, Taskiq.

## Critical Rules

- **No hardcoded values.** All configuration from `config/settings/*.yaml`. All secrets from `config/.env`. No hardcoded fallbacks in code, ever.
- **Absolute imports only.** Always `from modules.backend.core.config import ...`. Never relative imports.
- **Centralized logging only.** Always `from modules.backend.core.logging import get_logger`. Never `import logging` directly.
- **Timezone-naive UTC datetimes.** Use `from modules.backend.core.utils import utc_now`. Never `datetime.utcnow()` (deprecated) or `datetime.now()` (local time).
- **`.project_root` marker** determines the project root. Use `find_project_root()` from `modules.backend.core.config`.
- **All CLI scripts must have `--verbose` and `--debug` options** with appropriate logging for each.
- **Files must not exceed 1000 lines.** Target ~400-500 lines. Split into focused submodules if larger.
- **`__init__.py` files must be minimal.** Docstring and necessary exports only. No business logic.
- **Secure by default (P8).** All external interfaces deny access when unconfigured. Empty allowlists = deny all. Missing secrets = startup failure. New channels/features disabled by default.

## Architecture

### Layered Backend (strict — no skipping layers)

```
API Layer (modules/backend/api/)         → HTTP handlers, request/response
Service Layer (modules/backend/services/) → Business logic, orchestration
Repository Layer (modules/backend/repositories/) → Data access, queries
Model Layer (modules/backend/models/)     → SQLAlchemy entities
```

### Configuration

- Secrets (passwords, tokens, keys): `config/.env` via Pydantic Settings
- Application settings: `config/settings/*.yaml` via `get_app_config()`
- Access in code: `from modules.backend.core.config import get_settings, get_app_config`

### Entry Points

- `cli.py` — Click-based CLI (--service server|worker|scheduler|health|config|test|migrate|info --action start|stop|restart|status)
- `modules/backend/main.py` — FastAPI application (for uvicorn)

### Key Modules

| Module | Purpose |
|--------|---------|
| `modules/backend/core/config.py` | Configuration loading (YAML + .env) |
| `modules/backend/core/logging.py` | Centralized structured logging (structlog → logs/system.jsonl) |
| `modules/backend/core/exceptions.py` | Custom exception hierarchy |
| `modules/backend/core/middleware.py` | Request context (X-Request-ID, X-Frontend-ID → source field) |
| `modules/backend/core/database.py` | Async SQLAlchemy engine and sessions |
| `modules/backend/core/security.py` | JWT, password hashing, API keys |
| `modules/backend/core/utils.py` | Utilities (utc_now) |
| `modules/backend/core/config_schema.py` | Pydantic schemas for YAML config validation |
| `modules/backend/tasks/broker.py` | Taskiq broker (Redis backend) |
| `modules/backend/agents/` | Agent coordinator and vertical agents (PydanticAI) |
| `modules/backend/gateway/` | Channel adapter registry and security (rate limiting, startup checks) |
| `modules/telegram/` | Telegram bot (aiogram v3, webhook mode) |
| `modules/frontend/` | React + Vite + Tailwind |

## Code Patterns

### Error Handling

```python
from modules.backend.core.exceptions import NotFoundError, ValidationError
```

Raise domain exceptions in services. Exception handlers in `core/exception_handlers.py` convert to HTTP responses.

### Logging

```python
from modules.backend.core.logging import get_logger
logger = get_logger(__name__)
logger.info("Operation completed", extra={"task_id": task.id, "duration": elapsed})
```

### Database Sessions

```python
from modules.backend.core.dependencies import DbSession

@router.get("/items")
async def get_items(db: DbSession):
    ...
```

### Background Tasks

```python
from modules.backend.tasks.broker import get_broker
broker = get_broker()
```

## Testing

- `tests/unit/` — fast, mocked, no external dependencies
- `tests/integration/` — real database
- `tests/e2e/` — full stack
- Framework: pytest with pytest-asyncio
- Run: `pytest tests/unit -v`

## What NOT to Do

- Do not create helper or wrapper scripts (except in `scripts/`)
- Do not add business logic to `__init__.py` files
- Do not use `os.getenv()` with fallback defaults
- Do not create standalone loggers with `logging.getLogger()`
- Do not use relative imports
- Do not use `datetime.now()` or `datetime.utcnow()`
- Do not hardcode URLs, ports, timeouts, or any configurable value
- Do not skip layers (API calling repository directly)

## Reference Architecture

Full standards in `docs/99-reference-architecture/`:

| Doc | Topic |
|-----|-------|
| 01 | Core Principles |
| 03 | Backend Architecture |
| 10 | Python Coding Standards |
| 12 | Observability |
| 14 | Error Codes |
| 16 | Testing Standards |
| 19 | Background Tasks |
| 25 | Agentic AI Architecture (conceptual) |
| 26 | Agentic AI PydanticAI Implementation |
| 27 | Agent-First Infrastructure (MCP, A2A, agent identity) |
| 29 | Multi-Channel Gateway (channel adapters, sessions, WebSocket, security) |
| 30 | AI-First Interface Design (adapter registry, self-describing APIs, service factory) |
| 31 | Event-Driven Session Architecture (session model, event bus, streaming coordinator, plan management, memory, approval gates, cost tracking) |
