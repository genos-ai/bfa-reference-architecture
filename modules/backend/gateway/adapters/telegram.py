"""
Telegram Channel Adapter.

Wraps the existing modules/telegram/ module to conform to the
ChannelAdapter interface. The bot, dispatcher, handlers, keyboards,
and middlewares are unchanged — this adapter translates between
the gateway's standard message format and aiogram's native types.
"""

import re
from typing import TYPE_CHECKING

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger
from modules.backend.gateway.adapters import AgentResponse, ChannelAdapter

if TYPE_CHECKING:
    from aiogram import Bot

logger = get_logger(__name__)


class TelegramAdapter(ChannelAdapter):
    """
    Telegram channel adapter.

    Wraps aiogram Bot for outbound message delivery and
    provides formatting for Telegram's HTML parse mode.
    """

    def __init__(self, bot: "Bot") -> None:
        self._bot = bot

    @property
    def channel_name(self) -> str:
        return "telegram"

    @property
    def max_message_length(self) -> int:
        return get_app_config().application.telegram.max_message_length

    async def deliver_response(self, response: AgentResponse) -> bool:
        """
        Deliver a response to a Telegram chat.

        Handles chunking for messages exceeding 4096 characters.
        The session_key is the Telegram chat_id.
        """
        try:
            formatted = self.format_text(response.text)
            chunks = await self.chunk_message(formatted)

            for chunk in chunks:
                await self._bot.send_message(
                    chat_id=response.session_key,
                    text=chunk,
                    reply_to_message_id=(
                        int(response.reply_to_message_id)
                        if response.reply_to_message_id
                        else None
                    ),
                )

            logger.debug(
                "Telegram response delivered",
                extra={
                    "chat_id": response.session_key,
                    "chunks": len(chunks),
                    "total_length": len(response.text),
                },
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to deliver Telegram response",
                extra={
                    "chat_id": response.session_key,
                    "error": str(e),
                },
            )
            return False

    def format_text(self, text: str) -> str:
        """
        Format text for Telegram's HTML parse mode.

        Converts standard markdown bold/italic to HTML tags.
        Telegram supports: <b>, <i>, <code>, <pre>, <a>.
        """
        result = text
        result = _convert_markdown_bold(result)
        result = _convert_markdown_italic(result)
        result = _convert_markdown_code(result)
        return result


def _convert_markdown_bold(text: str) -> str:
    """Convert **bold** to <b>bold</b>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def _convert_markdown_italic(text: str) -> str:
    """Convert *italic* to <i>italic</i> (single asterisks not preceded by another)."""
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)


def _convert_markdown_code(text: str) -> str:
    """Convert `code` to <code>code</code>."""
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)
