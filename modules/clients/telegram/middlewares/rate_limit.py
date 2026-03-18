"""
Rate Limiting Middleware.

Prevents abuse by limiting request frequency per user.
Uses in-memory storage for simplicity; use Redis for distributed deployments.
"""

import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def _get_telegram_rate_limit() -> int:
    """Get telegram messages_per_minute from security.yaml."""
    return get_app_config().security.rate_limiting.telegram.messages_per_minute


class RateLimitMiddleware(BaseMiddleware):
    """
    Rate limiting middleware using sliding window counter.

    Limits the number of requests per user within a time window.
    Sends a warning message when rate limit is exceeded.

    Rate limit values are loaded from security.yaml
    (security.rate_limiting.telegram.messages_per_minute).

    Usage:
        # In dispatcher setup (reads from config)
        dp.message.middleware(RateLimitMiddleware())
        dp.callback_query.middleware(RateLimitMiddleware())

        # Or override for specific use cases
        dp.message.middleware(RateLimitMiddleware(rate_limit=10, rate_window=30))

    Note:
        For production with multiple workers, use Redis-based rate limiting:
        - Store counts in Redis with TTL
        - Use Redis INCR with EXPIRE for atomic operations
    """

    def __init__(
        self,
        rate_limit: int | None = None,
        rate_window: int = 60,
    ):
        """
        Initialize the rate limiter.

        Args:
            rate_limit: Maximum requests per window (from security.yaml if not provided)
            rate_window: Time window in seconds
        """
        self.rate_limit = rate_limit if rate_limit is not None else _get_telegram_rate_limit()
        self.rate_window = rate_window
        # In-memory storage: {user_id: [(timestamp, count), ...]}
        self._requests: dict[int, list[float]] = defaultdict(list)

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
            event: Telegram event
            data: Handler data dict

        Returns:
            Handler result or None if rate limited
        """
        # Extract user ID
        user_id = self._get_user_id(event)
        if not user_id:
            return await handler(event, data)

        # Check rate limit
        now = time.time()
        is_limited, remaining = self._check_rate_limit(user_id, now)

        if is_limited:
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "user_id": user_id,
                    "rate_limit": self.rate_limit,
                    "rate_window": self.rate_window,
                },
            )
            await self._send_rate_limit_message(event, remaining)
            return None

        # Record this request
        self._requests[user_id].append(now)

        return await handler(event, data)

    def _get_user_id(self, event: TelegramObject) -> int | None:
        """Extract user ID from the event."""
        if isinstance(event, Message) and event.from_user:
            return event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user.id
        return None

    def _check_rate_limit(self, user_id: int, now: float) -> tuple[bool, int]:
        """
        Check if user has exceeded rate limit.

        Args:
            user_id: Telegram user ID
            now: Current timestamp

        Returns:
            Tuple of (is_limited, seconds_until_reset)
        """
        # Clean old requests outside the window
        window_start = now - self.rate_window
        self._requests[user_id] = [
            ts for ts in self._requests[user_id] if ts > window_start
        ]

        # Check if limit exceeded
        request_count = len(self._requests[user_id])
        if request_count >= self.rate_limit:
            # Calculate time until oldest request expires
            oldest = min(self._requests[user_id]) if self._requests[user_id] else now
            remaining = int(self.rate_window - (now - oldest)) + 1
            return True, remaining

        return False, 0

    async def _send_rate_limit_message(
        self, event: TelegramObject, remaining: int
    ) -> None:
        """Send rate limit notification to user."""
        message = f"⏳ Rate limit exceeded. Please wait {remaining} seconds."

        if isinstance(event, Message):
            await event.answer(message)
        elif isinstance(event, CallbackQuery):
            await event.answer(message, show_alert=True)


class ThrottleMiddleware(BaseMiddleware):
    """
    Simple throttle middleware for specific commands.

    Prevents rapid-fire execution of expensive operations.

    Usage:
        @router.message(Command("expensive_operation"))
        @throttle(seconds=5)
        async def expensive_handler(message: Message):
            pass
    """

    def __init__(self, default_throttle: float = 1.0):
        """
        Initialize throttle middleware.

        Args:
            default_throttle: Default throttle time in seconds
        """
        self.default_throttle = default_throttle
        self._last_call: dict[tuple[int, str], float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process the middleware."""
        user_id = self._get_user_id(event)
        handler_name = handler.__name__ if hasattr(handler, "__name__") else "unknown"

        if user_id:
            key = (user_id, handler_name)
            now = time.time()
            last = self._last_call.get(key, 0)

            if now - last < self.default_throttle:
                return None

            self._last_call[key] = now

        return await handler(event, data)

    def _get_user_id(self, event: TelegramObject) -> int | None:
        """Extract user ID from the event."""
        if isinstance(event, Message) and event.from_user:
            return event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user.id
        return None
