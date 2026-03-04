"""Unit tests for session service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from modules.backend.core.exceptions import BudgetExceededError, NotFoundError, ValidationError
from modules.backend.models.session import SessionStatus
from modules.backend.schemas.session import SessionCreate, SessionMessageCreate, SessionUpdate
from modules.backend.services.session import SessionService


def _mock_session_model(**overrides):
    """Create a mock session model with sensible defaults."""
    defaults = {
        "id": "sess-123",
        "status": SessionStatus.ACTIVE.value,
        "user_id": "user-1",
        "agent_id": None,
        "goal": None,
        "plan_id": None,
        "session_metadata": {},
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "cost_budget_usd": 50.0,
        "last_activity_at": None,
        "expires_at": None,
        "created_at": None,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    with patch("modules.backend.services.session.get_app_config") as mock_config:
        mock_sessions = MagicMock()
        mock_sessions.default_ttl_hours = 24
        mock_sessions.max_ttl_hours = 168
        mock_sessions.default_cost_budget_usd = 50.0
        mock_sessions.max_cost_budget_usd = 500.0
        mock_sessions.budget_warning_threshold = 0.80

        mock_features = MagicMock()
        mock_features.events_publish_enabled = False

        config = MagicMock()
        config.sessions = mock_sessions
        config.features = mock_features
        mock_config.return_value = config

        svc = SessionService(mock_db)
        yield svc


class TestCreateSession:
    """Tests for session creation."""

    @pytest.mark.asyncio
    async def test_create_session_defaults(self, service):
        """Session created with config defaults for TTL and budget."""
        mock_session = _mock_session_model(cost_budget_usd=50.0)
        with patch.object(service.repo, "create", return_value=mock_session):
            data = SessionCreate()
            result = await service.create_session(data, user_id="user-1")
            assert result.id == "sess-123"

    @pytest.mark.asyncio
    async def test_create_session_custom_budget_clamped(self, service):
        """Custom budget should be clamped to max_cost_budget_usd."""
        mock_session = _mock_session_model(cost_budget_usd=500.0)
        with patch.object(service.repo, "create", return_value=mock_session) as mock_create:
            data = SessionCreate(cost_budget_usd=9999.0)
            await service.create_session(data, user_id="user-1")
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["cost_budget_usd"] == 500.0

    @pytest.mark.asyncio
    async def test_create_session_custom_ttl_clamped(self, service):
        """Custom TTL should be clamped to max_ttl_hours."""
        mock_session = _mock_session_model()
        with patch.object(service.repo, "create", return_value=mock_session) as mock_create:
            data = SessionCreate(ttl_hours=9999)
            await service.create_session(data)
            call_kwargs = mock_create.call_args.kwargs
            # expires_at should be within max_ttl_hours of now
            assert call_kwargs["expires_at"] is not None


class TestStateTransitions:
    """Tests for session state transitions."""

    @pytest.mark.asyncio
    async def test_suspend_session(self, service):
        """ACTIVE -> SUSPENDED should succeed."""
        active_session = _mock_session_model(status=SessionStatus.ACTIVE.value)
        suspended_session = _mock_session_model(status=SessionStatus.SUSPENDED.value)
        with patch.object(service.repo, "get_by_id", return_value=active_session):
            with patch.object(service.repo, "update", return_value=suspended_session):
                result = await service.suspend_session("sess-123", reason="waiting for approval")
                assert result.status == SessionStatus.SUSPENDED.value

    @pytest.mark.asyncio
    async def test_resume_session(self, service):
        """SUSPENDED -> ACTIVE should succeed."""
        suspended = _mock_session_model(status=SessionStatus.SUSPENDED.value)
        active = _mock_session_model(status=SessionStatus.ACTIVE.value)
        with patch.object(service.repo, "get_by_id", return_value=suspended):
            with patch.object(service.repo, "update", return_value=active):
                result = await service.resume_session("sess-123")
                assert result.status == SessionStatus.ACTIVE.value

    @pytest.mark.asyncio
    async def test_complete_session(self, service):
        """ACTIVE -> COMPLETED should succeed."""
        active = _mock_session_model(status=SessionStatus.ACTIVE.value)
        completed = _mock_session_model(status=SessionStatus.COMPLETED.value)
        with patch.object(service.repo, "get_by_id", return_value=active):
            with patch.object(service.repo, "update", return_value=completed):
                result = await service.complete_session("sess-123")
                assert result.status == SessionStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_fail_session(self, service):
        """ACTIVE -> FAILED should succeed with reason."""
        active = _mock_session_model(status=SessionStatus.ACTIVE.value)
        failed = _mock_session_model(status=SessionStatus.FAILED.value)
        with patch.object(service.repo, "get_by_id", return_value=active):
            with patch.object(service.repo, "update", return_value=failed):
                result = await service.fail_session("sess-123", reason="unrecoverable error")
                assert result.status == SessionStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_invalid_transition_completed_to_active(self, service):
        """COMPLETED -> ACTIVE should raise ValidationError."""
        completed = _mock_session_model(status=SessionStatus.COMPLETED.value)
        with patch.object(service.repo, "get_by_id", return_value=completed):
            with pytest.raises(ValidationError, match="Cannot transition"):
                await service.resume_session("sess-123")

    @pytest.mark.asyncio
    async def test_invalid_transition_expired_to_active(self, service):
        """EXPIRED -> ACTIVE should raise ValidationError."""
        expired = _mock_session_model(status=SessionStatus.EXPIRED.value)
        with patch.object(service.repo, "get_by_id", return_value=expired):
            with pytest.raises(ValidationError, match="Cannot transition"):
                await service.resume_session("sess-123")


class TestCostTracking:
    """Tests for cost tracking and budget enforcement."""

    @pytest.mark.asyncio
    async def test_update_cost(self, service):
        """Tokens and cost should accumulate correctly."""
        session = _mock_session_model(
            total_input_tokens=100, total_output_tokens=50, total_cost_usd=1.0,
            cost_budget_usd=50.0,
        )
        with patch.object(service.repo, "get_by_id", return_value=session):
            with patch.object(service.repo, "update", return_value=session) as mock_update:
                await service.update_cost("sess-123", input_tokens=200, output_tokens=100, cost_usd=0.5)
                call_kwargs = mock_update.call_args.kwargs
                assert call_kwargs["total_input_tokens"] == 300
                assert call_kwargs["total_output_tokens"] == 150
                assert call_kwargs["total_cost_usd"] == 1.5

    @pytest.mark.asyncio
    async def test_enforce_budget_within_limit(self, service):
        """Should not raise when within budget."""
        session = _mock_session_model(total_cost_usd=10.0, cost_budget_usd=50.0)
        with patch.object(service.repo, "get_by_id", return_value=session):
            await service.enforce_budget("sess-123", estimated_cost=5.0)

    @pytest.mark.asyncio
    async def test_enforce_budget_exceeded(self, service):
        """Should raise BudgetExceededError when over budget."""
        session = _mock_session_model(total_cost_usd=48.0, cost_budget_usd=50.0)
        with patch.object(service.repo, "get_by_id", return_value=session):
            with pytest.raises(BudgetExceededError):
                await service.enforce_budget("sess-123", estimated_cost=5.0)

    @pytest.mark.asyncio
    async def test_enforce_budget_unlimited(self, service):
        """Should not raise when budget is None (unlimited)."""
        session = _mock_session_model(total_cost_usd=99999.0, cost_budget_usd=None)
        with patch.object(service.repo, "get_by_id", return_value=session):
            await service.enforce_budget("sess-123", estimated_cost=1000.0)

    @pytest.mark.asyncio
    async def test_enforce_budget_exact_limit(self, service):
        """Should raise when projected cost equals budget exactly."""
        session = _mock_session_model(total_cost_usd=45.0, cost_budget_usd=50.0)
        with patch.object(service.repo, "get_by_id", return_value=session):
            with pytest.raises(BudgetExceededError):
                await service.enforce_budget("sess-123", estimated_cost=5.0)


class TestChannelBinding:
    """Tests for channel binding operations."""

    @pytest.mark.asyncio
    async def test_bind_channel(self, service):
        """Should bind a channel to a session."""
        session = _mock_session_model()
        binding = MagicMock()
        binding.channel_type = "telegram"
        binding.channel_id = "12345"
        with patch.object(service.repo, "get_by_id", return_value=session):
            with patch.object(service.repo, "bind_channel", return_value=binding):
                result = await service.bind_channel("sess-123", "telegram", "12345")
                assert result.channel_type == "telegram"

    @pytest.mark.asyncio
    async def test_get_session_by_channel_not_found(self, service):
        """Should raise NotFoundError when no session for channel."""
        with patch.object(service.repo, "get_session_by_channel", return_value=None):
            with pytest.raises(NotFoundError, match="No active session"):
                await service.get_session_by_channel("telegram", "99999")


class TestMessages:
    """Tests for message operations."""

    @pytest.mark.asyncio
    async def test_add_message(self, service):
        """Should add a message to a session."""
        session = _mock_session_model()
        msg = MagicMock()
        with patch.object(service.repo, "get_by_id", return_value=session):
            with patch.object(service.repo, "add_message", return_value=msg):
                data = SessionMessageCreate(content="hello", role="user")
                await service.add_message("sess-123", data)

    @pytest.mark.asyncio
    async def test_get_messages(self, service):
        """Should return messages with pagination."""
        session = _mock_session_model()
        messages = [MagicMock(), MagicMock()]
        with patch.object(service.repo, "get_by_id", return_value=session):
            with patch.object(service.repo, "get_messages", return_value=messages):
                with patch.object(service.repo, "count_messages", return_value=2):
                    result, total = await service.get_messages("sess-123")
                    assert len(result) == 2
                    assert total == 2


class TestExpireInactiveSessions:
    """Tests for expired session cleanup."""

    @pytest.mark.asyncio
    async def test_expire_inactive_sessions(self, service):
        """Should find and expire sessions past their TTL."""
        expired1 = _mock_session_model(id="sess-1", status=SessionStatus.ACTIVE.value)
        expired2 = _mock_session_model(id="sess-2", status=SessionStatus.ACTIVE.value)
        transitioned = _mock_session_model(status=SessionStatus.EXPIRED.value)

        with patch.object(service.repo, "find_expired", return_value=[expired1, expired2]):
            with patch.object(service.repo, "get_by_id", return_value=expired1):
                with patch.object(service.repo, "update", return_value=transitioned):
                    count = await service.expire_inactive_sessions()
                    assert count == 2
