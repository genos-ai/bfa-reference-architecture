"""
Configuration Schemas.

Pydantic models defining the expected structure of each YAML config file.
Used by AppConfig to validate configuration at load time. If a YAML file
has missing keys, wrong types, or unknown fields, a clear ValidationError
is raised at startup instead of a cryptic KeyError deep in application code.

Each top-level class corresponds to one file in config/settings/:
    ApplicationSchema  → application.yaml
    DatabaseSchema     → database.yaml
    LoggingSchema      → logging.yaml
    FeaturesSchema     → features.yaml
    SecuritySchema     → security.yaml
"""

from pydantic import BaseModel, ConfigDict, Field


class _StrictBase(BaseModel):
    """Base with extra='forbid' so unknown YAML keys are caught immediately."""

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# application.yaml
# =============================================================================


class ServerSchema(_StrictBase):
    host: str
    port: int


class CorsSchema(_StrictBase):
    origins: list[str]


class PaginationSchema(_StrictBase):
    default_limit: int
    max_limit: int


class TimeoutsSchema(_StrictBase):
    database: int
    external_api: int
    background: int


class TelegramAppSchema(_StrictBase):
    webhook_path: str
    authorized_users: list[int]
    max_message_length: int = 4096


class CliSchema(_StrictBase):
    console_width: int = 160


class ApplicationSchema(_StrictBase):
    name: str
    version: str
    description: str
    environment: str
    debug: bool
    api_prefix: str
    docs_enabled: bool
    server: ServerSchema
    cors: CorsSchema
    pagination: PaginationSchema
    timeouts: TimeoutsSchema
    telegram: TelegramAppSchema
    cli: CliSchema = Field(default_factory=CliSchema)


# =============================================================================
# database.yaml
# =============================================================================


class BrokerSchema(_StrictBase):
    queue_name: str
    result_expiry_seconds: int


class RedisSchema(_StrictBase):
    host: str
    port: int
    db: int
    broker: BrokerSchema


class DatabaseSchema(_StrictBase):
    host: str
    port: int
    name: str
    user: str
    pool_size: int
    max_overflow: int
    pool_timeout: int
    pool_recycle: int
    echo: bool
    echo_pool: bool
    redis: RedisSchema


# =============================================================================
# logging.yaml
# =============================================================================


class ConsoleHandlerSchema(_StrictBase):
    enabled: bool


class FileHandlerSchema(_StrictBase):
    enabled: bool
    path: str
    max_bytes: int
    backup_count: int


class HandlersSchema(_StrictBase):
    console: ConsoleHandlerSchema
    file: FileHandlerSchema


class LoggingSchema(_StrictBase):
    level: str
    format: str
    handlers: HandlersSchema


# =============================================================================
# features.yaml
# =============================================================================


class FeaturesSchema(_StrictBase):
    auth_require_email_verification: bool
    auth_allow_api_key_creation: bool
    auth_rate_limit_enabled: bool
    auth_require_api_authentication: bool
    api_detailed_errors: bool
    api_request_logging: bool
    channel_telegram_enabled: bool
    channel_slack_enabled: bool
    channel_discord_enabled: bool
    channel_whatsapp_enabled: bool
    gateway_enabled: bool
    gateway_websocket_enabled: bool
    gateway_pairing_enabled: bool
    agent_coordinator_enabled: bool
    agent_streaming_enabled: bool
    mcp_enabled: bool
    a2a_enabled: bool
    security_startup_checks_enabled: bool
    security_headers_enabled: bool
    security_cors_enforce_production: bool
    experimental_background_tasks_enabled: bool
    events_publish_enabled: bool


# =============================================================================
# security.yaml
# =============================================================================


class JwtSchema(_StrictBase):
    algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    audience: str


class ApiRateLimitSchema(_StrictBase):
    requests_per_minute: int
    requests_per_hour: int


class ChannelRateLimitSchema(_StrictBase):
    messages_per_minute: int
    messages_per_hour: int


class RateLimitingSchema(_StrictBase):
    api: ApiRateLimitSchema
    telegram: ChannelRateLimitSchema
    websocket: ChannelRateLimitSchema


class RequestLimitsSchema(_StrictBase):
    max_body_size_bytes: int
    max_header_size_bytes: int


class SecurityHeadersSchema(_StrictBase):
    x_content_type_options: str
    x_frame_options: str
    referrer_policy: str
    hsts_enabled: bool
    hsts_max_age: int


class SecretsValidationSchema(_StrictBase):
    jwt_secret_min_length: int
    api_key_salt_min_length: int
    webhook_secret_min_length: int


class CorsEnforcementSchema(_StrictBase):
    enforce_in_production: bool
    allow_methods: list[str]
    allow_headers: list[str]


class RoleSchema(_StrictBase):
    level: int
    description: str


class SecuritySchema(_StrictBase):
    jwt: JwtSchema
    rate_limiting: RateLimitingSchema
    request_limits: RequestLimitsSchema
    headers: SecurityHeadersSchema
    secrets_validation: SecretsValidationSchema
    roles: dict[str, RoleSchema] = Field(default_factory=dict)
    user_roles: dict[str, str] = Field(default_factory=dict)
    cors: CorsEnforcementSchema


# =============================================================================
# gateway.yaml
# =============================================================================


class GatewayChannelSchema(_StrictBase):
    allowlist: list[int]


class GatewaySchema(_StrictBase):
    default_policy: str
    channels: dict[str, GatewayChannelSchema]


# =============================================================================
# events.yaml
# =============================================================================


class EventsStreamSchema(_StrictBase):
    maxlen: int = 10000
    consumer_group: str = "bfa-workers"


class EventsSchema(_StrictBase):
    transport: str = "redis"
    channel_prefix: str = "session"
    streams: dict[str, EventsStreamSchema] = Field(default_factory=dict)
    consumer_timeout_ms: int = 5000
    dlq_enabled: bool = True
    dlq_prefix: str = "dlq"


# =============================================================================
# sessions.yaml
# =============================================================================


class SessionsSchema(_StrictBase):
    default_ttl_hours: int = 24
    max_ttl_hours: int = 168
    default_cost_budget_usd: float = 50.00
    max_cost_budget_usd: float = 500.00
    cleanup_interval_minutes: int = 60
    budget_warning_threshold: float = 0.80


# =============================================================================
# missions.yaml
# =============================================================================


class MissionsSchema(_StrictBase):
    """Mission persistence and audit trail configuration."""

    max_thinking_trace_length: int = 50000
    max_task_output_size_bytes: int = 1_048_576  # 1MB
    retention_days: int = 0  # 0 = keep forever
    default_page_size: int = 20
    max_page_size: int = 100
    persist_thinking_trace: bool = True
    persist_verification_details: bool = True


# =============================================================================
# temporal.yaml
# =============================================================================


class TemporalSchema(_StrictBase):
    """Temporal integration configuration (Tier 4 durable execution)."""

    enabled: bool = False
    server_url: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "agent-missions"
    workflow_execution_timeout_days: int = 30
    activity_start_to_close_seconds: int = 600
    activity_retry_max_attempts: int = 3
    approval_timeout_seconds: int = 14400
    escalation_timeout_seconds: int = 86400
    notification_timeout_seconds: int = 30


# =============================================================================
# playbooks.yaml
# =============================================================================


class PlaybooksSchema(_StrictBase):
    """Playbook and mission system configuration."""

    playbooks_dir: str = "config/playbooks"
    max_steps_per_playbook: int = 20
    max_context_size_bytes: int = 1_048_576  # 1MB
    default_step_timeout_seconds: int = 600
    default_budget_usd: float = 10.00
    max_budget_usd: float = 100.00
    max_concurrent_missions: int = 10
    enable_playbook_matching: bool = True
