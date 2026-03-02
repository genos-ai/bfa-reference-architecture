# 11 - Testing Standards

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-29*

## Changelog

- 1.1.0 (2026-03-02): Replaced mocking-first philosophy with live infrastructure testing per P12; removed mock fixtures; rewrote mocking strategy; updated anti-patterns
- 1.0.0 (2025-01-29): Initial testing standards document

---

## Purpose

This document defines testing standards for all projects. It covers test organization, fixture patterns, mocking strategies, and test execution.

---

## Context

Tests are the safety net that enables confident refactoring, deployment, and onboarding. Without shared testing standards, projects end up with inconsistent test organization, fragile fixtures that break across test files, and coverage gaps in the most critical code paths.

### Core Testing Principle: Test Against Real Infrastructure (P12)

**Tests run against the live platform. Mock only what you don't operate.**

A test that mocks the database proves your mock works, not your code. An AI writing tests can trivially game mocks to achieve 100% coverage while verifying nothing. Every test should exercise real PostgreSQL, real Redis, real FastStream, and real Temporal — the same systems the code runs against in production.

- **Service tests** call real repositories against real PostgreSQL. No mocked sessions.
- **Event bus tests** publish and subscribe on real Redis. No `AsyncMock(return_value=1)`.
- **Temporal tests** use the real Temporal test server.
- **Write operations** use transaction rollback so tests don't pollute data.
- **The only mocks** are for external services you don't operate: LLM providers (PydanticAI `TestModel` per P11), Telegram API, third-party webhooks.

This means the traditional "unit test = mock everything" pattern does not apply here. A "unit" test focuses on a single component but still connects to real infrastructure.

### Test Structure

The hybrid test structure — organized by test type at the top level (`unit/`, `integration/`, `e2e/`) with source structure mirrored within each type — answers the two most common questions simultaneously: "what scope is this test?" (top level) and "what code does it test?" (directory structure within). Fixtures follow a hierarchy with shared fixtures in root `conftest.py` and type-specific fixtures in each test type's `conftest.py`.

Coverage targets are intentionally asymmetric: 100% for critical paths (authentication, payments, data integrity) and 80% for general business logic. This reflects the reality that not all code carries equal risk, and chasing 100% everywhere produces low-value tests that slow down development without improving safety. The testing standards integrate with CI/CD (12) to gate all merges on passing tests and with the project template (13) for directory layout.

---

## Test Directory Structure

### Hybrid Approach

Tests are organized by test type at the top level, then mirror the source structure within each type:

```
tests/
├── __init__.py
├── conftest.py                      # Root fixtures (shared across all tests)
├── unit/
│   ├── __init__.py
│   ├── conftest.py                  # Unit test fixtures (real DB, Redis)
│   └── backend/
│       ├── __init__.py
│       ├── core/
│       │   └── test_config.py
│       ├── services/
│       │   └── test_user_service.py
│       └── repositories/
│           └── test_user_repository.py
├── integration/
│   ├── __init__.py
│   ├── conftest.py                  # Integration fixtures (real DB)
│   └── backend/
│       ├── __init__.py
│       ├── api/
│       │   └── test_user_endpoints.py
│       └── workflows/
│           └── test_user_registration.py
└── e2e/
    ├── __init__.py
    ├── conftest.py                  # E2E fixtures (browser, full stack)
    └── test_user_journey.py
```

### Why Hybrid

| Concern | How Hybrid Addresses It |
|---------|------------------------|
| Find tests for a module | `modules/backend/services/user.py` → `tests/unit/backend/services/test_user_service.py` |
| Run by test type | `pytest tests/unit` vs `pytest tests/integration` |
| CI pipeline stages | Unit tests first (fast), integration later (slow) |
| Fixture scoping | Different `conftest.py` per test type |
| Scalability | Clear structure as codebase grows |

### Mapping Convention

| Source File | Unit Test | Integration Test |
|-------------|-----------|------------------|
| `modules/backend/services/user.py` | `tests/unit/backend/services/test_user_service.py` | - |
| `modules/backend/repositories/user.py` | `tests/unit/backend/repositories/test_user_repository.py` | - |
| `modules/backend/api/v1/endpoints/users.py` | - | `tests/integration/backend/api/test_user_endpoints.py` |

---

## Test Types

### Unit Tests

**Purpose:** Test individual functions/classes with focused scope against real infrastructure.

**Characteristics:**
- Focused on a single component (one service, one repository, one handler)
- Connects to real PostgreSQL and Redis — the same systems used in production
- Write operations use transaction rollback — tests don't pollute data
- No mocks for infrastructure you operate (database, Redis, event bus)
- Mocks only for external services you don't control (LLM providers, Telegram API)

**Location:** `tests/unit/`

**When to use:**
- Testing business logic in services (through real repositories, real DB)
- Testing repository queries (against real PostgreSQL constraints and indexes)
- Testing data transformations and validation logic
- Testing utility functions (no infrastructure needed — pure functions)

**Example:**

```python
# tests/unit/backend/services/test_user_service.py

import pytest

from modules.backend.services.user import UserService
from modules.backend.schemas.user import UserCreate
from modules.backend.core.exceptions import NotFoundError


class TestUserService:
    """Tests for UserService against real database."""

    async def test_create_user_persists_to_database(self, db_session):
        """Should create user in real database and return it."""
        service = UserService(db_session)
        result = await service.create_user(
            UserCreate(email="test@example.com", name="Test User")
        )

        assert result.id is not None          # DB generated this
        assert result.email == "test@example.com"

    async def test_get_user_returns_user_when_found(self, db_session):
        """Should return user when user exists in database."""
        service = UserService(db_session)
        created = await service.create_user(
            UserCreate(email="test@example.com", name="Test User")
        )

        result = await service.get_user(created.id)

        assert result.id == created.id
        assert result.email == "test@example.com"

    async def test_get_user_raises_not_found_when_missing(self, db_session):
        """Should raise NotFoundError when user does not exist."""
        service = UserService(db_session)

        with pytest.raises(NotFoundError):
            await service.get_user("00000000-0000-0000-0000-000000000000")
```

### Integration Tests

**Purpose:** Test component interactions with real dependencies.

**Characteristics:**
- Slower (seconds per test)
- Uses real database (test database)
- Tests API endpoints end-to-end within backend
- Tests repository queries against real database

**Location:** `tests/integration/`

**When to use:**
- Testing API endpoints
- Testing database queries
- Testing multi-component workflows
- Testing external service integrations (with sandbox)

**Example:**

```python
# tests/integration/backend/api/test_user_endpoints.py

import pytest
from httpx import AsyncClient


class TestUserEndpoints:
    """Integration tests for user API endpoints."""

    async def test_create_user_returns_201(self, client: AsyncClient, db_session):
        """Should create user and return 201."""
        # Arrange
        payload = {"email": "new@example.com", "password": "securepassword123"}

        # Act
        response = await client.post("/api/v1/users", json=payload)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["email"] == "new@example.com"

    async def test_get_user_returns_404_when_not_found(self, client: AsyncClient):
        """Should return 404 for nonexistent user."""
        # Act
        response = await client.get("/api/v1/users/nonexistent-id")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "RES_NOT_FOUND"
```

### End-to-End Tests

**Purpose:** Test complete user journeys through the full stack.

**Characteristics:**
- Slowest (seconds to minutes per test)
- Tests frontend + backend together
- May use browser automation (Playwright)
- Tests critical user flows

**Location:** `tests/e2e/`

**When to use:**
- Testing critical user journeys (signup, checkout)
- Testing frontend-backend integration
- Smoke tests before deployment
- Testing real-world scenarios

**Example:**

```python
# tests/e2e/test_user_journey.py

import pytest


class TestUserRegistrationJourney:
    """E2E tests for user registration flow."""

    async def test_user_can_register_and_login(self, e2e_client):
        """User should be able to register and then login."""
        # Register
        register_response = await e2e_client.post(
            "/api/v1/auth/register",
            json={"email": "e2e@example.com", "password": "testpassword123"}
        )
        assert register_response.status_code == 201

        # Login
        login_response = await e2e_client.post(
            "/api/v1/auth/login",
            json={"email": "e2e@example.com", "password": "testpassword123"}
        )
        assert login_response.status_code == 200
        assert "access_token" in login_response.json()["data"]
```

---

## Fixture Patterns

### Fixture Hierarchy

Fixtures are organized in `conftest.py` files at each level:

```
tests/
├── conftest.py           # Level 0: Shared across ALL tests
├── unit/
│   └── conftest.py       # Level 1: Shared across unit tests
├── integration/
│   └── conftest.py       # Level 1: Shared across integration tests
└── e2e/
    └── conftest.py       # Level 1: Shared across e2e tests
```

### Root conftest.py (Level 0)

Contains infrastructure fixtures shared across all test types. These connect to the real platform:

```python
# tests/conftest.py

import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from modules.backend.core.config import get_settings
from modules.backend.models.base import Base

# Block real LLM calls globally (P11)
from pydantic_ai import models as pydantic_ai_models
pydantic_ai_models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Real PostgreSQL engine. Tables created once per test run."""
    settings = get_settings()
    engine = create_async_engine(settings.test_database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="session")
async def redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Real Redis connection for tests."""
    settings = get_settings()
    client = aioredis.from_url(settings.redis_url)
    yield client
    await client.aclose()
```

### Unit Test conftest.py

Provides real infrastructure fixtures. Unit tests connect to the same PostgreSQL and Redis used in production — write operations roll back after each test.

```python
# tests/unit/conftest.py

import pytest
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.backend.models.base import Base


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Real database session, rolls back after each test."""
    async_session = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def redis(redis_client):
    """Real Redis connection. Keys created during the test are cleaned up."""
    yield redis_client
```

No `mock_db_session`. No `mock_repository`. No `mock_redis`. Tests use real connections.

### Integration Test conftest.py

Integration tests use the same real infrastructure as unit tests (db_engine and redis_client from root conftest). They add the FastAPI test client for HTTP endpoint testing:

```python
# tests/integration/conftest.py

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.backend.main import app
from modules.backend.core.dependencies import get_db_session


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Real database session, rolls back after each test."""
    async_session = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Test HTTP client wired to real database session."""
    app.dependency_overrides[get_db_session] = lambda: db_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
    app.dependency_overrides.clear()
```

### Fixture Scopes

| Scope | Lifecycle | Use For |
|-------|-----------|---------|
| `function` | Created/destroyed per test | Most fixtures (default) |
| `class` | Created/destroyed per test class | Shared setup within class |
| `module` | Created/destroyed per test file | Expensive setup shared across file |
| `session` | Created/destroyed once per test run | Database engine, event loop |

**Rule:** Use the narrowest scope that meets your needs. Broader scopes risk test pollution.

---

## Mocking Strategy

### The Rule: Mock Only What You Don't Operate

Per P12, tests connect to real infrastructure. Mocks are reserved for external services outside your control.

### What to Mock

| Mock | Why |
|------|-----|
| LLM providers (Anthropic, OpenAI) | Expensive, non-deterministic, rate-limited. Use PydanticAI `TestModel` (P11). |
| Telegram API | Requires real bot tokens, sends real messages. |
| Third-party webhooks | External services you don't control. |
| Time/dates | Use `freezegun` for deterministic time-dependent tests. |
| Random values | Seed or patch for reproducibility when randomness affects assertions. |

### What NOT to Mock

| Don't Mock | Why |
|------------|-----|
| PostgreSQL | Your queries, constraints, and transactions are what you're testing. |
| Redis | Pub/sub timing, stream behavior, and serialization are where bugs live. |
| FastStream broker | Event publishing and consuming semantics matter. |
| Temporal | Workflow replay, signals, and activities are the whole point. |
| Repositories (in service tests) | A service test that mocks the repository tests nothing real. |
| The database session | `AsyncMock(commit=AsyncMock())` catches zero bugs. |

### When You Need a Mock

For the few cases where mocking is appropriate:

```python
from unittest.mock import AsyncMock, patch

# Mock an external API you don't operate
async def test_sends_telegram_notification(db_session):
    service = NotificationService(db_session)
    with patch.object(service, "telegram_client", new=AsyncMock()) as mock_tg:
        await service.notify_user(user_id, "Hello")
        mock_tg.send_message.assert_awaited_once()
```

The mock is for Telegram (external). The database session, service, and notification logic are all real.

---

## Test Naming

### File Naming

```
test_{module_name}.py
```

Examples:
- `test_user_service.py`
- `test_user_repository.py`
- `test_user_endpoints.py`

### Function Naming

```
test_{action}_{expected_result}_{condition}
```

Examples:
- `test_create_user_returns_user_on_success`
- `test_create_user_raises_error_when_email_exists`
- `test_get_user_returns_none_when_not_found`

### Class Naming

```
Test{ClassUnderTest}
```

Examples:
- `TestUserService`
- `TestUserRepository`
- `TestUserEndpoints`

---

## Coverage Requirements

### Critical Paths (100% Required)

These paths must have 100% test coverage:

- Authentication and authorization
- Data integrity operations (create, update, delete)
- Payment/financial operations
- Security-sensitive operations
- Input validation

### Business Logic (80% Target)

Service layer code should target 80% coverage.

### Overall

No strict requirement. Focus on critical paths over coverage percentage.

### Running Coverage

```bash
# Coverage for unit tests
pytest tests/unit --cov=modules/backend --cov-report=html

# Coverage for specific module
pytest tests/unit/backend/services --cov=modules/backend/services

# Fail if coverage below threshold
pytest tests/unit --cov=modules/backend --cov-fail-under=80
```

---

## Test Data Guidelines

### Do

- Use realistic data that reflects actual system behavior
- Use factories or fixtures for common test data
- Clean up test data after tests (or use transaction rollback)
- Use unique identifiers to avoid test pollution

### Do Not

- Fabricate arbitrary data just to make tests pass
- Share mutable test data between tests
- Depend on test execution order
- Use production data in tests

### Test Data Factories

```python
# tests/factories.py

from uuid import uuid4


def create_user_data(**overrides) -> dict:
    """Factory for user test data."""
    defaults = {
        "id": str(uuid4()),
        "email": f"test-{uuid4().hex[:8]}@example.com",
        "name": "Test User",
    }
    return {**defaults, **overrides}


def create_project_data(user_id: str, **overrides) -> dict:
    """Factory for project test data."""
    defaults = {
        "id": str(uuid4()),
        "user_id": user_id,
        "name": "Test Project",
    }
    return {**defaults, **overrides}
```

---

## Running Tests

### Commands

```bash
# Run all tests
pytest

# Run by test type
pytest tests/unit                    # Fast, isolated
pytest tests/integration             # With real DB
pytest tests/e2e                     # Full stack

# Run specific directory
pytest tests/unit/backend/services

# Run specific file
pytest tests/unit/backend/services/test_user_service.py

# Run specific test
pytest tests/unit/backend/services/test_user_service.py::TestUserService::test_get_user_returns_user

# Run with markers
pytest -m unit
pytest -m integration
pytest -m "not slow"

# Run with verbosity
pytest -v                            # Verbose
pytest -vv                           # More verbose

# Run with output capture disabled (see print statements)
pytest -s

# Run failed tests only
pytest --lf                          # Last failed
pytest --ff                          # Failed first
```

### Markers

Define markers in `pytest.ini`:

```ini
[pytest]
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (require database)
    e2e: End-to-end tests (full stack)
    slow: Slow running tests
```

Apply markers to tests:

```python
import pytest

@pytest.mark.unit
class TestUserService:
    ...

@pytest.mark.integration
@pytest.mark.slow
async def test_complex_workflow():
    ...
```

---

## CI/CD Integration

### Test Stages

All test stages connect to real PostgreSQL and Redis. CI provisions these as services:

```yaml
# .github/workflows/ci.yml

jobs:
  tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
      redis:
        image: redis:7
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v4
      - name: Run unit tests
        run: pytest tests/unit --cov=modules/backend --cov-fail-under=80
      - name: Run integration tests
        run: pytest tests/integration
      - name: Run E2E tests
        run: pytest tests/e2e
```

### Test Order in CI

1. **Unit tests first** — focused scope, real infrastructure, catch most bugs
2. **Integration tests second** — multi-component workflows, HTTP endpoints
3. **E2E tests last** — full user journeys

---

## Frontend Testing

Frontend tests (React/TypeScript) are co-located with components:

```
modules/frontend/src/
└── components/
    └── features/
        └── UserProfile/
            ├── UserProfile.tsx
            └── UserProfile.test.tsx
```

For frontend testing standards, see `23-typescript-coding-standards.md` (adopted with the web frontend module).

---

## Anti-Patterns

### Avoid

- **Mocking infrastructure you operate.** A test with `mock_db_session` and `mock_redis` proves nothing. Connect to the real thing.
- **Tests that verify mock calls instead of outcomes.** `repo.create.assert_called_once_with(...)` tests wiring, not behavior. Assert on the actual result from the real database.
- **Tests an AI can game.** If an AI can write a mock that returns the expected answer and the test passes — the test is worthless. Real infrastructure can't be gamed.
- Tests that depend on execution order
- Tests that share mutable state
- Tests without assertions
- Testing implementation details instead of behavior
- Flaky tests (pass/fail randomly)
- Commented-out tests

### Signs of Bad Tests

- Test mocks the system it's supposed to be testing
- Test passes with mocks but fails against real infrastructure
- Test name doesn't describe what's being tested
- Test has multiple unrelated assertions
- Test breaks when refactoring without behavior change
