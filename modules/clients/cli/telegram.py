"""
CLI handler for --service telegram-poll.

Starts the Telegram bot in polling mode for local development.
"""

import asyncio
import sys

import click

from modules.backend.core.config import get_app_config


def run_telegram_poll(logger) -> None:
    """Start the Telegram bot in polling mode for local development."""
    features = get_app_config().features
    if not features.channel_telegram_enabled:
        click.echo(
            click.style(
                "Error: channel_telegram_enabled is false in features.yaml. "
                "Enable it to use the Telegram bot.",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    logger.info("Starting Telegram bot in polling mode")

    try:
        from modules.clients.telegram.bot import create_bot, create_dispatcher

        bot = create_bot()
        dp = create_dispatcher()

        click.echo("Starting Telegram bot (polling mode)")
        click.echo("Send /start to your bot on Telegram")
        click.echo("Press Ctrl+C to stop\n")

        asyncio.run(_run_polling(bot, dp, logger))

    except RuntimeError as e:
        logger.error("Telegram bot failed to start", extra={"error": str(e)})
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


async def _run_polling(bot, dp, logger) -> None:
    """Run the bot polling loop."""
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted, starting polling")
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Telegram bot stopped")
    finally:
        await bot.session.close()
