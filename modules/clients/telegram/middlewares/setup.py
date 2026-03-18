"""
Middleware Registration.

Registers all middlewares on the aiogram dispatcher.
"""

from typing import TYPE_CHECKING

from modules.clients.telegram.middlewares.auth import AuthMiddleware
from modules.clients.telegram.middlewares.logging import LoggingMiddleware
from modules.clients.telegram.middlewares.rate_limit import RateLimitMiddleware

if TYPE_CHECKING:
    from aiogram import Dispatcher


def setup_middlewares(dp: "Dispatcher") -> None:
    """
    Setup all middlewares on the dispatcher.

    Middleware order matters:
    1. LoggingMiddleware (outer) - Log all updates
    2. AuthMiddleware (outer) - Check authorization before any processing
    3. RateLimitMiddleware (inner) - Rate limit after auth passes

    Args:
        dp: aiogram Dispatcher instance
    """
    # Outer middlewares (run on every update)
    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.outer_middleware(AuthMiddleware())

    # Inner middlewares (run after filters pass)
    # Note: Rate limiting is applied per-handler type
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
