"""Unit tests for session Pydantic schemas."""

import pytest
from pydantic import ValidationError

from modules.backend.schemas.session import (
    ChannelBindRequest,
    SessionCreate,
    SessionMessageCreate,
    SessionUpdate,
)


class TestSessionCreate:
    """Tests for SessionCreate schema."""

    def test_defaults(self):
        """All fields should be optional with defaults."""
        data = SessionCreate()
        assert data.goal is None
        assert data.agent_id is None
        assert data.cost_budget_usd is None
        assert data.ttl_hours is None
        assert data.session_metadata is None

    def test_goal_too_long(self):
        """Should reject goal longer than 2000 chars."""
        with pytest.raises(ValidationError):
            SessionCreate(goal="x" * 2001)

    def test_negative_budget(self):
        """Should reject negative budget."""
        with pytest.raises(ValidationError):
            SessionCreate(cost_budget_usd=-1.0)

    def test_zero_budget_allowed(self):
        """Zero budget should be allowed (ge=0)."""
        data = SessionCreate(cost_budget_usd=0.0)
        assert data.cost_budget_usd == 0.0

    def test_ttl_zero_rejected(self):
        """TTL must be >= 1."""
        with pytest.raises(ValidationError):
            SessionCreate(ttl_hours=0)


class TestSessionUpdate:
    """Tests for SessionUpdate schema."""

    def test_partial_update(self):
        """exclude_unset should work for partial updates."""
        data = SessionUpdate(goal="new goal")
        dump = data.model_dump(exclude_unset=True)
        assert dump == {"goal": "new goal"}

    def test_empty_update(self):
        """No fields set should produce empty dump."""
        data = SessionUpdate()
        dump = data.model_dump(exclude_unset=True)
        assert dump == {}


class TestSessionMessageCreate:
    """Tests for SessionMessageCreate schema."""

    @pytest.mark.parametrize("role", ["user", "assistant", "system", "tool_call", "tool_result"])
    def test_valid_roles(self, role):
        """All 5 roles should be accepted."""
        data = SessionMessageCreate(content="hello", role=role)
        assert data.role == role

    def test_invalid_role(self):
        """Should reject invalid role."""
        with pytest.raises(ValidationError):
            SessionMessageCreate(content="hello", role="admin")

    def test_empty_content(self):
        """Should reject empty content (min_length=1)."""
        with pytest.raises(ValidationError):
            SessionMessageCreate(content="", role="user")

    def test_content_required(self):
        """Content is required."""
        with pytest.raises(ValidationError):
            SessionMessageCreate(role="user")


class TestChannelBindRequest:
    """Tests for ChannelBindRequest schema."""

    def test_required_fields(self):
        """channel_type and channel_id are required."""
        with pytest.raises(ValidationError):
            ChannelBindRequest()

    def test_valid_request(self):
        """Should accept valid channel binding."""
        data = ChannelBindRequest(channel_type="telegram", channel_id="123456789")
        assert data.channel_type == "telegram"
        assert data.channel_id == "123456789"
