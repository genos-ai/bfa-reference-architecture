# 11 - Testing Standards

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-29*

## Changelog

- 1.0.0 (2025-01-29): Initial testing standards document

---

## Purpose

This document defines testing standards for all projects. It covers test organization, fixture patterns, mocking strategies, and test execution.

---

## Context

Tests are the safety net that enables confident refactoring, deployment, and onboarding. Without shared testing standards, projects end up with inconsistent test organization, fragile fixtures that break across test files, and coverage gaps in the most critical code paths.

The hybrid test structure — organized by test type at the top level (`unit/`, `integration/`, `e2e/`) with source structure mirrored within each type — was chosen because it answers the two most common questions simultaneously: "what kind of test is this?" (top level) and "what code does it test?" (directory structure within). Fixtures follow a hierarchy with shared fixtures in root `conftest.py` and type-specific fixtures in each test type's `conftest.py`, preventing the fixture duplication that makes test suites brittle.

Coverage targets are intentionally asymmetric: 100% for critical paths (authentication, payments, data integrity) and 80% for general business logic. This reflects the reality that not all code carries equal risk, and chasing 100% everywhere produces low-value tests that slow down development without improving safety. The testing standards integrate with CI/CD (13) to gate all merges on passing tests and with the project template (15) for directory layout.

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
│   ├── conftest.py                  # Unit test fixtures (mocks)
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

**Purpose:** Test individual functions/classes in isolation.

**Characteristics:**
- Fast (milliseconds per test)
- No external dependencies (database, Redis, APIs)
- All dependencies mocked
- Test a single unit of behavior

**Location:** `tests/unit/`

**When to use:**
- Testing business logic in services
- Testing data transformations
- Testing utility functions
- Testing validation logic

**Example:**

```python
# tests/unit/backend/services/test_user_service.py

import pytest
from unittest.mock import AsyncMock

from modules.backend.services.user import UserService
from modules.backend.core.exceptions import NotFoundError


class TestUserService:
    """Tests for UserService."""

    async def test_get_user_returns_user_when_found(self, mock_db_session):
        """Should return user when user exists."""
        # Arrange
        repository = AsyncMock()
        repository.get_by_id.return_value = {"id": "123", "email": "test@example.com"}
        service = UserService(repository=repository)

        # Act
        result = await service.get_user("123")

        # Assert
        assert result["id"] == "123"
        repository.get_by_id.assert_called_once_with("123")

    async def test_get_user_raises_not_found_when_missing(self, mock_db_session):
        """Should raise NotFoundError when user does not exist."""
        # Arrange
        repository = AsyncMock()
        repository.get_by_id.side_effect = NotFoundError()
        service = UserService(repository=repository)

        # Act & Assert
        with pytest.raises(NotFoundError):
            await service.get_user("nonexistent")
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

Contains fixtures needed by all test types:

```python
# tests/conftest.py

import asyncio
from collections.abc import Generator

import pytest


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

### Unit Test conftest.py

Contains mock fixtures for isolated testing:

```python
# tests/unit/conftest.py

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mock database session for unit tests."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_repository(mock_db_session) -> AsyncMock:
    """Mock repository for service tests."""
    return AsyncMock()


@pytest.fixture
def mock_redis() -> MagicMock:
    """Mock Redis client for unit tests."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis
```

### Integration Test conftest.py

Contains real service fixtures:

```python
# tests/integration/conftest.py

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.backend.main import app
from modules.backend.models.base import Base


@pytest.fixture(scope="session")
async def db_engine():
    """Create test database engine (session-scoped for performance)."""
    engine = create_async_engine(
        "postgresql+asyncpg://test:test@localhost/test_db",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session (function-scoped, rolls back after each test)."""
    async_session = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
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

## Mocking Strategies

### Mocking Async Functions

```python
from unittest.mock import AsyncMock

# Mock async function
mock_service = AsyncMock()
mock_service.get_user.return_value = {"id": "123"}

# Mock async function that raises
mock_service.get_user.side_effect = NotFoundError()

# Verify calls
mock_service.get_user.assert_called_once_with("123")
mock_service.get_user.assert_awaited_once()
```

### Mocking Context Managers

```python
from unittest.mock import AsyncMock, MagicMock
from contextlib import asynccontextmanager

# Mock async context manager
mock_session = MagicMock()
mock_session.__aenter__ = AsyncMock(return_value=mock_session)
mock_session.__aexit__ = AsyncMock(return_value=None)
```

### Patching Dependencies

```python
from unittest.mock import patch, AsyncMock

async def test_with_patched_dependency():
    with patch(
        "modules.backend.services.user.UserRepository",
        return_value=AsyncMock()
    ) as mock_repo:
        mock_repo.return_value.get_by_id.return_value = {"id": "123"}
        
        # Test code here
```

### When to Mock

| Mock | Don't Mock |
|------|------------|
| External APIs | Pure functions |
| Database (in unit tests) | The code under test |
| Redis/cache | Simple data structures |
| Time/dates | Internal private methods |
| Random values | |

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

```yaml
# .github/workflows/ci.yml

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run unit tests
        run: pytest tests/unit --cov=modules/backend --cov-fail-under=80

  integration-tests:
    needs: unit-tests
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - name: Run integration tests
        run: pytest tests/integration

  e2e-tests:
    needs: integration-tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run E2E tests
        run: pytest tests/e2e
```

### Test Order in CI

1. **Unit tests first** - Fast feedback, catch most bugs
2. **Integration tests second** - Verify component interactions
3. **E2E tests last** - Validate critical user journeys

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

See **23-typescript-coding-standards.md** for frontend testing standards.

---

## Anti-Patterns

### Avoid

- Tests that depend on execution order
- Tests that share mutable state
- Tests without assertions
- Testing implementation details instead of behavior
- Excessive mocking (testing mocks, not code)
- Flaky tests (pass/fail randomly)
- Tests that hit production services
- Commented-out tests

### Signs of Bad Tests

- Test name doesn't describe what's being tested
- Test has multiple unrelated assertions
- Test requires external state to pass
- Test takes more than a few seconds (unit test)
- Test breaks when refactoring without behavior change
