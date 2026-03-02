# Implementation Plan: Session Model

*Created: 2026-03-02*
*Status: Not Started*
*Phase: 2 of 6 (AI-First Platform Build)*
*Depends on: Phase 1 (Event Bus)*
*Blocked by: Phase 1*

---

## Summary

Build the session as the platform primitive. A session is a persistent bidirectional context stored in PostgreSQL that carries conversation history, active agents, cost tracking, plan progress, and channel bindings across arbitrarily long interactions. Sessions outlive any individual request, channel connection, or server restart.

The session model must support Tier 4 from day one: `SUSPENDED` state for approval waits lasting hours/days, long TTLs (up to 168 hours), cost budgets that accumulate over weeks, and multi-channel bindings (a session started in TUI can be checked via Telegram).

**Critical rule: The session is the interaction context — NOT a domain entity.** Sessions track how a human/agent interacts with the system. Domain data (notes, projects, users) lives in domain tables. Conversation history lives in `session_messages`. The session row is metadata, cost, and status.

## Context

- Reference architecture: BFF doc 35 (Section 1: Session Model)
- Local doc: `docs/99-reference-architecture/46-event-session-architecture.md` (Section 1)
- Axiom A1: The session outlives any individual request, connection, or server restart
- Anti-pattern: Do NOT store conversation history in the session row — that goes in `session_messages`. The session tracks metadata, cost, and status.

## What to Build

- `modules/backend/models/session.py` — `SessionStatus` enum, `Session`, `SessionChannel`, `SessionMessage` SQLAlchemy models
- `modules/backend/schemas/session.py` — `SessionCreate`, `SessionUpdate`, `SessionResponse`, `SessionListResponse`, `SessionMessageCreate`, `SessionMessageResponse` Pydantic schemas
- `modules/backend/repositories/session.py` — `SessionRepository` with custom queries
- `modules/backend/services/session.py` — `SessionService` (lifecycle, cost tracking, channel binding, event publishing)
- `modules/backend/api/v1/endpoints/sessions.py` — REST endpoints for session management
- `config/settings/sessions.yaml` — TTLs, cost budget defaults, cleanup intervals
- `modules/backend/core/config_schema.py` — `SessionsSchema` config schema
- `modules/backend/core/config.py` — Register sessions config in `AppConfig`
- `modules/backend/core/exceptions.py` — `BudgetExceededError`
- `modules/backend/agents/deps/base.py` — Add `session_id` to `BaseAgentDeps` (prepare for Phase 3)
- Alembic migration for `sessions`, `session_channels`, `session_messages` tables
- Tests for session lifecycle, cost tracking, state transitions, channel binding, budget enforcement

## Key Design Decisions

- Session status: `ACTIVE`, `SUSPENDED` (waiting for input/approval), `COMPLETED`, `EXPIRED`, `FAILED`
- State machine with explicit valid transitions — terminal states (`COMPLETED`, `EXPIRED`, `FAILED`) cannot transition
- Cost tracking: `total_input_tokens`, `total_output_tokens`, `total_cost_usd`, `cost_budget_usd` — budget enforcement via `BudgetExceededError` checked BEFORE any LLM call
- Channel binding: one session can be active across multiple channels simultaneously
- Session does NOT contain domain data — domain state lives in domain tables
- `session_metadata` column name (not `metadata`) to avoid shadowing SQLAlchemy's `Base.metadata`
- String UUIDs via `UUIDMixin` for consistency with existing codebase (SQLite test compatibility)
- `SessionMessage` model included in Phase 2 to give Phase 3 (streaming coordinator) a persistence layer from day one
- Session lifecycle domain events published via `EventPublisher` from Phase 1 (feature flag gated)
- Sliding window expiry: `expires_at` resets on each activity update

## Success Criteria

- [ ] Sessions persist in PostgreSQL with full lifecycle (create → active → suspend → resume → complete)
- [ ] State machine rejects invalid transitions (e.g., COMPLETED → ACTIVE)
- [ ] Cost accumulates correctly across multiple agent interactions within a session
- [ ] Budget enforcement raises `BudgetExceededError` when cost exceeds budget
- [ ] Budget pre-check works (estimated cost check before LLM call)
- [ ] Session events (created, suspended, resumed, completed, expired, failed) publish to the event bus
- [ ] Multi-channel binding works (bind Telegram chat ID and TUI connection to same session)
- [ ] Session lookup by channel works (find session from Telegram chat ID)
- [ ] Session messages are persisted and retrievable
- [ ] Expired session cleanup identifies sessions past their `expires_at`
- [ ] Config loads from `sessions.yaml` with defaults
- [ ] Existing tests still pass (no breaking changes)

---

## Detailed Steps

### Phase 0: Git Safety

| # | Task | Command/Notes |
|---|------|---------------|
| 0.1 | Commit any uncommitted work | `git status`, then commit if needed |
| 0.2 | Create feature branch | `git checkout -b feature/session-model` |

---

### Step 1: Add session config schema and YAML

**File:** `modules/backend/core/config_schema.py`

Add a new `SessionsSchema` class following the existing `_StrictBase` pattern:

```python
class SessionsSchema(_StrictBase):
    default_ttl_hours: int = 24                    # Sessions expire after 24h of inactivity
    max_ttl_hours: int = 168                       # Hard limit: 7 days (Tier 4 needs long TTLs)
    default_cost_budget_usd: float = 50.00         # Default per-session cost limit
    max_cost_budget_usd: float = 500.00            # Hard limit on cost budget
    cleanup_interval_minutes: int = 60             # Expired session cleanup interval
    budget_warning_threshold: float = 0.80         # Warn at 80% of budget
```

**File:** `modules/backend/core/config.py`

Add sessions config loading to `AppConfig.__init__()`:

```python
self._sessions = _load_validated_optional(SessionsSchema, "sessions.yaml")
```

Add property:

```python
@property
def sessions(self) -> SessionsSchema:
    """Session settings."""
    return self._sessions
```

**Note:** Use `_load_validated_optional()` — if `sessions.yaml` doesn't exist, return `SessionsSchema()` with defaults. This keeps sessions config optional for projects that don't use sessions. Add this helper function:

```python
def _load_validated_optional(schema_cls: type, filename: str):
    """Load YAML and validate against schema. Returns defaults if file missing."""
    try:
        raw = load_yaml_config(filename)
        return schema_cls(**raw)
    except FileNotFoundError:
        return schema_cls()
```

**File:** `config/settings/sessions.yaml` (NEW)

```yaml
# =============================================================================
# Session Configuration
# =============================================================================
#   Controls session lifecycle, TTLs, cost budgets, and cleanup intervals.
#   Sessions are the platform primitive — they outlive any request or connection.

default_ttl_hours: 24
max_ttl_hours: 168
default_cost_budget_usd: 50.00
max_cost_budget_usd: 500.00
cleanup_interval_minutes: 60
budget_warning_threshold: 0.80
```

**Verify:** `get_app_config().sessions.default_ttl_hours` returns `24`.

---

### Step 2: Add `BudgetExceededError` exception

**File:** `modules/backend/core/exceptions.py`

Add a new exception class for budget enforcement. This is distinct from `ValidationError` because budget exceeded is a business rule, not input validation:

```python
class BudgetExceededError(ApplicationError):
    """Raised when a session's cost budget is exceeded."""

    def __init__(
        self,
        message: str = "Cost budget exceeded",
        current_cost: float = 0.0,
        budget: float = 0.0,
    ) -> None:
        self.current_cost = current_cost
        self.budget = budget
        super().__init__(message, code="COST_BUDGET_EXCEEDED")
```

Place it after `RateLimitError`, before `DatabaseError`.

---

### Step 3: Create session models

**File:** `modules/backend/models/session.py` (NEW, ~130 lines)

Three models: `Session`, `SessionChannel`, `SessionMessage`. All follow the existing codebase pattern: SQLAlchemy 2.0 `Mapped` types, `UUIDMixin`, `TimestampMixin`.

```python
"""Session models — the platform primitive for persistent interaction context."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, JSON, String, Text, Boolean
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
        String(36), nullable=False, index=True
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

    Persisted for the streaming coordinator (Phase 3) and memory architecture.
    Not stored on the Session row — conversation history is always in this table.
    """

    __tablename__ = "session_messages"

    session_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
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
```

**Key decisions:**
- `session_metadata` NOT `metadata` (avoids shadowing `Base.metadata`)
- String UUIDs via `UUIDMixin` (matches existing `Note` model)
- `SessionMessage` uses only `created_at` (no `TimestampMixin`) because messages are immutable
- `channels` relationship uses `lazy="selectin"` (always loaded with session — channels are small)
- `messages` relationship uses `lazy="noload"` (never auto-loaded — messages can be large, load explicitly)
- Foreign keys are implicit via string column matching (no SQLAlchemy `ForeignKey` — keeps SQLite test compatibility). If using PostgreSQL-only, add `ForeignKey("sessions.id")` to `session_id` columns.

---

### Step 4: Update model registration

**File:** `modules/backend/models/__init__.py`

Add the new models so Alembic can detect them:

```python
# Database models package
from modules.backend.models.base import Base
from modules.backend.models.session import Session, SessionChannel, SessionMessage

__all__ = ["Base", "Session", "SessionChannel", "SessionMessage"]
```

---

### Step 5: Create session schemas

**File:** `modules/backend/schemas/session.py` (NEW, ~120 lines)

Follow the existing `NoteCreate`/`NoteResponse` pattern with `Field()` descriptions.

```python
"""Session Pydantic schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    """Create a new session. Goal is optional — sessions can start open-ended."""

    goal: str | None = Field(
        default=None,
        max_length=2000,
        description="What this session is trying to achieve",
        examples=["Analyze Q4 revenue data and generate a report"],
    )
    agent_id: str | None = Field(
        default=None,
        max_length=100,
        description="Primary agent to assign to this session",
        examples=["code.qa"],
    )
    cost_budget_usd: float | None = Field(
        default=None,
        ge=0,
        description="Cost limit in USD. None = use default from config.",
    )
    ttl_hours: int | None = Field(
        default=None,
        ge=1,
        description="Session TTL in hours. None = use default from config.",
    )
    session_metadata: dict | None = Field(
        default=None,
        description="Extensible key-value metadata for this session",
    )


class SessionUpdate(BaseModel):
    """Update session fields. Only provided fields are updated."""

    goal: str | None = Field(default=None, max_length=2000)
    agent_id: str | None = Field(default=None, max_length=100)
    cost_budget_usd: float | None = Field(default=None, ge=0)
    session_metadata: dict | None = None


class SessionResponse(BaseModel):
    """Full session representation for API responses."""

    id: str = Field(description="Session unique identifier")
    status: str = Field(description="Session lifecycle status")
    user_id: str | None = Field(description="User who owns this session")
    agent_id: str | None = Field(description="Primary agent assigned")
    goal: str | None = Field(description="Session goal")
    plan_id: str | None = Field(description="Active plan ID (Phase 5)")
    total_input_tokens: int = Field(description="Cumulative input tokens")
    total_output_tokens: int = Field(description="Cumulative output tokens")
    total_cost_usd: float = Field(description="Cumulative cost in USD")
    cost_budget_usd: float | None = Field(description="Cost limit. None = unlimited")
    budget_remaining_usd: float | None = Field(
        default=None,
        description="Remaining budget. None if unlimited.",
    )
    created_at: datetime = Field(description="Session creation time")
    updated_at: datetime = Field(description="Last update time")
    last_activity_at: datetime = Field(description="Last user/agent activity time")
    expires_at: datetime | None = Field(description="When this session expires")

    model_config = ConfigDict(from_attributes=True)


class SessionListResponse(BaseModel):
    """Lightweight session representation for list endpoints."""

    id: str
    status: str
    goal: str | None
    agent_id: str | None
    total_cost_usd: float
    created_at: datetime
    last_activity_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionMessageCreate(BaseModel):
    """A message sent into a session from any source."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Message content",
    )
    role: str = Field(
        ...,
        pattern="^(user|assistant|system|tool_call|tool_result)$",
        description="Message role",
    )
    sender_id: str | None = Field(
        default=None,
        max_length=100,
        description="Agent name or user ID",
    )
    model: str | None = Field(
        default=None,
        description="Model used for generation (assistant messages only)",
    )
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    tool_name: str | None = Field(default=None, max_length=200)
    tool_call_id: str | None = Field(default=None, max_length=100)


class SessionMessageResponse(BaseModel):
    """Session message representation for API responses."""

    id: str
    session_id: str
    role: str
    content: str
    sender_id: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    tool_name: str | None
    tool_call_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChannelBindRequest(BaseModel):
    """Bind a channel to a session."""

    channel_type: str = Field(
        ...,
        max_length=50,
        description="Channel type: telegram, tui, web, cli, mcp, a2a",
        examples=["telegram"],
    )
    channel_id: str = Field(
        ...,
        max_length=200,
        description="Channel-specific identifier (chat_id, connection_id, etc.)",
        examples=["123456789"],
    )


class ChannelResponse(BaseModel):
    """Channel binding representation."""

    id: str
    session_id: str
    channel_type: str
    channel_id: str
    bound_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
```

---

### Step 6: Create session repository

**File:** `modules/backend/repositories/session.py` (NEW, ~140 lines)

Extends `BaseRepository[Session]` with session-specific queries. Follow the existing `NoteRepository` pattern.

```python
"""Session repository — database queries for sessions and related tables."""

from datetime import datetime

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.utils import utc_now
from modules.backend.models.session import (
    Session,
    SessionChannel,
    SessionMessage,
    SessionStatus,
)
from modules.backend.repositories.base import BaseRepository


class SessionRepository(BaseRepository[Session]):
    """Repository for Session model with lifecycle and channel queries."""

    model = Session

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_active_by_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """Get active and suspended sessions for a user."""
        result = await self.session.execute(
            select(Session)
            .where(
                Session.user_id == user_id,
                Session.status.in_([
                    SessionStatus.ACTIVE.value,
                    SessionStatus.SUSPENDED.value,
                ]),
            )
            .order_by(Session.last_activity_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_user(
        self,
        user_id: str,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """Get sessions for a user, optionally filtered by status."""
        stmt = select(Session).where(Session.user_id == user_id)
        if status_filter:
            stmt = stmt.where(Session.status == status_filter)
        stmt = stmt.order_by(Session.last_activity_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_user(
        self,
        user_id: str,
        status_filter: str | None = None,
    ) -> int:
        """Count sessions for a user, optionally filtered by status."""
        stmt = select(func.count()).select_from(Session).where(Session.user_id == user_id)
        if status_filter:
            stmt = stmt.where(Session.status == status_filter)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def update_last_activity(self, session_id: str, new_expires_at: datetime | None = None) -> None:
        """Touch the session's last_activity_at and optionally update expires_at."""
        values: dict = {"last_activity_at": utc_now()}
        if new_expires_at is not None:
            values["expires_at"] = new_expires_at
        await self.session.execute(
            update(Session).where(Session.id == session_id).values(**values)
        )
        await self.session.flush()

    async def find_expired(self, now: datetime | None = None) -> list[Session]:
        """Find sessions past their expires_at that are still ACTIVE or SUSPENDED."""
        if now is None:
            now = utc_now()
        result = await self.session.execute(
            select(Session).where(
                Session.expires_at.isnot(None),
                Session.expires_at <= now,
                Session.status.in_([
                    SessionStatus.ACTIVE.value,
                    SessionStatus.SUSPENDED.value,
                ]),
            )
        )
        return list(result.scalars().all())

    # --- Channel queries ---

    async def bind_channel(
        self,
        session_id: str,
        channel_type: str,
        channel_id: str,
    ) -> SessionChannel:
        """Bind a channel to a session. Deactivates any existing binding for this channel."""
        # Deactivate existing bindings for this channel
        await self.session.execute(
            update(SessionChannel)
            .where(
                SessionChannel.channel_type == channel_type,
                SessionChannel.channel_id == channel_id,
                SessionChannel.is_active == True,  # noqa: E712
            )
            .values(is_active=False)
        )

        binding = SessionChannel(
            session_id=session_id,
            channel_type=channel_type,
            channel_id=channel_id,
        )
        self.session.add(binding)
        await self.session.flush()
        await self.session.refresh(binding)
        return binding

    async def unbind_channel(
        self,
        session_id: str,
        channel_type: str,
        channel_id: str,
    ) -> None:
        """Deactivate a channel binding."""
        await self.session.execute(
            update(SessionChannel)
            .where(
                SessionChannel.session_id == session_id,
                SessionChannel.channel_type == channel_type,
                SessionChannel.channel_id == channel_id,
                SessionChannel.is_active == True,  # noqa: E712
            )
            .values(is_active=False)
        )
        await self.session.flush()

    async def get_session_by_channel(
        self,
        channel_type: str,
        channel_id: str,
    ) -> Session | None:
        """Find the active session bound to a channel. Returns None if not found."""
        result = await self.session.execute(
            select(Session)
            .join(
                SessionChannel,
                SessionChannel.session_id == Session.id,
            )
            .where(
                SessionChannel.channel_type == channel_type,
                SessionChannel.channel_id == channel_id,
                SessionChannel.is_active == True,  # noqa: E712
                Session.status.in_([
                    SessionStatus.ACTIVE.value,
                    SessionStatus.SUSPENDED.value,
                ]),
            )
        )
        return result.scalar_one_or_none()

    # --- Message queries ---

    async def add_message(self, **kwargs) -> SessionMessage:
        """Add a message to a session."""
        msg = SessionMessage(**kwargs)
        self.session.add(msg)
        await self.session.flush()
        await self.session.refresh(msg)
        return msg

    async def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SessionMessage]:
        """Get messages for a session, ordered by creation time."""
        result = await self.session.execute(
            select(SessionMessage)
            .where(SessionMessage.session_id == session_id)
            .order_by(SessionMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_messages(self, session_id: str) -> int:
        """Count messages in a session."""
        result = await self.session.execute(
            select(func.count())
            .select_from(SessionMessage)
            .where(SessionMessage.session_id == session_id)
        )
        return result.scalar_one()
```

---

### Step 7: Create session service

**File:** `modules/backend/services/session.py` (NEW, ~280 lines)

The session service manages the full lifecycle: creation, state transitions, cost tracking, channel binding, activity tracking, and event publishing. Follows the existing `NoteService` pattern — extends `BaseService`, initializes `SessionRepository` in `__init__`.

```python
"""Session service — lifecycle management for the platform primitive."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from modules.backend.core.config import get_app_config
from modules.backend.core.exceptions import BudgetExceededError, NotFoundError, ValidationError
from modules.backend.core.logging import get_logger
from modules.backend.core.utils import utc_now
from modules.backend.models.session import Session, SessionStatus, VALID_TRANSITIONS
from modules.backend.repositories.session import SessionRepository
from modules.backend.schemas.session import (
    SessionCreate,
    SessionMessageCreate,
    SessionUpdate,
)
from modules.backend.services.base import BaseService

logger = get_logger(__name__)


class SessionService(BaseService):
    """Manages session lifecycle. Does not contain agent logic — that lives in the coordinator."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repo = SessionRepository(session)

    # --- Lifecycle ---

    async def create_session(
        self,
        data: SessionCreate,
        user_id: str | None = None,
    ) -> Session:
        """Create a new session with TTL and cost budget from config defaults."""
        config = get_app_config().sessions

        # Resolve TTL
        ttl_hours = data.ttl_hours or config.default_ttl_hours
        ttl_hours = min(ttl_hours, config.max_ttl_hours)
        now = utc_now()
        expires_at = now + timedelta(hours=ttl_hours)

        # Resolve cost budget
        cost_budget = data.cost_budget_usd
        if cost_budget is None:
            cost_budget = config.default_cost_budget_usd
        if cost_budget is not None:
            cost_budget = min(cost_budget, config.max_cost_budget_usd)

        session = await self._execute_db_operation(
            "create_session",
            self.repo.create(
                user_id=user_id,
                status=SessionStatus.ACTIVE.value,
                goal=data.goal,
                agent_id=data.agent_id,
                cost_budget_usd=cost_budget,
                session_metadata=data.session_metadata or {},
                expires_at=expires_at,
            ),
        )

        self._log_operation(
            "Session created",
            session_id=session.id,
            ttl_hours=ttl_hours,
            cost_budget=cost_budget,
        )

        await self._publish_session_event("session.created", session)
        return session

    async def get_session(self, session_id: str) -> Session:
        """Get a session by ID. Raises NotFoundError if not found."""
        return await self.repo.get_by_id(session_id)

    async def update_session(self, session_id: str, data: SessionUpdate) -> Session:
        """Update mutable session fields."""
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return await self.repo.get_by_id(session_id)

        # Enforce max cost budget
        if "cost_budget_usd" in update_data and update_data["cost_budget_usd"] is not None:
            config = get_app_config().sessions
            update_data["cost_budget_usd"] = min(
                update_data["cost_budget_usd"], config.max_cost_budget_usd
            )

        session = await self._execute_db_operation(
            "update_session",
            self.repo.update(session_id, **update_data),
        )
        return session

    async def list_user_sessions(
        self,
        user_id: str,
        status_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Session], int]:
        """List sessions for a user with pagination."""
        sessions = await self.repo.get_by_user(
            user_id, status_filter=status_filter, limit=limit, offset=offset
        )
        total = await self.repo.count_by_user(user_id, status_filter=status_filter)
        return sessions, total

    # --- State Transitions ---

    async def _transition(
        self,
        session_id: str,
        target_status: SessionStatus,
        reason: str | None = None,
    ) -> Session:
        """Transition a session to a new status with state machine validation."""
        session = await self.repo.get_by_id(session_id)
        current = SessionStatus(session.status)

        if target_status not in VALID_TRANSITIONS.get(current, set()):
            raise ValidationError(
                message=f"Cannot transition from {current.value} to {target_status.value}",
                details={"current_status": current.value, "target_status": target_status.value},
            )

        session = await self._execute_db_operation(
            f"session_{target_status.value}",
            self.repo.update(
                session_id,
                status=target_status.value,
                **({"session_metadata": {
                    **(session.session_metadata or {}),
                    f"{target_status.value}_reason": reason,
                }} if reason else {}),
            ),
        )

        self._log_operation(
            f"Session {target_status.value}",
            session_id=session_id,
            from_status=current.value,
            reason=reason,
        )

        await self._publish_session_event(f"session.{target_status.value}", session)
        return session

    async def suspend_session(self, session_id: str, reason: str) -> Session:
        """Suspend a session — waiting for human/AI input or approval."""
        return await self._transition(session_id, SessionStatus.SUSPENDED, reason=reason)

    async def resume_session(self, session_id: str) -> Session:
        """Resume a suspended session."""
        return await self._transition(session_id, SessionStatus.ACTIVE)

    async def complete_session(self, session_id: str) -> Session:
        """Mark a session as completed — goal achieved or user ended."""
        return await self._transition(session_id, SessionStatus.COMPLETED)

    async def fail_session(self, session_id: str, reason: str) -> Session:
        """Mark a session as failed — unrecoverable error."""
        return await self._transition(session_id, SessionStatus.FAILED, reason=reason)

    async def expire_session(self, session_id: str) -> Session:
        """Mark a session as expired — TTL exceeded."""
        return await self._transition(session_id, SessionStatus.EXPIRED, reason="TTL exceeded")

    # --- Cost Tracking ---

    async def update_cost(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        """Add token usage and cost to a session. Does NOT check budget — use enforce_budget() first."""
        session = await self.repo.get_by_id(session_id)
        await self._execute_db_operation(
            "update_cost",
            self.repo.update(
                session_id,
                total_input_tokens=session.total_input_tokens + input_tokens,
                total_output_tokens=session.total_output_tokens + output_tokens,
                total_cost_usd=session.total_cost_usd + cost_usd,
            ),
        )

        self._log_debug(
            "Cost updated",
            session_id=session_id,
            added_cost=cost_usd,
            total_cost=session.total_cost_usd + cost_usd,
        )

        # Check budget warning threshold
        if session.cost_budget_usd:
            new_total = session.total_cost_usd + cost_usd
            config = get_app_config().sessions
            if new_total >= session.cost_budget_usd * config.budget_warning_threshold:
                await self._publish_session_event("session.cost.budget_warning", session)

    async def enforce_budget(
        self,
        session_id: str,
        estimated_cost: float = 0.0,
    ) -> None:
        """Check if a session has budget remaining BEFORE making an LLM call.

        Call this before every LLM invocation. Raises BudgetExceededError if
        the current cost plus estimated cost exceeds the budget.
        """
        session = await self.repo.get_by_id(session_id)
        if session.cost_budget_usd is None:
            return  # Unlimited budget

        projected = session.total_cost_usd + estimated_cost
        if projected >= session.cost_budget_usd:
            raise BudgetExceededError(
                message=(
                    f"Session cost {session.total_cost_usd:.4f} + estimated "
                    f"{estimated_cost:.4f} = {projected:.4f} exceeds budget "
                    f"{session.cost_budget_usd:.4f}"
                ),
                current_cost=session.total_cost_usd,
                budget=session.cost_budget_usd,
            )

    # --- Activity Tracking ---

    async def touch_activity(self, session_id: str) -> None:
        """Update last_activity_at and slide the expiry window."""
        session = await self.repo.get_by_id(session_id)
        if session.expires_at is not None:
            config = get_app_config().sessions
            # Slide the expiry window based on original TTL or default
            ttl_hours = config.default_ttl_hours
            new_expires_at = utc_now() + timedelta(hours=ttl_hours)
            # Clamp to max TTL from original creation
            max_expires = session.created_at + timedelta(hours=config.max_ttl_hours)
            if new_expires_at > max_expires:
                new_expires_at = max_expires
            await self.repo.update_last_activity(session_id, new_expires_at)
        else:
            await self.repo.update_last_activity(session_id)

    # --- Channel Binding ---

    async def bind_channel(
        self,
        session_id: str,
        channel_type: str,
        channel_id: str,
    ) -> None:
        """Bind a channel to a session. Deactivates any previous binding for this channel."""
        await self.repo.get_by_id(session_id)  # Verify session exists
        await self._execute_db_operation(
            "bind_channel",
            self.repo.bind_channel(session_id, channel_type, channel_id),
        )
        self._log_operation(
            "Channel bound",
            session_id=session_id,
            channel_type=channel_type,
            channel_id=channel_id,
        )

    async def unbind_channel(
        self,
        session_id: str,
        channel_type: str,
        channel_id: str,
    ) -> None:
        """Unbind a channel from a session."""
        await self._execute_db_operation(
            "unbind_channel",
            self.repo.unbind_channel(session_id, channel_type, channel_id),
        )

    async def get_session_by_channel(
        self,
        channel_type: str,
        channel_id: str,
    ) -> Session:
        """Find the active session for a channel. Raises NotFoundError if not found."""
        session = await self.repo.get_session_by_channel(channel_type, channel_id)
        if session is None:
            raise NotFoundError(
                message=f"No active session for {channel_type}:{channel_id}"
            )
        return session

    # --- Messages ---

    async def add_message(
        self,
        session_id: str,
        data: SessionMessageCreate,
    ) -> None:
        """Add a message to a session's conversation history."""
        await self.repo.get_by_id(session_id)  # Verify session exists
        await self._execute_db_operation(
            "add_message",
            self.repo.add_message(
                session_id=session_id,
                role=data.role,
                content=data.content,
                sender_id=data.sender_id,
                model=data.model,
                input_tokens=data.input_tokens,
                output_tokens=data.output_tokens,
                cost_usd=data.cost_usd,
                tool_name=data.tool_name,
                tool_call_id=data.tool_call_id,
            ),
        )

    async def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list, int]:
        """Get messages for a session with pagination."""
        await self.repo.get_by_id(session_id)  # Verify session exists
        messages = await self.repo.get_messages(session_id, limit=limit, offset=offset)
        total = await self.repo.count_messages(session_id)
        return messages, total

    # --- Expired Session Cleanup ---

    async def expire_inactive_sessions(self) -> int:
        """Find and expire sessions past their TTL. Returns count of expired sessions."""
        expired = await self.repo.find_expired()
        count = 0
        for session in expired:
            try:
                await self.expire_session(session.id)
                count += 1
            except ValidationError:
                pass  # Already in terminal state — skip
        if count > 0:
            logger.info(
                "Expired inactive sessions",
                extra={"count": count},
            )
        return count

    # --- Event Publishing ---

    async def _publish_session_event(self, event_type: str, session: Session) -> None:
        """Publish a session lifecycle domain event via the event bus (Phase 1).

        Feature-flag gated via events_publish_enabled. If the event bus is not
        available or disabled, this is a no-op.
        """
        try:
            from modules.backend.core.config import get_app_config

            if not get_app_config().features.events_publish_enabled:
                return

            from modules.backend.events.publishers import EventPublisher
            from modules.backend.events.schemas import EventEnvelope

            envelope = EventEnvelope(
                event_type=event_type,
                source="session-service",
                correlation_id=session.id,
                session_id=session.id,
                payload={
                    "session_id": session.id,
                    "status": session.status,
                    "user_id": session.user_id,
                    "goal": session.goal,
                    "total_cost_usd": session.total_cost_usd,
                    "cost_budget_usd": session.cost_budget_usd,
                },
            )

            publisher = EventPublisher()
            await publisher.publish(
                stream=f"sessions:session-{event_type.split('.')[-1]}",
                event=envelope,
            )
        except Exception as e:
            # Event publishing is non-critical — log and continue
            logger.warning(
                "Failed to publish session event",
                extra={"event_type": event_type, "session_id": session.id, "error": str(e)},
            )
```

**Key patterns:**
- `_transition()` is the single choke point for all state changes — validates against `VALID_TRANSITIONS`
- `enforce_budget()` is called BEFORE LLM calls (pre-check). `update_cost()` is called AFTER (post-update). Two separate methods.
- `touch_activity()` implements sliding window expiry with max TTL clamp
- `_publish_session_event()` is feature-flag gated and wrapped in try/except — event publishing is never critical
- All methods use `_execute_db_operation()` from `BaseService` for consistent error handling
- Service returns domain models (not schemas) — the API layer converts to schemas

---

### Step 8: Create session API endpoints

**File:** `modules/backend/api/v1/endpoints/sessions.py` (NEW, ~200 lines)

Follow the existing `notes.py` endpoint pattern: `APIRouter`, `DbSession`, `RequestId`, `ApiResponse`, `PaginatedResponse`.

```python
"""Session management REST endpoints."""

from fastapi import APIRouter, Depends, Query

from modules.backend.core.dependencies import DbSession, RequestId
from modules.backend.schemas.base import ApiResponse
from modules.backend.schemas.session import (
    ChannelBindRequest,
    ChannelResponse,
    SessionCreate,
    SessionListResponse,
    SessionMessageCreate,
    SessionMessageResponse,
    SessionResponse,
    SessionUpdate,
)
from modules.backend.services.session import SessionService

router = APIRouter()


def _to_response(session) -> SessionResponse:
    """Convert Session model to SessionResponse with computed fields."""
    resp = SessionResponse.model_validate(session)
    if session.cost_budget_usd is not None:
        resp.budget_remaining_usd = max(
            0.0, session.cost_budget_usd - session.total_cost_usd
        )
    return resp


# --- Session CRUD ---


@router.post(
    "",
    response_model=ApiResponse[SessionResponse],
    status_code=201,
    summary="Create a session",
    description="Create a new interactive session with optional goal, agent, and cost budget.",
)
async def create_session(
    data: SessionCreate,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.create_session(data)
    return ApiResponse(data=_to_response(session))


@router.get(
    "/{session_id}",
    response_model=ApiResponse[SessionResponse],
    summary="Get a session",
    description="Get a session by ID with current cost and status.",
)
async def get_session(
    session_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.get_session(session_id)
    return ApiResponse(data=_to_response(session))


@router.patch(
    "/{session_id}",
    response_model=ApiResponse[SessionResponse],
    summary="Update a session",
    description="Update session fields (goal, agent, budget, metadata).",
)
async def update_session(
    session_id: str,
    data: SessionUpdate,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.update_session(session_id, data)
    return ApiResponse(data=_to_response(session))


@router.get(
    "",
    summary="List sessions",
    description="List sessions for the current user with optional status filter.",
)
async def list_sessions(
    db: DbSession,
    request_id: RequestId,
    user_id: str | None = Query(default=None, description="Filter by user ID"),
    status: str | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    service = SessionService(db)
    sessions, total = await service.list_user_sessions(
        user_id=user_id or "",
        status_filter=status,
        limit=limit,
        offset=offset,
    )
    from modules.backend.schemas.base import create_paginated_response
    return create_paginated_response(
        items=sessions,
        item_schema=SessionListResponse,
        total=total,
        limit=limit,
        offset=offset,
        request_id=request_id,
    )


# --- State Transitions ---


@router.post(
    "/{session_id}/suspend",
    response_model=ApiResponse[SessionResponse],
    summary="Suspend a session",
    description="Suspend a session — pauses for human/AI input or approval.",
)
async def suspend_session(
    session_id: str,
    reason: str = Query(..., description="Reason for suspension"),
    db: DbSession = Depends(),
    request_id: RequestId = Depends(),
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.suspend_session(session_id, reason)
    return ApiResponse(data=_to_response(session))


@router.post(
    "/{session_id}/resume",
    response_model=ApiResponse[SessionResponse],
    summary="Resume a session",
    description="Resume a suspended session.",
)
async def resume_session(
    session_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.resume_session(session_id)
    return ApiResponse(data=_to_response(session))


@router.post(
    "/{session_id}/complete",
    response_model=ApiResponse[SessionResponse],
    summary="Complete a session",
    description="Mark a session as completed — goal achieved or user ended.",
)
async def complete_session(
    session_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.complete_session(session_id)
    return ApiResponse(data=_to_response(session))


# --- Channel Binding ---


@router.post(
    "/{session_id}/channels",
    response_model=ApiResponse[ChannelResponse],
    status_code=201,
    summary="Bind a channel",
    description="Bind a communication channel to this session.",
)
async def bind_channel(
    session_id: str,
    data: ChannelBindRequest,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[ChannelResponse]:
    service = SessionService(db)
    await service.bind_channel(session_id, data.channel_type, data.channel_id)
    # Re-fetch to get the binding
    session = await service.get_session(session_id)
    binding = next(
        (c for c in session.channels if c.channel_type == data.channel_type and c.channel_id == data.channel_id and c.is_active),
        None,
    )
    return ApiResponse(data=ChannelResponse.model_validate(binding))


@router.delete(
    "/{session_id}/channels/{channel_type}/{channel_id}",
    status_code=204,
    summary="Unbind a channel",
    description="Unbind a communication channel from this session.",
)
async def unbind_channel(
    session_id: str,
    channel_type: str,
    channel_id: str,
    db: DbSession,
    request_id: RequestId,
) -> None:
    service = SessionService(db)
    await service.unbind_channel(session_id, channel_type, channel_id)


@router.get(
    "/by-channel/{channel_type}/{channel_id}",
    response_model=ApiResponse[SessionResponse],
    summary="Find session by channel",
    description="Find the active session bound to a specific channel.",
)
async def get_session_by_channel(
    channel_type: str,
    channel_id: str,
    db: DbSession,
    request_id: RequestId,
) -> ApiResponse[SessionResponse]:
    service = SessionService(db)
    session = await service.get_session_by_channel(channel_type, channel_id)
    return ApiResponse(data=_to_response(session))


# --- Messages ---


@router.get(
    "/{session_id}/messages",
    summary="Get session messages",
    description="Get conversation history for a session.",
)
async def get_messages(
    session_id: str,
    db: DbSession,
    request_id: RequestId,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    service = SessionService(db)
    messages, total = await service.get_messages(session_id, limit=limit, offset=offset)
    from modules.backend.schemas.base import create_paginated_response
    return create_paginated_response(
        items=messages,
        item_schema=SessionMessageResponse,
        total=total,
        limit=limit,
        offset=offset,
        request_id=request_id,
    )
```

**Note:** The `list_sessions` and `get_messages` endpoints use `create_paginated_response` from `schemas.base` — same pattern as the existing notes list endpoint. The `user_id` query parameter is temporary — in production, this will come from the authenticated user context.

---

### Step 9: Register session routes

**File:** `modules/backend/api/v1/__init__.py`

Add the sessions router alongside notes and agents:

```python
from modules.backend.api.v1.endpoints import agents, notes, sessions

router = APIRouter()

# Notes endpoints
router.include_router(notes.router, prefix="/notes", tags=["notes"])

# Agent endpoints
router.include_router(agents.router, prefix="/agents", tags=["agents"])

# Session endpoints
router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
```

**Important:** The `sessions` import and `include_router` call must be added. The `by-channel` route uses a path prefix to avoid ambiguity with `/{session_id}`.

---

### Step 10: Update Alembic env.py

**File:** `modules/backend/migrations/env.py`

Add imports for the new session models so Alembic's autogenerate detects them:

```python
from modules.backend.models.session import Session, SessionChannel, SessionMessage  # noqa: F401
```

Place this alongside the existing `from modules.backend.models.note import Note  # noqa: F401`.

---

### Step 11: Generate Alembic migration

Run autogenerate to create the migration for the three new tables:

```bash
cd modules/backend && alembic revision --autogenerate -m "add sessions session_channels session_messages tables"
```

**Verify the generated migration contains:**
- `create_table("sessions", ...)` with all columns and indexes
- `create_table("session_channels", ...)` with indexes
- `create_table("session_messages", ...)` with index
- Downgrade drops all three tables

**Review the migration file** — autogenerate sometimes misses indexes or gets defaults wrong. Ensure:
- All `Index(...)` definitions from the models are included
- Default values are correct
- `nullable` flags match the model

---

### Step 12: Add `session_id` to `BaseAgentDeps`

**File:** `modules/backend/agents/deps/base.py`

Add `session_id` field to `BaseAgentDeps` for Phase 3 (streaming coordinator).

```python
@dataclass
class BaseAgentDeps:
    """Common dependencies injected into every agent at runtime."""

    project_root: Path
    scope: FileScope
    config: AgentConfigSchema | None = None
    session_id: str | None = None  # Set when running within a session (Phase 3+)
```

Update all subclasses (`QaAgentDeps`, `HealthAgentDeps`, `HorizontalAgentDeps`) and any call sites that construct deps to include the new field. Since we're in dev mode, fix all callers directly rather than relying on default ordering.

---

### Step 13: Write tests

**File:** `tests/unit/backend/sessions/__init__.py` (NEW, empty)

**File:** `tests/unit/backend/sessions/test_models.py` (NEW, ~80 lines)

Test session models and state machine:

- `test_session_status_enum_values` — all 5 status values exist and are strings
- `test_valid_transitions_active` — ACTIVE can go to SUSPENDED, COMPLETED, FAILED, EXPIRED
- `test_valid_transitions_suspended` — SUSPENDED can go to ACTIVE, COMPLETED, FAILED, EXPIRED
- `test_terminal_states_have_no_transitions` — COMPLETED, EXPIRED, FAILED have empty transition sets
- `test_session_defaults` — new Session has correct defaults (status=ACTIVE, cost=0, etc.)
- `test_session_channel_defaults` — new SessionChannel has is_active=True
- `test_session_message_roles` — valid role strings accepted

**File:** `tests/unit/backend/sessions/test_service.py` (NEW, ~200 lines)

Test session service with mock database session (follow `test_note_service.py` pattern):

- `test_create_session_defaults` — session created with config defaults for TTL and budget
- `test_create_session_custom_budget` — custom budget used, clamped to max
- `test_create_session_custom_ttl` — custom TTL used, clamped to max
- `test_suspend_session` — ACTIVE → SUSPENDED, reason stored in metadata
- `test_resume_session` — SUSPENDED → ACTIVE
- `test_complete_session` — ACTIVE → COMPLETED
- `test_fail_session` — ACTIVE → FAILED, reason stored
- `test_invalid_transition_completed_to_active` — raises ValidationError
- `test_invalid_transition_expired_to_active` — raises ValidationError
- `test_update_cost` — tokens and cost accumulate correctly
- `test_enforce_budget_within_limit` — no error when within budget
- `test_enforce_budget_exceeded` — raises BudgetExceededError
- `test_enforce_budget_unlimited` — no error when budget is None
- `test_enforce_budget_with_estimated_cost` — checks current + estimated vs budget
- `test_touch_activity_slides_expiry` — expires_at moves forward on activity
- `test_touch_activity_clamps_to_max_ttl` — expires_at never exceeds max TTL
- `test_expire_inactive_sessions` — finds and expires sessions past their TTL
- `test_bind_channel` — channel bound to session
- `test_unbind_channel` — channel deactivated
- `test_get_session_by_channel` — finds session from channel binding
- `test_get_session_by_channel_not_found` — raises NotFoundError
- `test_add_message` — message persisted with correct fields
- `test_get_messages_ordered` — messages returned in creation order

**File:** `tests/unit/backend/sessions/test_schemas.py` (NEW, ~60 lines)

Test Pydantic schema validation:

- `test_session_create_defaults` — all fields optional with defaults
- `test_session_create_goal_too_long` — raises validation error for >2000 chars
- `test_session_create_negative_budget` — raises validation error for ge=0
- `test_session_response_from_attributes` — model_validate from ORM model works
- `test_session_message_create_valid_roles` — all 5 roles accepted
- `test_session_message_create_invalid_role` — rejects invalid role pattern
- `test_session_message_create_empty_content` — rejects empty content (min_length=1)
- `test_channel_bind_request_required_fields` — channel_type and channel_id required
- `test_session_update_partial` — exclude_unset works for partial updates

**File:** `tests/unit/backend/sessions/test_config.py` (NEW, ~40 lines)

Test session config loading:

- `test_sessions_config_defaults` — default values match expectations
- `test_sessions_config_from_yaml` — loads from sessions.yaml correctly
- `test_sessions_config_strict` — unknown keys rejected (extra=forbid)
- `test_sessions_config_budget_warning_threshold` — 0.80 default

**File:** `tests/unit/backend/sessions/test_repository.py` (NEW, ~100 lines)

Test repository queries with mock database session:

- `test_get_active_by_user` — returns only ACTIVE and SUSPENDED sessions
- `test_get_by_user_with_status_filter` — filters by status correctly
- `test_update_last_activity` — updates timestamp and optionally expires_at
- `test_find_expired` — finds sessions past expires_at in non-terminal states
- `test_bind_channel_deactivates_existing` — existing binding for same channel deactivated
- `test_get_session_by_channel` — joins channels and sessions correctly
- `test_add_message` — message created and flushed
- `test_get_messages_ordered` — ordered by created_at ascending
- `test_count_messages` — returns correct count

**File:** `tests/integration/backend/sessions/__init__.py` (NEW, empty)

**File:** `tests/integration/backend/sessions/test_sessions_api.py` (NEW, ~150 lines)

Integration tests for session API endpoints (follow `test_notes_api.py` pattern):

- `test_create_session` — POST /api/v1/sessions returns 201 with session data
- `test_create_session_with_goal` — goal is stored and returned
- `test_get_session` — GET /api/v1/sessions/{id} returns session
- `test_get_session_not_found` — returns 404
- `test_update_session` — PATCH updates goal and metadata
- `test_suspend_session` — POST /api/v1/sessions/{id}/suspend transitions to SUSPENDED
- `test_resume_session` — POST /api/v1/sessions/{id}/resume transitions to ACTIVE
- `test_complete_session` — POST /api/v1/sessions/{id}/complete transitions to COMPLETED
- `test_invalid_transition` — returns error for COMPLETED → ACTIVE
- `test_bind_channel` — POST /api/v1/sessions/{id}/channels returns 201
- `test_unbind_channel` — DELETE /api/v1/sessions/{id}/channels/{type}/{id} returns 204
- `test_find_session_by_channel` — GET /api/v1/sessions/by-channel/{type}/{id} returns session
- `test_get_messages_empty` — GET /api/v1/sessions/{id}/messages returns empty list

---

### Step 14: Verify existing tests pass

Run the full test suite to confirm no regressions:

```bash
python -m pytest tests/unit -v
```

All existing tests plus new session tests must pass.

---

### Step 15: Cleanup and review

- Verify no hardcoded values (all config from YAML or `SessionsSchema` defaults)
- Verify all imports are absolute (`from modules.backend.services...`)
- Verify all logging uses `get_logger(__name__)` with `source` in extra
- Verify all datetimes use `utc_now()` from `modules.backend.core.utils`
- Verify `session_metadata` is used everywhere (never `metadata` on the model)
- Verify `VALID_TRANSITIONS` is used for all state changes (no bypasses)
- Verify `BudgetExceededError` is raised pre-LLM call, not post
- Verify `__init__.py` files are minimal (exports only)
- Verify no file exceeds 500 lines (target ~100-200 per file)
- Verify the Alembic migration matches the model definitions exactly

---

## Files Summary

| Category | File | Action | Est. Lines |
|----------|------|--------|-----------|
| Config schema | `modules/backend/core/config_schema.py` | Modify | +10 |
| Config loader | `modules/backend/core/config.py` | Modify | +15 |
| Config YAML | `config/settings/sessions.yaml` | New | ~15 |
| Exceptions | `modules/backend/core/exceptions.py` | Modify | +10 |
| Models | `modules/backend/models/session.py` | New | ~130 |
| Models init | `modules/backend/models/__init__.py` | Modify | +3 |
| Schemas | `modules/backend/schemas/session.py` | New | ~120 |
| Repository | `modules/backend/repositories/session.py` | New | ~140 |
| Service | `modules/backend/services/session.py` | New | ~280 |
| API endpoints | `modules/backend/api/v1/endpoints/sessions.py` | New | ~200 |
| API router | `modules/backend/api/v1/__init__.py` | Modify | +3 |
| Alembic env | `modules/backend/migrations/env.py` | Modify | +1 |
| Alembic migration | `modules/backend/migrations/versions/xxx_add_sessions.py` | New (generated) | ~80 |
| Agent deps | `modules/backend/agents/deps/base.py` | Modify | +1 |
| Tests - models | `tests/unit/backend/sessions/test_models.py` | New | ~80 |
| Tests - service | `tests/unit/backend/sessions/test_service.py` | New | ~200 |
| Tests - schemas | `tests/unit/backend/sessions/test_schemas.py` | New | ~60 |
| Tests - config | `tests/unit/backend/sessions/test_config.py` | New | ~40 |
| Tests - repository | `tests/unit/backend/sessions/test_repository.py` | New | ~100 |
| Tests - integration | `tests/integration/backend/sessions/test_sessions_api.py` | New | ~150 |
| **Total** | **21 files** | **12 new, 9 modified** | **~1,640** |

---

## Anti-Patterns (Do NOT)

- Do not store conversation history in the session row. Conversation history goes in `session_messages`. The session row tracks metadata, cost, and status.
- Do not use sessions for stateless CRUD. A `POST /api/v1/notes` does not create a session. Only interactive, multi-turn, or long-running interactions need sessions.
- Do not make the session table the place for domain data. Domain state (notes, projects, users) lives in domain tables. The session tracks the interaction context around domain operations.
- Do not bypass `VALID_TRANSITIONS` for state changes. All transitions go through `_transition()`.
- Do not call `update_cost()` without calling `enforce_budget()` first. Budget check is pre-LLM, cost update is post-LLM.
- Do not use `metadata` as a column name — use `session_metadata` to avoid shadowing `Base.metadata`.
- Do not import `logging` directly. Use `from modules.backend.core.logging import get_logger`.
- Do not use `datetime.utcnow()`. Use `from modules.backend.core.utils import utc_now`.
- Do not hardcode TTLs, budgets, or timeouts. All from config.
- Do not make event publishing critical. Session lifecycle events are published best-effort — failures are logged and swallowed.

---
