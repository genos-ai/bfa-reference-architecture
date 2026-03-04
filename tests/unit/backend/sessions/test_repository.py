"""Unit tests for session repository.

These tests run against the real database (P12) using the db_session fixture
with transaction rollback for isolation.
"""

import pytest
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.utils import utc_now
from modules.backend.models.session import Session, SessionChannel, SessionMessage, SessionStatus
from modules.backend.repositories.session import SessionRepository


@pytest.fixture
def repo(db_session: AsyncSession) -> SessionRepository:
    """Create a SessionRepository with the test DB session."""
    return SessionRepository(db_session)


async def _create_session(db_session: AsyncSession, **overrides) -> Session:
    """Helper to create a session directly in the DB."""
    defaults = {
        "status": SessionStatus.ACTIVE.value,
        "user_id": "user-1",
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "last_activity_at": utc_now(),
        "session_metadata": {},
    }
    defaults.update(overrides)
    session = Session(**defaults)
    db_session.add(session)
    await db_session.flush()
    return session


class TestGetActiveByUser:
    """Tests for get_active_by_user query."""

    @pytest.mark.asyncio
    async def test_returns_active_and_suspended(self, repo, db_session):
        """Should return only ACTIVE and SUSPENDED sessions for the user."""
        await _create_session(db_session, user_id="user-1", status=SessionStatus.ACTIVE.value)
        await _create_session(db_session, user_id="user-1", status=SessionStatus.SUSPENDED.value)
        await _create_session(db_session, user_id="user-1", status=SessionStatus.COMPLETED.value)
        await _create_session(db_session, user_id="user-2", status=SessionStatus.ACTIVE.value)

        results = await repo.get_active_by_user("user-1")
        assert len(results) == 2
        statuses = {s.status for s in results}
        assert statuses == {SessionStatus.ACTIVE.value, SessionStatus.SUSPENDED.value}


class TestGetByUser:
    """Tests for get_by_user query."""

    @pytest.mark.asyncio
    async def test_filter_by_status(self, repo, db_session):
        """Should filter sessions by status."""
        await _create_session(db_session, user_id="user-1", status=SessionStatus.ACTIVE.value)
        await _create_session(db_session, user_id="user-1", status=SessionStatus.COMPLETED.value)

        results = await repo.get_by_user(user_id="user-1", status_filter=SessionStatus.ACTIVE.value)
        assert len(results) == 1
        assert results[0].status == SessionStatus.ACTIVE.value


class TestUpdateLastActivity:
    """Tests for update_last_activity."""

    @pytest.mark.asyncio
    async def test_updates_timestamp(self, repo, db_session):
        """Should update last_activity_at."""
        session = await _create_session(db_session)
        old_activity = session.last_activity_at

        await repo.update_last_activity(session.id)
        await db_session.refresh(session)
        assert session.last_activity_at >= old_activity

    @pytest.mark.asyncio
    async def test_updates_expires_at(self, repo, db_session):
        """Should update expires_at when provided."""
        session = await _create_session(db_session)
        new_expires = utc_now() + timedelta(hours=48)

        await repo.update_last_activity(session.id, new_expires_at=new_expires)
        await db_session.refresh(session)
        assert session.expires_at is not None


class TestFindExpired:
    """Tests for find_expired query."""

    @pytest.mark.asyncio
    async def test_finds_expired_sessions(self, repo, db_session):
        """Should find sessions past their expires_at in non-terminal states."""
        past = utc_now() - timedelta(hours=1)
        future = utc_now() + timedelta(hours=1)

        await _create_session(db_session, expires_at=past, status=SessionStatus.ACTIVE.value)
        await _create_session(db_session, expires_at=future, status=SessionStatus.ACTIVE.value)
        await _create_session(db_session, expires_at=past, status=SessionStatus.COMPLETED.value)

        results = await repo.find_expired()
        assert len(results) == 1
        assert results[0].status == SessionStatus.ACTIVE.value


class TestChannelOperations:
    """Tests for channel binding queries."""

    @pytest.mark.asyncio
    async def test_bind_channel(self, repo, db_session):
        """Should bind a channel to a session."""
        session = await _create_session(db_session)
        binding = await repo.bind_channel(session.id, "telegram", "12345")
        assert binding.session_id == session.id
        assert binding.channel_type == "telegram"
        assert binding.channel_id == "12345"
        assert binding.is_active is True

    @pytest.mark.asyncio
    async def test_bind_channel_deactivates_existing(self, repo, db_session):
        """Existing binding for same channel should be deactivated."""
        session1 = await _create_session(db_session)
        session2 = await _create_session(db_session)

        binding1 = await repo.bind_channel(session1.id, "telegram", "12345")
        binding2 = await repo.bind_channel(session2.id, "telegram", "12345")

        await db_session.refresh(binding1)
        assert binding1.is_active is False
        assert binding2.is_active is True

    @pytest.mark.asyncio
    async def test_get_session_by_channel(self, repo, db_session):
        """Should find session from channel binding."""
        session = await _create_session(db_session)
        await repo.bind_channel(session.id, "telegram", "12345")

        found = await repo.get_session_by_channel("telegram", "12345")
        assert found is not None
        assert found.id == session.id

    @pytest.mark.asyncio
    async def test_get_session_by_channel_not_found(self, repo, db_session):
        """Should return None when no binding exists."""
        result = await repo.get_session_by_channel("telegram", "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_unbind_channel(self, repo, db_session):
        """Should deactivate a channel binding."""
        session = await _create_session(db_session)
        binding = await repo.bind_channel(session.id, "telegram", "12345")

        await repo.unbind_channel(session.id, "telegram", "12345")
        await db_session.refresh(binding)
        assert binding.is_active is False


class TestMessageOperations:
    """Tests for message queries."""

    @pytest.mark.asyncio
    async def test_add_message(self, repo, db_session):
        """Should create a message and flush."""
        session = await _create_session(db_session)
        msg = await repo.add_message(
            session_id=session.id,
            role="user",
            content="hello world",
        )
        assert msg.id is not None
        assert msg.role == "user"
        assert msg.content == "hello world"

    @pytest.mark.asyncio
    async def test_get_messages_ordered(self, repo, db_session):
        """Messages should be returned in creation order."""
        session = await _create_session(db_session)
        await repo.add_message(session_id=session.id, role="user", content="first")
        await repo.add_message(session_id=session.id, role="assistant", content="second")

        messages = await repo.get_messages(session.id)
        assert len(messages) == 2
        assert messages[0].content == "first"
        assert messages[1].content == "second"

    @pytest.mark.asyncio
    async def test_count_messages(self, repo, db_session):
        """Should return correct message count."""
        session = await _create_session(db_session)
        await repo.add_message(session_id=session.id, role="user", content="msg1")
        await repo.add_message(session_id=session.id, role="user", content="msg2")
        await repo.add_message(session_id=session.id, role="user", content="msg3")

        count = await repo.count_messages(session.id)
        assert count == 3
