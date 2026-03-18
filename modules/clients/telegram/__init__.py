"""
Telegram Bot Module.

aiogram v3 integration for Telegram bot functionality running in webhook mode
inside the FastAPI application.

Architecture:
- Bot runs on the same event loop as FastAPI (shared Uvicorn process)
- Webhook mode for production, polling for local development
- Bot is a thin presentation layer - all business logic in services/

Structure:
    modules/clients/telegram/
    ├── __init__.py          # This file - bot initialization
    ├── bot.py               # Bot and dispatcher setup
    ├── webhook.py           # Webhook endpoint for FastAPI
    ├── handlers/            # Command and message handlers
    │   ├── __init__.py
    │   ├── common.py        # /start, /help, /cancel
    │   └── example.py       # Example handlers
    ├── middlewares/         # Auth, rate limiting, logging
    │   ├── __init__.py
    │   ├── auth.py          # User ID whitelisting
    │   ├── logging.py       # Request logging
    │   └── rate_limit.py    # Rate limiting
    ├── keyboards/           # Inline and reply keyboards
    │   ├── __init__.py
    │   └── common.py        # Common keyboard builders
    ├── states/              # FSM state definitions
    │   ├── __init__.py
    │   └── example.py       # Example states
    └── callbacks/           # CallbackData factories
        ├── __init__.py
        └── common.py        # Common callback data

Usage:
    # In FastAPI app
    from modules.clients.telegram import create_bot, create_dispatcher, get_webhook_router

    bot = create_bot()
    dp = create_dispatcher()
    webhook_router = get_webhook_router(bot, dp)
    app.include_router(webhook_router)

Environment Variables:
    TELEGRAM_BOT_TOKEN: Bot token from BotFather
    TELEGRAM_WEBHOOK_SECRET: Secret for webhook validation
    TELEGRAM_WEBHOOK_PATH: Webhook URL path (default: /webhook/telegram)
    TELEGRAM_AUTHORIZED_USERS: Comma-separated list of authorized user IDs
"""

from modules.clients.telegram.bot import create_bot, create_dispatcher, get_bot, get_dispatcher

__all__ = [
    "create_bot",
    "create_dispatcher",
    "get_bot",
    "get_dispatcher",
]
