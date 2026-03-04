"""Integration tests for session API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.models.session import Session, SessionStatus
from modules.backend.core.utils import utc_now


class TestCreateSession:
    """Tests for POST /api/v1/sessions."""

    @pytest.mark.asyncio
    async def test_create_session(self, client: AsyncClient, api):
        """Should create a session and return 201."""
        response = await client.post(
            "/api/v1/sessions",
            json={},
        )
        data = api.assert_success(response, expected_status=201)
        assert data["data"]["status"] == "active"
        assert "id" in data["data"]
        assert data["data"]["total_cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_create_session_with_goal(self, client: AsyncClient, api):
        """Goal should be stored and returned."""
        response = await client.post(
            "/api/v1/sessions",
            json={"goal": "Analyze Q4 data"},
        )
        data = api.assert_success(response, expected_status=201)
        assert data["data"]["goal"] == "Analyze Q4 data"

    @pytest.mark.asyncio
    async def test_create_session_with_budget(self, client: AsyncClient, api):
        """Custom budget should be set."""
        response = await client.post(
            "/api/v1/sessions",
            json={"cost_budget_usd": 25.0},
        )
        data = api.assert_success(response, expected_status=201)
        assert data["data"]["cost_budget_usd"] == 25.0
        assert data["data"]["budget_remaining_usd"] == 25.0


class TestGetSession:
    """Tests for GET /api/v1/sessions/{session_id}."""

    @pytest.mark.asyncio
    async def test_get_session(self, client: AsyncClient, db_session: AsyncSession, api):
        """Should return a session by ID."""
        session = Session(
            status=SessionStatus.ACTIVE.value,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
            last_activity_at=utc_now(),
            session_metadata={},
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.get(f"/api/v1/sessions/{session.id}")
        data = api.assert_success(response)
        assert data["data"]["id"] == session.id

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, client: AsyncClient, api):
        """Should return 404 for nonexistent session."""
        response = await client.get("/api/v1/sessions/nonexistent-id")
        api.assert_error(response, 404, "RES_NOT_FOUND")


class TestUpdateSession:
    """Tests for PATCH /api/v1/sessions/{session_id}."""

    @pytest.mark.asyncio
    async def test_update_session_goal(self, client: AsyncClient, db_session: AsyncSession, api):
        """Should update goal and metadata."""
        session = Session(
            status=SessionStatus.ACTIVE.value,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
            last_activity_at=utc_now(),
            session_metadata={},
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.patch(
            f"/api/v1/sessions/{session.id}",
            json={"goal": "Updated goal"},
        )
        data = api.assert_success(response)
        assert data["data"]["goal"] == "Updated goal"


class TestStateTransitions:
    """Tests for session state transition endpoints."""

    @pytest.mark.asyncio
    async def test_suspend_session(self, client: AsyncClient, db_session: AsyncSession, api):
        """Should suspend an active session."""
        session = Session(
            status=SessionStatus.ACTIVE.value,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
            last_activity_at=utc_now(),
            session_metadata={},
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.post(
            f"/api/v1/sessions/{session.id}/suspend?reason=waiting+for+approval",
        )
        data = api.assert_success(response)
        assert data["data"]["status"] == "suspended"

    @pytest.mark.asyncio
    async def test_resume_session(self, client: AsyncClient, db_session: AsyncSession, api):
        """Should resume a suspended session."""
        session = Session(
            status=SessionStatus.SUSPENDED.value,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
            last_activity_at=utc_now(),
            session_metadata={},
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.post(f"/api/v1/sessions/{session.id}/resume")
        data = api.assert_success(response)
        assert data["data"]["status"] == "active"

    @pytest.mark.asyncio
    async def test_complete_session(self, client: AsyncClient, db_session: AsyncSession, api):
        """Should complete an active session."""
        session = Session(
            status=SessionStatus.ACTIVE.value,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
            last_activity_at=utc_now(),
            session_metadata={},
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.post(f"/api/v1/sessions/{session.id}/complete")
        data = api.assert_success(response)
        assert data["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_invalid_transition(self, client: AsyncClient, db_session: AsyncSession, api):
        """COMPLETED -> ACTIVE should return error."""
        session = Session(
            status=SessionStatus.COMPLETED.value,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
            last_activity_at=utc_now(),
            session_metadata={},
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.post(f"/api/v1/sessions/{session.id}/resume")
        api.assert_error(response, 400, "VAL_VALIDATION_ERROR")


class TestChannelBinding:
    """Tests for channel binding endpoints."""

    @pytest.mark.asyncio
    async def test_bind_channel(self, client: AsyncClient, db_session: AsyncSession, api):
        """Should bind a channel and return 201."""
        session = Session(
            status=SessionStatus.ACTIVE.value,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
            last_activity_at=utc_now(),
            session_metadata={},
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.post(
            f"/api/v1/sessions/{session.id}/channels",
            json={"channel_type": "telegram", "channel_id": "123456789"},
        )
        data = api.assert_success(response, expected_status=201)
        assert data["data"]["channel_type"] == "telegram"
        assert data["data"]["is_active"] is True

    @pytest.mark.asyncio
    async def test_unbind_channel(self, client: AsyncClient, db_session: AsyncSession):
        """Should unbind a channel and return 204."""
        from modules.backend.models.session import SessionChannel

        session = Session(
            status=SessionStatus.ACTIVE.value,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
            last_activity_at=utc_now(),
            session_metadata={},
        )
        db_session.add(session)
        await db_session.flush()

        channel = SessionChannel(
            session_id=session.id,
            channel_type="telegram",
            channel_id="123456789",
        )
        db_session.add(channel)
        await db_session.flush()

        response = await client.delete(
            f"/api/v1/sessions/{session.id}/channels/telegram/123456789",
        )
        assert response.status_code == 204


class TestMessages:
    """Tests for message endpoints."""

    @pytest.mark.asyncio
    async def test_get_messages_empty(self, client: AsyncClient, db_session: AsyncSession, api):
        """Should return empty list for session with no messages."""
        session = Session(
            status=SessionStatus.ACTIVE.value,
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
            last_activity_at=utc_now(),
            session_metadata={},
        )
        db_session.add(session)
        await db_session.flush()

        response = await client.get(f"/api/v1/sessions/{session.id}/messages")
        data = api.assert_success(response)
        assert data["data"] == []
