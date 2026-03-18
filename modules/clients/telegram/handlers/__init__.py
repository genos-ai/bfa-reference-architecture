"""Telegram Bot Handlers — re-exports."""

from modules.clients.telegram.handlers.common import router as common_router
from modules.clients.telegram.handlers.example import router as example_router
from modules.clients.telegram.handlers.setup import get_all_routers

__all__ = [
    "common_router",
    "example_router",
    "get_all_routers",
]
