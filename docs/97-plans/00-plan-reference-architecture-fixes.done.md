# Implementation Plan: Reference Architecture Fixes

*Created: 2026-02-19*
*Status: Draft — awaiting decision review*

---

## Background

A cold-read audit of all 25 reference architecture documents identified structural contradictions, missing implementation details, ambiguities, stale cross-references, and redundancy that would cause an AI agent (or a human developer) to produce incorrect or inconsistent code. This plan addresses every issue found, organized by severity.

### Guiding Principle

The user clarified the core client philosophy:

> **Clients must be as thin as possible, so that clients of any form — web, CLI, instant messaging, or another AI agent — are as easy to build as possible, with all logic, even authentication and authorization, sitting in the backend.**

This principle should be reflected more explicitly throughout the documentation, particularly in P1/P2 (doc 01), backend architecture (doc 03), frontend architecture (doc 07), and Telegram integration (docs 20, 23).

---

## Issues Overview

| # | Severity | Issue | Documents Affected |
|---|----------|-------|--------------------|
| 1 | Critical | Project structure contradiction | 03, 04, 15 |
| 2 | Critical | Event naming conflict | 04, 06 |
| 3 | Critical | Worker count contradiction | 22 |
| 4 | Critical | Human delay function signature mismatch | 23 |
| 5 | High | Configuration loading mechanism never defined | 03, 10, 15, 19 |
| 6 | High | Primitive-to-module integration undefined | 02, 03, 04 |
| 7 | High | P3 "Single Database" vs multiple databases | 01, 05 |
| 8 | High | Authorization enforcement — no concrete pattern | 09, 03 |
| 9 | High | Rate limiting — no implementation | 09, 17 |
| 10 | High | Skeleton vs guidance — unclear throughout | All |
| 11 | Medium | Redundancy that will drift | 03/14, 07/10, 15/16, 21/22 |
| 12 | Medium | Stale cross-references | 22 |
| 13 | Medium | Undefined thresholds | 01, 05, 06, 16 |
| 14 | Medium | Missing function implementations | 20, 23 |
| 15 | Medium | "Business logic" boundary undefined | 01, 07 |

---

## Issue 1: Project Structure Contradiction (Critical) — RESOLVED

**Status: RESOLVED** (2026-03-02). D1 decided: Option B. Docs 03, 04, 13 updated to show single `modules/backend/` with layered directories. Doc 04 rewritten to define modules as top-level boundaries (backend, telegram, frontend) with domain separation via file naming within backend layers.

### Problem

Three documents define conflicting project structures:

**Doc 03 (Backend Architecture)** shows a single `modules/backend/` with layered directories:
```
modules/
└── backend/
    ├── api/v1/endpoints/
    ├── core/
    ├── models/
    ├── repositories/
    ├── schemas/
    ├── services/
    └── main.py
```

**Doc 04 (Module Structure)** shows domain-specific modules:
```
modules/
└── {module_name}/
    ├── api.py
    ├── service.py
    ├── repository.py
    ├── models.py
    └── schemas.py
```

**Doc 15 (Project Template)** follows doc 03's structure.

An AI reading doc 03 would put all services in `modules/backend/services/`. An AI reading doc 04 would create `modules/users/service.py`, `modules/orders/service.py`. The code would be organized completely differently.

### Proposed Resolution

> **DECISION NEEDED**: Choose one of the options below.

**Option A: Hybrid (recommended)**

`modules/backend/` is the HTTP-facing infrastructure layer (FastAPI app, middleware, API versioning, health checks). Domain modules sit alongside it as siblings. The backend's HTTP endpoint handlers call domain module APIs.

```
modules/
├── backend/                    # HTTP infrastructure (not a domain module)
│   ├── main.py                 # FastAPI app factory
│   ├── api/
│   │   ├── health.py           # Unversioned health endpoints
│   │   └── v1/
│   │       └── endpoints/      # HTTP handlers (thin — call domain module APIs)
│   │           ├── users.py
│   │           └── orders.py
│   └── core/                   # Config, middleware, exceptions, logging
│       ├── config.py
│       ├── middleware.py
│       ├── exceptions.py
│       └── logging.py
├── users/                      # Domain module (per doc 04 pattern)
│   ├── __init__.py             # Public interface exports
│   ├── api.py                  # Internal API (called by backend/api/ and other modules)
│   ├── service.py              # Business logic
│   ├── repository.py           # Data access
│   ├── models.py               # SQLAlchemy models (private)
│   ├── schemas.py              # Pydantic schemas
│   ├── events.py               # Events published/consumed
│   └── exceptions.py           # Module-specific exceptions
├── orders/                     # Another domain module
│   └── ...
└── telegram/                   # Optional: Telegram bot (client module, not domain)
    └── ...
```

Key clarification: `modules/backend/api/v1/endpoints/users.py` is a thin HTTP handler that imports and calls `modules.users.api.get_user()`. The endpoint handler deals only with HTTP concerns (parsing request, returning response envelope, status codes). The domain module's `api.py` is the true public interface.

**Option B: Single backend module**

Keep doc 03's structure. Domain separation happens via file naming within layers:
```
modules/backend/services/user_service.py
modules/backend/services/order_service.py
modules/backend/repositories/user_repository.py
```

Simpler for small projects but harder to extract modules later.

**Option C: Flat modules, no `backend/` directory**

Every module is a peer:
```
modules/
├── core/          # Config, middleware, exceptions
├── users/         # Domain module with own api.py, service.py, etc.
├── orders/
└── telegram/
```

`main.py` moves to project root. There is no `backend/` namespace.

### Files to Update

| File | Change |
|------|--------|
| `03-backend-architecture.md` | Replace project structure section with chosen option |
| `04-module-structure.md` | Align directory layout and add example showing how HTTP endpoints call module APIs |
| `13-project-template.md` | Update complete project structure to match |
| `08-python-coding-standards.md` | Update project structure section to match |

---

## Issue 2: Event Naming Conflict (Critical) — RESOLVED

**Status: RESOLVED** (2026-03-02). Docs 04 and 21 updated. Aligned with Plan 10 and doc 46.

### Resolution

The conflict was that two naming conventions served two different purposes but this was never documented explicitly. The resolution formalizes this distinction:

| Concern | Convention | Format | Example |
|---------|-----------|--------|---------|
| **`event_type` field** (inside the envelope) | Dot notation | `{domain}.{entity}.{action}` | `notes.note.created` |
| **Redis Stream name** (domain events) | Colon + hyphens | `{domain}:{entity}-{action}` | `notes:note-created` |
| **Redis Pub/Sub channel** (session events) | Session-scoped | `session:{session_id}` | `session:abc-123` |
| **Consumer group name** | Hyphenated | `{consuming-module}-{purpose}` | `notifications-user-welcome` |

**Decision**: One stream per event type (not per module). More granular, consumers subscribe to exactly the events they need.

### Files Updated

| File | Change |
|------|--------|
| `04-module-structure.md` | Added Redis stream and Pub/Sub naming alongside `event_type` dot notation |
| `21-event-architecture.md` | Replaced "Channel Naming" with "Naming Conventions" section covering all three patterns; fixed outbox relay code |

---

## Issue 3: Worker Count Contradiction (Critical) — RESOLVED

**Status: RESOLVED** (2026-03-02). Rewrote Worker Configuration section to explicitly state the formula applies to CPU-bound sync apps and direct the reader to use the async worker count table instead.

### Problem

Doc 22 (Azure Deployment) line 106 states the formula `(2 × vCPU) + 1` for Gunicorn workers. The table immediately below shows P2v3 (4 vCPU) = 3–4 workers. The formula gives 9.

### Analysis

The document actually explains this — the formula is the general starting point, and the table shows the *adjusted* recommendation for async I/O-bound applications. But an AI scanning for a quick answer would grab the formula and produce a wrong deployment config.

### Proposed Resolution

Rewrite the section to eliminate ambiguity:

```markdown
### Worker Configuration

The standard Gunicorn formula `(2 × vCPU) + 1` is designed for CPU-bound synchronous
applications. This architecture uses async FastAPI with Uvicorn workers, where each worker
handles hundreds of concurrent connections via asyncio. **Use the table below, not the formula.**

| SKU   | vCPU | Workers | Rationale |
|-------|------|---------|-----------|
| B1    | 1    | 2       | Development only |
| P1v3  | 2    | 2–3     | Each worker handles many concurrent async requests |
| P2v3  | 4    | 3–4     | Scale via async concurrency, not worker count |
| P3v3  | 8    | 4–6     | Diminishing returns beyond this |
```

### Files to Update

| File | Change |
|------|--------|
| `16-deployment-azure.md` | Rewrite Worker Configuration section |

---

## Issue 4: Human Delay Function Signature Mismatch (Critical) — RESOLVED

**Status: RESOLVED** (2026-03-02). Fixed `human_delay()` to accept optional `min_seconds`/`max_seconds` overrides with config defaults as fallback.

### Problem

Doc 23 (Telegram Client) defines `human_delay()` as a function that reads config (no parameters), then later calls it as `human_delay(1.0, 3.0)` with parameters.

### Proposed Resolution

Standardize the function to accept optional overrides:

```python
async def human_delay(
    min_seconds: float | None = None,
    max_seconds: float | None = None,
) -> None:
    """Delay with human-like timing. Uses config defaults if not overridden."""
    min_s = min_seconds or settings.telegram_client.human_delay_min
    max_s = max_seconds or settings.telegram_client.human_delay_max
    await asyncio.sleep(random.uniform(min_s, max_s))
```

### Files to Update

| File | Change |
|------|--------|
| `26-telegram-client-integration.md` | Fix function definition and all call sites |

---

## Issue 5: Configuration Loading Mechanism Never Defined (High) — RESOLVED

**Status: RESOLVED** (2026-03-02). Added "Configuration Loading" section to doc 03 documenting the two-mechanism approach: secrets via `.env`/Pydantic Settings, app config via YAML/`get_app_config()`. Includes precedence order, code examples, and rules.

### Problem

Every document says "no hardcoded values, use config" but none defines the actual loading mechanism. Docs 03, 10, 15, and 19 all reference configuration but never specify:
- What loads `.env` files
- What loads YAML files
- The precedence order (which overrides which)
- Where the `Settings` class lives
- How modules access configuration

### Proposed Resolution

Add a dedicated "Configuration" section to doc 03 (Backend Architecture), since it is the document that all others depend on. Define it once, reference it everywhere.

**Mechanism**: Pydantic Settings as the primary configuration framework.

```
Loading order:
1. YAML files loaded from config/settings/*.yaml (application defaults)
2. .env file loaded from config/.env (environment-specific overrides and secrets)
3. Environment variables override everything (for deployment)

Precedence: Environment variables > .env file > YAML defaults
```

**Settings class location**: `modules/backend/core/config.py`

**Module access**: Settings instance injected via FastAPI dependency injection or imported from `modules.backend.core.config`.

> **DECISION NEEDED**: Should every module define its own settings subsection (e.g., `settings.telegram`, `settings.llm`), or should there be one flat settings class? Subsections are cleaner but require each module to register its config schema.

### Files to Update

| File | Change |
|------|--------|
| `03-backend-architecture.md` | Add full Configuration Loading section with mechanism, code examples, and precedence |
| `08-python-coding-standards.md` | Reference doc 03's config section instead of redefining; keep coding patterns only |
| `13-project-template.md` | Add annotation to config/ directory explaining loading mechanism |
| `14-background-tasks.md` | Reference doc 03's config section for broker configuration |

---

## Issue 6: Primitive-to-Module Integration Undefined (High) — RESOLVED

**Status: RESOLVED** (2026-03-02). Added "Integration with Architecture Layers" section to doc 02 with layer flow diagram and worked Task example showing Model → Repository → Service → Schema → API → Events.

### Problem

Doc 02 (Primitive Identification) defines the primitive concept well but never connects it to:
- How modules (04) expose primitives through their APIs
- How backend endpoints (03) CRUD primitives
- How events (06) relate to primitive state changes
- How the data layer (05) stores primitives

An AI asked to "build a task management system following these standards" wouldn't know how to wire the primitive through the stack.

### Proposed Resolution

Add an "Integration with Other Standards" section to doc 02 that shows the primitive flowing through the architecture layers:

```
1. Model (05):     SQLAlchemy model with primitive fields (id, type, status, timestamps)
2. Repository:     CRUD operations on primitive table
3. Service (03):   Business logic that transitions primitive states
4. Module API (04): Public functions that accept/return primitive schemas
5. HTTP API (03):  Endpoints that expose primitive operations (create, get, list, update)
6. Events (06):    Primitive state changes publish events (task.task.created, task.task.completed)
7. Clients (07):   Display primitive state, trigger actions via HTTP API
```

Include a concrete worked example: a `Task` primitive flowing from HTTP request through service to database and back, with an event published on state change.

### Files to Update

| File | Change |
|------|--------|
| `02-primitive-identification.md` | Add "Integration with Other Standards" section with wiring example |

---

## Issue 7: P3 "Single Database" vs Multiple Databases (High) — RESOLVED

**Status: RESOLVED** (2026-03-02). Rewritten P3 in doc 01 from "Single Database of Record" to "Single Source of Truth Per Entity". Clarified: one authoritative write source, read replicas/caches/analytical copies are fine.

### Problem

Core Principle P3 says "One authoritative data store per data type. No data synchronization between databases for the same entity." Doc 05 then introduces PostgreSQL, TimescaleDB, DuckDB, and Redis. This appears contradictory.

### Analysis

P3 is actually about *write authority*, not about having a single database server. PostgreSQL is the authoritative write source. Redis is an ephemeral cache (not authoritative). TimescaleDB is a PostgreSQL extension (same server). DuckDB reads Parquet exports (read-only analytical copy). None of these violate P3 if stated correctly.

### Proposed Resolution

Clarify P3 in doc 01:

```markdown
### P3: Single Source of Truth Per Entity

One authoritative **write** source per data type. Read replicas, caches, and analytical
copies are acceptable — but they derive from the authoritative source, never the reverse.

Implications:
- User data writes go to PostgreSQL only
- Redis caches are ephemeral and reconstructable — never the source of truth
- DuckDB/Parquet are read-only analytical copies of data that originates in PostgreSQL
- TimescaleDB is a PostgreSQL extension, not a separate database
```

### Files to Update

| File | Change |
|------|--------|
| `01-core-principles.md` | Rewrite P3 to clarify "single write source" vs "single database server" |
| `20-data-layer.md` | Add note in Context section explaining how multiple technologies don't violate P3 |

---

## Issue 8: Authorization Enforcement — No Concrete Pattern (High) — RESOLVED

**Status: RESOLVED** (2026-03-02). Replaced bullet-point description with complete code example showing the 3-layer pattern: `get_current_user` dependency → API handler passes `requesting_user` → service enforces permissions.

### Problem

Doc 09 says "authorization checked at service layer, not API layer" but never shows:
- How the user identity gets from the API layer to the service layer
- The dependency injection or context pattern
- A concrete code example of the full flow

### Proposed Resolution

Add an "Authorization Flow" section to doc 09 showing the complete pattern:

```python
# 1. API layer: extract user identity (thin — no authorization logic)
@router.get("/orders/{order_id}")
async def get_order(order_id: UUID, current_user: User = Depends(get_current_user)):
    return await order_service.get_order(order_id, requesting_user=current_user)

# 2. Service layer: enforce authorization (all logic here)
async def get_order(order_id: UUID, requesting_user: User) -> OrderSchema:
    order = await order_repository.get(order_id)
    if not order:
        raise NotFoundError("Order not found")
    if order.user_id != requesting_user.id and not requesting_user.has_role("admin"):
        raise AuthorizationError("Not authorized to view this order")
    return OrderSchema.from_orm(order)

# 3. get_current_user dependency: resolves token/API key to User object
async def get_current_user(request: Request) -> User:
    # Extracts API key or JWT, validates, returns User
    # This is the ONLY place auth tokens are parsed
```

This reinforces the guiding principle: clients just send a token; the backend handles everything.

### Files to Update

| File | Change |
|------|--------|
| `05-authentication.md` | Add "Authorization Flow" section with complete code example |
| `03-backend-architecture.md` | Reference doc 09's authorization flow in the service layer section |

---

## Issue 9: Rate Limiting — No Implementation (High) — RESOLVED

**Status: RESOLVED** (2026-03-02). Added implementation details to doc 06: slowapi library, Redis storage, sliding window algorithm, code example with per-endpoint override, response headers.

### Problem

Docs 09 and 17 specify rate limits (1000/min authenticated, 100/min unauthenticated, etc.) but neither defines the algorithm, storage, or library.

### Proposed Resolution

Add a "Rate Limiting Implementation" section to doc 17 (Security Standards), since rate limiting is a security control:

- **Algorithm**: Sliding window (preferred) or token bucket
- **Storage**: Redis (same instance used for caching/tasks)
- **Key format**: `ratelimit:{identifier}:{window}` where identifier is user ID or IP
- **Library**: `slowapi` (built on `limits`, integrates with FastAPI) or custom middleware
- **Headers**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`

> **DECISION NEEDED**: Use `slowapi` (quick to implement, well-known) or custom Redis middleware (more control, no dependency)? Given the "prefer simple solutions" rule, `slowapi` seems appropriate.

### Files to Update

| File | Change |
|------|--------|
| `06-security-standards.md` | Add "Rate Limiting Implementation" section with algorithm, storage, and code |
| `05-authentication.md` | Keep the limit values, add reference to doc 17 for implementation |

---

## Issue 10: Skeleton vs Guidance — Unclear Throughout (High)

### Problem

Most documents mix "this is already implemented in skeleton code" with "this is guidance for when you need it." An AI doesn't know what already exists vs what to create.

### Proposed Resolution

Add a "Skeleton Implementation Status" section near the top of each document (after Context, before the first technical section). Use a consistent format:

```markdown
## Skeleton Implementation Status

| Feature | Status | Location |
|---------|--------|----------|
| FastAPI app with health endpoints | Implemented | `modules/backend/main.py` |
| Request context middleware | Implemented | `modules/backend/core/middleware.py` |
| Structured logging | Implemented | `modules/backend/core/logging.py` |
| Cursor-based pagination | Guidance | Implement when adding list endpoints |
| Background tasks (Taskiq) | Guidance | Implement when async processing needed |
```

**Status values**: `Implemented` (exists in skeleton), `Guidance` (implement when needed), `Partial` (skeleton has base, extend per project).

> **DECISION NEEDED**: Should this be done for all 25 documents, or only the ones that have implementable code (skipping pure-guidance docs like 01, 02)? Recommendation: only documents that describe code patterns (03, 04, 06, 07, 08, 09, 10, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 25). Skip 00, 01, 02, 05, 13.

### Files to Update

| File | Change |
|------|--------|
| ~20 documents | Add "Skeleton Implementation Status" table |

**Note**: This requires auditing the actual skeleton code to determine what's implemented. This should be done *after* the skeleton code is built, not before — otherwise the tables would all say "Guidance" for everything. **Defer this issue until skeleton code exists.**

---

## Issue 11: Redundancy That Will Drift (Medium) — RESOLVED

**Status: RESOLVED** (2026-03-02). Fixed 3 of 5 redundancies (items 2 and 4 were not actually redundant): doc 09 error envelope → references doc 03; doc 13 test structure → references doc 11; doc 00 philosophy → references doc 01.

### Problem

The same concepts are defined in multiple places, creating drift risk:

| Concept | Defined In | Risk |
|---------|-----------|------|
| Error response envelope | 03 and 14 | Different details could diverge |
| CLI standards (`--verbose`, `--debug`) | 07 and 10 | One updates, other doesn't |
| Test directory structure | 15 and 16 | Structural drift |
| Background task deployment | 21 and 22 | Platform-specific drift |
| Backend-first philosophy | 00, 01, 03 | Wording inconsistency |

### Proposed Resolution

Establish a **single source of truth** for each concept and make other documents reference it:

| Concept | Source of Truth | Other Docs |
|---------|----------------|------------|
| Error response envelope | 14 (Error Codes) | 03 references 14 |
| CLI standards | 10 (Python Coding Standards) | 07 references 10 |
| Test directory structure | 16 (Testing Standards) | 15 references 16 |
| Backend-first philosophy | 01 (Core Principles) | 00, 03 reference 01 |
| Background task deployment | 19 (Background Tasks) | 21, 22 reference 19 for task patterns, add only platform-specific config |

For each redundant section, replace the duplicated content with a brief summary + explicit reference:

```markdown
### Error Response Format

All API errors follow the standard envelope defined in **09-error-codes.md**. See that
document for the complete specification, error categories, and client handling guide.
```

### Files to Update

| File | Change |
|------|--------|
| `03-backend-architecture.md` | Replace error response section with reference to 14 |
| `22-frontend-architecture.md` | Replace CLI standards with reference to 10 |
| `13-project-template.md` | Replace test structure with reference to 16 |
| `00-overview.md` | Trim philosophy paragraph, reference 01 |

---

## Issue 12: Stale Cross-References (Medium) — RESOLVED

**Status: RESOLVED** (2026-03-02). Verified: no stale `14-Deployment` references remain. All cross-references use current doc numbers. The "15-Deployment" references in doc 16 are correct.

### Problem

Several cross-references use old document numbers or reference content that doesn't exist:

| Location | Issue |
|----------|-------|
| Doc 22, deeper sections | May still reference "14-Deployment" (old numbering) |
| Doc 22, line 129 | References "30-second ping interval" in doc 06 — doesn't exist there |
| Doc 22, "No Containers" section | References "14-Deployment" — already partially fixed to "21-Deployment" |

### Proposed Resolution

Full-text search all 25 documents for:
- `14-Deployment` or `14-deployment` (old numbering)
- Any reference to doc numbers that don't match current titles
- Any quoted values attributed to other docs that don't exist there

### Files to Update

| File | Change |
|------|--------|
| `16-deployment-azure.md` | Fix all remaining "14-Deployment" → "21-Deployment" references |
| `16-deployment-azure.md` | Fix WebSocket ping reference — either add 30s ping to doc 06, or change doc 22 to reference the correct source |
| All documents | Verify all cross-references (automated grep) |

---

## Issue 13: Undefined Thresholds (Medium) — RESOLVED

**Status: RESOLVED** (2026-03-02). Added concrete values: doc 21 "moderate scale" → "up to 10,000 events/sec sustained"; doc 20 "large datasets" → ">100MB or >1M rows", "basic PostgreSQL" → "single-table CRUD with standard indexes"; doc 01 "critical paths" → added "service outage". Git LFS 10-100MB threshold was already concrete.

### Problem

Multiple documents use vague terms without concrete values:
- "Moderate scale" (doc 06) — no event/second number
- "Large datasets" (doc 05) — no size threshold
- "Critical paths" (docs 01, 16) — no definition
- "Medium files" for Git LFS (doc 05) — no size range
- "Basic PostgreSQL" (doc 05) — no criteria

### Proposed Resolution

Add concrete thresholds:

| Term | Document | Proposed Definition |
|------|----------|---------------------|
| Moderate scale | 06 | Up to 10,000 events/second sustained |
| Large datasets | 05 | >100MB or >1M rows |
| Critical paths | 01, 16 | Operations where failure causes data loss, financial loss, security breach, or service outage |
| Medium files (Git LFS) | 05 | 10MB – 100MB |
| Basic PostgreSQL | 05 | Single-table CRUD with standard indexes, no time-series, no analytical queries |

> **DECISION NEEDED**: Are these thresholds reasonable for your projects, or should they be different?

### Files to Update

| File | Change |
|------|--------|
| `01-core-principles.md` | Define "critical paths" in D3 |
| `20-data-layer.md` | Add size thresholds for datasets, Git LFS |
| `21-event-architecture.md` | Add events/second threshold for Redis Streams |
| `11-testing-standards.md` | Reference doc 01's definition of critical paths |

---

## Issue 14: Missing Function Implementations (Medium) — RESOLVED

**Status: RESOLVED** (2026-03-02). Added function stubs to doc 25 (`setup_webhook`, `cleanup_bot`, `get_webhook_router`, `get_notification_service`) and doc 26 (`queue_message_for_processing`, `get_cached_channel_data`).

### Problem

Docs 20 and 23 reference functions that are never defined:

**Doc 20 (Telegram Bot)**:
- `setup_webhook()` — referenced but not shown
- `get_webhook_router()` — referenced but not shown
- `get_notification_service()` — referenced but not shown

**Doc 23 (Telegram Client)**:
- `queue_message_for_processing()` — called but not defined
- `get_cached_channel_data()` — called but not defined
- `NotificationService` — referenced in agent example but undefined

### Proposed Resolution

For each missing function, either:
1. Add a concrete implementation to the document, or
2. Add a clearly marked stub with a description of what it should do

Since these are reference architecture docs (not skeleton code), option 2 is more appropriate — provide the signature, docstring, and key implementation notes:

```python
async def queue_message_for_processing(message_data: dict) -> None:
    """Queue a scraped message for backend processing via Redis.

    Implementation: Publishes to the Redis stream defined in
    21-event-architecture.md. The backend module consumes
    these events and processes them through the service layer.
    """
    await redis.xadd("telegram:messages-scraped", message_data)
```

### Files to Update

| File | Change |
|------|--------|
| `25-telegram-bot-integration.md` | Add stubs for `setup_webhook`, `get_webhook_router`, `get_notification_service` |
| `26-telegram-client-integration.md` | Add stubs for `queue_message_for_processing`, `get_cached_channel_data`; fix `NotificationService` reference |

---

## Issue 15: "Business Logic" Boundary Undefined (Medium) — RESOLVED

**Status: RESOLVED** (2026-03-02). Added "Business Logic Boundary" section under P1 in doc 01 with explicit backend-always vs client-only lists and the "when uncertain, put it in the backend" rule.

### Problem

P1 says "Every business rule, validation, calculation, and decision lives in the backend." But the boundary between "business logic" (backend only) and "presentation logic" (client allowed) is never formally defined. This matters because it determines what clients are allowed to do.

### Proposed Resolution

Add a "Business Logic Boundary" section to doc 01, using the user's guiding principle:

```markdown
### What Belongs in the Backend (always)

- Data validation (format, range, uniqueness, business rules)
- Authentication (token validation, session management)
- Authorization (permission checks, resource ownership)
- Data calculations (totals, aggregations, derived fields)
- State transitions (order placed → order shipped)
- External service calls (payment processing, email sending)
- Data persistence (reads and writes)

### What Belongs in the Client (only)

- UI state (which tab is selected, whether a modal is open)
- Optimistic UI updates (show expected state while waiting for backend confirmation)
- Input formatting (display formatting, not validation)
- Navigation and routing
- Rendering and layout

### Grey Areas — Backend Wins

When uncertain, put it in the backend. The cost of a client being too thin
is a few extra API calls. The cost of a client being too thick is duplicated
logic across every client type (web, CLI, Telegram, AI agent).
```

### Files to Update

| File | Change |
|------|--------|
| `01-core-principles.md` | Add "Business Logic Boundary" under P1 with the above lists |
| `22-frontend-architecture.md` | Reference doc 01's boundary definition in the thin client section |

---

## Execution Sequence

Issues should be addressed in dependency order. Some fixes unblock others.

### Phase 1: Structural Resolution (Issues 1, 2)

These are the foundation — every other document references the project structure and event naming. Fix these first so all subsequent changes are consistent.

1. **Decide on project structure** (Issue 1) — this is the highest-impact decision
2. **Align event naming** (Issue 2) — depends on module naming from Issue 1
3. Update docs 03, 04, 06, 15 with the resolved structure

### Phase 2: Core Gaps (Issues 5, 6, 7, 8, 15)

These fill in the missing "wiring" that connects the architecture documents into a coherent whole.

4. **Define configuration loading** (Issue 5) — add to doc 03
5. **Add primitive integration example** (Issue 6) — add to doc 02
6. **Clarify P3** (Issue 7) — update doc 01
7. **Add authorization flow** (Issue 8) — add to doc 09
8. **Define business logic boundary** (Issue 15) — add to doc 01

### Phase 3: Implementation Details (Issues 3, 4, 9)

Fix specific errors and add missing implementation guidance.

9. **Fix worker count** (Issue 3) — update doc 22
10. **Fix human delay signature** (Issue 4) — update doc 23
11. **Add rate limiting implementation** (Issue 9) — add to doc 17

### Phase 4: Cleanup (Issues 11, 12, 13, 14)

Reduce drift risk and fix minor issues.

12. **Consolidate redundancy** (Issue 11) — update 03, 07, 15, 00
13. **Fix stale cross-references** (Issue 12) — update doc 22, verify all docs
14. **Add concrete thresholds** (Issue 13) — update 01, 05, 06, 16
15. **Add missing function stubs** (Issue 14) — update 20, 23

### Phase 5: Skeleton Status (Issue 10)

This should be done *after* skeleton code exists.

16. **Add skeleton implementation status** (Issue 10) — update ~20 docs after code is built

---

## Summary of All File Changes

| Document | Changes | Phase |
|----------|---------|-------|
| `00-overview.md` | Trim redundant philosophy, reference 01 | 4 |
| `01-core-principles.md` | Rewrite P3, add business logic boundary under P1, define "critical paths" in D3 | 2 |
| `02-primitive-identification.md` | Add "Integration with Other Standards" section with wiring example | 2 |
| `03-backend-architecture.md` | Rewrite project structure, add config loading, reference 14 for errors, reference 09 for auth | 1, 2, 4 |
| `04-module-structure.md` | Align directory layout, add HTTP→module wiring example, align event naming | 1 |
| `20-data-layer.md` | Add P3 clarification note, add size thresholds | 2, 4 |
| `21-event-architecture.md` | Align channel naming, add threshold for "moderate scale" | 1, 4 |
| `22-frontend-architecture.md` | Reference 10 for CLI standards, reference 01 for business logic boundary | 4 |
| `05-authentication.md` | Add authorization flow section with code example | 2 |
| `08-python-coding-standards.md` | Update project structure, reference 03 for config | 1, 2 |
| `13-project-template.md` | Update project structure, reference 16 for test structure | 1, 4 |
| `11-testing-standards.md` | Reference 01 for "critical paths" definition | 4 |
| `06-security-standards.md` | Add rate limiting implementation section | 3 |
| `25-telegram-bot-integration.md` | Add missing function stubs | 4 |
| `16-deployment-azure.md` | Fix worker count, fix stale references (14→21, WebSocket ping) | 3, 4 |
| `26-telegram-client-integration.md` | Fix human_delay signature, add missing function stubs | 3, 4 |

**Documents with no changes needed**: 08, 11, 12, 13, 14, 18, 19, 21, 25

---

## Decisions Needed

Before implementation can begin, the following decisions need to be made:

| # | Decision | Options | Resolution |
|---|----------|---------|------------|
| D1 | Project structure | A (hybrid), B (single backend), C (flat modules) | **RESOLVED**: Option B (single `modules/backend/` with layered directories). Matches current codebase. Domain separation via file naming within layers. Align docs 03, 04, 15 to match. |
| D2 | Event stream naming | One stream per module vs one stream per event type | **RESOLVED**: One stream per event type (`{domain}:{entity}-{action}`). `event_type` field uses dots (`{domain}.{entity}.{action}`). Session events use Pub/Sub (`session:{session_id}`). Docs 04, 21 updated. Aligned with Plan 10 and doc 46. |
| D3 | Config subsections | Per-module settings subsections vs one flat class | **RESOLVED**: Document what exists. Two mechanisms — secrets via `config/.env` + flat `Settings` class; app config via `config/settings/*.yaml` with per-module sections. No code changes needed. |
| D4 | Skeleton status markers | All docs, code-only docs, or defer | **DEFERRED** until skeleton code exists. |
| D5 | Rate limiting library | `slowapi` vs custom Redis middleware | **RESOLVED**: `slowapi` — integrates with FastAPI, built on `limits` library, minimal code. |
| D6 | Thresholds | Are proposed values reasonable? | **RESOLVED**: All proposed values accepted as-is. Moderate scale = 10K events/sec, Large datasets = >100MB or >1M rows, Critical paths = data/financial/security/outage risk, Medium files = 10-100MB, Basic PostgreSQL = single-table CRUD with standard indexes. |
