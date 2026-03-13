# Code Map — BFA Reference Architecture

Auto-generated structural overview ranked by PageRank importance.
Read this first to understand the codebase before diving into files.

- **205 files** | **28,378 lines** | **scope:** `modules/`
- Config schemas excluded — see `config/settings/*.yaml` for data shapes
- Full detail: `.codemap/map.json` or `.codemap/map.md`

Regenerate: `python scripts/generate_code_map.py --format markdown --scope modules/ --exclude "**/config_schema.py" --max-tokens 4096 -o CODEMAP.md`

---

modules/backend/core/config.py (253 lines):
│class Settings(BaseSettings):
│    db_password: str
│    redis_password: str
│    jwt_secret: str
│    api_key_salt: str
│    telegram_bot_token: str
│    telegram_webhook_secret: str
│    anthropic_api_key: str
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

modules/backend/core/__init__.py (1 lines):

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

modules/backend/models/base.py (53 lines):
│class Base(DeclarativeBase):
│class UUIDMixin:
│    id: Mapped[str]
│class TimestampMixin:
│    created_at: Mapped[datetime]
│    updated_at: Mapped[datetime]

modules/backend/agents/__init__.py (1 lines):

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

modules/backend/agents/mission_control/helpers.py (388 lines):
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

modules/telegram/keyboards/common.py (195 lines):
│def get_main_menu_keyboard(user_role: str) -> ReplyKeyboardMarkup
│def get_cancel_keyboard() -> ReplyKeyboardMarkup
│def get_confirmation_keyboard(action_id: str) -> InlineKeyboardMarkup
│def get_pagination_keyboard(list_type: str, current_page: int, total_pages: int, ...) -> InlineKeyboardMarkup
│def get_yes_no_keyboard(action_id: str) -> InlineKeyboardMarkup
│def get_back_keyboard(menu: str) -> InlineKeyboardMarkup

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

modules/backend/agents/mission_control/models.py (148 lines):
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
