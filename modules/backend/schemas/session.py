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
        examples=["code.quality"],
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
