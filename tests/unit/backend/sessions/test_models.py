"""Unit tests for session models and state machine."""

import pytest

from modules.backend.models.session import (
    Session,
    SessionChannel,
    SessionMessage,
    SessionStatus,
    VALID_TRANSITIONS,
)


class TestSessionStatus:
    """Tests for SessionStatus enum."""

    def test_enum_values(self):
        """All 5 status values should exist and be strings."""
        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.SUSPENDED.value == "suspended"
        assert SessionStatus.COMPLETED.value == "completed"
        assert SessionStatus.EXPIRED.value == "expired"
        assert SessionStatus.FAILED.value == "failed"

    def test_enum_count(self):
        """Should have exactly 5 statuses."""
        assert len(SessionStatus) == 5


class TestValidTransitions:
    """Tests for state machine transition rules."""

    def test_active_transitions(self):
        """ACTIVE can go to SUSPENDED, COMPLETED, FAILED, EXPIRED."""
        expected = {
            SessionStatus.SUSPENDED,
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.EXPIRED,
        }
        assert VALID_TRANSITIONS[SessionStatus.ACTIVE] == expected

    def test_suspended_transitions(self):
        """SUSPENDED can go to ACTIVE, COMPLETED, FAILED, EXPIRED."""
        expected = {
            SessionStatus.ACTIVE,
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.EXPIRED,
        }
        assert VALID_TRANSITIONS[SessionStatus.SUSPENDED] == expected

    def test_terminal_states_have_no_transitions(self):
        """COMPLETED, EXPIRED, FAILED are terminal — no outgoing transitions."""
        assert VALID_TRANSITIONS[SessionStatus.COMPLETED] == set()
        assert VALID_TRANSITIONS[SessionStatus.EXPIRED] == set()
        assert VALID_TRANSITIONS[SessionStatus.FAILED] == set()

    def test_all_statuses_have_transition_entries(self):
        """Every status should appear in the transition map."""
        for status in SessionStatus:
            assert status in VALID_TRANSITIONS


class TestSessionModel:
    """Tests for Session model defaults."""

    def test_session_repr(self):
        """Session repr should include id and status."""
        session = Session()
        session.id = "test-id"
        session.status = "active"
        assert "test-id" in repr(session)
        assert "active" in repr(session)


class TestSessionChannelModel:
    """Tests for SessionChannel model."""

    def test_channel_repr(self):
        """SessionChannel repr should include session_id and type."""
        channel = SessionChannel()
        channel.session_id = "sess-1"
        channel.channel_type = "telegram"
        assert "sess-1" in repr(channel)
        assert "telegram" in repr(channel)


class TestSessionMessageModel:
    """Tests for SessionMessage model."""

    def test_message_repr(self):
        """SessionMessage repr should include session_id and role."""
        msg = SessionMessage()
        msg.session_id = "sess-1"
        msg.role = "user"
        assert "sess-1" in repr(msg)
        assert "user" in repr(msg)
