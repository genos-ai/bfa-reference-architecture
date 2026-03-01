"""
Authentication Middleware.

User ID whitelisting and role-based access control for the Telegram bot.
Roles and user-to-role mappings are read from config/settings/security.yaml.
Telegram user IDs are immutable integers that cannot be spoofed within the Telegram API.
"""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def _get_role_hierarchy() -> dict[str, int]:
    """Build a role-name -> level mapping from security config."""
    security = get_app_config().security
    return {name: role.level for name, role in security.roles.items()}


def _get_user_roles_mapping() -> dict[int, str]:
    """Build a user-ID -> role-name mapping from security config.

    YAML stores keys as strings; convert to int for Telegram user IDs.
    """
    security = get_app_config().security
    return {int(uid): role for uid, role in security.user_roles.items()}


def _resolve_role(user_id: int, authorized_users: list[int]) -> str:
    """Determine a user's role from explicit mapping or default rules.

    Priority:
        1. Explicit mapping in security.yaml user_roles
        2. Default to 'viewer' for any authorized user without a mapping
    """
    explicit = _get_user_roles_mapping()
    if user_id in explicit:
        return explicit[user_id]
    return "viewer"


class AuthMiddleware(BaseMiddleware):
    """
    Authentication middleware using Telegram user ID whitelisting.

    Checks if the user is in the authorized users list before processing.
    Silently drops unauthorized requests to avoid revealing bot existence.

    Configuration:
        Set authorized_users in config/settings/application.yaml.
        Set role mappings in config/settings/security.yaml under user_roles.

    Usage:
        dp.update.outer_middleware(AuthMiddleware())

        @router.message(Command("admin_command"))
        async def admin_handler(message: Message, user_role: str):
            if user_role != "admin":
                await message.answer("Unauthorized")
                return
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process the middleware."""
        app_config = get_app_config()

        user = None
        chat_type = None

        if isinstance(event, Update):
            if event.message:
                user = event.message.from_user
                chat_type = event.message.chat.type
            elif event.callback_query:
                user = event.callback_query.from_user
                chat_type = event.callback_query.message.chat.type if event.callback_query.message else None
            elif event.inline_query:
                user = event.inline_query.from_user

        if not user:
            return await handler(event, data)

        user_id = user.id

        authorized_users = app_config.application.telegram.authorized_users

        if not authorized_users:
            logger.debug(
                "No authorized users configured, allowing all",
                extra={"user_id": user_id},
            )
            data["user_role"] = "admin"
            data["telegram_user"] = user
            return await handler(event, data)

        if user_id not in authorized_users:
            logger.warning(
                "Unauthorized Telegram access attempt",
                extra={
                    "user_id": user_id,
                    "username": user.username,
                    "chat_type": chat_type,
                },
            )
            return None

        role = _resolve_role(user_id, authorized_users)

        data["user_role"] = role
        data["telegram_user"] = user

        logger.debug(
            "Authorized Telegram user",
            extra={
                "user_id": user_id,
                "username": user.username,
                "role": role,
            },
        )

        return await handler(event, data)


def require_role(min_role: str):
    """
    Decorator to require a minimum role for a handler.

    Reads role hierarchy from config/settings/security.yaml.

    Args:
        min_role: Minimum required role name (e.g. "viewer", "trader", "admin")

    Usage:
        @router.message(Command("trade"))
        @require_role("trader")
        async def trade_handler(message: Message, user_role: str):
            pass
    """
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            hierarchy = _get_role_hierarchy()
            min_level = hierarchy.get(min_role, 0)
            user_role = kwargs.get("user_role", "viewer")
            user_level = hierarchy.get(user_role, 0)

            if user_level < min_level:
                message = args[0] if args else kwargs.get("message")
                if message and hasattr(message, "answer"):
                    await message.answer("⛔ You don't have permission for this action.")
                return None

            return await func(*args, **kwargs)

        return wrapper

    return decorator
