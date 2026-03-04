"""
Mission Control.

Routes user messages to agents, enforces budgets, manages sessions,
and yields typed events. Streaming is the default and only path.

Mission control is infrastructure, not intelligence (P6). It does not
have a personality, make domain decisions, or call LLMs. It is a state machine.

Public interface:
    handle(session_id, message, ...) -> AsyncIterator[SessionEvent]
    collect(session_id, message, ...) -> dict
    list_agents() -> list[dict]
"""

import importlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai import UserError, UsageLimits
from pydantic_ai.models import Model

from modules.backend.agents.config_schema import AgentConfigSchema, AgentModelSchema
from modules.backend.agents.mission_control.cost import compute_cost_usd, estimate_cost
from modules.backend.agents.mission_control.history import (
    model_messages_to_session_creates,
    session_messages_to_model_history,
)
from modules.backend.agents.mission_control.middleware import (
    _load_mission_control_config,
    check_guardrails,
)
from modules.backend.agents.mission_control.models import MissionControlRequest
from modules.backend.agents.mission_control.registry import get_registry
from modules.backend.agents.mission_control.router import RuleBasedRouter
from modules.backend.agents.deps.base import (
    BaseAgentDeps,
    FileScope,
    HealthAgentDeps,
    QaAgentDeps,
)
from modules.backend.core.config import find_project_root, get_app_config, get_settings
from modules.backend.core.logging import get_logger
from modules.backend.events.types import (
    AgentResponseChunkEvent,
    AgentResponseCompleteEvent,
    AgentThinkingEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    CostUpdateEvent,
    SessionEvent,
    UserMessageEvent,
)
from modules.backend.schemas.session import SessionMessageCreate
from modules.backend.services.session import SessionService

logger = get_logger(__name__)



def _build_model(config_model: str | AgentModelSchema) -> Model:
    """Construct a PydanticAI Model from a config string or AgentModelSchema.

    Accepts either a flat 'provider:model_name' string (legacy) or a structured
    AgentModelSchema with pinned temperature and max_tokens. API keys are injected
    from centralized settings — never from os.environ.
    """
    if isinstance(config_model, AgentModelSchema):
        model_name = config_model.name
    else:
        model_name = config_model

    settings = get_settings()

    if model_name.startswith("anthropic:"):
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        bare_name = model_name.split(":", 1)[1]
        provider = AnthropicProvider(api_key=settings.anthropic_api_key)
        return AnthropicModel(bare_name, provider=provider)

    raise ValueError(f"Unsupported model provider in '{model_name}'. Expected 'anthropic:model_name'.")



def assemble_instructions(category: str, name: str) -> str:
    """Compose layered prompt: organization -> category -> agent.

    Reads markdown files from config/prompts/ and concatenates them.
    Missing layers are silently skipped.
    """
    project_root = find_project_root()
    prompts_dir = project_root / "config" / "prompts"
    layers: list[str] = []

    org_dir = prompts_dir / "organization"
    if org_dir.exists():
        for org_file in sorted(org_dir.glob("*.md")):
            layers.append(org_file.read_text(encoding="utf-8").strip())

    cat_file = prompts_dir / "categories" / f"{category}.md"
    if cat_file.exists():
        layers.append(cat_file.read_text(encoding="utf-8").strip())

    agent_file = prompts_dir / "agents" / category / name / "system.md"
    if agent_file.exists():
        layers.append(agent_file.read_text(encoding="utf-8").strip())

    return "\n\n".join(layers)



def build_deps_from_config(agent_config: AgentConfigSchema) -> dict[str, Any]:
    """Build common dep fields from agent YAML config."""
    scope = FileScope(
        read_paths=agent_config.scope.read,
        write_paths=agent_config.scope.write,
    )
    return {
        "project_root": find_project_root(),
        "scope": scope,
        "config": agent_config,
    }


def _build_agent_deps(
    agent_name: str,
    agent_config: AgentConfigSchema,
    session_id: str | None = None,
) -> BaseAgentDeps:
    """Build the appropriate deps dataclass for a given agent."""
    common = build_deps_from_config(agent_config)
    common["session_id"] = session_id
    category = agent_name.split(".")[0]

    if category == "system" and "health" in agent_name:
        return HealthAgentDeps(**common, app_config=get_app_config())
    if category == "code" and "qa" in agent_name:
        return QaAgentDeps(**common)

    return BaseAgentDeps(**common)



def _get_usage_limits() -> UsageLimits:
    """Build UsageLimits from mission_control.yaml."""
    config = _load_mission_control_config()
    return UsageLimits(
        request_limit=config.limits.max_requests_per_task,
        total_tokens_limit=config.limits.max_tokens_per_task,
    )



def _import_agent_module(agent_name: str) -> Any:
    """Dynamically import an agent module from the registry."""
    registry = get_registry()
    module_path = registry.resolve_module_path(agent_name)
    return importlib.import_module(module_path)



def _resolve_agent(session: Any, message: str) -> str:
    """Determine which agent handles this message.

    Priority: session.agent_id > keyword routing > fallback.
    """
    registry = get_registry()

    if session.agent_id and registry.has(session.agent_id):
        return session.agent_id

    router = RuleBasedRouter(registry)
    request = MissionControlRequest(user_input=message)
    agent_name = router.route(request)

    if agent_name is not None:
        return agent_name

    mc_config = _load_mission_control_config()
    fallback = mc_config.routing.fallback_agent
    if fallback and registry.has(fallback):
        return fallback

    available = ", ".join(c["agent_name"] for c in registry.list_all()) or "none"
    raise ValueError(f"No agent matched. Available agents: {available}.")


async def _publish(event_bus: Any, event: SessionEvent) -> None:
    """Publish event to bus if available. Non-critical."""
    if event_bus is None:
        return
    try:
        await event_bus.publish(event)
    except Exception:
        logger.debug("Event bus publish failed", exc_info=True)


async def _persist_messages(
    session_service: SessionService,
    session_id: str,
    creates: list[SessionMessageCreate],
) -> None:
    """Persist messages to session. Non-critical."""
    try:
        for create in creates:
            await session_service.add_message(session_id, create)
    except Exception:
        logger.warning("Failed to persist session messages", exc_info=True)


def _get_model_name(config_model: str | AgentModelSchema) -> str:
    """Extract model name string from config model."""
    if isinstance(config_model, AgentModelSchema):
        return config_model.name
    return config_model



def list_agents() -> list[dict[str, Any]]:
    """List all available agents with their metadata."""
    return get_registry().list_all()


async def handle(
    session_id: str,
    message: str,
    *,
    session_service: SessionService,
    event_bus: Any | None = None,
    channel: str = "api",
    sender_id: str | None = None,
) -> AsyncIterator[SessionEvent]:
    """Universal streaming mission control entry point.

    All channels call this function:
    - REST/SSE: stream events directly
    - WebSocket: forward events to socket
    - Telegram: buffer chunks, edit message
    - TUI: render events in panels
    - CLI: print events to terminal
    - Temporal Activity: collect events, persist state

    Yields SessionEvent instances as the agent works.
    Error handling yields events instead of throwing — the stream
    always terminates cleanly.
    """
    sid = uuid.UUID(session_id) if not isinstance(session_id, uuid.UUID) else session_id
    source = "mission_control"

    try:
        # 1. Validate session exists
        session = await session_service.get_session(session_id)

        # 2. Enforce budget
        model_str = ""
        try:
            agent_name = _resolve_agent(session, message)
            agent_config = get_registry().get(agent_name)
            model_str = _get_model_name(agent_config.model)
            estimated = estimate_cost(len(message) * 4, model_str)
            await session_service.enforce_budget(session_id, estimated_cost=estimated)
        except Exception as budget_err:
            from modules.backend.core.exceptions import BudgetExceededError
            if isinstance(budget_err, BudgetExceededError):
                yield CostUpdateEvent(
                    session_id=sid,
                    source=source,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    cumulative_cost_usd=session.total_cost_usd,
                    budget_remaining_usd=0.0,
                    model=model_str,
                    metadata={"budget_exceeded": True},
                )
                return
            raise

        # 3. Yield UserMessageEvent
        user_event = UserMessageEvent(
            session_id=sid,
            source=source,
            content=message,
            channel=channel,
        )
        yield user_event
        await _publish(event_bus, user_event)

        # 4. Apply guardrails
        check_guardrails(message, agent_config)

        # 5. Yield AgentThinkingEvent
        thinking_event = AgentThinkingEvent(
            session_id=sid,
            source=source,
            agent_id=agent_name,
        )
        yield thinking_event
        await _publish(event_bus, thinking_event)

        # 6. Build agent and load history
        registry = get_registry()
        model = _build_model(agent_config.model)
        agent = registry.get_instance(agent_name, model)
        deps = _build_agent_deps(agent_name, agent_config, session_id)
        limits = _get_usage_limits()

        # Load conversation history
        history_messages, _ = await session_service.get_messages(session_id, limit=100)
        model_history = session_messages_to_model_history(history_messages)

        # 7. Execute agent with streaming
        full_content = ""
        input_tokens = 0
        output_tokens = 0
        cost_usd = 0.0

        async with agent.run_stream(
            message,
            message_history=model_history or None,
            deps=deps,
            usage_limits=limits,
        ) as stream:
            # Text output agents: stream text deltas.
            # Structured output agents: stream_text() raises UserError,
            # so fall back to get_output() and serialize.
            try:
                async for text in stream.stream_text(delta=True):
                    full_content += text
                    chunk_event = AgentResponseChunkEvent(
                        session_id=sid,
                        source=source,
                        agent_id=agent_name,
                        content=text,
                    )
                    yield chunk_event
                    await _publish(event_bus, chunk_event)
            except UserError:
                output = await stream.get_output()
                if isinstance(output, str):
                    full_content = output
                elif hasattr(output, "model_dump_json"):
                    full_content = output.model_dump_json()
                else:
                    full_content = str(output)

            # After streaming completes, get usage
            usage = stream.usage()
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            cost_usd = compute_cost_usd(input_tokens, output_tokens, model_str)

            # Extract tool events from new_messages (retrospective)
            try:
                new_msgs = stream.new_messages()
                for msg in new_msgs:
                    from pydantic_ai.messages import ModelResponse, ToolCallPart, ModelRequest, ToolReturnPart
                    if isinstance(msg, ModelResponse):
                        for part in msg.parts:
                            if isinstance(part, ToolCallPart):
                                tool_event = AgentToolCallEvent(
                                    session_id=sid,
                                    source=source,
                                    agent_id=agent_name,
                                    tool_name=part.tool_name,
                                    tool_args={"raw": part.args if isinstance(part.args, str) else str(part.args)},
                                    tool_call_id=part.tool_call_id or str(uuid.uuid4()),
                                )
                                yield tool_event
                                await _publish(event_bus, tool_event)
                    elif isinstance(msg, ModelRequest):
                        for part in msg.parts:
                            if isinstance(part, ToolReturnPart):
                                result_event = AgentToolResultEvent(
                                    session_id=sid,
                                    source=source,
                                    agent_id=agent_name,
                                    tool_name=part.tool_name,
                                    tool_call_id=part.tool_call_id or "",
                                    result=part.content if isinstance(part.content, str) else str(part.content),
                                )
                                yield result_event
                                await _publish(event_bus, result_event)
            except Exception:
                logger.debug("Failed to extract tool events", exc_info=True)

        # 8. Yield complete event
        complete_event = AgentResponseCompleteEvent(
            session_id=sid,
            source=source,
            agent_id=agent_name,
            full_content=full_content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            model=model_str,
        )
        yield complete_event
        await _publish(event_bus, complete_event)

        # 9. Update session cost
        try:
            await session_service.update_cost(
                session_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )
        except Exception:
            logger.warning("Failed to update session cost", exc_info=True)

        # 10. Yield cost update event
        updated_session = await session_service.get_session(session_id)
        budget_remaining = None
        if updated_session.cost_budget_usd is not None:
            budget_remaining = max(0.0, updated_session.cost_budget_usd - updated_session.total_cost_usd)

        cost_event = CostUpdateEvent(
            session_id=sid,
            source=source,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            cumulative_cost_usd=updated_session.total_cost_usd,
            budget_remaining_usd=budget_remaining,
            model=model_str,
        )
        yield cost_event
        await _publish(event_bus, cost_event)

        # 11. Persist messages
        user_create = SessionMessageCreate(role="user", content=message, sender_id=sender_id)
        assistant_create = SessionMessageCreate(
            role="assistant",
            content=full_content,
            sender_id=agent_name,
            model=model_str,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        await _persist_messages(session_service, session_id, [user_create, assistant_create])

        # 12. Touch activity
        try:
            await session_service.touch_activity(session_id)
        except Exception:
            logger.debug("Failed to touch session activity", exc_info=True)

    except Exception as exc:
        logger.error("Mission control error", exc_info=True, extra={"session_id": session_id})
        # Yield a partial complete event so the stream always terminates cleanly
        yield AgentResponseCompleteEvent(
            session_id=sid,
            source=source,
            agent_id="unknown",
            full_content=f"Error: {exc}",
            metadata={"error": True},
        )


async def collect(session_id: str, message: str, **kwargs: Any) -> dict[str, Any]:
    """Collect all events from handle(), return a dict.

    Returns: {"agent_name": str, "output": str, "cost_usd": float, "session_id": str}
    """
    agent_name = ""
    output = ""
    cost_usd = 0.0

    async for event in handle(session_id, message, **kwargs):
        if isinstance(event, AgentResponseCompleteEvent):
            agent_name = event.agent_id
            output = event.full_content
            cost_usd = event.cost_usd
        elif isinstance(event, AgentResponseChunkEvent):
            pass  # chunks are already accumulated in full_content

    return {
        "agent_name": agent_name,
        "output": output,
        "cost_usd": cost_usd,
        "session_id": session_id,
    }
