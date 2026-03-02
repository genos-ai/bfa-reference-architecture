"""
Root Pytest Fixtures.

Shared fixtures available to all test types.

Test Database Configuration:
    Test DB params come from config/settings/test.yaml. To use PostgreSQL
    instead of the default in-memory SQLite, set the TEST_DATABASE_URL
    environment variable (see config/.env.example).
"""

from pydantic_ai import models as pydantic_ai_models

pydantic_ai_models.ALLOW_MODEL_REQUESTS = False

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from redis.asyncio import Redis as AsyncRedis

from modules.backend.models.base import Base
from tests.test_config import get_test_database_url as _get_test_database_url
from tests.test_config import get_test_redis_url as _get_test_redis_url


# =============================================================================
# Event Loop Fixture
# =============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Database Configuration (from config/settings/test.yaml or TEST_DATABASE_URL)
# =============================================================================


def get_test_database_url() -> str:
    """Get test database URL from env or config/settings/test.yaml."""
    return _get_test_database_url()


def is_sqlite() -> bool:
    """Check if using SQLite database."""
    return "sqlite" in get_test_database_url()


# =============================================================================
# Database Engine Fixtures
# =============================================================================


@pytest.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    Create the test database engine.

    For SQLite: Uses in-memory database with shared cache for connection reuse.
    For PostgreSQL: Creates tables at start, drops them at end.

    Scope is session to avoid recreating the engine for each test.
    """
    url = get_test_database_url()

    if is_sqlite():
        # SQLite in-memory requires special handling for async
        engine = create_async_engine(
            url,
            echo=False,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    else:
        # PostgreSQL or other databases
        engine = create_async_engine(
            url,
            echo=False,
            pool_size=5,
            max_overflow=10,
        )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="session")
def db_session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    Create a session factory bound to the test engine.

    Scope is session to reuse the factory across tests.
    """
    return async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


# =============================================================================
# Database Session Fixtures
# =============================================================================


@pytest.fixture
async def db_session(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a database session for a single test.

    Each test gets its own session. Changes are rolled back after the test
    to ensure test isolation - no test can affect another.

    Usage:
        async def test_create_user(db_session: AsyncSession):
            user = User(email="test@example.com")
            db_session.add(user)
            await db_session.flush()
            assert user.id is not None
    """
    async with db_session_factory() as session:
        yield session
        # Rollback any changes made during the test
        await session.rollback()


@pytest.fixture
async def db_session_committed(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a database session that commits changes.

    Use this fixture when you need to test behavior that requires
    committed data (e.g., testing unique constraints, triggers).

    WARNING: Data persists until the end of the test session.
    Use sparingly and clean up after yourself.

    Usage:
        async def test_unique_constraint(db_session_committed: AsyncSession):
            user1 = User(email="test@example.com")
            db_session_committed.add(user1)
            await db_session_committed.commit()

            user2 = User(email="test@example.com")
            db_session_committed.add(user2)
            with pytest.raises(IntegrityError):
                await db_session_committed.commit()
    """
    async with db_session_factory() as session:
        yield session
        await session.commit()


# =============================================================================
# Redis Fixtures
# =============================================================================


def get_test_redis_url() -> str:
    """Get test Redis URL from env or config/settings/test.yaml."""
    return _get_test_redis_url()


@pytest.fixture
async def redis() -> AsyncGenerator[AsyncRedis, None]:
    """
    Real Redis connection for a single test.

    Creates a fresh connection per test (function-scoped) to avoid
    event loop conflicts with session-scoped fixtures. Uses db 1
    (from test.yaml) to isolate test data from development.

    Flushes the test database after each test for isolation.
    """
    url = get_test_redis_url()
    client = AsyncRedis.from_url(url, decode_responses=False)
    try:
        await client.ping()
    except Exception as exc:
        pytest.skip(f"Redis not available: {exc}")
    yield client
    await client.flushdb()
    await client.close()


# =============================================================================
# Test Settings Fixtures
# =============================================================================


@pytest.fixture
def test_settings() -> dict[str, Any]:
    """
    Provide test-specific settings.

    These can be used to override application settings during tests.
    """
    return {
        "app_name": "Test Application",
        "app_env": "test",
        "app_debug": True,
        "app_log_level": "DEBUG",
        "jwt_secret": "test-secret-key-for-testing-only",
        "jwt_algorithm": "HS256",
        "jwt_access_token_expire_minutes": 5,
        "api_key_salt": "test-salt",
    }


# =============================================================================
# Utility Fixtures
# =============================================================================


@pytest.fixture
def anyio_backend() -> str:
    """Specify the async backend for anyio."""
    return "asyncio"
