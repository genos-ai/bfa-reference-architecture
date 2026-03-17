"""
Agent Configuration Schemas.

Pydantic models defining the expected structure of agent and mission control
YAML config files. Used by AgentRegistry and middleware to validate
configuration at load time.

Each top-level class corresponds to one config file:
    AgentConfigSchema              -> config/agents/**/agent.yaml
    MissionControlConfigSchema     -> config/agents/mission_control.yaml
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictBase(BaseModel):
    """Base with extra='forbid' so unknown YAML keys are caught immediately."""

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Agent config schemas (config/agents/**/agent.yaml)
# =============================================================================


class FileScopeConfigSchema(_StrictBase):
    """Filesystem access control for an agent."""

    read: list[str] = Field(default_factory=list)
    write: list[str] = Field(default_factory=list)


class ExecutionSchema(_StrictBase):
    """Agent execution environment."""

    mode: str


class ComplianceRuleSchema(_StrictBase):
    """A single compliance rule definition."""

    id: str
    description: str
    severity: str
    enabled: bool


class ExclusionsSchema(_StrictBase):
    """Paths and patterns excluded from scanning."""

    paths: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)


class AgentInterfaceSchema(_StrictBase):
    """Typed input/output contract for an agent.

    Defines the fields an agent expects as input and produces as output.
    Used by Mission Control for Tier 1 structural validation (Plan 14)
    and by the Planning Agent for input compatibility checks (Plan 13).
    """

    input: dict[str, str] = Field(
        default_factory=dict,
        description="Input fields: field_name → type_name",
    )
    output: dict[str, str] = Field(
        default_factory=dict,
        description="Output fields: field_name → type_name",
    )


class AgentModelSchema(_StrictBase):
    """Pinned model configuration. Immutable at runtime.

    Models are pinned to agents as non-overridable properties (research doc 11).
    Model upgrades are agent version bumps: create agent_v2 with new model,
    validate, then update roster. No runtime model override path exists.
    """

    name: str = Field(
        ...,
        description="Model identifier, e.g. 'anthropic:claude-sonnet-4-20250514'",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature. Pinned, non-overridable.",
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        description="Max output tokens. Pinned, non-overridable.",
    )


class AgentConfigSchema(_StrictBase):
    """Schema for config/agents/**/agent.yaml files.

    Common fields are required. Agent-specific fields (rules, exclusions,
    file_size_limit) are optional — absent in agents that don't need them.
    """

    agent_name: str
    agent_type: str
    description: str
    enabled: bool
    model: str | AgentModelSchema
    keywords: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    max_input_length: int
    max_budget_usd: float
    execution: ExecutionSchema
    scope: FileScopeConfigSchema = Field(default_factory=FileScopeConfigSchema)
    interface: AgentInterfaceSchema | None = None
    version: str = "1.0.0"

    # Per-agent usage limits (override system defaults from mission_control.yaml)
    max_tokens: int | None = None
    max_requests: int | None = None

    # Agent-specific optional fields
    file_size_limit: int | None = None
    rules: list[ComplianceRuleSchema] | None = None
    exclusions: ExclusionsSchema | None = None

    # Horizontal agent fields (Plan 13)
    thinking_budget: dict[str, int] | None = None

    @field_validator("model", mode="before")
    @classmethod
    def _normalize_model(cls, v: str | dict) -> str | dict:
        """Accept flat string model specs as-is; dicts become AgentModelSchema."""
        return v


# =============================================================================
# Mission Control config schema (config/agents/mission_control.yaml)
# =============================================================================


class ModelPricingRateSchema(_StrictBase):
    """Cost per million tokens for a specific model."""

    input: float
    output: float


class RoutingSchema(_StrictBase):
    """Agent routing configuration."""

    strategy: str
    llm_model: str
    complex_request_agent: str
    fallback_agent: str
    max_routing_depth: int


class MissionControlLimitsSchema(_StrictBase):
    """Budget and safety limits."""

    max_requests_per_task: int
    max_tool_calls_per_task: int
    max_tokens_per_task: int
    max_cost_per_plan: float
    max_cost_per_user_daily: float
    task_timeout_seconds: int
    plan_timeout_seconds: int


class GuardrailsSchema(_StrictBase):
    """Input validation and injection blocking."""

    max_input_length: int
    injection_patterns: list[str]


class RedisTtlSchema(_StrictBase):
    """Redis key TTLs in seconds."""

    session: int
    approval: int
    lock: int
    result: int


class ApprovalSchema(_StrictBase):
    """Human-in-the-loop approval settings."""

    poll_interval_seconds: int
    timeout_seconds: int


class DispatchSchema(_StrictBase):
    """Dispatch loop execution defaults for Mission Control."""

    default_request_limit: int = 50
    token_cost_factor: int = 333_333  # tokens per dollar of cost ceiling
    context_token_budget: int = 50_000  # assembled context packet budget
    history_reserve_tokens: int = 1_500  # reserved for Layer 2 history


class EscalationThresholdsSchema(_StrictBase):
    """Deterministic risk thresholds for automated approval decisions."""

    max_auto_approve_cost_usd: float = 1.00
    max_medium_approve_cost_usd: float = 10.00
    max_auto_approve_retries: int = 3


class MissionControlConfigSchema(_StrictBase):
    """Schema for config/agents/mission_control.yaml."""

    model_pricing: dict[str, ModelPricingRateSchema]
    routing: RoutingSchema
    limits: MissionControlLimitsSchema
    guardrails: GuardrailsSchema
    redis_ttl: RedisTtlSchema
    approval: ApprovalSchema
    dispatch: DispatchSchema = Field(default_factory=DispatchSchema)
    escalation: EscalationThresholdsSchema = Field(
        default_factory=EscalationThresholdsSchema,
    )
