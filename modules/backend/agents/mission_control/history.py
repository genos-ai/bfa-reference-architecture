"""Session message ↔ PydanticAI ModelMessage conversion.

Converts between our persistence format (session_messages table) and
PydanticAI's ModelMessage format used by agent.run(message_history=...).

Two public functions:
    session_messages_to_model_history() — load for agent context
    model_messages_to_session_creates() — persist after agent response
"""

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from modules.backend.core.logging import get_logger
from modules.backend.schemas.session import SessionMessageCreate

logger = get_logger(__name__)


def session_messages_to_model_history(
    messages: list,
) -> list[ModelMessage]:
    """Convert session_message rows to PydanticAI's ModelMessage list.

    Args:
        messages: List of SessionMessage model instances, ordered by created_at.

    Returns:
        List of ModelMessage instances suitable for agent.run(message_history=...).
    """
    result: list[ModelMessage] = []

    for msg in messages:
        role = msg.role
        content = msg.content or ""

        if role == "user":
            result.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            result.append(ModelResponse(parts=[TextPart(content=content)]))
        elif role == "system":
            result.append(ModelRequest(parts=[SystemPromptPart(content=content)]))
        elif role == "tool_call":
            # tool_call messages store tool_name and tool_call_id
            result.append(
                ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name=msg.tool_name or "unknown",
                            args=content,
                            tool_call_id=msg.tool_call_id or "unknown",
                        )
                    ]
                )
            )
        elif role == "tool_result":
            result.append(
                ModelRequest(
                    parts=[
                        ToolReturnPart(
                            tool_name=msg.tool_name or "unknown",
                            content=content,
                            tool_call_id=msg.tool_call_id or "unknown",
                        )
                    ]
                )
            )
        else:
            logger.warning(
                "Unknown message role, skipping",
                extra={"role": role, "session_id": str(getattr(msg, "session_id", ""))},
            )

    return result


def model_messages_to_session_creates(
    messages: list[ModelMessage],
    session_id: str,
    agent_id: str | None = None,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
) -> list[SessionMessageCreate]:
    """Convert PydanticAI's new_messages() output to SessionMessageCreate schemas.

    Cost fields are attached to the last assistant message only.

    Args:
        messages: From stream.new_messages() after agent execution.
        session_id: Session these messages belong to.
        agent_id: Agent that produced the response.
        model: Model used for generation.
        input_tokens: Total input tokens for this interaction.
        output_tokens: Total output tokens for this interaction.
        cost_usd: Computed cost for this interaction.

    Returns:
        List of SessionMessageCreate ready for persistence.
    """
    creates: list[SessionMessageCreate] = []

    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    creates.append(
                        SessionMessageCreate(
                            role="user",
                            content=part.content if isinstance(part.content, str) else str(part.content),
                        )
                    )
                elif isinstance(part, SystemPromptPart):
                    creates.append(
                        SessionMessageCreate(
                            role="system",
                            content=part.content,
                        )
                    )
                elif isinstance(part, ToolReturnPart):
                    creates.append(
                        SessionMessageCreate(
                            role="tool_result",
                            content=part.content if isinstance(part.content, str) else str(part.content),
                            tool_name=part.tool_name,
                            tool_call_id=part.tool_call_id,
                        )
                    )
        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart):
                    creates.append(
                        SessionMessageCreate(
                            role="assistant",
                            content=part.content,
                            sender_id=agent_id,
                        )
                    )
                elif isinstance(part, ToolCallPart):
                    args_str = part.args if isinstance(part.args, str) else str(part.args)
                    creates.append(
                        SessionMessageCreate(
                            role="tool_call",
                            content=args_str,
                            tool_name=part.tool_name,
                            tool_call_id=part.tool_call_id or "",
                            sender_id=agent_id,
                        )
                    )

    # Attach cost info to the last assistant message
    for create in reversed(creates):
        if create.role == "assistant":
            create.model = model
            create.input_tokens = input_tokens
            create.output_tokens = output_tokens
            create.cost_usd = cost_usd
            break

    return creates
