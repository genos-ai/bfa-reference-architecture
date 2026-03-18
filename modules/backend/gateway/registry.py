"""
Channel Adapter Registry.

Discovers and manages enabled channel adapters based on feature flags
and gateway configuration. Provides adapter lookup by channel name.
"""

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger
from modules.backend.gateway.adapters import ChannelAdapter

logger = get_logger(__name__)

_adapters: dict[str, ChannelAdapter] = {}
_initialized: bool = False


def _register_enabled_adapters() -> None:
    """Discover and register adapters for enabled channels."""
    global _initialized
    if _initialized:
        return

    features = get_app_config().features

    if features.channel_telegram_enabled:
        try:
            from modules.clients.telegram.bot import get_bot
            from modules.backend.gateway.adapters.telegram import TelegramAdapter

            bot = get_bot()
            adapter = TelegramAdapter(bot=bot)
            _adapters[adapter.channel_name] = adapter
            logger.info("Channel adapter registered", extra={"channel": "telegram"})
        except Exception as e:
            logger.error(
                "Failed to register Telegram adapter",
                extra={"error": str(e)},
            )
            raise

    _initialized = True
    logger.info(
        "Channel registry initialized",
        extra={"registered_channels": list(_adapters.keys())},
    )


def get_adapter(channel_name: str) -> ChannelAdapter | None:
    """
    Get a registered adapter by channel name.

    Returns None if the channel is not registered/enabled.
    """
    _register_enabled_adapters()
    return _adapters.get(channel_name)


def get_all_adapters() -> dict[str, ChannelAdapter]:
    """Get all registered adapters."""
    _register_enabled_adapters()
    return dict(_adapters)


def is_channel_enabled(channel_name: str) -> bool:
    """Check if a channel is registered and enabled."""
    _register_enabled_adapters()
    return channel_name in _adapters
