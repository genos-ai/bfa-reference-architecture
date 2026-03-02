# 04 - Module Structure

*Version: 1.1.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.1.0 (2026-03-02): Aligned with D1 decision (Option B — single backend module with layered directories); updated module examples, directory layout, and inter-module communication to match codebase
- 1.0.0 (2025-01-27): Initial module architecture standard

---

## Context

The architecture uses a modular monolith — a single deployable unit that is internally organized as independent modules. This pattern exists because microservices solve scaling and team-boundary problems but introduce distributed systems complexity (network latency, distributed transactions, service discovery, coordinated deployments) that most projects don't need on day one.

The key design decision is that modules communicate through defined interfaces (`api.py` functions and events), never through direct imports of each other's internals. Each module owns its database tables exclusively — no shared tables, no cross-module joins. This boundary discipline means a module can be extracted into a separate service later by replacing its `api.py` interface with an HTTP API, without rewriting the consumers.

This document directly implements the separation of concerns mandate from Core Principles (01) and provides the organizational backbone for backend development (03). Event-driven communication between modules follows the patterns in Event Architecture (21), and the module layout defined here is reflected in the project template (13) and testing standards (11).

---

## Philosophy

### Modular Monolith

Applications are structured as modular monoliths:
- Single deployable unit
- Internally organized as independent modules
- Modules communicate via defined interfaces, not direct imports
- Enables future service extraction without rewriting

### Why Not Microservices From Start

Microservices add operational complexity:
- Network latency between services
- Distributed transactions
- Service discovery
- Multiple deployments to coordinate

Start with modular monolith. Extract services only when:
- Module needs independent scaling
- Module needs different deployment cadence
- Team boundaries require separation

---

## Module Definition

### What Is A Module

A module is a top-level deployment or technology boundary under `modules/`. Each module is a cohesive unit with:
- Clear responsibility boundary (backend infrastructure, client adapter, frontend)
- Defined public interface
- Internal implementation hidden from other modules
- Independent testability

### Top-Level Modules

| Module | Type | Responsibility |
|--------|------|----------------|
| `backend` | Infrastructure | FastAPI app, business logic, data access, agents, background tasks |
| `telegram` | Client adapter | Telegram bot (aiogram v3, webhook mode) |
| `frontend` | Client | React + Vite + Tailwind web UI |

Additional client modules (TUI, MCP server, A2A endpoint) follow the same pattern — each is a sibling under `modules/`.

### Domain Separation Within Backend

Domain separation (users, notes, orders) happens via **file naming within layers**, not via separate module directories:

```
modules/backend/services/user_service.py
modules/backend/services/note_service.py
modules/backend/repositories/user_repository.py
modules/backend/repositories/note_repository.py
modules/backend/models/user.py
modules/backend/models/note.py
```

This is simpler for projects where domains share infrastructure (database, middleware, auth) and don't need independent deployment.

---

## Module Structure

### Backend Module Layout

The backend module uses **layered directories** with strict layer separation (API → Service → Repository → Model):

```
modules/
├── backend/
│   ├── __init__.py
│   ├── main.py                  # FastAPI entry point
│   ├── api/
│   │   ├── health.py            # Health check endpoints
│   │   └── v1/
│   │       └── endpoints/       # HTTP handlers (thin — call services)
│   ├── core/                    # Config, middleware, exceptions, logging, security
│   ├── models/                  # SQLAlchemy models
│   ├── repositories/            # Data access layer
│   ├── schemas/                 # Pydantic request/response schemas
│   ├── services/                # Business logic
│   ├── agents/                  # PydanticAI agents (coordinator, verticals)
│   ├── gateway/                 # Channel adapter registry, security
│   ├── tasks/                   # Background tasks (Taskiq broker)
│   ├── cli/                     # CLI subcommands
│   └── migrations/              # Alembic database migrations
├── telegram/                    # Telegram bot (client module)
│   ├── handlers/
│   ├── callbacks/
│   ├── keyboards/
│   ├── middlewares/
│   ├── services/
│   └── states/
└── frontend/                    # React web UI (client module)
    └── src/
```

### Client Module Layout

Client modules (telegram, frontend, future TUI) have their own internal structure appropriate to their technology. They communicate with `backend` only through its HTTP API or event bus — never by importing backend internals.

### Module Independence

Each top-level module:
- Does not import from other modules' internals
- Communicates only via HTTP API, events, or defined interfaces
- Can be tested in isolation
- Has its own `__init__.py` with minimal exports

---

## Inter-Module Communication

### The Rule

**Top-level modules never import each other's internals.**

Wrong:
```python
# In telegram module
from modules.backend.repositories.user_repository import UserRepository  # FORBIDDEN
from modules.backend.models.user import User  # FORBIDDEN
```

Right:
```python
# In telegram module — communicate via HTTP API
response = await httpx_client.get(f"{backend_url}/api/v1/users/{user_id}")
```

### Communication Methods

Top-level modules communicate via two mechanisms:

**1. HTTP API**
- Client modules (telegram, frontend, TUI) call `backend` via its REST API
- Backend never imports from client modules
- All authentication, authorization, and business logic lives in backend

**2. Events**
- Backend publishes events when state changes (Redis Streams for domain events, Redis Pub/Sub for session events)
- Client modules subscribe to relevant events for real-time updates
- Async, decoupled
- Used for: Streaming responses, notifications, session events

### Within Backend: Layered Architecture

Within `modules/backend/`, code follows strict layer dependencies:

```
API endpoints  →  Services  →  Repositories  →  Models
     ↓               ↓
   Schemas        Exceptions
```

- API handlers call services, never repositories directly
- Services contain business logic and call repositories
- Repositories handle data access and return ORM models
- Schemas define the API contract (request/response shapes)

---

## Data Ownership

### All Data Lives in Backend

The `backend` module owns all database tables. Client modules (telegram, frontend) never access the database directly — they go through the backend's HTTP API.

Within backend, data access follows the layered architecture:
- Services orchestrate business logic
- Repositories encapsulate queries
- Models define the schema
- Domain separation is via file naming (e.g., `user_repository.py`, `note_repository.py`)

---

## Event Communication

### When To Use Events

Use events when:
- Multiple modules need to react to a change
- Reaction doesn't need to be synchronous
- Loose coupling is more important than immediate consistency

### Event Structure

Events follow standard envelope:
- Event type identifies the event
- Payload contains relevant data
- Source module publishes, interested modules subscribe

### Event Naming

Two naming conventions serve two purposes — do not mix them.

**`event_type` field** (inside the event envelope): dot notation.

Format: `{module}.{entity}.{action}`

Examples:
- `notes.note.created`
- `agent.response.chunk`
- `plan.task.completed`

**Redis Stream name** (the transport channel for domain events): colon + hyphens.

Format: `{module}:{entity}-{action}`

Examples:
- `notes:note-created`
- `orders:order-completed`

**Redis Pub/Sub channel** (ephemeral session events): `session:{session_id}`

See doc 21 (Event Architecture) and doc 46 (Event-Driven Session Architecture) for full details.

### Event Payload

Include enough data for consumers to act without API calls:
- Entity ID (always)
- Key attributes that changed
- Timestamp

Do not include:
- Entire entity (too large, may be stale)
- Sensitive data (passwords, tokens)

---

## Module Dependencies

### Dependency Direction

```
telegram ──→ backend (via HTTP API)
frontend ──→ backend (via HTTP API)
backend  ──→ nothing (self-contained)
```

Client modules depend on backend. Backend depends on nothing. No circular dependencies between top-level modules.

### Within Backend: Layer Dependencies

```
API endpoints  →  Services  →  Repositories  →  Models
```

No skipping layers. API handlers never call repositories directly.

### Enforcing Boundaries

- Client modules never import from `modules.backend` — they use HTTP
- Within backend, strict layering enforced via code review and import checks
- Absolute imports only (`from modules.backend.services.user_service import ...`)

---

## Service Extraction

### When To Extract

Extract a domain from backend into a separate service when:
- Different scaling requirements
- Different deployment frequency
- Team ownership boundaries

### How Layered Design Helps

Because domains are already separated by file naming and service boundaries:
1. Create a new top-level module for the domain
2. Move the relevant service, repository, model, and schema files
3. Replace internal service calls with HTTP API calls
4. Existing event patterns already decouple consumers

---

## Testing

### Unit Testing

Test backend layers in isolation:
- Mock repository for service tests
- Mock database for repository tests
- Test business logic thoroughly

### Integration Testing

Test through HTTP API:
- Real database
- Test via API endpoints
- Verify expected behavior end-to-end

### Client Module Testing

Test client modules with mocked backend API:
- Mock HTTP responses
- Verify correct API calls made
- Verify event handling

---

## Module Checklist

When creating a new top-level module:

- [ ] Clear responsibility boundary defined
- [ ] Directory structure follows standard
- [ ] No imports from other modules' internals
- [ ] Communication via HTTP API or events only
- [ ] Unit tests for core logic
- [ ] Integration tests for API
- [ ] Added to AGENTS.md module table
