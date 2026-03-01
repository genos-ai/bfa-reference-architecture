"""
Unit Tests for channel adapters — base chunking and Telegram formatting.

Tests use real objects with mocked bot — no LLM, no network.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from modules.backend.gateway.adapters.base import AgentResponse, ChannelAdapter, ChannelMessage
from modules.backend.gateway.adapters.telegram import (
    TelegramAdapter,
    _convert_markdown_bold,
    _convert_markdown_code,
    _convert_markdown_italic,
)


class ConcreteAdapter(ChannelAdapter):
    """Minimal concrete adapter for testing the base class chunk logic."""

    @property
    def channel_name(self) -> str:
        return "test"

    @property
    def max_message_length(self) -> int:
        return 100

    async def deliver_response(self, response: AgentResponse) -> bool:
        return True

    def format_text(self, text: str) -> str:
        return text


class TestChannelMessage:
    """Tests for the standard inbound message dataclass."""

    def test_creates_with_required_fields(self):
        msg = ChannelMessage(
            channel="telegram",
            user_id="user_123",
            text="hello",
            session_key="chat_456",
        )
        assert msg.channel == "telegram"
        assert msg.text == "hello"
        assert msg.is_group is False
        assert msg.received_at is not None

    def test_group_message(self):
        msg = ChannelMessage(
            channel="telegram",
            user_id="user_123",
            text="hello",
            session_key="chat_456",
            group_id="group_789",
            is_group=True,
        )
        assert msg.is_group is True
        assert msg.group_id == "group_789"


class TestAgentResponse:
    """Tests for the standard outbound response dataclass."""

    def test_creates_with_required_fields(self):
        resp = AgentResponse(
            text="result",
            session_key="chat_123",
            channel="telegram",
        )
        assert resp.text == "result"
        assert resp.cost_usd is None
        assert resp.agent_name is None

    def test_creates_with_metadata(self):
        resp = AgentResponse(
            text="result",
            session_key="chat_123",
            channel="telegram",
            cost_usd=0.003,
            token_input=500,
            token_output=200,
            duration_ms=1500,
            agent_name="code.qa.agent",
        )
        assert resp.cost_usd == 0.003
        assert resp.agent_name == "code.qa.agent"


class TestBaseChunking:
    """Tests for the base ChannelAdapter.chunk_message() implementation."""

    @pytest.mark.asyncio
    async def test_short_message_not_chunked(self):
        adapter = ConcreteAdapter()
        chunks = await adapter.chunk_message("short text")
        assert len(chunks) == 1
        assert chunks[0] == "short text"

    @pytest.mark.asyncio
    async def test_long_message_chunked(self):
        adapter = ConcreteAdapter()
        text = "A" * 250
        chunks = await adapter.chunk_message(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 100

    @pytest.mark.asyncio
    async def test_splits_on_paragraph_boundary(self):
        adapter = ConcreteAdapter()
        text = ("A" * 40) + "\n\n" + ("B" * 40) + "\n\n" + ("C" * 40)
        chunks = await adapter.chunk_message(text)
        assert len(chunks) >= 2

    @pytest.mark.asyncio
    async def test_splits_on_newline_when_no_paragraph(self):
        adapter = ConcreteAdapter()
        text = ("A" * 40) + "\n" + ("B" * 40) + "\n" + ("C" * 40)
        chunks = await adapter.chunk_message(text)
        assert len(chunks) >= 2


class TestTelegramFormatting:
    """Tests for Telegram markdown-to-HTML conversion."""

    def test_bold_conversion(self):
        assert _convert_markdown_bold("**hello**") == "<b>hello</b>"

    def test_bold_multiple(self):
        result = _convert_markdown_bold("**a** and **b**")
        assert "<b>a</b>" in result
        assert "<b>b</b>" in result

    def test_italic_conversion(self):
        assert _convert_markdown_italic("*hello*") == "<i>hello</i>"

    def test_code_conversion(self):
        assert _convert_markdown_code("`code`") == "<code>code</code>"

    def test_format_text_combined(self):
        adapter = TelegramAdapter(bot=MagicMock())
        result = adapter.format_text("**bold** and `code`")
        assert "<b>bold</b>" in result
        assert "<code>code</code>" in result


class TestTelegramAdapter:
    """Tests for the Telegram adapter."""

    def test_channel_name(self):
        adapter = TelegramAdapter(bot=MagicMock())
        assert adapter.channel_name == "telegram"

    def test_max_message_length(self):
        adapter = TelegramAdapter(bot=MagicMock())
        assert adapter.max_message_length == 4096

    @pytest.mark.asyncio
    async def test_deliver_short_message(self):
        bot = AsyncMock()
        adapter = TelegramAdapter(bot=bot)

        response = AgentResponse(
            text="hello",
            session_key="12345",
            channel="telegram",
        )
        result = await adapter.deliver_response(response)

        assert result is True
        bot.send_message.assert_awaited_once()
        call_kwargs = bot.send_message.call_args
        assert call_kwargs.kwargs["chat_id"] == "12345"

    @pytest.mark.asyncio
    async def test_deliver_long_message_chunks(self):
        bot = AsyncMock()
        adapter = TelegramAdapter(bot=bot)

        response = AgentResponse(
            text="A" * 5000,
            session_key="12345",
            channel="telegram",
        )
        result = await adapter.deliver_response(response)

        assert result is True
        assert bot.send_message.await_count >= 2

    @pytest.mark.asyncio
    async def test_deliver_failure_returns_false(self):
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("network error")
        adapter = TelegramAdapter(bot=bot)

        response = AgentResponse(
            text="hello",
            session_key="12345",
            channel="telegram",
        )
        result = await adapter.deliver_response(response)

        assert result is False
