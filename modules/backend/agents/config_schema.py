"""
Agent Configuration Schemas.

Pydantic models defining the expected structure of agent and coordinator
YAML config files. Used by AgentRegistry and middleware to validate
configuration at load time.

Each top-level class corresponds to one config file:
    AgentConfigSchema       -> config/agents/**/agent.yaml
    CoordinatorConfigSchema -> config/agents/coordinator.yaml
"""

from pydantic import BaseModel, ConfigDict, Field


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


class AgentConfigSchema(_StrictBase):
    """Schema for config/agents/**/agent.yaml files.

    Common fields are required. Agent-specific fields (rules, exclusions,
    file_size_limit) are optional — absent in agents that don't need them.
    """

    agent_name: str
    agent_type: str
    description: str
    enabled: bool
    model: str
    keywords: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    max_input_length: int
    max_budget_usd: float
    execution: ExecutionSchema
    scope: FileScopeConfigSchema = Field(default_factory=FileScopeConfigSchema)

    file_size_limit: int | None = None
    rules: list[ComplianceRuleSchema] | None = None
    exclusions: ExclusionsSchema | None = None


# =============================================================================
# Coordinator config schema (config/agents/coordinator.yaml)
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


class CoordinatorLimitsSchema(_StrictBase):
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


class CoordinatorConfigSchema(_StrictBase):
    """Schema for config/agents/coordinator.yaml."""

    model_pricing: dict[str, ModelPricingRateSchema]
    routing: RoutingSchema
    limits: CoordinatorLimitsSchema
    guardrails: GuardrailsSchema
    redis_ttl: RedisTtlSchema
    approval: ApprovalSchema
