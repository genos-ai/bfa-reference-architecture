"""
Unit Tests for mission_control/history.py.

Tests the bidirectional conversion between session messages and
PydanticAI ModelMessage format.
"""

from types import SimpleNamespace

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from modules.backend.agents.mission_control.history import (
    model_messages_to_session_creates,
    session_messages_to_model_history,
)


def _msg(**kwargs):
    """Create a SimpleNamespace pretending to be a SessionMessage row."""
    defaults = {
        "role": "user",
        "content": "hello",
        "tool_name": None,
        "tool_call_id": None,
        "session_id": "test-session",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestSessionMessagesToModelHistory:
    """Tests for session_messages_to_model_history()."""

    def test_user_message(self):
        msgs = session_messages_to_model_history([_msg(role="user", content="hi")])
        assert len(msgs) == 1
        assert isinstance(msgs[0], ModelRequest)
        assert isinstance(msgs[0].parts[0], UserPromptPart)
        assert msgs[0].parts[0].content == "hi"

    def test_assistant_message(self):
        msgs = session_messages_to_model_history([_msg(role="assistant", content="hello back")])
        assert len(msgs) == 1
        assert isinstance(msgs[0], ModelResponse)
        assert isinstance(msgs[0].parts[0], TextPart)
        assert msgs[0].parts[0].content == "hello back"

    def test_system_message(self):
        msgs = session_messages_to_model_history([_msg(role="system", content="you are helpful")])
        assert len(msgs) == 1
        assert isinstance(msgs[0], ModelRequest)
        assert isinstance(msgs[0].parts[0], SystemPromptPart)

    def test_tool_call_message(self):
        msgs = session_messages_to_model_history([
            _msg(role="tool_call", content='{"query": "test"}', tool_name="search", tool_call_id="tc-1"),
        ])
        assert len(msgs) == 1
        assert isinstance(msgs[0], ModelResponse)
        part = msgs[0].parts[0]
        assert isinstance(part, ToolCallPart)
        assert part.tool_name == "search"
        assert part.tool_call_id == "tc-1"

    def test_tool_result_message(self):
        msgs = session_messages_to_model_history([
            _msg(role="tool_result", content="found 3 results", tool_name="search", tool_call_id="tc-1"),
        ])
        assert len(msgs) == 1
        assert isinstance(msgs[0], ModelRequest)
        part = msgs[0].parts[0]
        assert isinstance(part, ToolReturnPart)
        assert part.tool_name == "search"
        assert part.content == "found 3 results"

    def test_unknown_role_skipped(self):
        msgs = session_messages_to_model_history([_msg(role="unknown_role", content="wat")])
        assert len(msgs) == 0

    def test_empty_list(self):
        assert session_messages_to_model_history([]) == []

    def test_conversation_order_preserved(self):
        history = session_messages_to_model_history([
            _msg(role="user", content="first"),
            _msg(role="assistant", content="second"),
            _msg(role="user", content="third"),
        ])
        assert len(history) == 3
        assert isinstance(history[0], ModelRequest)
        assert isinstance(history[1], ModelResponse)
        assert isinstance(history[2], ModelRequest)


class TestModelMessagesToSessionCreates:
    """Tests for model_messages_to_session_creates()."""

    def test_user_prompt_creates_user_message(self):
        msgs = [ModelRequest(parts=[UserPromptPart(content="hello")])]
        creates = model_messages_to_session_creates(msgs, session_id="s1")
        assert len(creates) == 1
        assert creates[0].role == "user"
        assert creates[0].content == "hello"

    def test_text_part_creates_assistant_message(self):
        msgs = [ModelResponse(parts=[TextPart(content="response")])]
        creates = model_messages_to_session_creates(msgs, session_id="s1", agent_id="test.agent")
        assert len(creates) == 1
        assert creates[0].role == "assistant"
        assert creates[0].content == "response"
        assert creates[0].sender_id == "test.agent"

    def test_tool_call_part(self):
        msgs = [
            ModelResponse(
                parts=[ToolCallPart(tool_name="search", args='{"q": "test"}', tool_call_id="tc-1")]
            )
        ]
        creates = model_messages_to_session_creates(msgs, session_id="s1", agent_id="a1")
        assert len(creates) == 1
        assert creates[0].role == "tool_call"
        assert creates[0].tool_name == "search"
        assert creates[0].tool_call_id == "tc-1"

    def test_tool_return_part(self):
        msgs = [
            ModelRequest(
                parts=[ToolReturnPart(tool_name="search", content="results", tool_call_id="tc-1")]
            )
        ]
        creates = model_messages_to_session_creates(msgs, session_id="s1")
        assert len(creates) == 1
        assert creates[0].role == "tool_result"
        assert creates[0].tool_name == "search"

    def test_cost_attached_to_last_assistant(self):
        msgs = [
            ModelRequest(parts=[UserPromptPart(content="hi")]),
            ModelResponse(parts=[TextPart(content="first")]),
            ModelResponse(parts=[TextPart(content="second")]),
        ]
        creates = model_messages_to_session_creates(
            msgs,
            session_id="s1",
            agent_id="a1",
            model="anthropic:claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=200,
            cost_usd=0.005,
        )
        # Find assistant messages
        assistants = [c for c in creates if c.role == "assistant"]
        assert len(assistants) == 2
        # Last assistant has cost
        assert assistants[-1].model == "anthropic:claude-haiku-4-5-20251001"
        assert assistants[-1].input_tokens == 100
        assert assistants[-1].output_tokens == 200
        assert assistants[-1].cost_usd == 0.005
        # First assistant has no cost
        assert assistants[0].model is None

    def test_empty_messages(self):
        creates = model_messages_to_session_creates([], session_id="s1")
        assert creates == []

    def test_system_prompt_part(self):
        msgs = [ModelRequest(parts=[SystemPromptPart(content="be helpful")])]
        creates = model_messages_to_session_creates(msgs, session_id="s1")
        assert len(creates) == 1
        assert creates[0].role == "system"
        assert creates[0].content == "be helpful"
