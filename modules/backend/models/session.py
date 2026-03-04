"""Session models — the platform primitive for persistent interaction context."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from modules.backend.core.utils import utc_now
from modules.backend.models.base import Base, TimestampMixin, UUIDMixin


class SessionStatus(str, enum.Enum):
    """Session lifecycle states."""
    ACTIVE = "active"
    SUSPENDED = "suspended"       # Waiting for human/AI input or approval
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"


# Valid state transitions — terminal states have empty sets
VALID_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.ACTIVE: {
        SessionStatus.SUSPENDED,
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
        SessionStatus.EXPIRED,
    },
    SessionStatus.SUSPENDED: {
        SessionStatus.ACTIVE,
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
        SessionStatus.EXPIRED,
    },
    SessionStatus.COMPLETED: set(),
    SessionStatus.EXPIRED: set(),
    SessionStatus.FAILED: set(),
}


class Session(UUIDMixin, TimestampMixin, Base):
    """Persistent interaction context. Outlives any request, connection, or restart."""

    __tablename__ = "sessions"

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SessionStatus.ACTIVE.value
    )

    # Identity
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # Primary agent assigned

    # Context
    goal: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )  # What this session is trying to achieve
    plan_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )  # Active plan (Phase 5)
    session_metadata: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=dict
    )  # Extensible key-value pairs

    # Cost tracking
    total_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost_budget_usd: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # None = unlimited

    # Activity tracking
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )  # Auto-expire after inactivity

    # Relationships
    channels: Mapped[list["SessionChannel"]] = relationship(
        "SessionChannel", back_populates="session", lazy="selectin"
    )
    messages: Mapped[list["SessionMessage"]] = relationship(
        "SessionMessage", back_populates="session", lazy="noload"
    )

    __table_args__ = (
        Index("ix_sessions_user_status", "user_id", "status"),
        Index("ix_sessions_last_activity", "last_activity_at"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<Session(id={self.id}, status={self.status})>"


class SessionChannel(UUIDMixin, Base):
    """Binds a session to a communication channel. One session, many channels."""

    __tablename__ = "session_channels"

    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=False, index=True
    )
    channel_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # telegram, tui, web, cli, mcp, a2a
    channel_id: Mapped[str] = mapped_column(
        String(200), nullable=False
    )  # chat_id, connection_id, etc.
    bound_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationship
    session: Mapped["Session"] = relationship("Session", back_populates="channels")

    __table_args__ = (
        Index("ix_session_channels_session", "session_id", "is_active"),
        Index("ix_session_channels_channel", "channel_type", "channel_id"),
    )

    def __repr__(self) -> str:
        return f"<SessionChannel(session_id={self.session_id}, type={self.channel_type})>"


class SessionMessage(UUIDMixin, Base):
    """A single message in a session's conversation history.

    Persisted for the streaming mission control (Phase 3) and memory architecture.
    Not stored on the Session row — conversation history is always in this table.
    """

    __tablename__ = "session_messages"

    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # user, assistant, system, tool_call, tool_result
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sender_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # agent name or user ID

    # LLM metadata (populated for assistant messages)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Tool correlation (populated for tool_call / tool_result messages)
    tool_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timestamp (no updated_at — messages are immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now
    )

    # Relationship
    session: Mapped["Session"] = relationship("Session", back_populates="messages")

    __table_args__ = (
        Index("ix_session_messages_session_created", "session_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<SessionMessage(session_id={self.session_id}, role={self.role})>"
