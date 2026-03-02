# 01 - Core Principles

*Version: 1.1.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.1.0 (2026-02-24): Added P8 Secure by Default — deny-by-default posture for all external interfaces, complements P5 Fail Fast
- 1.0.0 (2025-01-27): Initial generic principles document

---

## Context

Every codebase accumulates implicit rules — assumptions baked into code that new team members discover only by reading hundreds of files or breaking something. This document makes those rules explicit and non-negotiable, so they are enforced by convention rather than discovered by accident.

The architecture is backend-first by design. Business logic lives exclusively in the backend because splitting it across clients (web, CLI, mobile) creates divergent behavior, doubles validation effort, and makes bugs harder to trace. Clients are thin presentation layers that display what the backend provides. This single decision shapes everything else in these standards.

The remaining principles address the failure modes that most commonly destroy codebases: implicit magic that nobody understands six months later (P4), silent failures that corrupt data without alerting anyone (P5), operations that can't be safely retried (P6), and hardcoded values scattered across files instead of centralized configuration (P7). Each principle exists because it prevents a specific, recurring class of production incident. These principles are the foundation — every other document in this set implements or reinforces them.

---

## Mandatory Principles

These principles are non-negotiable. All architectural decisions must align with them.

### P1: Backend Owns All Business Logic

Every business rule, validation, calculation, and decision lives in the backend. Clients display results; they do not compute them.

Implications:
- Data calculations happen server-side
- Input validation happens server-side
- User permission checks happen server-side
- Data transformations happen server-side

### Business Logic Boundary

**Backend (always):** data validation, authentication, authorization, data calculations, state transitions, external service calls, data persistence.

**Client (only):** UI state (tab selection, modal open/closed), optimistic UI updates, input formatting (display only, not validation), navigation/routing, rendering/layout.

**When uncertain, put it in the backend.** The cost of a client being too thin is a few extra API calls. The cost of a client being too thick is duplicated logic across every client type (web, CLI, Telegram, AI agent).

### P2: Clients Are Stateless Presentation Layers

Clients maintain only UI state (which tab is selected, whether a modal is open). All application state comes from the backend via API calls or real-time connections.

Implications:
- Refresh the page, application state persists
- Switch clients (web to CLI), same data available
- Client bugs cannot corrupt application state

### P3: Single Source of Truth Per Entity

One authoritative **write** source per data type. Read replicas, caches, and analytical copies are acceptable — but they derive from the authoritative source, never the reverse.

Implications:
- User data writes go to PostgreSQL only
- Redis caches are ephemeral and reconstructable — never the source of truth
- DuckDB/Parquet are read-only analytical copies of data that originates in PostgreSQL
- TimescaleDB is a PostgreSQL extension, not a separate database
- Multiple technologies are fine; multiple write sources for the same entity are not

### P4: Explicit Over Implicit

Configuration is explicit. Dependencies are declared. Side effects are documented. Nothing happens "magically."

Implications:
- No auto-discovery of services
- No implicit type coercion
- No hidden global state
- All environment variables documented

### P5: Fail Fast, Fail Loudly

Errors surface immediately with clear messages. Silent failures are forbidden. Systems should not continue operating with corrupted or uncertain state.

Implications:
- Missing configuration fails at startup, not at first use
- Invalid data raises exceptions, not default values
- All errors are logged with context

### P6: Idempotency for All Operations

Operations can be safely retried. Duplicate requests produce the same result as single requests. This enables reliable recovery from network failures.

Implications:
- Create operations check for existing records
- Update operations use version checks or timestamps
- Delete operations succeed even if already deleted
- Critical operations use idempotency keys

### P7: No Hardcoded Values

All configurable values come from configuration files or environment variables. Magic numbers, URLs, credentials, and feature flags never appear in code.

Implications:
- Environment-specific values in .env files
- Application settings in YAML configuration
- Secrets in environment variables only

### P8: Secure by Default

All external interfaces start in a denied state and require explicit configuration to open. When a security-relevant configuration value is missing, empty, or ambiguous, the system denies access — it never silently degrades to permissiveness. This is the Linux model (no permissions until granted) not the Windows model (full access until restricted).

P5 (Fail Fast) says crash when configuration is missing. P8 says that even when configuration is *present*, the default posture must be closed. An empty allowlist means deny all, not allow all. A new feature means disabled until enabled. A new endpoint means authenticated until exempted. A new channel means closed until opened.

Implications:
- Empty allowlists deny all access — never interpreted as "allow everyone"
- New features, channels, and external interfaces are disabled by default in feature flags
- Secrets have minimum length validation enforced at startup (not just non-empty)
- API endpoints require authentication unless explicitly exempted in configuration
- Webhook endpoints require secret validation — empty secret means the endpoint refuses to mount
- CORS, rate limiting, and security headers are enforced in production without opt-in
- Production environment rejects debug mode, detailed errors, and localhost CORS origins at startup

---

## Structural Principles

### S1: Layered Architecture

Backend services follow strict layering:

1. **API Layer** - HTTP handlers, request/response transformation
2. **Service Layer** - Business logic, orchestration
3. **Repository Layer** - Data access, queries
4. **Model Layer** - Data structures, entities

Each layer only calls the layer directly below it. No skipping layers. No upward calls.

### S2: Dependency Injection

Services receive their dependencies through constructors, not global imports or service locators. This enables testing and makes dependencies explicit.

### S3: Interface Segregation

Clients receive only the data they need. API responses are shaped for consumer needs, not database structure. Different clients may receive different response shapes for the same underlying data.

### S4: Separation of Concerns

Each module has one responsibility. Authentication does not handle user profile updates. Order processing does not handle inventory management. Clear boundaries enable independent development and testing.

---

## Operational Principles

### O1: Observable by Default

All services emit structured logs. Key operations include timing. Errors include stack traces. Health endpoints expose service status.

### O2: Graceful Degradation

When non-critical dependencies fail, the system continues operating with reduced functionality. A failed recommendation engine does not prevent core operations.

### O3: Bounded Resource Usage

All operations have timeouts. All queries have limits. All queues have maximum sizes. Unbounded operations do not exist.

### O4: Reversible Changes

Database migrations include rollback scripts. Feature deployments use feature flags. Configuration changes can be reverted without code deployment.

---

## Development Principles

### D1: Consistent Patterns

Similar problems receive similar solutions. If user authentication uses JWT, service authentication uses JWT. If one API returns paginated results with cursor-based navigation, all paginated APIs do.

### D2: Documentation as Code

Architecture decisions are documented. API contracts are specified. Database schemas include comments. If it is not documented, it does not exist for other developers.

### D3: Test Critical Paths

Not everything requires tests. Critical paths require tests. A critical path is any operation where failure causes data loss, financial loss, security breach, or service outage.

### D4: Version Everything

APIs are versioned. Configuration schemas are versioned. Database migrations are versioned. Breaking changes are never introduced without version increment.
