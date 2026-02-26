# 26 - Telegram Client Integration (Optional Module)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2026-02-18*

## Changelog

- 1.0.0 (2026-02-18): Initial Telegram Client API integration guide (MTProto)

---

## Module Status: Optional

This module is **optional**. Adopt when your project needs:
- Channel/group message scraping
- Message history access
- Monitoring external Telegram channels
- Agentic AI with autonomous Telegram access
- Data collection from public channels

For standard bot interactions (user commands, notifications, interactive UI), use **25-telegram-bot-integration.md** (Bot API) instead.

This module is often adopted **alongside** 25-telegram-bot-integration.md in a hybrid architecture.

---

## Context

The Bot API (25-telegram-bot-integration) is designed for bots that respond to users — it cannot access channel message history, scrape public channels, search messages, or join channels programmatically. When a project needs any of these data acquisition capabilities, it must use Telegram's Client API (MTProto protocol), which operates as a user account rather than a bot.

This module exists because Client API integration carries significant risks that must be managed carefully. Unlike the Bot API (which is designed for automation), the Client API was designed for human users. Telegram actively detects and restricts automated usage, and misuse can result in account bans. The module defines rate limiting patterns, human-like delay strategies, session management, and connection recovery specifically to mitigate these risks.

The recommended architecture is hybrid: Bot API for user interaction (commands, notifications, interactive UI) and Client API for data acquisition (channel monitoring, message history, scraping), decoupled via a Redis message queue. This separation means a Client API failure or rate limit does not disrupt user-facing bot functionality. The module integrates with event architecture (21) for message queue patterns and can feed data into the agentic architecture (40) for AI-powered analysis of scraped content.

---

## Bot API vs Client API

Telegram exposes two fundamentally different APIs. Understanding when to use each is critical.

### Comparison

| Capability | Bot API (aiogram) | Client API (Telethon/Pyrogram) |
|------------|-------------------|--------------------------------|
| Authentication | Bot token from @BotFather | Phone number + OTP + 2FA |
| Message history | Only new messages after bot added | Full history access |
| Join channels programmatically | Must be manually added | Can join via API |
| Scrape public channels | Not possible | Full access |
| Search messages | Not available | Full search capability |
| Initiate conversations | User must /start first | Can message any user |
| Inline keyboards/interactive UI | Excellent support | Limited |
| File downloads | 20 MB limit | Up to 4 GB |
| Account ban risk | None | Significant |
| Rate limits | Documented, generous | Opaque, strict |
| Session management | Simple token | Complex session files |

### When to Use Each

| Use Case | Recommended API | Rationale |
|----------|-----------------|-----------|
| User-initiated commands | Bot API | Interactive, safe, designed for this |
| Push notifications to users | Bot API | Channel posts or DMs |
| Interactive workflows (FSM) | Bot API | Built-in state management |
| Scraping external channels | Client API | Bot API cannot access |
| Message history retrieval | Client API | Bot API has no history access |
| Automated channel monitoring | Client API | Real-time event handlers |
| Agentic AI with Telegram access | Either/Both | Depends on agent capabilities needed |
| Multi-user service | Bot API | One bot serves many users |
| Single-user automation | Client API | Personal account automation |

---

## Architecture: Hybrid Pattern

For applications requiring both user interaction and data acquisition, deploy both APIs:

```
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐              ┌──────────────────┐         │
│  │   Bot (aiogram)  │              │ Client (Telethon)│         │
│  │                  │              │                  │         │
│  │  - User commands │              │  - Channel scrape│         │
│  │  - Notifications │              │  - History access│         │
│  │  - Interactive UI│              │  - Data collection│        │
│  │  - Webhook mode  │              │  - Event handlers│         │
│  └────────┬─────────┘              └────────┬─────────┘         │
│           │                                 │                    │
│           └─────────────┬───────────────────┘                    │
│                         │                                        │
│                         ▼                                        │
│           ┌─────────────────────────┐                           │
│           │   Message Queue (Redis) │                           │
│           │   - Decouple scraping   │                           │
│           │   - Buffer processing   │                           │
│           └────────────┬────────────┘                           │
│                        │                                         │
│                        ▼                                         │
│           ┌─────────────────────────┐                           │
│           │  Business Logic Layer   │                           │
│           │  modules/backend/       │                           │
│           └─────────────────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Bot for user interaction**: All user-facing features use Bot API
2. **Client for data access**: Channel monitoring, history, scraping use Client API
3. **Message queue between layers**: Decouple data acquisition from processing
4. **Graceful degradation**: System continues if Client API fails (account ban risk)
5. **Shared business logic**: Both APIs call the same backend services

---

## Module Structure

```
modules/telegram_client/
├── __init__.py              # Module exports
├── client.py                # Telethon client creation
├── session.py               # Session management
├── handlers/                # Event handlers
│   ├── __init__.py
│   └── channel_monitor.py   # Channel message handlers
├── scrapers/                # Data collection
│   ├── __init__.py
│   ├── channel.py           # Channel scraping
│   └── history.py           # Message history
└── services/                # Client-specific services
    ├── __init__.py
    └── message_processor.py # Process scraped messages
```

---

## Configuration

### Secrets (.env)

Add to `config/.env` (secrets only):

```bash
# Telegram Client API (MTProto) - secrets
TELEGRAM_CLIENT_API_ID=12345678
TELEGRAM_CLIENT_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_CLIENT_PHONE=+1234567890
TELEGRAM_CLIENT_SESSION_STRING=
TELEGRAM_CLIENT_2FA_PASSWORD=
```

These fields must be added to the `Settings` class in `modules/backend/core/config.py`:

```python
class Settings(BaseSettings):
    """Secrets loaded from config/.env. Only passwords, tokens, and keys."""

    # ... existing secrets ...

    # Telegram Client API (MTProto)
    telegram_client_api_id: str
    telegram_client_api_hash: str
    telegram_client_phone: str
    telegram_client_session_string: str
    telegram_client_2fa_password: str
```

### Application Settings (YAML)

Add to `config/settings/application.yaml`:

```yaml
telegram_client:
  monitored_channels:
    - "channel_username_1"
    - "channel_username_2"
  scrape_limit: 100
  human_delay_min: 0.5
  human_delay_max: 2.0
  flood_wait_max: 300
  connection_check_interval: 60
```

---

## Core Components

### Client Creation

```python
# modules/telegram_client/client.py

from telethon import TelegramClient
from telethon.sessions import StringSession

from modules.backend.core.config import get_settings

async def create_client() -> TelegramClient:
    """Create configured Telethon client."""
    settings = get_settings()

    session = StringSession(settings.telegram_client_session_string or "")

    client = TelegramClient(
        session,
        int(settings.telegram_client_api_id),
        settings.telegram_client_api_hash,
        connection_retries=5,
        retry_delay=1,
        auto_reconnect=True,
    )

    return client


async def get_connected_client() -> TelegramClient:
    """Get authenticated and connected client."""
    client = await create_client()
    await client.connect()
    
    if not await client.is_user_authorized():
        raise RuntimeError(
            "Client not authorized. Run session generation script first."
        )
    
    return client
```

### Session Generation Script

```python
# scripts/telegram_generate_session.py

"""
Generate Telegram session string for Client API.

Run once interactively, then store the session string securely.

Usage:
    python scripts/telegram_generate_session.py
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

async def main():
    api_id = input("Enter API ID: ")
    api_hash = input("Enter API Hash: ")
    
    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()
    
    if not await client.is_user_authorized():
        phone = input("Enter phone number (with country code): ")
        await client.send_code_request(phone)
        code = input("Enter the code you received: ")
        
        try:
            await client.sign_in(phone, code)
        except Exception:
            password = input("Enter 2FA password: ")
            await client.sign_in(password=password)
    
    session_string = client.session.save()
    print("\n" + "=" * 60)
    print("SESSION STRING (store securely in TELEGRAM_SESSION_STRING):")
    print("=" * 60)
    print(session_string)
    print("=" * 60)
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Channel Monitoring

### Event-Based Monitoring

```python
# modules/telegram_client/handlers/channel_monitor.py

from telethon import events
from telethon.tl.types import Channel

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


def setup_channel_handlers(client: TelegramClient, channels: list[str]):
    """Register event handlers for channel monitoring."""
    
    @client.on(events.NewMessage(chats=channels))
    async def handle_new_message(event):
        """Process new messages from monitored channels."""
        message = event.message
        chat = await event.get_chat()
        
        logger.info(
            "New channel message",
            extra={
                "channel": chat.title if hasattr(chat, "title") else str(chat.id),
                "message_id": message.id,
                "has_media": message.media is not None,
            }
        )
        
        # Queue for processing (don't block event handler)
        await queue_message_for_processing({
            "channel_id": chat.id,
            "message_id": message.id,
            "text": message.text,
            "date": message.date.isoformat(),
            "media_type": type(message.media).__name__ if message.media else None,
        })
    
    @client.on(events.MessageEdited(chats=channels))
    async def handle_edited_message(event):
        """Process edited messages."""
        logger.info(
            "Message edited",
            extra={"message_id": event.message.id}
        )
        # Handle edit as needed
```

### Starting the Monitor

```python
# Integration with FastAPI lifespan

from contextlib import asynccontextmanager
from modules.backend.core.config import get_app_config, get_settings
from modules.telegram_client.client import get_connected_client
from modules.telegram_client.handlers.channel_monitor import setup_channel_handlers

@asynccontextmanager
async def lifespan(app: FastAPI):
    app_config = get_app_config()
    settings = get_settings()
    client = None

    # Start Bot API (from 25-telegram-bot-integration.md)
    # ... bot setup ...

    # Start Client API monitoring (if configured)
    if settings.telegram_client_session_string:
        try:
            client = await get_connected_client()
            channels = app_config.application["telegram_client"]["monitored_channels"]
            setup_channel_handlers(client, channels)
            asyncio.create_task(client.run_until_disconnected())
            logger.info("Telegram client monitoring started")
        except Exception as e:
            logger.warning(f"Client API not available: {e}")

    yield

    if client and client.is_connected():
        await client.disconnect()
```

---

## Message History Retrieval

### Fetching History

```python
# modules/telegram_client/scrapers/history.py

from datetime import datetime
from telethon.tl.functions.messages import GetHistoryRequest

async def get_channel_history(
    client: TelegramClient,
    channel: str | int,
    limit: int = 100,
    offset_date: datetime | None = None,
) -> list[dict]:
    """
    Fetch message history from a channel.
    
    Args:
        client: Connected Telethon client
        channel: Channel username or ID
        limit: Maximum messages to fetch (max 100 per request)
        offset_date: Fetch messages before this date
    
    Returns:
        List of message dictionaries
    """
    entity = await client.get_entity(channel)
    
    messages = []
    async for message in client.iter_messages(
        entity,
        limit=limit,
        offset_date=offset_date,
    ):
        messages.append({
            "id": message.id,
            "date": message.date.isoformat(),
            "text": message.text,
            "sender_id": message.sender_id,
            "reply_to": message.reply_to_msg_id,
            "forwards": message.forwards,
            "views": message.views,
            "media_type": type(message.media).__name__ if message.media else None,
        })
    
    return messages
```

### Pagination Pattern

```python
async def scrape_full_history(
    client: TelegramClient,
    channel: str,
    max_messages: int = 10000,
) -> list[dict]:
    """
    Scrape full channel history with pagination.
    
    Handles rate limits automatically.
    """
    all_messages = []
    offset_date = None
    
    while len(all_messages) < max_messages:
        batch = await get_channel_history(
            client,
            channel,
            limit=100,
            offset_date=offset_date,
        )
        
        if not batch:
            break  # No more messages
        
        all_messages.extend(batch)
        offset_date = datetime.fromisoformat(batch[-1]["date"])
        
        logger.info(
            "History progress",
            extra={"fetched": len(all_messages), "target": max_messages}
        )
        
        # Respect rate limits
        await asyncio.sleep(1)
    
    return all_messages[:max_messages]
```

---

## Rate Limits and Error Handling

### FloodWait Handling

Telegram enforces rate limits via `FloodWaitError`. Handle gracefully:

```python
from telethon.errors import FloodWaitError

async def safe_api_call(coro, max_wait: int = 300):
    """
    Execute API call with FloodWait handling.
    
    Args:
        coro: Coroutine to execute
        max_wait: Maximum seconds to wait (default 5 minutes)
    
    Raises:
        FloodWaitError: If wait time exceeds max_wait
    """
    try:
        return await coro
    except FloodWaitError as e:
        if e.seconds > max_wait:
            logger.error(
                "FloodWait too long",
                extra={"wait_seconds": e.seconds, "max_wait": max_wait}
            )
            raise
        
        logger.warning(
            "FloodWait, sleeping",
            extra={"wait_seconds": e.seconds}
        )
        await asyncio.sleep(e.seconds)
        return await coro
```

### Connection Recovery

```python
async def maintain_connection(client: TelegramClient):
    """Monitor and recover connection."""
    while True:
        if not client.is_connected():
            logger.warning("Client disconnected, reconnecting...")
            try:
                await client.connect()
                logger.info("Client reconnected")
            except Exception as e:
                logger.error(f"Reconnection failed: {e}")
                await asyncio.sleep(30)
        
        await asyncio.sleep(60)  # Check every minute
```

---

## Account Ban Risk Mitigation

### Understanding the Risk

Telegram actively monitors Client API usage. Accounts can be banned for:
- Automated behavior patterns
- Bulk messaging
- Rapid channel joining
- VoIP/virtual phone numbers
- New accounts with immediate API usage
- Usage from flagged IP ranges

### Mitigation Strategies

| Strategy | Implementation |
|----------|----------------|
| Use established account | Account should be 6+ months old with normal usage history |
| Real phone number | Avoid VoIP numbers; use real SIM |
| Gradual warm-up | Don't immediately start heavy API usage |
| Human-like delays | Add random delays between operations |
| Residential IP | Avoid datacenter IPs if possible |
| Single session | Only one active session per account |
| Rate limit respect | Never retry immediately after FloodWait |

### Implementation

```python
import random
import asyncio

async def human_delay():
    """Add human-like delay between operations. Reads bounds from YAML config."""
    from modules.backend.core.config import get_app_config
    tc = get_app_config().application["telegram_client"]
    delay = random.uniform(tc["human_delay_min"], tc["human_delay_max"])
    await asyncio.sleep(delay)


async def safe_join_channel(client: TelegramClient, channel: str):
    """Join channel with human-like behavior."""
    # Random delay before action
    await human_delay(1.0, 3.0)
    
    try:
        entity = await client.get_entity(channel)
        await human_delay(0.5, 1.5)
        await client(JoinChannelRequest(entity))
        logger.info(f"Joined channel: {channel}")
    except FloodWaitError as e:
        logger.warning(f"Rate limited, cannot join {channel}")
        raise
```

### Graceful Degradation

Design the system to function without the Client API:

```python
async def get_channel_data(channel: str) -> dict | None:
    """
    Get channel data with fallback.
    
    Tries Client API first, falls back to cached data.
    """
    try:
        client = await get_connected_client()
        return await fetch_channel_data(client, channel)
    except (RuntimeError, ConnectionError) as e:
        logger.warning(
            "Client API unavailable, using cache",
            extra={"error": str(e)}
        )
        return await get_cached_channel_data(channel)
```

---

## Security Considerations

### Session String Protection

The session string grants full account access. Protect it like a password:

```python
# Session string contains auth key - never log it
# Store in:
# - Environment variable (development)
# - Secrets manager (production: Vault, AWS Secrets Manager)
# - Encrypted at rest

# Never:
# - Commit to version control
# - Log in any form
# - Share across environments
```

### Credential Separation

Use different `config/.env` files per environment:

```bash
# Development config/.env
TELEGRAM_CLIENT_API_ID=dev_id
TELEGRAM_CLIENT_API_HASH=dev_hash

# Production config/.env
TELEGRAM_CLIENT_API_ID=prod_id
TELEGRAM_CLIENT_API_HASH=prod_hash
```

### Audit Logging

```python
# Log all Client API operations
logger.info(
    "Client API operation",
    extra={
        "operation": "get_history",
        "channel": channel_id,
        "message_count": len(messages),
        "timestamp": utc_now().isoformat(),
    }
)
```

---

## Integration with AI-First Platform

When adopting the AI-First Platform profile (docs 40-46), the Telegram Client API serves as an autonomous data acquisition layer — monitoring channels, scraping history, and feeding data to agents for analysis. Agent implementation patterns are defined in `41-agentic-pydanticai.md`.

| Agent Type | API Choice | Pattern |
|------------|------------|---------|
| Reactive (responds to users) | Bot API | Webhook handlers |
| Autonomous (monitors channels) | Client API | Event handlers |
| Hybrid (both capabilities) | Both APIs | Coordinated via message queue |

---

## Testing

### Unit Testing (Mocked Client)

```python
# tests/unit/telegram_client/test_scrapers.py

import pytest
from unittest.mock import AsyncMock, MagicMock

from modules.telegram_client.scrapers.history import get_channel_history


class TestGetChannelHistory:
    @pytest.mark.asyncio
    async def test_returns_message_list(self):
        # Arrange
        mock_client = AsyncMock()
        mock_message = MagicMock()
        mock_message.id = 123
        mock_message.text = "Test message"
        mock_message.date.isoformat.return_value = "2026-02-18T12:00:00"
        mock_message.sender_id = 456
        mock_message.reply_to_msg_id = None
        mock_message.forwards = 10
        mock_message.views = 100
        mock_message.media = None
        
        mock_client.iter_messages = AsyncMock(return_value=[mock_message])
        mock_client.get_entity = AsyncMock()
        
        # Act
        result = await get_channel_history(mock_client, "test_channel", limit=10)
        
        # Assert
        assert len(result) == 1
        assert result[0]["id"] == 123
        assert result[0]["text"] == "Test message"
```

### Integration Testing

```python
# tests/integration/telegram_client/test_connection.py

import pytest
from modules.telegram_client.client import get_connected_client


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("TELEGRAM_SESSION_STRING"),
    reason="Telegram session not configured"
)
class TestClientConnection:
    @pytest.mark.asyncio
    async def test_client_connects(self):
        client = await get_connected_client()
        assert client.is_connected()
        assert await client.is_user_authorized()
        await client.disconnect()
```

---

## Deployment

### Production Checklist

- [ ] Session string stored in secrets manager
- [ ] API credentials separate from bot credentials
- [ ] Account is established (6+ months old)
- [ ] Real phone number (not VoIP)
- [ ] Monitoring for connection drops
- [ ] Graceful degradation implemented
- [ ] Rate limit handling tested
- [ ] Audit logging enabled

### Process Management

Run as separate process from main API (isolation):

```ini
# /etc/systemd/system/app-telegram-client.service

[Unit]
Description=Telegram Client Monitor
After=network.target redis.service

[Service]
Type=simple
User=app
WorkingDirectory=/opt/app/current
EnvironmentFile=/opt/app/.env
ExecStart=/opt/app/venv/bin/python -m modules.telegram_client.monitor
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

---

## When to Avoid Client API

Do not use Client API when:

| Situation | Reason | Alternative |
|-----------|--------|-------------|
| Multi-user SaaS | Each user would need own account | Bot API only |
| High-volume messaging | Ban risk too high | Bot API for messaging |
| Mission-critical path | Ban would break system | Bot API or redundancy |
| Compliance requirements | ToS concerns | Bot API only |
| No fallback acceptable | Single point of failure | Bot API only |

---

## Adoption Checklist

When adopting this module:

- [ ] Review account ban risks with stakeholders
- [ ] Obtain Telegram API credentials from my.telegram.org
- [ ] Set up dedicated Telegram account (not personal)
- [ ] Generate session string interactively
- [ ] Store session string in secrets manager
- [ ] Implement graceful degradation
- [ ] Set up connection monitoring
- [ ] Configure rate limit handling
- [ ] Test FloodWait scenarios
- [ ] Document which channels are monitored
- [ ] Establish account recovery procedure

---

## Related Documentation

- [25-telegram-bot-integration.md](25-telegram-bot-integration.md) - Bot API integration (aiogram)
- [21-event-architecture.md](21-event-architecture.md) - Message queue patterns
- [24-llm-integration.md](24-llm-integration.md) - LLM integration patterns
- [10-observability.md](10-observability.md) - Logging standards
