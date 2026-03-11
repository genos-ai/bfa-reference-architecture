"""Mission Control — routes messages to agents, enforces budgets, streams events.

Infrastructure, not intelligence (P6). Does not call LLMs directly.

Public: handle(), handle_mission(), collect(), list_agents().
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai import UserError
from sqlalchemy.exc import SQLAlchemyError

from modules.backend.agents.mission_control.cost import compute_cost_usd, estimate_cost
from modules.backend.core.exceptions import ApplicationError
from modules.backend.agents.mission_control.dispatch import dispatch
from modules.backend.agents.mission_control.persistence_bridge import persist_mission_results
from modules.backend.agents.mission_control.helpers import (
    _build_agent_deps,
    _build_model,
    _build_planning_prompt,
    _build_roster_prompt,
    _append_validation_feedback,
    _call_planning_agent,
    _get_model_name,
    _get_usage_limits,
    _make_agent_executor,
    _persist_messages,
    _publish,
    _resolve_agent,
    assemble_instructions,
    build_deps_from_config,
)
from modules.backend.agents.mission_control.history import (
    session_messages_to_model_history,
)
from modules.backend.agents.mission_control.middleware import check_guardrails
from modules.backend.agents.mission_control.models import CollectResult, EventBusProtocol
from modules.backend.agents.mission_control.outcome import MissionOutcome, MissionStatus
from modules.backend.agents.mission_control.plan_validator import validate_plan
from modules.backend.agents.mission_control.registry import get_registry
from modules.backend.agents.mission_control.roster import load_roster
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
from modules.backend.schemas.task_plan import TaskPlan
from modules.backend.services.session import SessionService

logger = get_logger(__name__)

# Re-export for backwards compatibility (vertical agents import these)
__all__ = [
    "handle",
    "handle_mission",
    "collect",
    "list_agents",
    "assemble_instructions",
    "build_deps_from_config",
    "_build_model",
]


def list_agents() -> list[dict[str, Any]]:
    """List all available agents with their metadata."""
    return get_registry().list_all()


async def handle(
    session_id: str,
    message: str,
    *,
    session_service: SessionService,
    event_bus: EventBusProtocol | None = None,
    channel: str = "api",
    sender_id: str | None = None,
    mission_brief: str | None = None,
) -> AsyncIterator[SessionEvent]:
    """Universal streaming mission control entry point.

    Simple requests: existing direct-agent path (Plan 12).
    Complex requests: routed to dispatch via handle_mission() (Plan 13).

    A request is complex if mission_brief is explicitly provided.

    Yields SessionEvent instances as the agent works.
    Error handling yields events instead of throwing — the stream
    always terminates cleanly.
    """
    sid = uuid.UUID(session_id) if not isinstance(session_id, uuid.UUID) else session_id
    source = "mission_control"

    # Complex request — route to dispatch loop
    if mission_brief is not None:
        try:
            outcome = await handle_mission(
                mission_id=f"mission-{session_id}",
                mission_brief=mission_brief,
                session_service=session_service,
                event_bus=event_bus,
                session_id=session_id,
            )
            yield AgentResponseCompleteEvent(
                session_id=sid,
                source=source,
                agent_id="mission_control",
                full_content=outcome.model_dump_json(),
                metadata={"mission_status": outcome.status},
            )
        except Exception as exc:
            logger.error("Mission dispatch error", exc_info=True)
            yield AgentResponseCompleteEvent(
                session_id=sid,
                source=source,
                agent_id="mission_control",
                full_content=f"Error: {exc}",
                metadata={"error": True},
            )
        return

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
        limits = _get_usage_limits(agent_name)

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

            # Extract tool events and thinking from new_messages (retrospective)
            thinking_parts: list[str] = []
            try:
                new_msgs = stream.new_messages()
                for msg in new_msgs:
                    from pydantic_ai.messages import ModelResponse, ToolCallPart, ModelRequest, ToolReturnPart, ThinkingPart
                    if isinstance(msg, ModelResponse):
                        for part in msg.parts:
                            if isinstance(part, ThinkingPart) and part.has_content():
                                thinking_parts.append(part.content)
                            elif isinstance(part, ToolCallPart):
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
            except (AttributeError, TypeError, KeyError, ValueError):
                logger.debug("Failed to extract tool events", exc_info=True)

        # 8. Yield complete event
        metadata: dict[str, Any] = {}
        if thinking_parts:
            metadata["thinking"] = "\n\n".join(thinking_parts)

        complete_event = AgentResponseCompleteEvent(
            session_id=sid,
            source=source,
            agent_id=agent_name,
            full_content=full_content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            model=model_str,
            metadata=metadata,
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
        except (SQLAlchemyError, ApplicationError):
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
        except (SQLAlchemyError, ApplicationError):
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


async def collect(session_id: str, message: str, **kwargs: Any) -> CollectResult:
    """Collect all events from handle(), return a typed result dict."""
    agent_name = ""
    output = ""
    cost_usd = 0.0
    thinking: str | None = None

    async for event in handle(session_id, message, **kwargs):
        if isinstance(event, AgentResponseCompleteEvent):
            agent_name = event.agent_id
            output = event.full_content
            cost_usd = event.cost_usd
            if event.metadata and "thinking" in event.metadata:
                thinking = event.metadata["thinking"]
        elif isinstance(event, AgentResponseChunkEvent):
            pass  # chunks are already accumulated in full_content

    return CollectResult(
        agent_name=agent_name,
        output=output,
        cost_usd=cost_usd,
        session_id=session_id,
        thinking=thinking,
    )


# =============================================================================
# Mission dispatch — multi-agent mission execution (Plan 13)
# =============================================================================


async def handle_mission(
    mission_id: str,
    mission_brief: str,
    *,
    session_service: SessionService,
    event_bus: EventBusProtocol | None = None,
    roster_name: str = "default",
    mission_budget_usd: float = 10.0,
    upstream_context: dict | None = None,
    session_id: str | None = None,
) -> MissionOutcome:
    """Dispatch entry point for complex multi-agent missions.

    1. Load roster
    2. Call Planning Agent for task decomposition
    3. Validate TaskPlan against all 11 rules
    4. Execute dispatch loop
    5. Return MissionOutcome

    Simple requests continue through handle() from Plan 12.
    Complex requests (explicit mission_brief or matched playbook)
    route here.
    """
    roster = load_roster(roster_name)

    roster_description = _build_roster_prompt(roster)
    planning_prompt = _build_planning_prompt(
        mission_brief=mission_brief,
        mission_id=mission_id,
        roster_description=roster_description,
        upstream_context=upstream_context,
    )

    # Call Planning Agent (with retry on validation failure)
    plan = None
    thinking_trace = None
    max_planning_attempts = 3

    for attempt in range(max_planning_attempts):
        try:
            planning_result = await _call_planning_agent(
                planning_prompt, roster, upstream_context,
            )
            thinking_trace = planning_result.get("thinking_trace")

            plan = TaskPlan.model_validate(planning_result["task_plan"])

            validation = validate_plan(plan, roster, mission_budget_usd)
            if validation.is_valid:
                break

            logger.warning(
                "TaskPlan validation failed, retrying Planning Agent",
                extra={
                    "attempt": attempt + 1,
                    "errors": validation.errors,
                    "mission_id": mission_id,
                },
            )
            planning_prompt = _append_validation_feedback(
                planning_prompt, validation.errors,
            )
            plan = None

        except (ValueError, Exception) as e:
            logger.warning(
                "Planning Agent error, retrying",
                extra={
                    "attempt": attempt + 1,
                    "error": str(e),
                    "mission_id": mission_id,
                },
            )
            planning_prompt = _append_validation_feedback(
                planning_prompt, [str(e)],
            )

    if plan is None:
        return MissionOutcome(
            mission_id=mission_id,
            status=MissionStatus.FAILED,
            planning_trace_reference=thinking_trace,
        )

    # Execute dispatch loop
    outcome = await dispatch(
        plan=plan,
        roster=roster,
        execute_agent_fn=_make_agent_executor(session_service, event_bus),
        mission_budget_usd=mission_budget_usd,
    )

    outcome.planning_trace_reference = thinking_trace
    outcome.task_plan_reference = plan.model_dump_json()

    # Best-effort persistence — does not block or fail the mission
    if hasattr(session_service, "_session") and session_service._session:
        await persist_mission_results(
            outcome,
            session_id=session_id or mission_id,
            roster_name=roster_name,
            task_plan_json=plan.model_dump(),
            thinking_trace=thinking_trace,
            db_session=session_service._session,
        )

    return outcome
