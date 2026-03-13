# Code Map — 

**209 files** | **29,600 lines** | **308 classes** | **487 functions** | commit `786a4e975814`

Symbols ranked by PageRank (most-connected first).

## Dependencies

**Circular dependencies (1):**
  ! backend.agents.mission_control.checks -> backend.agents.mission_control.checks

  backend.agents.mission_control.mission_control -> backend.agents.mission_control.cost, backend.core.exceptions, backend.agents.mission_control.dispatch, backend.agents.mission_control.persistence_bridge, backend.agents.mission_control.helpers, backend.agents.mission_control.history, backend.agents.mission_control.middleware, backend.agents.mission_control.models, backend.core.protocols, backend.agents.mission_control.outcome, backend.agents.mission_control.plan_validator, backend.agents.mission_control.registry, backend.agents.mission_control.roster, backend.core.logging, backend.events.types, backend.schemas.session, backend.schemas.task_plan, backend.services.context_assembler, backend.services.context_curator, backend.services.history_query, backend.services.project_context
  backend.agents.mission_control.helpers -> backend.agents.config_schema, backend.agents.deps.base, backend.agents.mission_control.middleware, backend.agents.mission_control.models, backend.core.protocols, backend.agents.mission_control.registry, backend.agents.mission_control.roster, backend.agents.mission_control.router, backend.core.config, backend.agents.mission_control.cost, backend.core.exceptions, backend.core.logging, backend.events.types, backend.schemas.session
  backend.services.mission -> backend.core.config, backend.core.exceptions, backend.agents.mission_control.models, backend.core.logging, backend.core.protocols, backend.core.utils, backend.models.mission, backend.repositories.mission, backend.services.base
  backend.services.playbook_run -> backend.core.config, backend.core.logging, backend.core.utils, backend.models.mission, backend.repositories.playbook_run, backend.schemas.playbook, backend.services.base, backend.services.mission, backend.services.playbook
  backend.migrations.env -> backend.models.base, backend.models.mission, backend.models.mission_record, backend.models.note, backend.models.project, backend.models.project_context, backend.models.project_history, backend.models.session
  backend.services.session -> backend.core.config, backend.core.exceptions, backend.core.logging, backend.core.utils, backend.models.session, backend.repositories.session, backend.schemas.session, backend.services.base
  backend.agents.mission_control.dispatch -> backend.agents.mission_control.middleware, backend.agents.mission_control.models, backend.agents.mission_control.outcome, backend.agents.mission_control.roster, backend.agents.mission_control.verification, backend.core.logging, backend.schemas.task_plan
  backend.api.v1.endpoints.playbooks -> backend.core.dependencies, backend.core.exceptions, backend.schemas.base, backend.schemas.mission, backend.schemas.playbook, backend.services.mission, backend.services.playbook
  backend.services.mission_persistence -> backend.core.config, backend.core.logging, backend.core.utils, backend.models.mission_record, backend.repositories.mission_record, backend.schemas.mission_record, backend.services.base
  backend.main -> backend.api, backend.api.v1, backend.core.config, backend.core.exception_handlers, backend.core.logging, backend.core.middleware
  backend.services.summarization -> backend.core.logging, backend.models.mission_record, backend.models.project_history, backend.repositories.project_history, backend.services.base, backend.services.project_context
  backend.agents.mission_control.dispatch_adapter -> backend.agents.mission_control.mission_control, backend.agents.mission_control.models, backend.core.config, backend.core.protocols, backend.core.logging
  backend.agents.mission_control.plan_validator -> backend.agents.mission_control.check_registry, backend.agents.mission_control.roster, backend.core.logging, backend.schemas.task_plan, backend.agents.mission_control.checks
  backend.agents.vertical.code.architecture.agent -> backend.agents.mission_control.helpers, backend.agents.deps.base, backend.agents.schemas, backend.agents.tools, backend.core.logging
  backend.agents.vertical.code.quality.agent -> backend.agents.mission_control.helpers, backend.agents.deps.base, backend.agents.schemas, backend.agents.tools, backend.core.logging
  backend.agents.vertical.system.health.agent -> backend.agents.deps.base, backend.agents.mission_control.helpers, backend.agents.schemas, backend.agents.tools, backend.core.logging
  backend.api.v1.endpoints.missions -> backend.core.dependencies, backend.core.exceptions, backend.schemas.base, backend.schemas.mission_record, backend.services.mission_persistence
  backend.api.v1.endpoints.notes -> backend.core.dependencies, backend.core.pagination, backend.schemas.base, backend.schemas.note, backend.services.note
  backend.api.v1.endpoints.sessions -> backend.core.dependencies, backend.core.pagination, backend.schemas.base, backend.schemas.session, backend.services.session
  backend.models -> backend.models.base, backend.models.mission, backend.models.mission_record, backend.models.note, backend.models.session
  backend.services.pqi.scorer -> backend.services.pqi.ast_analysis, backend.services.pqi.composite, backend.services.pqi.dimensions, backend.services.pqi.tools, backend.services.pqi.types
  backend.services.project_context -> backend.core.logging, backend.core.utils, backend.models.project_context, backend.repositories.project_context, backend.services.base
  telegram.handlers.example -> backend.core.config, backend.core.logging, telegram.callbacks.common, telegram.keyboards.common, telegram.states.example
  backend.core.security -> backend.core.config, backend.core.exceptions, backend.core.logging, backend.core.utils
  backend.events -> backend.events.bus, backend.events.publishers, backend.events.schemas, backend.events.types
  backend.services.code_map.generator -> backend.services.code_map.assembler, backend.services.code_map.graph, backend.services.code_map.parser, backend.services.code_map.ranker
  backend.services.context_assembler -> backend.core.logging, backend.core.utils, backend.services.history_query, backend.services.project_context
  backend.services.note -> backend.models.note, backend.repositories.note, backend.schemas.note, backend.services.base
  backend.services.pqi.dimensions -> backend.services.pqi.ast_analysis, backend.services.pqi.normalizers, backend.services.pqi.tools, backend.services.pqi.types
  backend.services.project -> backend.core.logging, backend.models.project, backend.repositories.project, backend.services.base
  backend.temporal.worker -> backend.core.logging, backend.temporal.activities, backend.temporal.client, backend.temporal.workflow
  telegram.middlewares -> telegram.middlewares.auth, telegram.middlewares.logging, telegram.middlewares.rate_limit, telegram.middlewares.setup
  backend.agents.horizontal.planning.agent -> backend.agents.deps.base, backend.agents.mission_control.helpers, backend.core.logging
  backend.agents.horizontal.summarization.agent -> backend.agents.mission_control.helpers, backend.agents.mission_control.registry, backend.core.logging
  backend.agents.horizontal.verification.agent -> backend.agents.deps.base, backend.agents.mission_control.helpers, backend.core.logging
  backend.agents.mission_control.middleware -> backend.agents.config_schema, backend.core.config, backend.core.logging
  backend.agents.mission_control.persistence_bridge -> backend.agents.mission_control.outcome, backend.core.logging, backend.services.mission_persistence
  backend.agents.mission_control.registry -> backend.agents.config_schema, backend.core.config, backend.core.logging
  backend.agents.mission_control.router -> backend.agents.mission_control.models, backend.agents.mission_control.registry, backend.core.logging
  backend.agents.preflight -> backend.agents.mission_control.helpers, backend.agents.mission_control.roster, backend.core.logging
  backend.agents.tools.compliance -> backend.agents.config_schema, backend.agents.deps.base, backend.services.compliance
  backend.api.v1.endpoints.agents -> backend.core.dependencies, backend.core.logging, backend.schemas.base
  backend.core.exception_handlers -> backend.core.exceptions, backend.core.logging, backend.schemas.base
  backend.events.bus -> backend.core.config, backend.core.logging, backend.events.types
  backend.gateway.adapters.telegram -> backend.core.config, backend.core.logging, backend.gateway.adapters
  backend.gateway.registry -> backend.core.config, backend.core.logging, backend.gateway.adapters
  backend.gateway.security.startup_checks -> backend.core.config, backend.core.config_schema, backend.core.logging
  backend.repositories.base -> backend.core.exceptions, backend.core.logging, backend.models.base
  backend.repositories.mission -> backend.core.logging, backend.models.mission, backend.repositories.base
  backend.repositories.mission_record -> backend.core.logging, backend.models.mission_record, backend.repositories.base
  backend.repositories.playbook_run -> backend.core.logging, backend.models.mission, backend.repositories.base
  backend.repositories.session -> backend.core.utils, backend.models.session, backend.repositories.base
  backend.services.code_map -> backend.services.code_map.generator, backend.services.code_map.assembler, backend.services.code_map.loader
  backend.services.history_query -> backend.core.logging, backend.models.mission_record, backend.services.base
  backend.services.playbook -> backend.core.config, backend.core.logging, backend.schemas.playbook
  telegram.handlers -> telegram.handlers.common, telegram.handlers.example, telegram.handlers.setup
  telegram.middlewares.setup -> telegram.middlewares.auth, telegram.middlewares.logging, telegram.middlewares.rate_limit
  telegram.services.notifications -> backend.core.config, backend.core.logging, backend.core.utils
  backend.agents.horizontal.synthesis.agent -> backend.agents.mission_control.helpers, backend.core.logging
  backend.agents.mission_control.approval -> backend.core.config, backend.core.logging
  backend.agents.mission_control.checks.builtin -> backend.agents.mission_control.check_registry, backend.core.logging
  backend.agents.mission_control.cost -> backend.agents.mission_control.middleware, backend.core.logging
  backend.agents.mission_control.escalation -> backend.core.config, backend.core.logging
  backend.agents.mission_control.history -> backend.core.logging, backend.schemas.session
  backend.agents.mission_control.models -> backend.core.protocols, backend.events.types
  backend.agents.mission_control.roster -> backend.core.config, backend.core.logging
  backend.agents.mission_control.verification -> backend.agents.mission_control.models, backend.core.logging
  backend.api.health -> backend.core.logging, backend.core.utils
  backend.core.middleware -> backend.core.logging, backend.core.utils
  backend.events.publishers -> backend.core.logging, backend.events.schemas
  backend.events.types -> backend.core.logging, backend.core.utils
  backend.gateway.security.rate_limiter -> backend.core.config, backend.core.logging
  backend.models.session -> backend.core.utils, backend.models.base
  backend.repositories.note -> backend.models.note, backend.repositories.base
  backend.repositories.project -> backend.models.project, backend.repositories.base
  backend.repositories.project_context -> backend.models.project_context, backend.repositories.base
  backend.repositories.project_history -> backend.models.project_history, backend.repositories.base
  backend.services.base -> backend.core.exceptions, backend.core.logging
  backend.services.context_curator -> backend.core.logging, backend.services.project_context
  backend.tasks.example -> backend.core.logging, backend.core.utils
  backend.tasks.scheduled -> backend.core.logging, backend.core.utils
  backend.temporal.activities -> backend.core.logging, backend.temporal.models
  backend.temporal.client -> backend.core.config, backend.core.logging
  telegram.handlers.common -> backend.core.logging, telegram.keyboards.common
  telegram.handlers.setup -> telegram.handlers.common, telegram.handlers.example
  telegram.middlewares.auth -> backend.core.config, backend.core.logging
  telegram.middlewares.rate_limit -> backend.core.config, backend.core.logging
  telegram.webhook -> backend.core.config, backend.core.logging
  backend.agents.deps -> backend.agents.deps.base
  backend.agents.deps.base -> backend.agents.config_schema
  backend.agents.mission_control -> backend.agents.mission_control.mission_control
  backend.agents.mission_control.check_registry -> backend.core.logging
  backend.agents.mission_control.checks -> backend.agents.mission_control.checks [circular]
  backend.agents.tools.code -> backend.agents.deps.base
  backend.agents.tools.codemap -> backend.agents.deps.base
  backend.agents.tools.filesystem -> backend.agents.deps.base
  backend.agents.tools.system -> backend.agents.deps.base
  backend.api.v1 -> backend.api.v1.endpoints
  backend.cli.agent -> backend.core.logging
  backend.cli.db -> backend.core.logging
  backend.cli.migrate -> backend.core.config
  backend.cli.mission -> backend.core.logging
  backend.cli.playbook -> backend.core.logging
  backend.cli.project -> backend.cli.report
  backend.cli.report -> backend.core.logging
  backend.cli.server -> backend.core.config
  backend.cli.telegram -> backend.core.config
  backend.core.config -> backend.core.config_schema
  backend.core.database -> backend.core.logging
  backend.core.dependencies -> backend.core.database
  backend.core.logging -> backend.core.config
  backend.core.pagination -> backend.schemas.base
  backend.events.broker -> backend.core.logging
  backend.events.middleware -> backend.core.logging
  backend.events.schemas -> backend.core.utils
  backend.gateway.adapters -> backend.gateway.adapters.base
  backend.gateway.adapters.base -> backend.core.utils
  backend.models.base -> backend.core.utils
  backend.models.mission -> backend.models.base
  backend.models.mission_record -> backend.models.base
  backend.models.note -> backend.models.base
  backend.models.project -> backend.models.base
  backend.models.project_context -> backend.models.base
  backend.models.project_history -> backend.models.base
  backend.repositories -> backend.repositories.base
  backend.schemas -> backend.schemas.base
  backend.schemas.base -> backend.core.utils
  backend.services.code_map.assembler -> backend.services.code_map.types
  backend.services.code_map.graph -> backend.services.code_map.types
  backend.services.code_map.loader -> backend.core.logging
  backend.services.code_map.parser -> backend.services.code_map.types
  backend.services.code_map.ranker -> backend.services.code_map.types
  backend.services.compliance -> backend.core.logging
  backend.services.pqi -> backend.services.pqi.scorer
  backend.services.pqi.composite -> backend.services.pqi.types
  backend.services.pqi.tools.bandit -> backend.services.pqi.tools
  backend.services.pqi.tools.radon -> backend.services.pqi.tools
  backend.tasks.broker -> backend.core.logging
  backend.tasks.scheduler -> backend.core.logging
  backend.temporal.workflow -> backend.temporal.models
  telegram -> telegram.bot
  telegram.bot -> backend.core.logging
  telegram.callbacks -> telegram.callbacks.common
  telegram.keyboards -> telegram.keyboards.common
  telegram.keyboards.common -> telegram.callbacks.common
  telegram.middlewares.logging -> backend.core.logging
  telegram.services -> telegram.services.notifications
  telegram.states -> telegram.states.example

## backend.core

modules/backend/core/config.py (253 lines):
│class AppConfig:
│    def __init__() -> None
│    def application() -> ApplicationSchema
│    def database() -> DatabaseSchema
│    def logging() -> LoggingSchema
│    def features() -> FeaturesSchema
│    def security() -> SecuritySchema
│    def gateway() -> GatewaySchema
│    def events() -> EventsSchema
│    def sessions() -> SessionsSchema
│    def missions() -> MissionsSchema
│    def temporal() -> TemporalSchema
│    def playbooks() -> PlaybooksSchema
│    def projects() -> ProjectsSchema
│class Settings(BaseSettings):
│    db_password: str
│    redis_password: str
│    jwt_secret: str
│    api_key_salt: str
│    telegram_bot_token: str
│    telegram_webhook_secret: str
│    anthropic_api_key: str
│def find_project_root() -> Path
│def validate_project_root() -> Path
│def load_yaml_config(filename: str) -> dict[str, Any]
│def _load_validated(schema_cls: type, filename: str) -> Any
│def _load_validated_optional(schema_cls: type, filename: str) -> Any
│@lru_cache
│def get_settings() -> Settings
│@lru_cache
│def get_app_config() -> AppConfig
│def get_database_url(async_driver: bool) -> str
│def get_redis_url() -> str
│def get_server_base_url() -> tuple[str, float]

modules/backend/core/config_schema.py (368 lines):
│class FeaturesSchema(_StrictBase):
│    auth_require_email_verification: bool
│    auth_allow_api_key_creation: bool
│    auth_rate_limit_enabled: bool
│    auth_require_api_authentication: bool
│    api_detailed_errors: bool
│    api_request_logging: bool
│    channel_telegram_enabled: bool
│    channel_slack_enabled: bool
│    channel_discord_enabled: bool
│    channel_whatsapp_enabled: bool
│    gateway_enabled: bool
│    gateway_websocket_enabled: bool
│    gateway_pairing_enabled: bool
│    agent_coordinator_enabled: bool
│    agent_streaming_enabled: bool
│    mcp_enabled: bool
│    a2a_enabled: bool
│    security_startup_checks_enabled: bool
│    security_headers_enabled: bool
│    security_cors_enforce_production: bool
│    experimental_background_tasks_enabled: bool
│    events_publish_enabled: bool
│class SecuritySchema(_StrictBase):
│    jwt: JwtSchema
│    rate_limiting: RateLimitingSchema
│    request_limits: RequestLimitsSchema
│    headers: SecurityHeadersSchema
│    secrets_validation: SecretsValidationSchema
│    roles: dict[str, RoleSchema]
│    user_roles: dict[str, str]
│    cors: CorsEnforcementSchema
│class ApplicationSchema(_StrictBase):
│    name: str
│    version: str
│    description: str
│    environment: str
│    debug: bool
│    api_prefix: str
│    docs_enabled: bool
│    server: ServerSchema
│    cors: CorsSchema
│    pagination: PaginationSchema
│    timeouts: TimeoutsSchema
│    telegram: TelegramAppSchema
│    cli: CliSchema
│class DatabaseSchema(_StrictBase):
│    host: str
│    port: int
│    name: str
│    user: str
│    pool_size: int
│    max_overflow: int
│    pool_timeout: int
│    pool_recycle: int
│    echo: bool
│    echo_pool: bool
│    redis: RedisSchema
│class LoggingSchema(_StrictBase):
│    level: str
│    format: str
│    handlers: HandlersSchema
│class GatewaySchema(_StrictBase):
│    default_policy: str
│    channels: dict[str, GatewayChannelSchema]
│class EventsSchema(_StrictBase):
│    transport: str
│    channel_prefix: str
│    streams: dict[str, EventsStreamSchema]
│    consumer_timeout_ms: int
│    dlq_enabled: bool
│    dlq_prefix: str
│class SessionsSchema(_StrictBase):
│    default_ttl_hours: int
│    max_ttl_hours: int
│    default_cost_budget_usd: float
│    max_cost_budget_usd: float
│    cleanup_interval_minutes: int
│    budget_warning_threshold: float
│class MissionsSchema(_StrictBase):
│    max_thinking_trace_length: int
│    max_task_output_size_bytes: int
│    retention_days: int
│    default_page_size: int
│    max_page_size: int
│    persist_thinking_trace: bool
│    persist_verification_details: bool
│class TemporalSchema(_StrictBase):
│    enabled: bool
│    server_url: str
│    namespace: str
│    task_queue: str
│    workflow_execution_timeout_days: int
│    activity_start_to_close_seconds: int
│    activity_retry_max_attempts: int
│    approval_timeout_seconds: int
│    escalation_timeout_seconds: int
│    notification_timeout_seconds: int
│    budget_timeout_multiplier_seconds: int
│    min_activity_timeout_seconds: int
│    persistence_timeout_seconds: int
│    persistence_retry_max_attempts: int
│    execution_retry_max_attempts: int
│    execution_retry_initial_interval_seconds: int
│    execution_retry_max_interval_seconds: int
│    def _require_server_url_when_enabled() -> 'TemporalSchema'
│class PlaybooksSchema(_StrictBase):
│    playbooks_dir: str
│    max_steps_per_playbook: int
│    max_context_size_bytes: int
│    default_step_timeout_seconds: int
│    default_budget_usd: float
│    max_budget_usd: float
│    max_concurrent_missions: int
│    enable_playbook_matching: bool
│class ProjectsSchema(_StrictBase):
│    default_budget_ceiling_usd: float | None
│    max_projects_per_owner: int
│    pcd_max_size_bytes: int
│    pcd_target_size_bytes: int
│    pcd_prune_threshold_pct: int
│    pcd_alert_threshold_pct: int
│    history_summarize_after_days: int
│    enable_context_assembly: bool
│class RedisSchema(_StrictBase):
│    host: str
│    port: int
│    db: int
│    broker: BrokerSchema
│class HandlersSchema(_StrictBase):
│    console: ConsoleHandlerSchema
│    file: FileHandlerSchema
│class GatewayChannelSchema(_StrictBase):
│    allowlist: list[int]
│class EventsStreamSchema(_StrictBase):
│    maxlen: int
│    consumer_group: str
│class BrokerSchema(_StrictBase):
│    queue_name: str
│    result_expiry_seconds: int
│class ConsoleHandlerSchema(_StrictBase):
│    enabled: bool
│class FileHandlerSchema(_StrictBase):
│    enabled: bool
│    path: str
│    max_bytes: int
│    backup_count: int
│class ApiRateLimitSchema(_StrictBase):
│    requests_per_minute: int
│    requests_per_hour: int
│class ChannelRateLimitSchema(_StrictBase):
│    messages_per_minute: int
│    messages_per_hour: int
│class ServerSchema(_StrictBase):
│    host: str
│    port: int
│class CorsSchema(_StrictBase):
│    origins: list[str]
│class PaginationSchema(_StrictBase):
│    default_limit: int
│    max_limit: int
│class TimeoutsSchema(_StrictBase):
│    database: int
│    external_api: int
│    background: int
│class TelegramAppSchema(_StrictBase):
│    webhook_path: str
│    authorized_users: list[int]
│    max_message_length: int
│class CliSchema(_StrictBase):
│    console_width: int
│class JwtSchema(_StrictBase):
│    algorithm: str
│    access_token_expire_minutes: int
│    refresh_token_expire_days: int
│    audience: str
│class RateLimitingSchema(_StrictBase):
│    api: ApiRateLimitSchema
│    telegram: ChannelRateLimitSchema
│    websocket: ChannelRateLimitSchema
│class RequestLimitsSchema(_StrictBase):
│    max_body_size_bytes: int
│    max_header_size_bytes: int
│class SecurityHeadersSchema(_StrictBase):
│    x_content_type_options: str
│    x_frame_options: str
│    referrer_policy: str
│    hsts_enabled: bool
│    hsts_max_age: int
│class SecretsValidationSchema(_StrictBase):
│    jwt_secret_min_length: int
│    api_key_salt_min_length: int
│    webhook_secret_min_length: int
│class CorsEnforcementSchema(_StrictBase):
│    enforce_in_production: bool
│    allow_methods: list[str]
│    allow_headers: list[str]
│class RoleSchema(_StrictBase):
│    level: int
│    description: str
│class _StrictBase(BaseModel):

modules/backend/core/logging.py (263 lines):
│def _load_logging_config() -> dict[str, Any]
│def _get_logging_config() -> dict[str, Any]
│def _resolve_log_path(configured_path: str) -> Path
│def setup_logging(level: str | None, format_type: str | None, enable_console: bool | None, ...) -> None
│def get_logger(name: str) -> Any
│def log_with_source(logger: Any, source: str, level: str, ...) -> None
│def bind_context() -> None
│def clear_context() -> None

modules/backend/core/utils.py (37 lines):
│def estimate_tokens(data: Any) -> int
│def utc_now() -> datetime

modules/backend/core/exceptions.py (85 lines):
│class ApplicationError(Exception):
│    def __init__(message: str, code: str) -> None
│class NotFoundError(ApplicationError):
│    def __init__(message: str) -> None
│class ValidationError(ApplicationError):
│    def __init__(message: str, details: dict | None) -> None
│class AuthenticationError(ApplicationError):
│    def __init__(message: str) -> None
│class AuthorizationError(ApplicationError):
│    def __init__(message: str) -> None
│class ConflictError(ApplicationError):
│    def __init__(message: str) -> None
│class ExternalServiceError(ApplicationError):
│    def __init__(message: str) -> None
│class RateLimitError(ApplicationError):
│    def __init__(message: str) -> None
│class BudgetExceededError(ApplicationError):
│    def __init__(message: str, current_cost: float, budget: float) -> None
│class DatabaseError(ApplicationError):
│    def __init__(message: str) -> None

modules/backend/core/database.py (113 lines):
│def _create_engine() -> Any
│def get_engine() -> Any
│def get_session_factory() -> async_sessionmaker[AsyncSession]
│@asynccontextmanager
│def get_async_session() -> AsyncGenerator[AsyncSession, None]
│def get_db_session() -> AsyncGenerator[AsyncSession, None]

modules/backend/core/protocols.py (63 lines):
│class SessionServiceProtocol(Protocol):
│    def get_session(session_id: str) -> Any
│    def enforce_budget(session_id: str, estimated_cost: float) -> None
│    def get_messages(session_id: str, limit: int, offset: int) -> tuple[list, int]
│    def update_cost(session_id: str, input_tokens: int, output_tokens: int, cost_usd: float) -> None
│    def touch_activity(session_id: str) -> None
│    def add_message(session_id: str, data: Any) -> None
│class MissionDispatchProtocol(Protocol):
│    def execute(mission_brief: str, roster_ref: str, complexity_tier: str, upstream_context: dict | None, cost_ceiling_usd: float | None, session_id: str | None, project_id: str | None) -> dict

modules/backend/core/dependencies.py (38 lines):
│def get_request_id(x_request_id: str | None) -> str
│def get_event_bus()

modules/backend/core/pagination.py (266 lines):
│class PaginationParams:
│    limit: int
│    offset: int
│    cursor: str | None
│    def is_cursor_based() -> bool
│class PagedResult:
│    items: list[T]
│    total: int | None
│    limit: int
│    offset: int
│    has_more: bool
│    next_cursor: str | None
│def get_pagination_params(limit: int | None, offset: int, cursor: str | None) -> PaginationParams
│def encode_cursor(value: str | int) -> str
│def decode_cursor(cursor: str) -> str
│def create_paginated_response(items: list[Any], item_schema: type[BaseModel], total: int | None, ...) -> dict[str, Any]
│def paginate_query(query_func, params: PaginationParams, count_func) -> PagedResult

modules/backend/core/exception_handlers.py (253 lines):
│def _get_request_id(request: Request) -> str | None
│def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse
│def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse
│def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse
│def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse
│def register_exception_handlers(app: FastAPI) -> None

modules/backend/core/middleware.py (121 lines):
│class RequestContextMiddleware(BaseHTTPMiddleware):
│    def dispatch(request: Request, call_next: RequestResponseEndpoint) -> Response

modules/backend/__init__.py (1 lines):

modules/backend/core/__init__.py (1 lines):

modules/backend/core/security.py (131 lines):
│def hash_password(password: str) -> str
│def verify_password(plain_password: str, hashed_password: str) -> bool
│def create_access_token(data: dict[str, Any], expires_delta: timedelta | None) -> str
│def create_refresh_token(data: dict[str, Any]) -> str
│def decode_token(token: str) -> dict[str, Any]
│def generate_api_key() -> tuple[str, str]
│def verify_api_key(plain_key: str, hashed_key: str) -> bool

modules/backend/main.py (128 lines):
│@asynccontextmanager
│def lifespan(app: FastAPI) -> AsyncGenerator[None, None]
│def create_app() -> FastAPI
│def _mount_channel_adapters(app: FastAPI, app_config) -> None
│def get_app() -> FastAPI
│def __getattr__(name: str) -> FastAPI


## backend.agents

modules/backend/agents/config_schema.py (223 lines):
│class _StrictBase(BaseModel):
│class AgentConfigSchema(_StrictBase):
│    agent_name: str
│    agent_type: str
│    description: str
│    enabled: bool
│    model: str | AgentModelSchema
│    keywords: list[str]
│    tools: list[str]
│    max_input_length: int
│    max_budget_usd: float
│    execution: ExecutionSchema
│    scope: FileScopeConfigSchema
│    interface: AgentInterfaceSchema | None
│    version: str
│    max_tokens: int | None
│    max_requests: int | None
│    file_size_limit: int | None
│    rules: list[ComplianceRuleSchema] | None
│    exclusions: ExclusionsSchema | None
│    thinking_budget: dict[str, int] | None
│    def _normalize_model(v: str | dict) -> str | dict
│class FileScopeConfigSchema(_StrictBase):
│    read: list[str]
│    write: list[str]
│class ExecutionSchema(_StrictBase):
│    mode: str
│class ComplianceRuleSchema(_StrictBase):
│    id: str
│    description: str
│    severity: str
│    enabled: bool
│class ExclusionsSchema(_StrictBase):
│    paths: list[str]
│    patterns: list[str]
│class AgentInterfaceSchema(_StrictBase):
│    input: dict[str, str]
│    output: dict[str, str]
│class MissionControlConfigSchema(_StrictBase):
│    model_pricing: dict[str, ModelPricingRateSchema]
│    routing: RoutingSchema
│    limits: MissionControlLimitsSchema
│    guardrails: GuardrailsSchema
│    redis_ttl: RedisTtlSchema
│    approval: ApprovalSchema
│    dispatch: DispatchSchema
│    escalation: EscalationThresholdsSchema
│class ModelPricingRateSchema(_StrictBase):
│    input: float
│    output: float
│class RoutingSchema(_StrictBase):
│    strategy: str
│    llm_model: str
│    complex_request_agent: str
│    fallback_agent: str
│    max_routing_depth: int
│class MissionControlLimitsSchema(_StrictBase):
│    max_requests_per_task: int
│    max_tool_calls_per_task: int
│    max_tokens_per_task: int
│    max_cost_per_plan: float
│    max_cost_per_user_daily: float
│    task_timeout_seconds: int
│    plan_timeout_seconds: int
│class GuardrailsSchema(_StrictBase):
│    max_input_length: int
│    injection_patterns: list[str]
│class RedisTtlSchema(_StrictBase):
│    session: int
│    approval: int
│    lock: int
│    result: int
│class ApprovalSchema(_StrictBase):
│    poll_interval_seconds: int
│    timeout_seconds: int
│class DispatchSchema(_StrictBase):
│    default_request_limit: int
│    token_cost_factor: int
│class EscalationThresholdsSchema(_StrictBase):
│    max_auto_approve_cost_usd: float
│    max_medium_approve_cost_usd: float
│    max_auto_approve_retries: int
│class AgentModelSchema(_StrictBase):
│    name: str
│    temperature: float
│    max_tokens: int

modules/backend/agents/deps/base.py (89 lines):
│class FileScope:
│    read_paths: list[str]
│    write_paths: list[str]
│    def check_read(rel_path: str) -> None
│    def check_write(rel_path: str) -> None
│    def is_readable(rel_path: str) -> bool
│    def _matches(rel_path: str, allowed: list[str]) -> bool
│class BaseAgentDeps:
│    project_root: Path
│    scope: FileScope
│    config: AgentConfigSchema | None
│    session_id: str | None
│    on_event: Any
│class QaAgentDeps(BaseAgentDeps):
│    on_progress: Any
│    def emit(event: dict) -> None
│class HealthAgentDeps(BaseAgentDeps):
│    app_config: Any
│class HorizontalAgentDeps(BaseAgentDeps):
│    allowed_agents: set[str]
│    max_delegation_depth: int
│    mission_control: Any

modules/backend/agents/mission_control/helpers.py (425 lines):
│def _build_model(config_model: str | AgentModelSchema) -> Model
│def assemble_instructions(category: str, name: str) -> str
│def _get_model_name(config_model: str | AgentModelSchema) -> str
│def build_deps_from_config(agent_config: AgentConfigSchema) -> dict[str, Any]
│def _build_agent_deps(agent_name: str, agent_config: AgentConfigSchema, session_id: str | None) -> BaseAgentDeps
│def _get_usage_limits(agent_name: str | None) -> UsageLimits
│def _import_agent_module(agent_name: str) -> Any
│def _resolve_agent(session: 'SessionResponse', message: str) -> str
│def _publish(event_bus: EventBusProtocol, event: SessionEvent) -> None
│def _persist_messages(session_service: SessionServiceProtocol, session_id: str, creates: list[SessionMessageCreate]) -> None
│def _build_roster_prompt(roster: Roster) -> str
│def _build_planning_prompt(mission_brief: str, mission_id: str, roster_description: str, ...) -> str
│def _append_validation_feedback(prompt: str, errors: list[str]) -> str
│def _make_agent_executor(session_service: SessionServiceProtocol, event_bus: EventBusProtocol) -> ExecuteAgentFn
│def _call_planning_agent(prompt: str, roster: Roster, upstream_context: dict | None) -> dict

modules/backend/agents/mission_control/models.py (149 lines):
│class ExecuteAgentFn(Protocol):
│    def __call__(agent_name: str, instructions: str, inputs: dict, usage_limits: UsageLimits) -> Awaitable[dict]
│class EventBusProtocol(Protocol):
│    def publish(event: SessionEvent) -> None
│class MissionControlRequest:
│    user_input: str
│    agent: str | None
│    conversation_id: str | None
│    channel: str
│    session_type: str
│    tool_access_level: str
│class CollectResult(TypedDict):
│    agent_name: str
│    output: str
│    cost_usd: float
│    session_id: str
│    thinking: str | None
│class MissionControlResponse:
│    agent_name: str
│    output: str
│    metadata: dict[str, Any]
│class NoOpEventBus:
│    def publish(event: SessionEvent) -> None
│class ContextCuratorProtocol(Protocol):
│    def get_project_context(project_id: str) -> dict
│    def apply_task_updates(project_id: str, task_result_context_updates: list[dict]) -> tuple[int, list[str]]
│class ContextAssemblerProtocol(Protocol):
│    def build(project_id: str, task_definition: dict, resolved_inputs: dict) -> dict

modules/backend/agents/mission_control/mission_control.py (517 lines):
│def list_agents() -> list[dict[str, Any]]
│def handle(session_id: str, message: str) -> AsyncIterator[SessionEvent]
│def collect(session_id: str, message: str) -> CollectResult
│def handle_mission(mission_id: str, mission_brief: str) -> MissionOutcome

modules/backend/agents/mission_control/middleware.py (74 lines):
│@lru_cache
│def _load_mission_control_config() -> MissionControlConfigSchema
│def check_guardrails(user_input: str, agent_config: AgentConfigSchema | None) -> None
│def with_guardrails(agent_config: AgentConfigSchema | None)

modules/backend/agents/mission_control/registry.py (169 lines):
│class AgentRegistry:
│    def __init__() -> None
│    def _ensure_loaded() -> None
│    def get(agent_name: str) -> AgentConfigSchema
│    def has(agent_name: str) -> bool
│    def list_all() -> list[dict[str, Any]]
│    def get_by_keyword(text: str) -> str | None
│    def resolve_module_path(agent_name: str) -> str
│    def get_instance(agent_name: str, model: Any) -> Any
│    def reset() -> None
│@lru_cache
│def get_registry() -> AgentRegistry

modules/backend/agents/mission_control/roster.py (135 lines):
│class RosterAgentEntry(BaseModel):
│    agent_name: str
│    agent_version: str
│    description: str
│    model: RosterModelSchema
│    tools: list[str]
│    interface: RosterInterfaceSchema
│    constraints: RosterConstraintsSchema
│class Roster(BaseModel):
│    agents: list[RosterAgentEntry]
│    def get_agent(name: str, version: str) -> RosterAgentEntry | None
│    def get_agent_by_name(name: str) -> RosterAgentEntry | None
│    def agent_names() -> list[str]
│class RosterModelSchema(BaseModel):
│    name: str
│    temperature: float
│    max_tokens: int
│class RosterInterfaceSchema(BaseModel):
│    input: dict[str, str]
│    output: dict[str, str]
│class RosterConstraintsSchema(BaseModel):
│    timeout_seconds: int
│    cost_ceiling_usd: float
│    retry_budget: int
│    parallelism: str
│def load_roster(roster_name: str) -> Roster

modules/backend/agents/mission_control/check_registry.py (85 lines):
│class CheckResult:
│    passed: bool
│    details: str
│    execution_time_ms: float
│def register_check(name: str) -> Callable[[CheckFn], CheckFn]
│def get_check(name: str) -> CheckFn | None
│def check_exists(name: str) -> bool
│def list_checks() -> list[str]
│def get_registry_snapshot() -> dict[str, CheckFn]

modules/backend/agents/mission_control/outcome.py (200 lines):
│class MissionOutcome(BaseModel):
│    mission_id: str
│    status: MissionStatus
│    task_results: list[TaskResult]
│    total_cost_usd: float
│    total_duration_seconds: float
│    total_tokens: TaskTokenUsage
│    planning_trace_reference: str | None
│    task_plan_reference: str | None
│class TaskTokenUsage(BaseModel):
│    input: int
│    output: int
│    thinking: int
│class TaskResult(BaseModel):
│    task_id: str
│    agent_name: str
│    status: TaskStatus
│    output_reference: dict
│    token_usage: TaskTokenUsage
│    cost_usd: float
│    duration_seconds: float
│    verification_outcome: VerificationOutcome
│    retry_count: int
│    retry_history: list[RetryHistoryEntry]
│    execution_id: str
│    context_updates: list[dict]
│class FailedCheck(BaseModel):
│    check: str
│    reason: str
│class VerificationOutcome(BaseModel):
│    tier_1: Tier1Outcome
│    tier_2: Tier2Outcome
│    tier_3: Tier3Outcome
│class MissionStatus(StrEnum):
│class RetryHistoryEntry(BaseModel):
│    attempt: int
│    failure_tier: int
│    failure_reason: str
│    feedback_provided: str
│class Tier1Outcome(BaseModel):
│    status: str
│    details: str
│class Tier2Outcome(BaseModel):
│    status: str
│    checks_run: int
│    checks_passed: int
│    failed_checks: list[FailedCheck]
│class Tier3Outcome(BaseModel):
│    status: str
│    overall_score: float
│    criteria_results_reference: str
│    evaluator_thinking_trace_reference: str
│    cost_usd: float
│class TaskStatus(StrEnum):
│def build_verification_outcome(result: VerificationResult) -> VerificationOutcome

modules/backend/agents/schemas.py (73 lines):
│class Violation(BaseModel):
│    rule_id: str
│    file: str
│    line: int | None
│    message: str
│    severity: str
│    recommendation: str | None
│class ArchitectureFinding(BaseModel):
│    principle: str
│    file: str
│    line: int | None
│    message: str
│    recommendation: str
│    related_files: list[str]
│class HealthFinding(BaseModel):
│    category: str
│    severity: str
│    message: str
│    details: str | None
│class QaAuditResult(BaseModel):
│    summary: str
│    total_violations: int
│    error_count: int
│    warning_count: int
│    violations: list[Violation]
│    scanned_files_count: int
│class ArchitectureReviewResult(BaseModel):
│    summary: str
│    total_findings: int
│    findings: list[ArchitectureFinding]
│    files_reviewed: int
│    new_findings: int
│    baseline_findings: int
│class HealthCheckResult(BaseModel):
│    summary: str
│    overall_status: str
│    findings: list[HealthFinding]
│    error_count: int
│    warning_count: int
│    checks_performed: list[str]

modules/backend/agents/tools/__init__.py (1 lines):

modules/backend/agents/mission_control/cost.py (37 lines):
│def compute_cost_usd(input_tokens: int, output_tokens: int, model: str | None) -> float
│def estimate_cost(estimated_input_tokens: int, model: str | None) -> float

modules/backend/agents/mission_control/router.py (40 lines):
│class RuleBasedRouter:
│    def __init__(registry: AgentRegistry) -> None
│    def route(request: MissionControlRequest) -> str | None

modules/backend/agents/mission_control/checks/__init__.py (7 lines):

modules/backend/agents/mission_control/verification.py (525 lines):
│class TierStatus(str, Enum):
│class TierResult:
│    tier: int
│    status: TierStatus
│    details: str
│    execution_time_ms: float
│    check_results: list[dict[str, Any]]
│class VerificationResult:
│    passed: bool
│    tier_1: TierResult | None
│    tier_2: TierResult | None
│    tier_3: TierResult | Tier3Result | None
│    failed_tier: int | None
│    total_execution_time_ms: float
│class Tier3Result(TierResult):
│    overall_score: float
│    criteria_results_reference: str
│    evaluator_thinking_trace_reference: str
│    cost_usd: float
│def run_verification_pipeline(output: dict[str, Any], task: dict[str, Any], agent_interface: dict[str, Any] | None, ...) -> VerificationResult
│def _run_tier_1(output: dict[str, Any], verification_config: dict[str, Any], agent_interface: dict[str, Any] | None) -> TierResult
│def _run_tier_2(output: dict[str, Any], verification_config: dict[str, Any]) -> TierResult
│def _run_tier_3(output: dict[str, Any], task: dict[str, Any], verification_config: dict[str, Any], ...) -> TierResult | Tier3Result
│def build_retry_feedback(verification_result: VerificationResult, attempt: int) -> dict[str, Any]
│def _elapsed_ms(start: float) -> float

modules/backend/agents/mission_control/dispatch.py (547 lines):
│def topological_sort(plan: TaskPlan) -> list[list[str]]
│def resolve_upstream_inputs(task: TaskDefinition, completed_outputs: dict[str, dict]) -> dict[str, Any]
│def verify_task(task: TaskDefinition, output: dict, roster_entry: RosterAgentEntry, ...) -> VerificationResult
│def execute_task(task: TaskDefinition, roster_entry: RosterAgentEntry, resolved_inputs: dict[str, Any], ...) -> dict
│def dispatch(plan: TaskPlan, roster: Roster, execute_agent_fn: ExecuteAgentFn, ...) -> MissionOutcome
│def _execute_with_retry(task: TaskDefinition, roster_entry: RosterAgentEntry, resolved_inputs: dict[str, Any], ...) -> TaskResult
│def _append_feedback(original_instructions: str, feedback: str) -> str
│def _failed_result(task: TaskDefinition, reason: str, retry_count: int, ...) -> TaskResult

modules/backend/agents/mission_control/history.py (169 lines):
│def session_messages_to_model_history(messages: list) -> list[ModelMessage]
│def model_messages_to_session_creates(messages: list[ModelMessage], session_id: str, agent_id: str | None, ...) -> list[SessionMessageCreate]

modules/backend/agents/mission_control/persistence_bridge.py (129 lines):
│def persist_mission_results(outcome: MissionOutcome) -> None

modules/backend/agents/mission_control/plan_validator.py (286 lines):
│class ValidationResult:
│    def __init__() -> None
│    def is_valid() -> bool
│    def add_error(rule: str, message: str) -> None
│    def __repr__() -> str
│def validate_plan(plan: TaskPlan, roster: Roster, mission_budget_usd: float) -> ValidationResult
│def _rule_2_agent_validation(plan: TaskPlan, roster: Roster, result: ValidationResult) -> None
│def _rule_3_dag_validation(plan: TaskPlan, result: ValidationResult) -> None
│def _rule_4_dependency_consistency(plan: TaskPlan, result: ValidationResult) -> None
│def _rule_5_input_compatibility(plan: TaskPlan, roster: Roster, result: ValidationResult) -> None
│def _rule_6_check_registry(plan: TaskPlan, result: ValidationResult) -> None
│def _rule_7_budget_validation(plan: TaskPlan, mission_budget_usd: float, result: ValidationResult) -> None
│def _rule_8_timeout_validation(plan: TaskPlan, roster: Roster, result: ValidationResult) -> None
│def _rule_9_critical_path_validation(plan: TaskPlan, result: ValidationResult) -> None
│def _rule_10_tier3_completeness(plan: TaskPlan, roster: Roster, result: ValidationResult) -> None
│def _rule_11_self_evaluation_prevention(plan: TaskPlan, result: ValidationResult) -> None

modules/backend/agents/__init__.py (1 lines):

modules/backend/agents/deps/__init__.py (17 lines):

modules/backend/agents/horizontal/__init__.py (1 lines):

modules/backend/agents/horizontal/planning/__init__.py (1 lines):

modules/backend/agents/horizontal/planning/agent.py (108 lines):
│class PlanningAgentDeps(BaseAgentDeps):
│    mission_brief: str
│    roster_description: str
│    upstream_context: dict[str, Any] | None
│    code_map: dict | None
│def create_agent(config: dict) -> Agent
│def run_agent(agent: Agent, deps: PlanningAgentDeps, user_prompt: str) -> dict
│def extract_task_plan_json(text: str) -> dict

modules/backend/agents/horizontal/summarization/__init__.py (0 lines):

modules/backend/agents/horizontal/summarization/agent.py (109 lines):
│class SummarizationOutput(BaseModel):
│    title: str
│    summary: str
│    key_outcomes: list[str]
│    domain_tags: list[str]
│@lru_cache
│def _get_agent() -> Agent[None, SummarizationOutput]
│def get_agent(model: Model | None) -> Agent[None, SummarizationOutput]
│def summarize_missions(mission_outcomes: list[dict]) -> dict[str, Any]

modules/backend/agents/horizontal/synthesis/__init__.py (0 lines):

modules/backend/agents/horizontal/synthesis/agent.py (65 lines):
│@lru_cache
│def _get_agent() -> Agent[None, str]
│def synthesize(outcome_data: dict[str, Any]) -> str

modules/backend/agents/horizontal/verification/__init__.py (1 lines):

modules/backend/agents/horizontal/verification/agent.py (105 lines):
│class CriterionResult(BaseModel):
│    criterion: str
│    score: float
│    passed: bool
│    evidence: str
│    issues: list[str]
│class VerificationEvaluation(BaseModel):
│    overall_score: float
│    passed: bool
│    criteria_results: list[CriterionResult]
│    blocking_issues: list[str]
│    recommendations: list[str]
│def create_agent(model: str | Model) -> Agent[BaseAgentDeps, VerificationEvaluation]
│def run_agent(user_message: str, deps: BaseAgentDeps, agent: Agent[BaseAgentDeps, VerificationEvaluation], ...) -> VerificationEvaluation

modules/backend/agents/mission_control/__init__.py (10 lines):

modules/backend/agents/mission_control/approval.py (54 lines):
│def request_approval(mission_id: str, task_id: str, action: str, ...) -> dict

modules/backend/agents/mission_control/checks/builtin.py (226 lines):
│@register_check
│def validate_json_schema(output: dict[str, Any], params: dict[str, Any]) -> CheckResult
│@register_check
│def validate_field_exists(output: dict[str, Any], params: dict[str, Any]) -> CheckResult
│@register_check
│def validate_field_type(output: dict[str, Any], params: dict[str, Any]) -> CheckResult
│@register_check
│def validate_field_range(output: dict[str, Any], params: dict[str, Any]) -> CheckResult
│def _elapsed_ms(start: float) -> float

modules/backend/agents/mission_control/dispatch_adapter.py (91 lines):
│class MissionControlDispatchAdapter:
│    def __init__(session_service: SessionServiceProtocol, db_session: AsyncSession, event_bus: EventBusProtocol) -> None
│    def execute(mission_brief: str, roster_ref: str, complexity_tier: str, upstream_context: dict | None, cost_ceiling_usd: float | None, session_id: str | None, project_id: str | None) -> dict

modules/backend/agents/mission_control/escalation.py (231 lines):
│class EscalationLevel:
│    level: int
│    responder_type: str
│    timeout_seconds: int
│    description: str
│class RiskThresholds:
│    max_auto_approve_cost_usd: float
│    max_medium_approve_cost_usd: float
│    max_auto_approve_retries: int
│    allowed_retry_actions: frozenset[str]
│def _build_escalation_chain() -> list[EscalationLevel]
│def get_escalation_chain() -> list[EscalationLevel]
│def get_escalation_level(current_level: int) -> EscalationLevel | None
│def get_next_escalation(current_level: int) -> EscalationLevel | None
│def _get_thresholds() -> RiskThresholds
│def evaluate_automated_rules(action: str, context: dict) -> dict | None
│def evaluate_risk_matrix(action: str, context: dict) -> dict | None

modules/backend/agents/preflight.py (102 lines):
│class ModelCheckResult:
│    model_name: str
│    ok: bool
│    elapsed_ms: float
│    error: str | None
│    error_type: str | None
│class PreflightResult:
│    ok: bool
│    checks: list[ModelCheckResult]
│    def failed() -> list[ModelCheckResult]
│def _ping_model(model_name: str) -> ModelCheckResult
│def preflight_check(roster_name: str, models: list[str] | None) -> PreflightResult

modules/backend/agents/tools/code.py (77 lines):
│def apply_fix(project_root: Path, file_path: str, old_text: str, ...) -> dict
│def run_tests(project_root: Path) -> dict

modules/backend/agents/tools/codemap.py (145 lines):
│def generate_code_map(project_root: Path, scope: FileScope) -> dict
│def load_code_map(project_root: Path, scope: FileScope) -> dict
│def get_dependency_analysis(project_root: Path, scope: FileScope) -> dict
│def run_quality_score(project_root: Path, scope: FileScope) -> dict

modules/backend/agents/tools/compliance.py (98 lines):
│def _get_scanner(project_root: Path, config: AgentConfigSchema) -> ComplianceScannerService
│def scan_imports(project_root: Path, scope: FileScope, config: AgentConfigSchema) -> list[dict]
│def scan_datetime(project_root: Path, scope: FileScope, config: AgentConfigSchema) -> list[dict]
│def scan_hardcoded(project_root: Path, scope: FileScope, config: AgentConfigSchema) -> list[dict]
│def scan_file_sizes(project_root: Path, scope: FileScope, config: AgentConfigSchema) -> list[dict]
│def scan_cli_options(project_root: Path, scope: FileScope, config: AgentConfigSchema) -> list[dict]
│def scan_config_files(project_root: Path, scope: FileScope, config: AgentConfigSchema) -> list[dict]
│def load_project_standards(project_root: Path, scope: FileScope) -> dict

modules/backend/agents/tools/filesystem.py (66 lines):
│def read_file(project_root: Path, file_path: str, scope: FileScope) -> str
│def list_files(project_root: Path, scope: FileScope, exclusion_paths: set[str] | None) -> list[str]

modules/backend/agents/tools/system.py (367 lines):
│def check_system_health() -> dict
│def get_app_info(app_config: Any) -> dict
│def scan_log_errors(project_root: Path, scope: FileScope, max_lines: int) -> dict
│def validate_config_files(project_root: Path, scope: FileScope) -> dict
│def check_dependencies(project_root: Path, scope: FileScope) -> dict
│def check_file_structure(project_root: Path, scope: FileScope) -> dict

modules/backend/agents/vertical/__init__.py (1 lines):

modules/backend/agents/vertical/code/__init__.py (1 lines):

modules/backend/agents/vertical/code/architecture/__init__.py (1 lines):

modules/backend/agents/vertical/code/architecture/agent.py (154 lines):
│def create_agent(model: str | Model) -> Agent[QaAgentDeps, ArchitectureReviewResult]
│def run_agent(user_message: str, deps: QaAgentDeps, agent: Agent[QaAgentDeps, ArchitectureReviewResult], ...) -> ArchitectureReviewResult
│def run_agent_stream(user_message: str, deps: QaAgentDeps, agent: Agent[QaAgentDeps, ArchitectureReviewResult], ...) -> AsyncGenerator[dict, None]

modules/backend/agents/vertical/code/quality/__init__.py (1 lines):

modules/backend/agents/vertical/code/quality/agent.py (233 lines):
│def create_agent(model: str | Model) -> Agent[QaAgentDeps, QaAuditResult]
│def run_agent(user_message: str, deps: QaAgentDeps, agent: Agent[QaAgentDeps, QaAuditResult], ...) -> QaAuditResult
│def run_agent_stream(user_message: str, deps: QaAgentDeps, agent: Agent[QaAgentDeps, QaAuditResult], ...) -> AsyncGenerator[dict, None]

modules/backend/agents/vertical/system/__init__.py (1 lines):

modules/backend/agents/vertical/system/health/__init__.py (1 lines):

modules/backend/agents/vertical/system/health/agent.py (128 lines):
│def create_agent(model: str | Model) -> Agent[HealthAgentDeps, HealthCheckResult]
│def run_agent(user_message: str, deps: HealthAgentDeps, agent: Agent[HealthAgentDeps, HealthCheckResult], ...) -> HealthCheckResult
│def run_agent_stream(user_message: str, deps: HealthAgentDeps, agent: Agent[HealthAgentDeps, HealthCheckResult], ...) -> AsyncGenerator[dict, None]


## backend.services

modules/backend/services/code_map/types.py (78 lines):
│class SymbolInfo:
│    name: str
│    kind: SymbolKind
│    qualified_name: str
│    line: int
│    params: list[str]
│    return_type: str
│    bases: list[str]
│    fields: list[str]
│    methods: list[SymbolInfo]
│    decorators: list[str]
│    end_line: int
│class SymbolKind(str, Enum):
│class ModuleInfo:
│    path: str
│    lines: int
│    imports: list[str]
│    classes: list[SymbolInfo]
│    functions: list[SymbolInfo]
│    constants: list[str]
│    references: list[str]
│class ReferenceKind(str, Enum):
│class ReferenceEdge:
│    source: str
│    target: str
│    kind: ReferenceKind
│class ReferenceGraph:
│    nodes: list[str]
│    edges: list[ReferenceEdge]

modules/backend/services/pqi/tools/__init__.py (76 lines):
│class Finding:
│    rule_id: str
│    severity: str
│    confidence: str
│    message: str
│    file: str
│    line: int
│    tool: str
│class ToolResult:
│    tool: str
│    available: bool
│    findings: list[Finding]
│    metrics: dict[str, float]
│    raw_output: str
│    error: str
│    def success() -> bool
│def check_installed(command: str) -> bool
│def run_command(args: list[str], cwd: Path, timeout: int) -> tuple[str, str, int]

modules/backend/services/base.py (214 lines):
│class BaseService:
│    def __init__(session: AsyncSession) -> None
│    def session() -> AsyncSession
│    def _execute_db_operation(operation: str, coro: Any) -> T
│    def _validate_required(fields: dict[str, Any], field_names: list[str]) -> None
│    def _validate_string_length(value: str, field_name: str, min_length: int | None, max_length: int | None) -> None
│    def _log_operation(operation: str) -> None
│    def _log_debug(message: str) -> None

modules/backend/services/pqi/types.py (96 lines):
│class DimensionScore:
│    name: str
│    score: float
│    sub_scores: dict[str, float]
│    confidence: float
│    recommendations: list[str]
│class QualityBand(str, Enum):
│class PQIResult:
│    composite: float
│    dimensions: dict[str, DimensionScore]
│    quality_band: QualityBand
│    floor_penalty: float
│    file_count: int
│    line_count: int
│def classify_band(score: float) -> QualityBand

modules/backend/services/project_context.py (365 lines):
│class ProjectContextManager(BaseService):
│    def __init__(session: AsyncSession) -> None
│    def factory() -> AsyncGenerator['ProjectContextManager', None]
│    def _build_seed_pcd(project_name: str, description: str) -> dict
│    def create_context(project_id: str, project_name: str, description: str) -> ProjectContext
│    def get_context(project_id: str) -> dict
│    def get_context_with_version(project_id: str) -> tuple[dict, int]
│    def get_context_size(project_id: str) -> dict
│    def apply_updates(project_id: str, updates: list[dict]) -> tuple[int, list[str]]
│    def get_history(project_id: str, limit: int) -> list[ContextChange]
│def _get_nested(data: dict, path: str) -> Any
│def _set_nested(data: dict, path: str, value: Any) -> None
│def _delete_nested(data: dict, path: str) -> Any

modules/backend/services/pqi/scorer.py (116 lines):
│def score_project(repo_root: Path, scope: list[str] | None, exclude: list[str] | None, ...) -> PQIResult
│def _run_tools(repo_root: Path, scope: list[str] | None, exclude: list[str] | None, ...) -> dict[str, ToolResult]

modules/backend/services/pqi/ast_analysis.py (296 lines):
│class FileAnalysis:
│    path: str
│    lines: int
│    functions: int
│    classes: int
│    methods: int
│    documented_callables: int
│    total_callables: int
│    annotated_params: int
│    total_params: int
│    annotated_returns: int
│    total_returns: int
│    exception_handlers: int
│    bare_excepts: int
│    broad_excepts: int
│    max_nesting: int
│    function_lengths: list[int]
│    naming_violations: int
│    unsafe_calls: list[str]
│    public_definitions: int
│    private_definitions: int
│class ProjectAnalysis:
│    files: list[FileAnalysis]
│    test_files: int
│    test_lines: int
│    source_files: int
│    source_lines: int
│def analyze_file(file_path: Path, rel_path: str) -> FileAnalysis | None
│def analyze_project(repo_root: Path, scope: list[str] | None, exclude: list[str] | None) -> ProjectAnalysis
│def _analyze_callable(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, analysis: FileAnalysis, is_class: bool) -> None
│def _analyze_except_handler(node: ast.ExceptHandler, analysis: FileAnalysis) -> None
│def _compute_max_nesting(tree: ast.Module) -> int
│def _detect_unsafe_patterns(tree: ast.Module) -> list[str]
│def _count_naming_violations(tree: ast.Module) -> int

modules/backend/services/code_map/assembler.py (510 lines):
│def assemble_code_map(modules: list[ModuleInfo], ranks: dict[str, float], repo_root_name: str, ...) -> dict
│def trim_by_rank(code_map: dict, max_tokens: int) -> dict
│def render_markdown_tree(code_map: dict) -> str
│def _render_module(lines: list[str], path: str, mod: dict) -> None
│def _get_layer(path: str) -> str
│def find_circular_deps(import_graph: dict[str, list[str]]) -> list[list[str]]
│def _shorten_module(qname: str) -> str
│def render_for_agent(code_map: dict, max_tokens: int) -> str
│def _estimate_tokens(data: dict | str) -> int
│def _collect_ranked_symbols(code_map: dict) -> list[tuple[str, float, str, str, str | None]]
│def _remove_symbol(code_map: dict, path: str, kind: str, ...) -> None
│def _method_name(sig: str) -> str
│def _is_internal_import(imp: str, internal_modules: set[str]) -> bool
│def _path_to_qname(rel_path: str) -> str

modules/backend/services/mission_persistence.py (380 lines):
│class MissionPersistenceService(BaseService):
│    def __init__(session: AsyncSession) -> None
│    def save_mission(session_id: str, status: str) -> MissionRecord
│    def save_task_execution(mission_record_id: str, task_id: str, agent_name: str, status: str) -> TaskExecution
│    def save_attempt(task_execution_id: str, attempt_number: int, status: str) -> TaskAttempt
│    def save_decision(mission_record_id: str, decision_type: str, reasoning: str) -> MissionDecision
│    def get_mission(mission_id: str) -> MissionRecord | None
│    def get_task_executions(mission_id: str) -> list
│    def list_missions(status: str | None, roster_name: str | None, objective_category: str | None, limit: int | None, offset: int) -> tuple[list[MissionRecord], int]
│    def get_decisions(mission_id: str) -> list[MissionDecision]
│    def get_cost_breakdown(mission_id: str) -> MissionCostBreakdown
│    def get_mission_status(mission_id: str) -> dict
│    def get_missions_by_session(session_id: str) -> list[MissionRecord]
│    def get_replan_chain(mission_id: str) -> list[MissionRecord]

modules/backend/services/pqi/composite.py (85 lines):
│def compute_pqi(dimensions: dict[str, DimensionScore], profile: str, file_count: int, ...) -> PQIResult
│def floor_penalty(dimension_scores: dict[str, float]) -> float

modules/backend/services/pqi/dimensions.py (710 lines):
│def score_maintainability(project: ProjectAnalysis, tool_results: dict[str, ToolResult] | None) -> DimensionScore
│def score_security(project: ProjectAnalysis, tool_results: dict[str, ToolResult] | None) -> DimensionScore
│def score_modularity(project: ProjectAnalysis, code_map: dict | None) -> DimensionScore
│def score_testability(project: ProjectAnalysis, tool_results: dict[str, ToolResult] | None) -> DimensionScore
│def score_robustness(project: ProjectAnalysis) -> DimensionScore
│def score_elegance(project: ProjectAnalysis, tool_results: dict[str, ToolResult] | None) -> DimensionScore
│def score_reusability(project: ProjectAnalysis, code_map: dict | None) -> DimensionScore
│def _count_cycles(graph: dict[str, list[str]]) -> int
│def _gini_coefficient(values: list[int | float]) -> float

modules/backend/services/history_query.py (167 lines):
│class HistoryQueryService(BaseService):
│    def __init__(session: AsyncSession) -> None
│    def factory() -> AsyncGenerator['HistoryQueryService', None]
│    def get_recent_task_executions(project_id: str) -> list[dict]
│    def get_recent_failures(project_id: str) -> list[dict]
│    def get_mission_summaries(project_id: str) -> list[dict]

modules/backend/services/code_map/generator.py (83 lines):
│def generate_code_map(repo_root: Path, scope: list[str] | None, exclude: list[str] | None, ...) -> dict
│def _get_git_commit(repo_root: Path) -> str

modules/backend/services/code_map/loader.py (167 lines):
│class CodeMapLoader:
│    def __init__(project_root: Path) -> None
│    def get_json() -> dict | None
│    def get_markdown() -> str | None
│    def is_stale() -> bool
│    def ensure_fresh() -> dict | None
│    def regenerate() -> dict | None
│    def invalidate_cache() -> None
│    def _git_head() -> str

modules/backend/services/compliance.py (333 lines):
│class ComplianceScannerService:
│    def __init__(project_root: Path, config: dict[str, Any]) -> None
│    def _get_exclusion_paths() -> set[str]
│    def _get_enabled_rule_ids() -> set[str]
│    def get_rule_severity(rule_id: str) -> str
│    def collect_python_files() -> list[str]
│    def scan_file_lines(rel_path: str) -> list[str]
│    def _is_excluded(file_path: str) -> bool
│    def scan_import_violations() -> list[dict]
│    def scan_datetime_violations() -> list[dict]
│    def scan_hardcoded_values() -> list[dict]
│    def scan_file_sizes() -> list[dict]
│    def scan_cli_options() -> list[dict]
│    def scan_config_files() -> list[dict]
│    def scan_all() -> list[dict]

modules/backend/services/pqi/normalizers.py (69 lines):
│def sigmoid(x: float, midpoint: float, k: float) -> float
│def exp_decay(count: float, rate: float) -> float
│def linear(value: float, max_value: float) -> float
│def inverse_linear(value: float, good: float, bad: float) -> float
│def ratio_score(numerator: float, denominator: float) -> float

modules/backend/services/code_map/graph.py (288 lines):
│def build_reference_graph(modules: list[ModuleInfo]) -> ReferenceGraph
│def _add_symbol_references(symbol: SymbolInfo, module_qname: str, import_tables: dict[str, dict[str, str]], ...) -> None
│def _build_module_index(modules: list[ModuleInfo]) -> set[str]
│def _build_symbol_index(modules: list[ModuleInfo]) -> dict[str, str]
│def _build_import_tables(modules: list[ModuleInfo], known_modules: set[str]) -> dict[str, dict[str, str]]
│def _resolve_import(imp: str, known_modules: set[str]) -> str | None
│def _resolve_name(name: str, module_qname: str, import_tables: dict[str, dict[str, str]], ...) -> str | None
│def _strip_generics(type_str: str) -> str
│def _split_type_args(args_str: str) -> list[str]
│def _path_to_qname(rel_path: str) -> str

modules/backend/services/code_map/parser.py (316 lines):
│def parse_modules(repo_root: Path, scope: list[str] | None, exclude: list[str] | None) -> list[ModuleInfo]
│def _collect_files(repo_root: Path, scope: list[str] | None, exclude: list[str] | None) -> list[Path]
│def _matches_exclude(rel_path: str, pattern: str) -> bool
│def _parse_file(repo_root: Path, file_path: Path) -> ModuleInfo | None
│def _extract_imports(tree: ast.Module) -> list[str]
│def _extract_classes(tree: ast.Module, module_path: str) -> list[SymbolInfo]
│def _parse_class(node: ast.ClassDef, module_qname: str) -> SymbolInfo
│def _extract_functions(tree: ast.Module, module_path: str) -> list[SymbolInfo]
│def _parse_function(node: ast.FunctionDef | ast.AsyncFunctionDef, parent_qname: str, is_method: bool) -> SymbolInfo
│def _extract_constants(tree: ast.Module) -> list[str]
│def _extract_references(tree: ast.Module) -> list[str]
│def _attribute_chain(node: ast.Attribute) -> str
│def _annotation_str(node: ast.expr | None) -> str
│def _name_from_node(node: ast.expr) -> str
│def _path_to_module(rel_path: str) -> str

modules/backend/services/code_map/ranker.py (85 lines):
│def rank_symbols(graph: ReferenceGraph, damping: float, max_iterations: int, ...) -> dict[str, float]

modules/backend/services/mission.py (488 lines):
│class MissionService(BaseService):
│    def __init__(session: AsyncSession, mission_control_dispatch: MissionDispatchProtocol | None, session_service: Any | None, event_bus: EventBusProtocol) -> None
│    def factory() -> AsyncGenerator['MissionService', None]
│    def _publish_event(event: Any) -> None
│    def create_mission_from_step(playbook_run_id: str, step_id: str, objective: str, roster_ref: str, complexity_tier: str, cost_ceiling_usd: float, upstream_context: dict, session_id: str, environment: str, project_id: str | None) -> Mission
│    def create_adhoc_mission(objective: str, triggered_by: str, session_id: str, roster_ref: str, complexity_tier: str, cost_ceiling_usd: float | None, upstream_context: dict | None) -> Mission
│    def execute_mission(mission_id: str) -> Mission
│    def complete_mission(mission_id: str) -> Mission
│    def fail_mission(mission_id: str, error: str, error_data: dict | None) -> Mission
│    def cancel_mission(mission_id: str, reason: str) -> Mission
│    def extract_outputs(mission: Mission, output_mapping: dict | None) -> dict[str, Any]
│    def get_mission(mission_id: str) -> Mission
│    def list_missions(status: str | None, playbook_run_id: str | None, limit: int, offset: int) -> tuple[list[Mission], int]
│    def _get_mission(mission_id: str) -> Mission
│    def _validate_transition(mission: Mission, new_status: MissionState) -> None

modules/backend/services/playbook.py (312 lines):
│class PlaybookService:
│    def __init__(agent_registry: dict[str, Any] | None) -> None
│    def load_playbooks() -> dict[str, PlaybookSchema]
│    def list_playbooks(enabled_only: bool) -> list[PlaybookSchema]
│    def get_playbook(playbook_name: str) -> PlaybookSchema | None
│    def resolve_capability(capability: str) -> str
│    def validate_playbook_capabilities(playbook: PlaybookSchema) -> list[str]
│    def generate_mission_briefs(playbook: PlaybookSchema) -> list[dict[str, Any]]
│    def match_playbook(user_input: str) -> PlaybookSchema | None
│    def resolve_upstream_context(step: PlaybookStepSchema, completed_outcomes: dict[str, dict], playbook_context: dict[str, Any]) -> dict[str, Any]

modules/backend/services/note.py (208 lines):
│class NoteService(BaseService):
│    def __init__(session: AsyncSession) -> None
│    def create_note(data: NoteCreate) -> Note
│    def get_note(note_id: str) -> Note
│    def list_notes(include_archived: bool, limit: int, offset: int) -> list[Note]
│    def list_notes_paginated(include_archived: bool, limit: int, offset: int) -> tuple[list[Note], int]
│    def update_note(note_id: str, data: NoteUpdate) -> Note
│    def delete_note(note_id: str) -> None
│    def archive_note(note_id: str) -> Note
│    def unarchive_note(note_id: str) -> Note
│    def search_notes(query: str, limit: int) -> list[Note]

modules/backend/services/session.py (397 lines):
│class SessionService(BaseService):
│    def __init__(session: AsyncSession) -> None
│    def create_session(data: SessionCreate, user_id: str | None) -> Session
│    def get_session(session_id: str) -> Session
│    def update_session(session_id: str, data: SessionUpdate) -> Session
│    def list_sessions(user_id: str | None, status_filter: str | None, limit: int, offset: int) -> tuple[list[Session], int]
│    def _transition(session_id: str, target_status: SessionStatus, reason: str | None) -> Session
│    def suspend_session(session_id: str, reason: str) -> Session
│    def resume_session(session_id: str) -> Session
│    def complete_session(session_id: str) -> Session
│    def fail_session(session_id: str, reason: str) -> Session
│    def expire_session(session_id: str) -> Session
│    def update_cost(session_id: str, input_tokens: int, output_tokens: int, cost_usd: float) -> None
│    def enforce_budget(session_id: str, estimated_cost: float) -> None
│    def touch_activity(session_id: str) -> None
│    def bind_channel(session_id: str, channel_type: str, channel_id: str) -> SessionChannel
│    def unbind_channel(session_id: str, channel_type: str, channel_id: str) -> None
│    def get_session_by_channel(channel_type: str, channel_id: str) -> Session
│    def add_message(session_id: str, data: SessionMessageCreate) -> None
│    def get_messages(session_id: str, limit: int, offset: int) -> tuple[list, int]
│    def expire_inactive_sessions() -> int
│    def _publish_session_event(event_type: str, session: Session) -> None

modules/backend/services/context_assembler.py (194 lines):
│class ContextAssembler:
│    def __init__(context_manager: ProjectContextManager, history_service: HistoryQueryService) -> None
│    def build(project_id: str, task_definition: dict, resolved_inputs: dict) -> dict
│    def _is_coding_task(domain_tags: list[str] | None) -> bool
│    def _load_code_map_markdown(max_tokens: int | None) -> str | None
│    def _assemble_history(project_id: str, domain_tags: list[str], remaining_budget: int) -> dict[str, Any]

modules/backend/services/context_curator.py (68 lines):
│class ContextCurator:
│    def __init__(context_manager: ProjectContextManager) -> None
│    def get_project_context(project_id: str) -> dict
│    def apply_task_updates(project_id: str, task_result_context_updates: list[dict]) -> tuple[int, list[str]]

modules/backend/services/__init__.py (1 lines):

modules/backend/services/code_map/__init__.py (31 lines):

modules/backend/services/playbook_run.py (422 lines):
│class PlaybookRunService(BaseService):
│    def __init__(session: AsyncSession, mission_service_factory: MissionServiceFactory | None, playbook_service: PlaybookService | None) -> None
│    def run_playbook(playbook_name: str, triggered_by: str, context_overrides: dict[str, Any] | None, on_progress: Any | None, project_id: str | None) -> PlaybookRun
│    def list_runs(playbook_name: str | None, limit: int) -> tuple[list[PlaybookRun], int]
│    def get_run(run_id: str) -> PlaybookRun | None
│    def _execute_steps(run: PlaybookRun, playbook: PlaybookSchema, session_id: str, on_progress: Any | None) -> None
│    def _execute_wave(run: PlaybookRun, steps: list[PlaybookStepSchema], session_id: str, completed_outcomes: dict[str, dict]) -> list[tuple[Any, dict]]
│    def _execute_step(run: PlaybookRun, step: PlaybookStepSchema, session_id: str, completed_outcomes: dict[str, dict], mission_service: MissionService) -> tuple[Any, dict]
│    def _build_step_objective(step: PlaybookStepSchema, step_input: dict[str, Any]) -> str
│    def _compute_waves(steps: list[PlaybookStepSchema]) -> list[list[str]]

modules/backend/services/pqi/__init__.py (9 lines):

modules/backend/services/pqi/tools/bandit.py (157 lines):
│def is_available() -> bool
│def run(repo_root: Path, scope: list[str] | None, exclude: list[str] | None) -> ToolResult
│def _strip_progress(raw: str) -> str
│def _parse_output(raw_json: str) -> ToolResult

modules/backend/services/pqi/tools/radon.py (209 lines):
│def is_available() -> bool
│def run(repo_root: Path, scope: list[str] | None, exclude: list[str] | None) -> ToolResult
│def _build_targets(repo_root: Path, scope: list[str] | None) -> list[str]
│def _build_excludes(repo_root: Path, exclude: list[str] | None) -> list[str]
│def _run_cc(targets: list[str], exclude_args: list[str], cwd: Path) -> dict | str
│def _run_mi(targets: list[str], exclude_args: list[str], cwd: Path) -> dict | str
│def _merge_results(cc_data: dict | str, mi_data: dict | str) -> ToolResult
│def _rank_to_severity(rank: str) -> str

modules/backend/services/project.py (137 lines):
│class ProjectService(BaseService):
│    def __init__(session: AsyncSession) -> None
│    def factory() -> AsyncGenerator['ProjectService', None]
│    def create_project() -> Project
│    def get_project(project_id: str) -> Project
│    def get_project_by_name(name: str) -> Project | None
│    def list_projects(owner_id: str | None, status: str | None, limit: int) -> list[Project]
│    def update_project(project_id: str) -> Project
│    def archive_project(project_id: str) -> Project

modules/backend/services/summarization.py (333 lines):
│class SummarizationService(BaseService):
│    def __init__(session: AsyncSession) -> None
│    def factory() -> AsyncGenerator['SummarizationService', None]
│    def prune_pcd_decisions(project_id: str, max_age_days: int) -> int
│    def prune_completed_workstreams(project_id: str, keep_recent: int) -> int
│    def summarize_mission_records(project_id: str, max_age_days: int, batch_size: int) -> int
│    def run_full_pipeline(project_id: str) -> dict


## telegram

modules/telegram/callbacks/common.py (115 lines):
│class ActionCallback(CallbackData):
│    action: str
│    action_id: str
│class MenuCallback(CallbackData):
│    menu: str
│    item_id: str | None
│class PaginationCallback(CallbackData):
│    list_type: str
│    page: int
│    per_page: int
│class ItemCallback(CallbackData):
│    action: str
│    item_type: str
│    item_id: str

modules/telegram/keyboards/common.py (195 lines):
│def get_main_menu_keyboard(user_role: str) -> ReplyKeyboardMarkup
│def get_cancel_keyboard() -> ReplyKeyboardMarkup
│def get_confirmation_keyboard(action_id: str) -> InlineKeyboardMarkup
│def get_pagination_keyboard(list_type: str, current_page: int, total_pages: int, ...) -> InlineKeyboardMarkup
│def get_yes_no_keyboard(action_id: str) -> InlineKeyboardMarkup
│def get_back_keyboard(menu: str) -> InlineKeyboardMarkup

modules/telegram/states/example.py (50 lines):
│class FeedbackForm(StatesGroup):
│class SettingsForm(StatesGroup):
│class RegistrationForm(StatesGroup):

modules/telegram/bot.py (147 lines):
│def create_bot() -> 'Bot'
│def create_dispatcher() -> 'Dispatcher'
│def get_bot() -> 'Bot'
│def get_dispatcher() -> 'Dispatcher'
│def setup_webhook(bot: 'Bot', webhook_url: str, secret_token: str) -> None
│def cleanup_bot(bot: 'Bot') -> None

modules/telegram/services/notifications.py (473 lines):
│class NotificationResult:
│    success: bool
│    user_id: int
│    message_id: int | None
│    error: str | None
│    rate_limited: bool
│    timestamp: datetime
│class AlertType(str, Enum):
│class NotificationService:
│    def __init__() -> None
│    def _check_rate_limit(user_id: int) -> bool
│    def send(user_id: int, text: str, parse_mode: str, disable_notification: bool, reply_markup: Any) -> NotificationResult
│    def send_alert(user_id: int, title: str, body: str, alert_type: AlertType, data: dict[str, Any] | None, disable_notification: bool) -> NotificationResult
│    def broadcast(user_ids: list[int], text: str, parse_mode: str, disable_notification: bool, delay_between: float) -> list[NotificationResult]
│    def send_success(user_id: int, title: str, message: str, data: dict[str, Any] | None) -> NotificationResult
│    def send_warning(user_id: int, title: str, message: str, data: dict[str, Any] | None) -> NotificationResult
│    def send_error(user_id: int, title: str, error_message: str, context: dict[str, Any] | None) -> NotificationResult
│    def send_system(user_id: int, title: str, message: str) -> NotificationResult
│def _get_notification_rate_limit() -> int
│def get_notification_service() -> NotificationService
│def send_alert(user_id: int, message: str, alert_type: AlertType, ...) -> NotificationResult
│def send_notification(user_id: int, title: str, body: str, ...) -> NotificationResult

modules/telegram/handlers/common.py (184 lines):
│@router.message
│def cmd_start(message: Message, telegram_user: User, user_role: str) -> None
│@router.message
│def cmd_help(message: Message, user_role: str) -> None
│@router.message
│def cmd_cancel(message: Message, state: FSMContext) -> None
│@router.message
│def cmd_status(message: Message) -> None
│@router.message
│def btn_cancel(message: Message, state: FSMContext) -> None

modules/telegram/handlers/example.py (243 lines):
│@router.message
│def cmd_echo(message: Message) -> None
│@router.message
│def cmd_info(message: Message, user_role: str) -> None
│@router.message
│def cmd_feedback(message: Message, state: FSMContext) -> None
│@router.message
│def process_category(message: Message, state: FSMContext) -> None
│@router.message
│def process_invalid_category(message: Message) -> None
│@router.message
│def process_feedback_message(message: Message, state: FSMContext) -> None
│@router.message
│def cmd_confirm(message: Message) -> None
│@router.callback_query
│def callback_confirm(callback: CallbackQuery, callback_data: ActionCallback) -> None
│@router.callback_query
│def callback_cancel(callback: CallbackQuery, callback_data: ActionCallback) -> None
│@router.message
│def cmd_api_example(message: Message) -> None

modules/telegram/middlewares/auth.py (167 lines):
│class AuthMiddleware(BaseMiddleware):
│    def __call__(handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any
│def _get_role_hierarchy() -> dict[str, int]
│def _get_user_roles_mapping() -> dict[int, str]
│def _resolve_role(user_id: int, authorized_users: list[int]) -> str
│def require_role(min_role: str)

modules/telegram/middlewares/logging.py (150 lines):
│class LoggingMiddleware(BaseMiddleware):
│    def __call__(handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any
│    def _extract_context(event: TelegramObject) -> dict[str, Any]

modules/telegram/middlewares/rate_limit.py (208 lines):
│class RateLimitMiddleware(BaseMiddleware):
│    def __init__(rate_limit: int | None, rate_window: int)
│    def __call__(handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any
│    def _get_user_id(event: TelegramObject) -> int | None
│    def _check_rate_limit(user_id: int, now: float) -> tuple[bool, int]
│    def _send_rate_limit_message(event: TelegramObject, remaining: int) -> None
│class ThrottleMiddleware(BaseMiddleware):
│    def __init__(default_throttle: float)
│    def __call__(handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any
│    def _get_user_id(event: TelegramObject) -> int | None
│def _get_telegram_rate_limit() -> int

modules/telegram/handlers/setup.py (28 lines):
│def get_all_routers() -> list[Router]

modules/telegram/middlewares/setup.py (36 lines):
│def setup_middlewares(dp: 'Dispatcher') -> None

modules/telegram/__init__.py (59 lines):

modules/telegram/callbacks/__init__.py (35 lines):

modules/telegram/handlers/__init__.py (11 lines):

modules/telegram/keyboards/__init__.py (37 lines):

modules/telegram/middlewares/__init__.py (13 lines):

modules/telegram/services/__init__.py (19 lines):

modules/telegram/states/__init__.py (31 lines):

modules/telegram/webhook.py (117 lines):
│def get_webhook_router(bot: 'Bot', dp: 'Dispatcher') -> APIRouter
│def get_webhook_url(base_url: str) -> str


## backend.models

modules/backend/models/base.py (53 lines):
│class Base(DeclarativeBase):
│class UUIDMixin:
│    id: Mapped[str]
│class TimestampMixin:
│    created_at: Mapped[datetime]
│    updated_at: Mapped[datetime]

modules/backend/models/mission_record.py (403 lines):
│class MissionRecord(UUIDMixin, TimestampMixin, Base):
│    session_id: Mapped[str]
│    project_id: Mapped[str | None]
│    roster_name: Mapped[str | None]
│    objective_statement: Mapped[str | None]
│    objective_category: Mapped[str | None]
│    status: Mapped[str]
│    task_plan_json: Mapped[dict | None]
│    mission_outcome_json: Mapped[dict | None]
│    planning_thinking_trace: Mapped[str | None]
│    total_cost_usd: Mapped[float]
│    started_at: Mapped[str | None]
│    completed_at: Mapped[str | None]
│    summarized: Mapped[bool]
│    parent_mission_id: Mapped[str | None]
│    task_executions: Mapped[list['TaskExecution']]
│    decisions: Mapped[list['MissionDecision']]
│    def __repr__() -> str
│class MissionDecision(UUIDMixin, TimestampMixin, Base):
│    mission_record_id: Mapped[str]
│    decision_type: Mapped[str]
│    task_id: Mapped[str | None]
│    reasoning: Mapped[str]
│    mission_record: Mapped['MissionRecord']
│    def __repr__() -> str
│class TaskExecution(UUIDMixin, TimestampMixin, Base):
│    mission_record_id: Mapped[str]
│    task_id: Mapped[str]
│    agent_name: Mapped[str]
│    status: Mapped[str]
│    output_data: Mapped[dict | None]
│    token_usage: Mapped[dict | None]
│    cost_usd: Mapped[float]
│    duration_seconds: Mapped[float | None]
│    verification_outcome: Mapped[dict | None]
│    started_at: Mapped[str | None]
│    completed_at: Mapped[str | None]
│    execution_id: Mapped[str | None]
│    domain_tags: Mapped[list | None]
│    mission_record: Mapped['MissionRecord']
│    attempts: Mapped[list['TaskAttempt']]
│    def __repr__() -> str
│class MissionRecordStatus(str, enum.Enum):
│class TaskAttempt(UUIDMixin, TimestampMixin, Base):
│    task_execution_id: Mapped[str]
│    attempt_number: Mapped[int]
│    status: Mapped[str]
│    failure_tier: Mapped[str | None]
│    failure_reason: Mapped[str | None]
│    feedback_provided: Mapped[str | None]
│    input_tokens: Mapped[int]
│    output_tokens: Mapped[int]
│    cost_usd: Mapped[float]
│    task_execution: Mapped['TaskExecution']
│    def __repr__() -> str
│class TaskExecutionStatus(str, enum.Enum):
│class TaskAttemptStatus(str, enum.Enum):
│class DecisionType(str, enum.Enum):
│class FailureTier(str, enum.Enum):

modules/backend/models/mission.py (197 lines):
│class Mission(UUIDMixin, TimestampMixin, Base):
│    playbook_run_id: Mapped[str | None]
│    playbook_step_id: Mapped[str | None]
│    project_id: Mapped[str | None]
│    objective: Mapped[str]
│    roster_ref: Mapped[str]
│    complexity_tier: Mapped[str]
│    status: Mapped[str]
│    session_id: Mapped[str]
│    trigger_type: Mapped[str]
│    triggered_by: Mapped[str]
│    upstream_context: Mapped[dict]
│    context: Mapped[dict]
│    total_cost_usd: Mapped[float]
│    cost_ceiling_usd: Mapped[float | None]
│    started_at: Mapped[str | None]
│    completed_at: Mapped[str | None]
│    error_data: Mapped[dict | None]
│    mission_outcome: Mapped[dict | None]
│    result_summary: Mapped[str | None]
│    def __repr__() -> str
│class PlaybookRun(UUIDMixin, TimestampMixin, Base):
│    playbook_name: Mapped[str]
│    playbook_version: Mapped[int]
│    project_id: Mapped[str | None]
│    status: Mapped[str]
│    session_id: Mapped[str]
│    trigger_type: Mapped[str]
│    triggered_by: Mapped[str]
│    context: Mapped[dict]
│    total_cost_usd: Mapped[float]
│    budget_usd: Mapped[float | None]
│    started_at: Mapped[str | None]
│    completed_at: Mapped[str | None]
│    error_data: Mapped[dict | None]
│    result_summary: Mapped[str | None]
│    def __repr__() -> str
│class MissionState(str, enum.Enum):
│class PlaybookRunState(str, enum.Enum):

modules/backend/models/note.py (39 lines):
│class Note(UUIDMixin, TimestampMixin, Base):
│    title: Mapped[str]
│    content: Mapped[str | None]
│    is_archived: Mapped[bool]
│    def __repr__() -> str

modules/backend/models/project_context.py (124 lines):
│class ContextChange(UUIDMixin, TimestampMixin, Base):
│    context_id: Mapped[str]
│    version: Mapped[int]
│    change_type: Mapped[str]
│    path: Mapped[str]
│    old_value: Mapped[dict | None]
│    new_value: Mapped[dict | None]
│    agent_id: Mapped[str | None]
│    mission_id: Mapped[str | None]
│    task_id: Mapped[str | None]
│    execution_id: Mapped[str | None]
│    reason: Mapped[str]
│    context: Mapped['ProjectContext']
│    def __repr__() -> str
│class ProjectContext(UUIDMixin, TimestampMixin, Base):
│    project_id: Mapped[str]
│    context_data: Mapped[dict]
│    version: Mapped[int]
│    size_characters: Mapped[int]
│    size_tokens: Mapped[int]
│    changes: Mapped[list['ContextChange']]
│    def __repr__() -> str
│class ChangeType(str, enum.Enum):

modules/backend/models/project.py (117 lines):
│class Project(UUIDMixin, TimestampMixin, Base):
│    name: Mapped[str]
│    description: Mapped[str]
│    status: Mapped[str]
│    owner_id: Mapped[str]
│    team_id: Mapped[str | None]
│    default_roster: Mapped[str]
│    budget_ceiling_usd: Mapped[float | None]
│    repo_url: Mapped[str | None]
│    repo_root: Mapped[str | None]
│    members: Mapped[list['ProjectMember']]
│    def __repr__() -> str
│class ProjectMember(UUIDMixin, TimestampMixin, Base):
│    project_id: Mapped[str]
│    user_id: Mapped[str]
│    role: Mapped[str]
│    project: Mapped['Project']
│    def __repr__() -> str
│class ProjectStatus(str, enum.Enum):
│class ProjectMemberRole(str, enum.Enum):

modules/backend/models/project_history.py (119 lines):
│class ProjectDecision(UUIDMixin, TimestampMixin, Base):
│    project_id: Mapped[str]
│    decision_id: Mapped[str]
│    domain: Mapped[str]
│    decision: Mapped[str]
│    rationale: Mapped[str]
│    made_by: Mapped[str]
│    mission_id: Mapped[str | None]
│    status: Mapped[str]
│    superseded_by: Mapped[str | None]
│    def __repr__() -> str
│class MilestoneSummary(UUIDMixin, TimestampMixin, Base):
│    project_id: Mapped[str]
│    title: Mapped[str]
│    summary: Mapped[str]
│    mission_ids: Mapped[list]
│    key_outcomes: Mapped[dict]
│    domain_tags: Mapped[list]
│    period_start: Mapped[str | None]
│    period_end: Mapped[str | None]
│    def __repr__() -> str
│class DecisionStatus(str, enum.Enum):

modules/backend/models/session.py (175 lines):
│class Session(UUIDMixin, TimestampMixin, Base):
│    status: Mapped[str]
│    user_id: Mapped[str | None]
│    agent_id: Mapped[str | None]
│    goal: Mapped[str | None]
│    plan_id: Mapped[str | None]
│    session_metadata: Mapped[dict | None]
│    total_input_tokens: Mapped[int]
│    total_output_tokens: Mapped[int]
│    total_cost_usd: Mapped[float]
│    cost_budget_usd: Mapped[float | None]
│    last_activity_at: Mapped[datetime]
│    expires_at: Mapped[datetime | None]
│    channels: Mapped[list['SessionChannel']]
│    messages: Mapped[list['SessionMessage']]
│    def __repr__() -> str
│class SessionChannel(UUIDMixin, Base):
│    session_id: Mapped[str]
│    channel_type: Mapped[str]
│    channel_id: Mapped[str]
│    bound_at: Mapped[datetime]
│    is_active: Mapped[bool]
│    session: Mapped['Session']
│    def __repr__() -> str
│class SessionMessage(UUIDMixin, Base):
│    session_id: Mapped[str]
│    role: Mapped[str]
│    content: Mapped[str]
│    sender_id: Mapped[str | None]
│    model: Mapped[str | None]
│    input_tokens: Mapped[int | None]
│    output_tokens: Mapped[int | None]
│    cost_usd: Mapped[float | None]
│    tool_name: Mapped[str | None]
│    tool_call_id: Mapped[str | None]
│    created_at: Mapped[datetime]
│    session: Mapped['Session']
│    def __repr__() -> str
│class SessionStatus(str, enum.Enum):

modules/backend/models/__init__.py (25 lines):


## backend.cli

modules/backend/cli/report.py (808 lines):
│def get_console() -> Console
│def status_color(status: Any) -> str
│def styled_status(status: Any) -> str
│def build_table(title: str | None) -> Table
│def status_panel(content: str, status: Any) -> Panel
│def info_panel(content: str, title: str | None) -> Panel
│def render_task_outputs(console: Console, tasks: list[dict]) -> None
│def render_mission_outcomes(console: Console, missions: list[Any]) -> None
│def primary_panel(content: str, title: str | None) -> Panel
│def thinking_panel(content: str) -> Panel
│def output_panel(body: Any) -> Panel
│def format_json_body(raw: str) -> Any
│def cost_line(input_tokens: int, output_tokens: int, cost_usd: float) -> str
│def summary_table() -> Table
│def severity_color(severity: str) -> str
│def render_human(raw: str) -> list[Any]
│def _find_list_field(parsed: dict) -> tuple[str, list[dict]]
│def _build_dynamic_table(items: list[dict]) -> Table
│def _extract_scalars(parsed: dict) -> list[tuple[str, str]]
│def _build_scalars_table(scalars: list[tuple[str, str]]) -> Table
│def render_mission(mission: Any, output_format: str) -> None
│def render_playbook_run(run: Any, missions: list[Any], output_format: str) -> None
│def _render_summary(title: str, status_line: str, data: dict) -> None
│def _generate_narrative(data: dict) -> str
│def _fallback_narrative(data: dict) -> str
│def colorize_narrative(text: str) -> str
│def _emit_json(data: dict) -> None
│def _render_mission_detail(mission: Any) -> None
│def _render_playbook_detail(run: Any, missions: list[Any]) -> None
│def _render_errors(error_data: dict | None) -> None
│def _status_str(status: Any) -> str
│def _styled_status(status: Any, pad: int) -> str
│def _mission_to_dict(mission: Any) -> dict
│def _playbook_run_to_dict(run: Any, missions: list[Any]) -> dict
│def _extract_task_summaries(outcome: dict) -> list[dict]
│def _extract_findings(data: dict) -> list[str]

modules/backend/cli/__init__.py (1 lines):

modules/backend/cli/agent.py (233 lines):
│def show_agents(cli_logger) -> None
│def run_agent(cli_logger, message: str, agent: str | None, ...) -> None
│def _dispatch(message: str, agent: str | None) -> dict
│def _print_jsonl(result: dict) -> None
│def _print_human(result: dict, console) -> None
│def _print_result(result: dict, console) -> None

modules/backend/cli/config_display.py (44 lines):
│def show_config(logger, output_format: str) -> None

modules/backend/cli/credits.py (60 lines):
│def check_credits(logger, roster: str, output_format: str) -> None
│def _check_credits_async(logger, roster: str) -> None

modules/backend/cli/db.py (292 lines):
│def run_db(cli_logger, action: str, table: str | None, ...) -> None
│def _action_stats(cli_logger)
│def _action_tables(cli_logger)
│def _action_query(cli_logger)
│def _action_clear(cli_logger)
│def _action_clear_missions(cli_logger)
│def _action_clear_sessions(cli_logger)
│def _format_value(val) -> str

modules/backend/cli/event_worker.py (27 lines):
│def run_event_worker(logger)

modules/backend/cli/health.py (90 lines):
│def check_health(logger, output_format: str) -> None

modules/backend/cli/helpers.py (53 lines):
│def find_process_on_port(port: int) -> list[int]
│def service_stop(logger, service: str, port: int) -> None
│def service_status(logger, service: str, port: int) -> None
│def get_service_port(port: int | None) -> int

modules/backend/cli/info.py (65 lines):
│def show_info(logger, output_format: str) -> None

modules/backend/cli/migrate.py (70 lines):
│def run_migrations(logger, migrate_action: str, revision: str, ...) -> None

modules/backend/cli/mission.py (510 lines):
│class _AbortMission(Exception):
│def run_mission(cli_logger, action: str, objective: str | None, ...) -> None
│def _action_create(cli_logger)
│def _action_execute(cli_logger)
│def _action_run(cli_logger)
│def _action_list(cli_logger)
│def _action_detail(cli_logger)
│def _action_plan(cli_logger)
│def _action_cost(cli_logger)
│def _generate_session_id() -> str
│def _preflight_gate(roster: str) -> None

modules/backend/cli/playbook.py (413 lines):
│def run_playbook_cli(cli_logger, action: str, playbook_name: str | None, ...) -> None
│def _action_list(cli_logger)
│def _action_detail(cli_logger)
│def _action_run(cli_logger)
│def _action_runs(cli_logger)
│def _action_run_detail(cli_logger)
│def _action_report(cli_logger)
│def _preflight_gate(playbook_name: str) -> None
│def _load_run_with_missions(run_id: str)

modules/backend/cli/project.py (260 lines):
│def run_project(cli_logger, action: str) -> None
│def _action_create(cli_logger)
│def _action_list(cli_logger)
│def _action_detail(cli_logger)
│def _action_archive(cli_logger)
│def _action_context_show(cli_logger)
│def _action_context_history(cli_logger)
│def _action_summarize(cli_logger)

modules/backend/cli/scheduler.py (62 lines):
│def run_scheduler(logger) -> None

modules/backend/cli/server.py (54 lines):
│def run_server(logger, host: str | None, port: int | None, ...) -> None

modules/backend/cli/telegram.py (58 lines):
│def run_telegram_poll(logger) -> None
│def _run_polling(bot, dp, logger) -> None

modules/backend/cli/testing.py (40 lines):
│def run_tests(logger, test_type: str, coverage: bool) -> None

modules/backend/cli/worker.py (45 lines):
│def run_worker(logger, workers: int) -> None


## backend.schemas

modules/backend/schemas/base.py (86 lines):
│class ApiResponse(BaseModel):
│    success: bool
│    data: DataT | None
│    error: ErrorDetail | None
│    metadata: ResponseMetadata
│class ResponseMetadata(BaseModel):
│    timestamp: datetime
│    request_id: str | None
│class ErrorDetail(BaseModel):
│    code: str
│    message: str
│    details: dict[str, Any] | None
│class ErrorResponse(BaseModel):
│    success: bool
│    data: None
│    error: ErrorDetail
│    metadata: ResponseMetadata
│class PaginatedResponse(BaseModel):
│    success: bool
│    data: list[DataT]
│    error: None
│    metadata: ResponseMetadata
│    pagination: 'PaginationInfo'
│class PaginationInfo(BaseModel):
│    total: int | None
│    limit: int
│    cursor: str | None
│    next_cursor: str | None
│    has_more: bool

modules/backend/schemas/session.py (163 lines):
│class SessionResponse(BaseModel):
│    id: str
│    status: str
│    user_id: str | None
│    agent_id: str | None
│    goal: str | None
│    plan_id: str | None
│    total_input_tokens: int
│    total_output_tokens: int
│    total_cost_usd: float
│    cost_budget_usd: float | None
│    budget_remaining_usd: float | None
│    created_at: datetime
│    updated_at: datetime
│    last_activity_at: datetime
│    expires_at: datetime | None
│class SessionMessageCreate(BaseModel):
│    content: str
│    role: str
│    sender_id: str | None
│    model: str | None
│    input_tokens: int | None
│    output_tokens: int | None
│    cost_usd: float | None
│    tool_name: str | None
│    tool_call_id: str | None
│class SessionCreate(BaseModel):
│    goal: str | None
│    agent_id: str | None
│    cost_budget_usd: float | None
│    ttl_hours: int | None
│    session_metadata: dict | None
│class SessionUpdate(BaseModel):
│    goal: str | None
│    agent_id: str | None
│    cost_budget_usd: float | None
│    session_metadata: dict | None
│class ChannelBindRequest(BaseModel):
│    channel_type: str
│    channel_id: str
│class ChannelResponse(BaseModel):
│    id: str
│    session_id: str
│    channel_type: str
│    channel_id: str
│    bound_at: datetime
│    is_active: bool
│class SessionListResponse(BaseModel):
│    id: str
│    status: str
│    goal: str | None
│    agent_id: str | None
│    total_cost_usd: float
│    created_at: datetime
│    last_activity_at: datetime
│class SessionMessageResponse(BaseModel):
│    id: str
│    session_id: str
│    role: str
│    content: str
│    sender_id: str | None
│    model: str | None
│    input_tokens: int | None
│    output_tokens: int | None
│    cost_usd: float | None
│    tool_name: str | None
│    tool_call_id: str | None
│    created_at: datetime

modules/backend/schemas/playbook.py (265 lines):
│class PlaybookStepSchema(BaseModel):
│    id: str
│    description: str | None
│    capability: str
│    roster: str
│    complexity_tier: str
│    cost_ceiling_usd: float | None
│    environment: str
│    input: dict[str, Any]
│    output_mapping: PlaybookStepOutputMapping | None
│    depends_on: list[str]
│    timeout_seconds: int | None
│class PlaybookOutputFieldMapping(BaseModel):
│    source_task: str
│    source_field: str
│    target_key: str
│class PlaybookStepOutputMapping(BaseModel):
│    summary_key: str | None
│    field_mappings: list[PlaybookOutputFieldMapping]
│class PlaybookSchema(BaseModel):
│    playbook_name: str
│    description: str
│    objective: PlaybookObjectiveSchema
│    version: int
│    enabled: bool
│    project_id: str
│    project_name: str | None
│    trigger: PlaybookTriggerSchema
│    budget: PlaybookBudgetSchema
│    context: dict[str, Any]
│    steps: list[PlaybookStepSchema]
│    def validate_steps(steps: list[PlaybookStepSchema]) -> list[PlaybookStepSchema]
│class PlaybookTriggerSchema(BaseModel):
│    type: str
│    schedule: str | None
│    event_type: str | None
│    match_patterns: list[str]
│class PlaybookBudgetSchema(BaseModel):
│    max_cost_usd: float
│    max_tokens: int | None
│class PlaybookObjectiveSchema(BaseModel):
│    statement: str
│    category: str
│    owner: str
│    priority: str
│    regulatory_reference: str | None
│class PlaybookListResponse(BaseModel):
│    playbook_name: str
│    description: str
│    version: int
│    enabled: bool
│    trigger_type: str
│    step_count: int
│    budget_usd: float
│    objective_category: str
│    objective_priority: str
│    objective_owner: str
│class PlaybookDetailResponse(BaseModel):
│    playbook_name: str
│    description: str
│    objective: PlaybookObjectiveSchema
│    version: int
│    enabled: bool
│    trigger: PlaybookTriggerSchema
│    budget: PlaybookBudgetSchema
│    context_keys: list[str]
│    steps: list[PlaybookStepSchema]

modules/backend/schemas/note.py (71 lines):
│class NoteResponse(BaseModel):
│    id: str
│    title: str
│    content: str | None
│    is_archived: bool
│    created_at: datetime
│    updated_at: datetime
│class NoteCreate(BaseModel):
│    title: str
│    content: str | None
│class NoteUpdate(BaseModel):
│    title: str | None
│    content: str | None
│    is_archived: bool | None
│class NoteListResponse(BaseModel):
│    id: str
│    title: str
│    is_archived: bool
│    created_at: datetime

modules/backend/schemas/task_plan.py (204 lines):
│class TaskDefinition(BaseModel):
│    task_id: str
│    agent: str
│    agent_version: str
│    description: str
│    instructions: str
│    inputs: TaskInputs
│    dependencies: list[str]
│    verification: TaskVerification
│    constraints: TaskConstraints
│    domain_tags: list[str]
│class TaskPlan(BaseModel):
│    version: str
│    mission_id: str
│    summary: str
│    estimated_cost_usd: float
│    estimated_duration_seconds: int
│    tasks: list[TaskDefinition]
│    execution_hints: ExecutionHints
│    def task_ids() -> list[str]
│    def get_task(task_id: str) -> TaskDefinition | None
│class ExecutionHints(BaseModel):
│    min_success_threshold: float
│    critical_path: list[str]
│class FileManifestEntry(BaseModel):
│    path: str
│    reason: str
│class TaskInputs(BaseModel):
│    static: dict
│    from_upstream: dict[str, FromUpstreamRef]
│    file_manifest: FileManifest | None
│class TaskVerification(BaseModel):
│    tier_1: Tier1Verification
│    tier_2: Tier2Verification
│    tier_3: Tier3Verification
│class TaskConstraints(BaseModel):
│    timeout_override_seconds: int | None
│    priority: str
│class DeterministicCheck(BaseModel):
│    check: str
│    params: dict
│class FromUpstreamRef(BaseModel):
│    source_task: str
│    source_field: str
│class FileManifest(BaseModel):
│    read_for_pattern: list[FileManifestEntry]
│    read_first: list[FileManifestEntry]
│    modify: list[FileManifestEntry]
│class Tier1Verification(BaseModel):
│    schema_validation: bool
│    required_output_fields: list[str]
│class Tier2Verification(BaseModel):
│    deterministic_checks: list[DeterministicCheck]
│class Tier3Verification(BaseModel):
│    requires_ai_evaluation: bool
│    evaluation_criteria: list[str]
│    evaluator_agent: str | None
│    min_evaluation_score: float | None

modules/backend/schemas/mission_record.py (118 lines):
│class MissionRecordResponse(BaseModel):
│    id: str
│    session_id: str
│    roster_name: str | None
│    status: str
│    total_cost_usd: float
│    started_at: str | None
│    completed_at: str | None
│    parent_mission_id: str | None
│    created_at: str
│    updated_at: str
│class MissionCostBreakdown(BaseModel):
│    mission_id: str
│    total_cost_usd: float
│    task_costs: list[dict]
│    model_costs: dict[str, float]
│    attempt_count: int
│    total_input_tokens: int
│    total_output_tokens: int
│class TaskExecutionResponse(BaseModel):
│    id: str
│    task_id: str
│    agent_name: str
│    status: str
│    output_data: dict | None
│    token_usage: dict | None
│    cost_usd: float
│    duration_seconds: float | None
│    verification_outcome: dict | None
│    started_at: str | None
│    completed_at: str | None
│    created_at: str
│class TaskAttemptResponse(BaseModel):
│    id: str
│    attempt_number: int
│    status: str
│    failure_tier: str | None
│    failure_reason: str | None
│    feedback_provided: str | None
│    input_tokens: int
│    output_tokens: int
│    cost_usd: float
│    created_at: str
│class MissionDecisionResponse(BaseModel):
│    id: str
│    decision_type: str
│    task_id: str | None
│    reasoning: str
│    created_at: str
│class TaskExecutionDetailResponse(TaskExecutionResponse):
│    attempts: list[TaskAttemptResponse]
│class MissionRecordDetailResponse(MissionRecordResponse):
│    objective_statement: str | None
│    objective_category: str | None
│    task_plan_json: dict | None
│    mission_outcome_json: dict | None
│    planning_thinking_trace: str | None
│    task_executions: list[TaskExecutionResponse]
│    decisions: list[MissionDecisionResponse]
│class MissionListResponse(BaseModel):
│    missions: list[MissionRecordResponse]
│    total: int
│    page_size: int
│    offset: int

modules/backend/schemas/mission.py (78 lines):
│class MissionCreate(BaseModel):
│    objective: str
│    roster_ref: str
│    complexity_tier: str
│    triggered_by: str
│    cost_ceiling_usd: float | None
│    upstream_context: dict | None
│class MissionResponse(BaseModel):
│    id: str
│    playbook_run_id: str | None
│    playbook_step_id: str | None
│    objective: str
│    roster_ref: str
│    complexity_tier: str
│    status: str
│    session_id: str
│    trigger_type: str
│    triggered_by: str
│    total_cost_usd: float
│    cost_ceiling_usd: float | None
│    started_at: str | None
│    completed_at: str | None
│class MissionDetailResponse(BaseModel):
│    id: str
│    playbook_run_id: str | None
│    playbook_step_id: str | None
│    objective: str
│    roster_ref: str
│    complexity_tier: str
│    status: str
│    session_id: str
│    trigger_type: str
│    triggered_by: str
│    upstream_context: dict
│    context: dict
│    total_cost_usd: float
│    cost_ceiling_usd: float | None
│    started_at: str | None
│    completed_at: str | None
│    result_summary: str | None
│    error_data: dict | None
│class MissionStateSummary(BaseModel):
│    mission_id: str
│    objective: str
│    status: str
│    roster_ref: str
│    total_cost_usd: float
│    cost_ceiling_usd: float | None
│    started_at: str | None
│    elapsed_seconds: float | None

modules/backend/schemas/__init__.py (16 lines):

modules/backend/schemas/project.py (92 lines):
│class ProjectCreate(BaseModel):
│    name: str
│    description: str
│    owner_id: str
│    team_id: str | None
│    default_roster: str
│    budget_ceiling_usd: float | None
│    repo_url: str | None
│    repo_root: str | None
│class ProjectUpdate(BaseModel):
│    description: str | None
│    status: str | None
│    default_roster: str | None
│    budget_ceiling_usd: float | None
│    repo_url: str | None
│    repo_root: str | None
│class ProjectResponse(BaseModel):
│    id: str
│    name: str
│    description: str
│    status: str
│    owner_id: str
│    team_id: str | None
│    default_roster: str
│    budget_ceiling_usd: float | None
│    repo_url: str | None
│    repo_root: str | None
│    created_at: str
│    updated_at: str
│class ProjectMemberResponse(BaseModel):
│    id: str
│    project_id: str
│    user_id: str
│    role: str
│    created_at: str

modules/backend/schemas/project_context.py (73 lines):
│class ContextUpdateOp(BaseModel):
│    op: str
│    path: str
│    value: Any
│    reason: str
│class ContextUpdateRequest(BaseModel):
│    context_updates: list[ContextUpdateOp]
│class PCDResponse(BaseModel):
│    project_id: str
│    version: int
│    size_characters: int
│    size_tokens: int
│    context_data: dict
│class ContextChangeResponse(BaseModel):
│    id: str
│    version: int
│    change_type: str
│    path: str
│    old_value: Any | None
│    new_value: Any | None
│    agent_id: str | None
│    mission_id: str | None
│    task_id: str | None
│    reason: str
│    created_at: str


## backend.repositories

modules/backend/repositories/base.py (116 lines):
│class BaseRepository:
│    model: type[ModelType]
│    def __init__(session: AsyncSession) -> None
│    def get_by_id(id: str | UUID) -> ModelType
│    def get_by_id_or_none(id: str | UUID) -> ModelType | None
│    def get_all(limit: int, offset: int) -> list[ModelType]
│    def create() -> ModelType
│    def update(id: str | UUID) -> ModelType
│    def delete(id: str | UUID) -> None
│    def exists(id: str | UUID) -> bool
│    def count() -> int

modules/backend/repositories/project_context.py (89 lines):
│class ProjectContextRepository:
│    def get_by_project_id(project_id: str) -> ProjectContext | None
│    def update_context(project_id: str, context_data: dict, new_version: int, size_characters: int, size_tokens: int) -> int
│class ContextChangeRepository:
│    def list_by_context(context_id: str, limit: int) -> list[ContextChange]
│    def list_by_agent(context_id: str, agent_id: str, limit: int) -> list[ContextChange]

modules/backend/repositories/note.py (137 lines):
│class NoteRepository:
│    def __init__(session: AsyncSession) -> None
│    def get_all_active(limit: int, offset: int) -> list[Note]
│    def get_archived(limit: int, offset: int) -> list[Note]
│    def search_by_title(query: str, limit: int) -> list[Note]
│    def archive(id: str) -> Note
│    def unarchive(id: str) -> Note
│    def count_active() -> int

modules/backend/repositories/project.py (89 lines):
│class ProjectRepository:
│    def get_by_name(name: str) -> Project | None
│    def list_by_owner(owner_id: str, status: ProjectStatus | None, limit: int, offset: int) -> list[Project]
│    def list_active(limit: int, offset: int) -> list[Project]
│class ProjectMemberRepository:
│    def get_members(project_id: str) -> list[ProjectMember]
│    def get_membership(project_id: str, user_id: str) -> ProjectMember | None

modules/backend/repositories/mission_record.py (140 lines):
│class MissionRecordRepository:
│    def __init__(session: AsyncSession) -> None
│    def get_with_details(mission_id: str) -> MissionRecord | None
│    def get_by_session(session_id: str) -> list[MissionRecord]
│    def list_missions(status: MissionRecordStatus | None, roster_name: str | None, objective_category: str | None, limit: int, offset: int) -> tuple[list[MissionRecord], int]
│    def get_decisions(mission_id: str) -> list[MissionDecision]
│    def get_task_executions(mission_id: str) -> list[TaskExecution]
│    def get_cost_by_model(mission_id: str) -> dict[str, float]
│    def get_replan_chain(mission_id: str) -> list[MissionRecord]

modules/backend/repositories/project_history.py (73 lines):
│class ProjectDecisionRepository:
│    def list_by_domain(project_id: str, domain: str, limit: int) -> list[ProjectDecision]
│    def list_active(project_id: str, limit: int) -> list[ProjectDecision]
│class MilestoneSummaryRepository:
│    def list_by_project(project_id: str, limit: int) -> list[MilestoneSummary]

modules/backend/repositories/session.py (211 lines):
│class SessionRepository:
│    def __init__(session: AsyncSession) -> None
│    def get_active_by_user(user_id: str, limit: int, offset: int) -> list[Session]
│    def get_by_user(user_id: str | None, status_filter: str | None, limit: int, offset: int) -> list[Session]
│    def count_by_user(user_id: str | None, status_filter: str | None) -> int
│    def update_last_activity(session_id: str, new_expires_at: datetime | None) -> None
│    def find_expired(now: datetime | None) -> list[Session]
│    def bind_channel(session_id: str, channel_type: str, channel_id: str) -> SessionChannel
│    def unbind_channel(session_id: str, channel_type: str, channel_id: str) -> None
│    def get_session_by_channel(channel_type: str, channel_id: str) -> Session | None
│    def add_message() -> SessionMessage
│    def get_messages(session_id: str, limit: int, offset: int) -> list[SessionMessage]
│    def count_messages(session_id: str) -> int

modules/backend/repositories/mission.py (96 lines):
│class MissionRepository:
│    def __init__(session: AsyncSession) -> None
│    def get_by_session(session_id: str) -> list[Mission]
│    def get_by_playbook_run(playbook_run_id: str) -> list[Mission]
│    def count_active() -> int
│    def list_missions(status: MissionState | None, playbook_run_id: str | None, limit: int, offset: int) -> tuple[list[Mission], int]

modules/backend/repositories/playbook_run.py (57 lines):
│class PlaybookRunRepository:
│    def __init__(session: AsyncSession) -> None
│    def list_runs(playbook_name: str | None, status: PlaybookRunState | None, limit: int, offset: int) -> tuple[list[PlaybookRun], int]

modules/backend/repositories/__init__.py (4 lines):


## backend.api

modules/backend/api/v1/endpoints/__init__.py (1 lines):

modules/backend/api/__init__.py (1 lines):

modules/backend/api/v1/__init__.py (26 lines):

modules/backend/api/health.py (227 lines):
│def check_database() -> dict[str, Any]
│def check_redis() -> dict[str, Any]
│@router.get
│def health_check() -> dict[str, str]
│@router.get
│def readiness_check() -> dict[str, Any]
│@router.get
│def detailed_health_check() -> dict[str, Any]

modules/backend/api/v1/endpoints/agents.py (152 lines):
│class ChatRequest(BaseModel):
│    message: str
│    agent: str | None
│    session_id: str | None
│class ChatResponse(BaseModel):
│    agent_name: str
│    output: str
│    session_id: str | None
│class AgentInfo(BaseModel):
│    agent_name: str
│    description: str
│    keywords: list[str]
│    tools: list[str]
│@router.post
│def agent_chat(data: ChatRequest, db: DbSession, request_id: RequestId) -> ApiResponse[ChatResponse]
│@router.post
│def agent_chat_stream(data: ChatRequest, db: DbSession) -> StreamingResponse
│@router.get
│def agent_registry(request_id: RequestId) -> ApiResponse[list[AgentInfo]]

modules/backend/api/v1/endpoints/missions.py (350 lines):
│@router.get
│def list_missions(db: DbSession, request_id: RequestId, status: str | None, ...) -> ApiResponse
│@router.get
│def get_mission(mission_id: str, db: DbSession, request_id: RequestId) -> ApiResponse
│@router.get
│def get_mission_decisions(mission_id: str, db: DbSession, request_id: RequestId) -> ApiResponse
│@router.get
│def get_mission_cost(mission_id: str, db: DbSession, request_id: RequestId) -> ApiResponse
│@router.post
│def execute_mission(mission_id: str, db: DbSession, request_id: RequestId) -> ApiResponse
│def _execute_direct(mission_id: str, db: DbSession, request_id: RequestId) -> ApiResponse
│def _execute_via_temporal(mission_id: str, db: DbSession, request_id: RequestId, ...) -> ApiResponse
│@router.post
│def submit_approval(mission_id: str, decision: str, responder_id: str, ...) -> ApiResponse
│@router.get
│def get_mission_status(mission_id: str, db: DbSession, request_id: RequestId) -> ApiResponse

modules/backend/api/v1/endpoints/notes.py (193 lines):
│@router.post
│def create_note(data: NoteCreate, db: DbSession, request_id: RequestId) -> ApiResponse[NoteResponse]
│@router.get
│def list_notes(db: DbSession, request_id: RequestId, pagination: PaginationParams, ...) -> dict[str, Any]
│@router.get
│def search_notes(db: DbSession, request_id: RequestId, q: str, ...) -> ApiResponse[list[NoteListResponse]]
│@router.get
│def get_note(note_id: str, db: DbSession, request_id: RequestId) -> ApiResponse[NoteResponse]
│@router.patch
│def update_note(note_id: str, data: NoteUpdate, db: DbSession, ...) -> ApiResponse[NoteResponse]
│@router.delete
│def delete_note(note_id: str, db: DbSession, request_id: RequestId) -> None
│@router.post
│def archive_note(note_id: str, db: DbSession, request_id: RequestId) -> ApiResponse[NoteResponse]
│@router.post
│def unarchive_note(note_id: str, db: DbSession, request_id: RequestId) -> ApiResponse[NoteResponse]

modules/backend/api/v1/endpoints/playbooks.py (217 lines):
│def _get_playbook_service() -> PlaybookService
│def _get_mission_service(db: DbSession) -> MissionService
│@router.get
│def list_playbooks(request_id: RequestId, enabled_only: bool) -> ApiResponse
│@router.get
│def get_playbook(playbook_name: str, request_id: RequestId) -> ApiResponse
│@router.post
│def create_mission(data: MissionCreate, db: DbSession, request_id: RequestId) -> ApiResponse
│@router.get
│def list_missions(db: DbSession, request_id: RequestId, status: str | None, ...) -> ApiResponse
│@router.get
│def get_mission(mission_id: str, db: DbSession, request_id: RequestId) -> ApiResponse
│@router.post
│def cancel_mission(mission_id: str, db: DbSession, request_id: RequestId, ...) -> ApiResponse

modules/backend/api/v1/endpoints/sessions.py (292 lines):
│def _to_response(session) -> SessionResponse
│@router.post
│def create_session(data: SessionCreate, db: DbSession, request_id: RequestId, ...) -> ApiResponse[SessionResponse]
│@router.get
│def get_session(session_id: str, db: DbSession, request_id: RequestId) -> ApiResponse[SessionResponse]
│@router.patch
│def update_session(session_id: str, data: SessionUpdate, db: DbSession, ...) -> ApiResponse[SessionResponse]
│@router.get
│def list_sessions(db: DbSession, request_id: RequestId, pagination: PaginationParams, ...) -> dict
│@router.post
│def suspend_session(session_id: str, db: DbSession, request_id: RequestId, ...) -> ApiResponse[SessionResponse]
│@router.post
│def resume_session(session_id: str, db: DbSession, request_id: RequestId) -> ApiResponse[SessionResponse]
│@router.post
│def complete_session(session_id: str, db: DbSession, request_id: RequestId) -> ApiResponse[SessionResponse]
│@router.post
│def bind_channel(session_id: str, data: ChannelBindRequest, db: DbSession, ...) -> ApiResponse[ChannelResponse]
│@router.delete
│def unbind_channel(session_id: str, channel_type: str, channel_id: str, ...) -> None
│@router.get
│def get_session_by_channel(channel_type: str, channel_id: str, db: DbSession, ...) -> ApiResponse[SessionResponse]
│@router.get
│def get_messages(session_id: str, db: DbSession, request_id: RequestId, ...) -> dict
│@router.post
│def send_message_stream(session_id: str, data: SessionMessageCreate, db: DbSession) -> StreamingResponse


## backend.events

modules/backend/events/types.py (323 lines):
│class SessionEvent(BaseModel):
│    event_id: uuid.UUID
│    event_type: str
│    session_id: uuid.UUID
│    timestamp: datetime
│    source: str
│    correlation_id: str | None
│    trace_id: str | None
│    metadata: dict
│class UserMessageEvent(SessionEvent):
│    event_type: str
│    content: str
│    channel: str
│    attachments: list[str]
│class UserApprovalEvent(SessionEvent):
│    event_type: str
│    decision: str
│    approval_request_id: str
│    reason: str | None
│    modified_params: dict
│class AgentThinkingEvent(SessionEvent):
│    event_type: str
│    agent_id: str
│class AgentToolCallEvent(SessionEvent):
│    event_type: str
│    agent_id: str
│    tool_name: str
│    tool_args: dict
│    tool_call_id: str
│class AgentToolResultEvent(SessionEvent):
│    event_type: str
│    agent_id: str
│    tool_name: str
│    tool_call_id: str
│    result: str | None
│    status: str
│    error_detail: str | None
│class AgentResponseChunkEvent(SessionEvent):
│    event_type: str
│    agent_id: str
│    content: str
│    is_final: bool
│class AgentResponseCompleteEvent(SessionEvent):
│    event_type: str
│    agent_id: str
│    full_content: str
│    input_tokens: int
│    output_tokens: int
│    cost_usd: float
│    model: str
│class ApprovalRequestedEvent(SessionEvent):
│    event_type: str
│    approval_request_id: str
│    agent_id: str
│    action: str
│    context: dict
│    allowed_decisions: list[str]
│    responder_options: list[str]
│    timeout_seconds: int
│class ApprovalResponseEvent(SessionEvent):
│    event_type: str
│    approval_request_id: str
│    decision: str
│    responder_type: str
│    responder_id: str | None
│    reason: str | None
│    modified_params: dict
│class PlanCreatedEvent(SessionEvent):
│    event_type: str
│    plan_id: str
│    goal: str
│    step_count: int
│class PlanStepStartedEvent(SessionEvent):
│    event_type: str
│    plan_id: str
│    step_id: str
│    step_name: str
│    assigned_agent: str
│class PlanStepCompletedEvent(SessionEvent):
│    event_type: str
│    plan_id: str
│    step_id: str
│    result_summary: str
│    status: str
│class PlanRevisedEvent(SessionEvent):
│    event_type: str
│    plan_id: str
│    revision_reason: str
│    steps_added: int
│    steps_removed: int
│    steps_modified: int
│class CostUpdateEvent(SessionEvent):
│    event_type: str
│    input_tokens: int
│    output_tokens: int
│    cost_usd: float
│    cumulative_cost_usd: float
│    budget_remaining_usd: float | None
│    model: str
│    source_event_type: str
│class PlaybookRunStartedEvent(SessionEvent):
│    event_type: str
│    playbook_run_id: str
│    playbook_name: str
│    playbook_version: int
│    step_count: int
│    trigger_type: str
│    triggered_by: str
│class PlaybookMissionStartedEvent(SessionEvent):
│    event_type: str
│    playbook_run_id: str
│    mission_id: str
│    step_id: str
│    roster_ref: str
│    complexity_tier: str
│class PlaybookMissionCompletedEvent(SessionEvent):
│    event_type: str
│    playbook_run_id: str
│    mission_id: str
│    step_id: str
│    success: bool
│    cost_usd: float
│class PlaybookRunCompletedEvent(SessionEvent):
│    event_type: str
│    playbook_run_id: str
│    playbook_name: str
│    total_cost_usd: float
│    mission_count: int
│    elapsed_seconds: float | None
│    result_summary: str | None
│class PlaybookRunFailedEvent(SessionEvent):
│    event_type: str
│    playbook_run_id: str
│    playbook_name: str
│    error: str
│    failed_step: str | None
│    total_cost_usd: float
│def deserialize_event(data: dict) -> SessionEvent | None

modules/backend/events/schemas.py (33 lines):
│class EventEnvelope(BaseModel):
│    event_id: str
│    event_type: str
│    event_version: int
│    timestamp: str
│    source: str
│    correlation_id: str
│    trace_id: str | None
│    session_id: str | None
│    payload: dict

modules/backend/events/bus.py (98 lines):
│class SessionEventBus:
│    def __init__(redis: Redis) -> None
│    def _channel_name(session_id: uuid.UUID) -> str
│    def publish(event: SessionEvent) -> None
│    def subscribe(session_id: uuid.UUID) -> AsyncIterator[SessionEvent]

modules/backend/events/publishers.py (47 lines):
│class EventPublisher:
│    def publish(stream: str, event: EventEnvelope) -> None

modules/backend/events/__init__.py (47 lines):

modules/backend/events/broker.py (91 lines):
│def create_event_broker() -> 'RedisBroker'
│def get_event_broker() -> 'RedisBroker'
│def create_event_app() -> 'FastStream'

modules/backend/events/middleware.py (106 lines):
│class EventObservabilityMiddleware:
│    def __init__() -> None
│    def on_receive() -> None
│    def after_processed(exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any | None) -> bool | None
│    def __aenter__() -> 'EventObservabilityMiddleware'
│    def __aexit__(exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any | None) -> bool | None
│    def consume_scope(call_next: Callable, msg: Any) -> Any


## backend.gateway

modules/backend/gateway/adapters/base.py (115 lines):
│class ChannelAdapter(ABC):
│    def channel_name() -> str
│    def deliver_response(response: AgentResponse) -> bool
│    def format_text(text: str) -> str
│    def max_message_length() -> int
│    def chunk_message(text: str) -> list[str]
│class AgentResponse:
│    text: str
│    session_key: str
│    channel: str
│    reply_to_message_id: str | None
│    media: list[dict] | None
│    cost_usd: float | None
│    token_input: int | None
│    token_output: int | None
│    duration_ms: int | None
│    agent_name: str | None
│class ChannelMessage:
│    channel: str
│    user_id: str
│    text: str
│    session_key: str
│    message_id: str | None
│    group_id: str | None
│    is_group: bool
│    reply_to_message_id: str | None
│    media: list[dict] | None
│    raw_event: dict | None
│    received_at: str

modules/backend/gateway/adapters/__init__.py (13 lines):

modules/backend/gateway/__init__.py (1 lines):

modules/backend/gateway/adapters/telegram.py (110 lines):
│class TelegramAdapter(ChannelAdapter):
│    def __init__(bot: 'Bot') -> None
│    def channel_name() -> str
│    def max_message_length() -> int
│    def deliver_response(response: AgentResponse) -> bool
│    def format_text(text: str) -> str
│def _convert_markdown_bold(text: str) -> str
│def _convert_markdown_italic(text: str) -> str
│def _convert_markdown_code(text: str) -> str

modules/backend/gateway/registry.py (68 lines):
│def _register_enabled_adapters() -> None
│def get_adapter(channel_name: str) -> ChannelAdapter | None
│def get_all_adapters() -> dict[str, ChannelAdapter]
│def is_channel_enabled(channel_name: str) -> bool

modules/backend/gateway/security/__init__.py (1 lines):

modules/backend/gateway/security/rate_limiter.py (118 lines):
│class RateLimitResult:
│    def __init__(allowed: bool, retry_after_seconds: int) -> None
│class GatewayRateLimiter:
│    def __init__() -> None
│    def check(channel: str, user_id: str) -> RateLimitResult
│    def _get_limits(channel: str) -> dict | None
│    def _check_window(key: str, store: dict[str, list[float]], now: float, window_seconds: int, max_requests: int) -> RateLimitResult
│def get_rate_limiter() -> GatewayRateLimiter

modules/backend/gateway/security/startup_checks.py (137 lines):
│class StartupSecurityError(RuntimeError):
│def run_startup_checks() -> None
│def _check_secret_strength(settings: Settings, security_config: SecuritySchema, features: FeaturesSchema, ...) -> None
│def _check_channel_secrets(settings: Settings, features: FeaturesSchema, errors: list[str]) -> None
│def _check_production_safety(app_config: AppConfig, is_production: bool, errors: list[str]) -> None
│def _check_channel_allowlists(app_config: AppConfig, features: FeaturesSchema, errors: list[str]) -> None


## backend.temporal

modules/backend/temporal/models.py (82 lines):
│class MissionWorkflowInput:
│    mission_id: str
│    session_id: str
│    mission_brief: str
│    roster_name: str
│    mission_budget_usd: float
│    approval_timeout_seconds: int
│    escalation_timeout_seconds: int
│    notification_timeout_seconds: int
│class WorkflowStatus:
│    mission_id: str
│    workflow_status: str
│    mission_status: str | None
│    total_cost_usd: float
│    waiting_for_approval: bool
│    error: str | None
│class ApprovalDecision:
│    decision: str
│    responder_type: str
│    responder_id: str
│    reason: str | None
│class NotificationPayload:
│    channel: str
│    recipient: str
│    title: str
│    body: str
│    action_url: str
│    urgency: str
│class MissionExecutionResult:
│    mission_id: str
│    status: str
│    total_cost_usd: float
│    total_duration_seconds: float
│    task_count: int
│    success_count: int
│    failed_count: int
│    outcome_json: dict
│class MissionModification:
│    instruction: str
│    reasoning: str

modules/backend/temporal/activities.py (142 lines):
│@activity.defn
│def execute_mission(input: MissionWorkflowInput) -> MissionExecutionResult
│@activity.defn
│def persist_mission_outcome(mission_id: str, session_id: str, roster_name: str, ...) -> bool
│@activity.defn
│def send_notification(payload: NotificationPayload) -> bool

modules/backend/temporal/client.py (55 lines):
│def get_temporal_config()
│def get_temporal_client()

modules/backend/temporal/workflow.py (247 lines):
│class AgentMissionWorkflow:
│    def __init__() -> None
│    def submit_approval(decision: ApprovalDecision) -> None
│    def get_status() -> WorkflowStatus
│    def run(input: MissionWorkflowInput) -> WorkflowStatus
│    def _wait_for_approval_with_escalation(input: MissionWorkflowInput, notification_timeout: timedelta) -> None

modules/backend/temporal/__init__.py (1 lines):

modules/backend/temporal/worker.py (54 lines):
│def start_worker() -> None
│def main() -> None


## backend.migrations

modules/backend/migrations/env.py (119 lines):
│def get_database_url() -> str
│def run_migrations_offline() -> None
│def do_run_migrations(connection: Connection) -> None
│def run_async_migrations() -> None
│def run_migrations_online() -> None

modules/backend/migrations/versions/001_add_mission_record_tables.py (116 lines):
│def upgrade() -> None
│def downgrade() -> None

modules/backend/migrations/versions/0fbf5d6801d8_add_summarized_flag_to_mission_records.py (32 lines):
│def upgrade() -> None
│def downgrade() -> None

modules/backend/migrations/versions/1dc5c2cc9d93_add_project_context_layer_tables.py (156 lines):
│def upgrade() -> None
│def downgrade() -> None

modules/backend/migrations/versions/27c14af891b2_add_sessions_notes_missions_playbook_.py (407 lines):
│def upgrade() -> None
│def downgrade() -> None

modules/backend/migrations/versions/92813afeaf50_add_foreign_key_constraints_to_project_.py (44 lines):
│def upgrade() -> None
│def downgrade() -> None


## backend.tasks

modules/backend/tasks/__init__.py (28 lines):
│def __getattr__(name: str)

modules/backend/tasks/broker.py (96 lines):
│def create_broker() -> 'ListQueueBroker'
│def get_broker() -> 'ListQueueBroker'
│def __getattr__(name: str)

modules/backend/tasks/example.py (236 lines):
│def send_notification(user_id: str, message: str, channel: str) -> dict[str, Any]
│def process_data(data: dict[str, Any], operation: str) -> dict[str, Any]
│def cleanup_expired_records(table_name: str, older_than_days: int) -> dict[str, Any]
│def generate_report(report_type: str, parameters: dict[str, Any], user_id: str) -> dict[str, Any]
│def register_tasks() -> dict[str, Any]

modules/backend/tasks/scheduled.py (203 lines):
│def daily_cleanup(older_than_days: int) -> dict[str, Any]
│def hourly_health_check() -> dict[str, Any]
│def weekly_report_generation() -> dict[str, Any]
│def metrics_aggregation(interval_minutes: int) -> dict[str, Any]
│def register_scheduled_tasks() -> dict[str, Any]

modules/backend/tasks/scheduler.py (79 lines):
│def create_scheduler() -> 'TaskiqScheduler'
│def get_scheduler() -> 'TaskiqScheduler'
│def __getattr__(name: str)


## root

modules/__init__.py (6 lines):

