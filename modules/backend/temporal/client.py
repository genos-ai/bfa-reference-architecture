"""
Temporal Client Factory.

Provides a cached Temporal client connection. Gated by the
temporal.enabled feature flag — raises RuntimeError if Temporal
is not enabled.
"""

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)

_client = None


def get_temporal_config():
    """Get Temporal config, raising if not enabled."""
    config = get_app_config().temporal
    if not config.enabled:
        raise RuntimeError(
            "Temporal is not enabled. Set temporal.enabled=true "
            "in config/settings/temporal.yaml to use Tier 4 features."
        )
    return config


async def get_temporal_client():
    """Create and return a connected Temporal client.

    Raises RuntimeError if temporal.enabled is False.
    Caches the client after first connection.
    """
    global _client
    if _client is not None:
        return _client

    from temporalio.client import Client

    config = get_temporal_config()

    _client = await Client.connect(
        config.server_url,
        namespace=config.namespace,
    )

    logger.info(
        "Temporal client connected",
        extra={
            "server_url": config.server_url,
            "namespace": config.namespace,
        },
    )

    return _client
