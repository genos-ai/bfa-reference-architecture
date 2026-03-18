"""
Webhook Endpoint for Telegram Bot.

Provides FastAPI router for handling Telegram webhook requests.
"""

import hmac
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request, Response

from modules.backend.core.config import get_app_config, get_settings
from modules.backend.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher

logger = get_logger(__name__)


def get_webhook_router(bot: "Bot", dp: "Dispatcher") -> APIRouter:
    """
    Create a FastAPI router for handling Telegram webhook requests.

    Args:
        bot: aiogram Bot instance
        dp: aiogram Dispatcher instance

    Returns:
        FastAPI APIRouter with webhook endpoint

    Usage:
        from modules.clients.telegram import create_bot, create_dispatcher
        from modules.clients.telegram.webhook import get_webhook_router

        bot = create_bot()
        dp = create_dispatcher()
        webhook_router = get_webhook_router(bot, dp)
        app.include_router(webhook_router)
    """
    from aiogram.types import Update

    settings = get_settings()
    app_config = get_app_config()
    router = APIRouter(tags=["telegram"])

    webhook_path = app_config.application.telegram.webhook_path
    webhook_secret = settings.telegram_webhook_secret

    @router.post(webhook_path)
    async def telegram_webhook(request: Request) -> Response:
        """
        Handle incoming Telegram webhook requests.

        Validates the secret token header and processes the update.
        """
        # Validate webhook secret token
        if webhook_secret:
            secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if not secret_header or not hmac.compare_digest(secret_header, webhook_secret):
                logger.warning(
                    "Invalid webhook secret token",
                    extra={"client_ip": request.client.host if request.client else None},
                )
                return Response(status_code=403)

        try:
            # Parse and process the update
            update_data = await request.json()
            update = Update.model_validate(update_data, context={"bot": bot})

            # Log the update (debug level to avoid noise)
            logger.debug(
                "Received Telegram update",
                extra={
                    "update_id": update.update_id,
                    "update_type": update.event_type,
                    "user_id": update.event.from_user.id if update.event and update.event.from_user else None,
                },
            )

            # Process the update through the dispatcher
            await dp.feed_update(bot, update)

            return Response(status_code=200)

        except Exception as e:
            logger.error(
                "Error processing Telegram update",
                extra={"error": str(e)},
                exc_info=True,
            )
            # Return 200 to prevent Telegram from retrying
            # Log the error for investigation
            return Response(status_code=200)

    @router.get(webhook_path + "/health")
    async def telegram_webhook_health() -> dict:
        """Health check for the Telegram webhook endpoint."""
        return {"status": "healthy", "webhook_path": webhook_path}

    return router


def get_webhook_url(base_url: str) -> str:
    """
    Construct the full webhook URL.

    Args:
        base_url: Base URL of the application (e.g., https://example.com)

    Returns:
        Full webhook URL
    """
    app_config = get_app_config()
    webhook_path = app_config.application.telegram.webhook_path
    return f"{base_url.rstrip('/')}{webhook_path}"
