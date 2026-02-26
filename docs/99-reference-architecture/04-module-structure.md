# 04 - Module Structure

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

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

A module is a cohesive unit of functionality with:
- Clear domain responsibility
- Defined public interface
- Internal implementation hidden from other modules
- Own database tables (no shared tables between modules)

### Module Examples

| Module | Responsibility |
|--------|----------------|
| `users` | User accounts, authentication, profiles |
| `projects` | Project CRUD, configuration, metadata |
| `orders` | Order processing, fulfillment |
| `payments` | Payment processing, invoicing |
| `notifications` | Email, SMS, push notifications |
| `reports` | Report generation, analytics |

---

## Module Structure

### Directory Layout

Each module follows consistent internal structure:

```
modules/
└── {module_name}/
    ├── __init__.py          # Public interface exports only
    ├── api.py               # Internal API (callable by other modules)
    ├── models.py            # Database models (private to module)
    ├── schemas.py           # Pydantic schemas for API
    ├── service.py           # Business logic
    ├── repository.py        # Data access
    ├── events.py            # Events this module publishes/consumes
    └── exceptions.py        # Module-specific exceptions
```

### Public Interface

The module's `__init__.py` exports only the public interface:
- API functions/classes
- Schemas needed by callers
- Events published by module
- Exceptions callers might handle

Internal implementation details are not exported.

### Module Independence

Each module:
- Owns its database tables exclusively
- Does not import from other modules' internals
- Communicates only via public APIs or events
- Can be tested in isolation

---

## Inter-Module Communication

### The Rule

**Modules never import each other's internals.**

Wrong:
```python
# In orders module
from modules.users.repository import UserRepository  # FORBIDDEN
from modules.users.models import User  # FORBIDDEN
```

Right:
```python
# In orders module
from modules.users import user_api  # Public interface only
user = await user_api.get_user(user_id)
```

### Communication Methods

Modules communicate via three mechanisms:

**1. Synchronous API Calls**
- Module exposes functions in `api.py`
- Other modules call these functions
- Returns data via Pydantic schemas
- Used for: Queries, commands requiring immediate response

**2. Events**
- Module publishes events when state changes
- Other modules subscribe to relevant events
- Async, decoupled
- Used for: Notifications, eventual consistency, side effects

**3. Shared Identifiers**
- Modules reference each other via IDs (UUIDs)
- Never via object references or foreign key joins across modules
- Each module resolves IDs through the owning module's API

### API Design

Module API functions:
- Accept primitive types and Pydantic schemas
- Return Pydantic schemas (never ORM models)
- Raise module-specific exceptions
- Are async when involving I/O
- Include docstrings documenting contract

### Example Module API

```python
# modules/users/api.py

async def get_user(user_id: UUID) -> UserSchema:
    """Get user by ID. Raises UserNotFoundError if not found."""

async def get_users_by_ids(user_ids: list[UUID]) -> list[UserSchema]:
    """Get multiple users. Returns only found users, no error for missing."""

async def validate_user_permission(user_id: UUID, permission: str) -> bool:
    """Check if user has permission. Returns False if user not found."""

async def create_user(data: CreateUserSchema) -> UserSchema:
    """Create new user. Raises UserExistsError if email taken."""
```

---

## Data Ownership

### Tables Belong To Modules

Each database table is owned by exactly one module:
- Only that module reads/writes the table
- Other modules access data via module API
- No cross-module joins in queries

### Foreign Keys Across Modules

Foreign keys referencing other modules' tables:
- Allowed at database level for referential integrity
- But queries don't join across module boundaries
- Resolve references via API calls

### Data Denormalization

When performance requires avoiding API calls:
- Module may cache relevant data from other modules
- Cache updated via events from source module
- Source module remains authoritative

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

Format: `{module}.{entity}.{action}`

Examples:
- `users.user.created`
- `orders.order.completed`
- `payments.payment.processed`

### Event Payload

Include enough data for consumers to act without API calls:
- Entity ID (always)
- Key attributes that changed
- Timestamp

Do not include:
- Entire entity (too large, may be stale)
- Sensitive data (passwords, tokens)

---

## Cross-Module Queries

### The Problem

Sometimes you need data from multiple modules in one response.

### Solution: Aggregation Layer

Create aggregation at the API layer (not in modules):

```python
# api/v1/endpoints/dashboard.py

async def get_dashboard(user_id: UUID):
    # Call multiple module APIs
    user = await user_api.get_user(user_id)
    projects = await project_api.get_user_projects(user_id)
    recent_orders = await order_api.get_recent_orders(user_id)
    
    # Aggregate into response
    return DashboardResponse(
        user=user,
        projects=projects,
        recent_orders=recent_orders
    )
```

### Performance Optimization

For high-frequency aggregations:
- Parallel API calls when independent
- Caching at aggregation layer
- Consider read model (CQRS) for complex dashboards

---

## Module Dependencies

### Dependency Direction

Establish clear dependency hierarchy:
- Core modules (users, auth) have no dependencies
- Domain modules depend on core modules
- Feature modules depend on domain modules
- No circular dependencies

### Dependency Diagram

```
                    ┌─────────────┐
                    │   billing   │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│    orders     │  │   reports     │  │   analytics   │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │    projects     │
                  └────────┬────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│     users     │  │     auth      │  │  notifications│
└───────────────┘  └───────────────┘  └───────────────┘
```

### Enforcing Boundaries

Prevent accidental coupling:
- Code review checks for cross-module imports
- Linting rules to flag violations
- Module API is the only allowed entry point

---

## Service Extraction

### When To Extract

Extract module to separate service when:
- Different scaling requirements
- Different deployment frequency
- Team ownership boundaries
- Technology mismatch (e.g., need different language)

### How Modular Design Helps

If modules communicate via APIs:
- API becomes HTTP API with minimal changes
- Schemas already define contracts
- Events already decouple consumers
- No code rewriting, only infrastructure changes

### Extraction Steps

1. Deploy module as separate service
2. Replace internal API calls with HTTP calls
3. Replace internal events with message broker
4. Update configuration for service discovery
5. Remove module from monolith

---

## Testing Modules

### Unit Testing

Test module internals in isolation:
- Mock database for repository tests
- Mock repository for service tests
- Test business logic thoroughly

### Integration Testing

Test module API:
- Real database
- Test via public API functions
- Verify expected behavior

### Cross-Module Testing

Test module interactions:
- Mock other modules' APIs
- Verify correct API calls made
- Verify event publishing

---

## Module Checklist

When creating a new module:

- [ ] Clear domain responsibility defined
- [ ] Directory structure follows standard
- [ ] Public API in `api.py`
- [ ] Schemas for all API inputs/outputs
- [ ] No imports from other modules' internals
- [ ] Database tables owned exclusively
- [ ] Events defined for state changes
- [ ] Exceptions defined for error cases
- [ ] Unit tests for service layer
- [ ] Integration tests for API
- [ ] Added to dependency diagram
