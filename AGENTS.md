# AGENTS.md — AI Assistant Instructions

Read `.codemap/map.md` for a structural overview of the codebase ranked by importance. Machine-readable version in `.codemap/map.json`.

This file tells AI coding assistants how to work with this codebase.
For full details, see `docs/99-reference-architecture/`.

## Design Principles

- **AI-first, not human-first.** Agents are the primary consumers of this platform. Humans participate; agents drive.
- **Tier 4 is the target.** Every decision must support long-running autonomous tasks (hours/days/weeks). No shortcuts that need retrofitting.
- **The session is the primitive.** Not the request. Sessions outlive any individual request, connection, or server restart.
- **Write code that never needs editing.** Black box modules, testable interfaces, replacement readiness.

## Project Overview

AI-first autonomous agent platform. FastAPI backend, PydanticAI agents, PostgreSQL, Redis, FastStream, Temporal.

## Critical Rules

- **No hardcoded values.** All configuration from `config/settings/*.yaml`. All secrets from `config/.env`. No hardcoded fallbacks in code, ever.
- **Absolute imports only.** Always `from modules.backend.core.config import ...`. Never relative imports.
- **Centralized logging only.** Always `from modules.backend.core.logging import get_logger`. Never `import logging` directly.
- **Timezone-naive UTC datetimes.** Use `from modules.backend.core.utils import utc_now`. Never `datetime.utcnow()` (deprecated) or `datetime.now()` (local time).
- **`.project_root` marker** determines the project root. Use `find_project_root()` from `modules.backend.core.config`.
- **CLI uses Click groups and subcommands.** Single entry point `cli.py` with `tree` command for full discoverability. Every group shows help when called bare — no default actions. `--verbose` and `--debug` on root group only.
- **CLI display is centralized in `report.py`.** All Rich tables, panels, formatting, and styling use shared primitives from `modules/backend/cli/report.py`. Never create `Console`, `Table`, or `Panel` directly in handlers — import from `report.py`.
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

- `cli.py` — Click-based CLI with groups and subcommands (e.g., `cli.py server start`, `cli.py mission run "..."`, `cli.py tree`)
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

## Codebase Intelligence Tools

Two scripts in `scripts/` provide structural and quality analysis:

```bash
# Code map — structural overview for LLM context
python scripts/generate_code_map.py --scope modules/ --format markdown --stats

# PQI score — composite 0-100 quality metric across 7 dimensions
python scripts/score_quality.py --scope modules/ tests/

# Full-fidelity PQI with external tools and code map
python scripts/score_quality.py --scope modules/ tests/ --use-bandit --use-radon --with-code-map --recommendations
```

Use these as quick-reference tools when assessing code quality, planning refactors, or understanding module structure. The code map shows symbol importance (PageRank), cross-references, and import graphs. PQI breaks down into: Maintainability, Security, Modularity, Testability, Robustness, Elegance, Reusability.

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
| **Core (01-16)** | |
| 01 | Core Principles |
| 03 | Backend Architecture |
| 05 | Authentication |
| 06 | Security Standards |
| 08 | Python Coding Standards |
| 09 | Error Codes |
| 10 | Observability |
| 11 | Testing Standards |
| 14 | Background Tasks |
| **Optional Platform (20-28)** | |
| 21 | Event Architecture |
| 24 | LLM Integration |
| 27 | TUI Architecture (Textual + Textual Web) |
| 28 | CLI Architecture (Click, --options, service lifecycle, testing) |
| **AI-First Platform (40-47)** | |
| 40 | Agentic AI Architecture (conceptual) |
| 41 | Agentic AI PydanticAI Implementation |
| 42 | Agent-First Infrastructure (MCP, A2A, agent identity) |
| 43 | AI-First Interface Design (adapter registry, self-describing APIs, service factory) |
| 44 | Multi-Channel Gateway (channel adapters, sessions, WebSocket, security) |
| 46 | Event-Driven Session Architecture (session model, event bus, streaming coordinator, plan management, memory, approval gates, cost tracking) |
| 47 | Agent Module Organization (layout, naming, agent types, shared tools, layered prompts, access control) |