"""
Bot and Dispatcher Configuration.

Creates and configures the aiogram Bot and Dispatcher instances.
Uses lazy initialization to prevent import-time failures.
"""

from typing import TYPE_CHECKING

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher

# Module-level state for lazy initialization
_bot: "Bot | None" = None
_dispatcher: "Dispatcher | None" = None


def create_bot() -> "Bot":
    """
    Create and configure the aiogram Bot instance.

    Returns:
        Configured Bot instance

    Raises:
        RuntimeError: If TELEGRAM_BOT_TOKEN is not configured
    """
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from modules.backend.core.config import get_settings

    settings = get_settings()

    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN not configured. "
            "Set TELEGRAM_BOT_TOKEN environment variable or configure it in config/.env"
        )

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    logger.info("Telegram bot created")
    return bot


def create_dispatcher() -> "Dispatcher":
    """
    Create and configure the aiogram Dispatcher instance.

    Includes all routers and middlewares.

    Returns:
        Configured Dispatcher instance
    """
    from aiogram import Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage

    from modules.clients.telegram.handlers import get_all_routers
    from modules.clients.telegram.middlewares import setup_middlewares

    # Use MemoryStorage for development
    # For production, use RedisStorage:
    # from aiogram.fsm.storage.redis import RedisStorage
    # from modules.backend.core.config import get_redis_url
    # storage = RedisStorage.from_url(get_redis_url())
    storage = MemoryStorage()

    dp = Dispatcher(storage=storage)

    # Setup middlewares (auth, logging, rate limiting)
    setup_middlewares(dp)

    # Include all routers
    for router in get_all_routers():
        dp.include_router(router)

    logger.info("Telegram dispatcher created with routers and middlewares")
    return dp


def get_bot() -> "Bot":
    """
    Get or create the Bot instance (lazy initialization).

    Returns:
        Bot instance
    """
    global _bot
    if _bot is None:
        _bot = create_bot()
    return _bot


def get_dispatcher() -> "Dispatcher":
    """
    Get or create the Dispatcher instance (lazy initialization).

    Returns:
        Dispatcher instance
    """
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = create_dispatcher()
    return _dispatcher


async def setup_webhook(bot: "Bot", webhook_url: str, secret_token: str) -> None:
    """
    Configure the webhook for the bot.

    Args:
        bot: Bot instance
        webhook_url: Full webhook URL (e.g., https://example.com/webhook/telegram)
        secret_token: Secret token for webhook validation
    """
    from modules.clients.telegram.bot import get_dispatcher

    dp = get_dispatcher()

    await bot.set_webhook(
        url=webhook_url,
        secret_token=secret_token,
        drop_pending_updates=True,
        allowed_updates=dp.resolve_used_update_types(),
    )
    logger.info("Webhook configured", extra={"webhook_url": webhook_url})


async def cleanup_bot(bot: "Bot") -> None:
    """
    Cleanup bot resources on shutdown.

    Args:
        bot: Bot instance to cleanup
    """
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("Bot webhook deleted and session closed")
