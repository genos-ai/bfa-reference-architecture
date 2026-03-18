"""
Logging Middleware.

Logs all incoming Telegram updates with structured context.
Integrates with the centralized logging system.
"""

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from modules.backend.core.logging import get_logger, log_with_source

logger = get_logger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """
    Middleware for logging all Telegram updates.

    Logs:
    - Update type and ID
    - User information (ID, username)
    - Chat information (ID, type)
    - Processing time
    - Errors

    All logs are written to logs/system.jsonl with source="telegram".

    Usage:
        # In dispatcher setup
        dp.update.outer_middleware(LoggingMiddleware())
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """
        Process the middleware.

        Args:
            handler: Next handler in the chain
            event: Telegram event (Update)
            data: Handler data dict

        Returns:
            Handler result
        """
        start_time = time.perf_counter()

        # Extract context from the update
        context = self._extract_context(event)

        # Log incoming update
        log_with_source(
            logger,
            "telegram",
            "info",
            "Telegram update received",
            **context,
        )

        try:
            result = await handler(event, data)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            log_with_source(
                logger,
                "telegram",
                "debug",
                "Telegram update processed",
                elapsed_ms=round(elapsed_ms, 2),
                **context,
            )

            return result

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            log_with_source(
                logger,
                "telegram",
                "error",
                "Telegram update processing error",
                error=str(e),
                error_type=type(e).__name__,
                elapsed_ms=round(elapsed_ms, 2),
                **context,
            )
            raise

    def _extract_context(self, event: TelegramObject) -> dict[str, Any]:
        """
        Extract logging context from the event.

        Args:
            event: Telegram event

        Returns:
            Context dictionary for logging
        """
        context: dict[str, Any] = {}

        if not isinstance(event, Update):
            return context

        context["update_id"] = event.update_id
        context["update_type"] = event.event_type

        # Extract from message
        if event.message:
            msg = event.message
            context["chat_id"] = msg.chat.id
            context["chat_type"] = msg.chat.type
            if msg.from_user:
                context["user_id"] = msg.from_user.id
                context["username"] = msg.from_user.username
            if msg.text:
                # Log command or truncated text
                if msg.text.startswith("/"):
                    context["command"] = msg.text.split()[0]
                else:
                    context["text_preview"] = msg.text[:50] + "..." if len(msg.text) > 50 else msg.text

        # Extract from callback query
        elif event.callback_query:
            cb = event.callback_query
            if cb.from_user:
                context["user_id"] = cb.from_user.id
                context["username"] = cb.from_user.username
            if cb.message:
                context["chat_id"] = cb.message.chat.id
                context["chat_type"] = cb.message.chat.type
            context["callback_data"] = cb.data

        # Extract from inline query
        elif event.inline_query:
            iq = event.inline_query
            if iq.from_user:
                context["user_id"] = iq.from_user.id
                context["username"] = iq.from_user.username
            context["inline_query"] = iq.query[:50] if iq.query else None

        return context
