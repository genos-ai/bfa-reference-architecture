"""
Notification Service.

Service for sending proactive notifications and alerts to users via Telegram.
Handles rate limiting, message queuing, and delivery tracking.

Usage:
    # Simple alert
    await send_alert(user_id=123456789, message="Task completed successfully!")

    # Rich notification with data
    await send_notification(
        user_id=123456789,
        title="Task Completed",
        body="Your background job has finished",
        alert_type=AlertType.SUCCESS,
        data={"task_id": "123", "duration": "5.2s"},
    )

    # Using the service directly
    service = get_notification_service()
    await service.send_alert(user_id, "Title", "Body", AlertType.INFO)
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger, log_with_source
from modules.backend.core.utils import utc_now

logger = get_logger(__name__)

# Window in seconds (1 minute, matching messages_per_minute config)
RATE_LIMIT_WINDOW = 60


def _get_notification_rate_limit() -> int:
    """Get telegram messages_per_minute from security.yaml."""
    return get_app_config().security.rate_limiting.telegram.messages_per_minute


class AlertType(str, Enum):
    """Types of alerts for categorization and formatting."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    SYSTEM = "system"


# Emoji mapping for alert types
ALERT_EMOJI = {
    AlertType.INFO: "ℹ️",
    AlertType.SUCCESS: "✅",
    AlertType.WARNING: "⚠️",
    AlertType.ERROR: "❌",
    AlertType.SYSTEM: "🔧",
}


@dataclass
class NotificationResult:
    """Result of a notification send attempt."""

    success: bool
    user_id: int
    message_id: int | None = None
    error: str | None = None
    rate_limited: bool = False
    timestamp: datetime = field(default_factory=utc_now)


class NotificationService:
    """
    Service for sending Telegram notifications with rate limiting.

    Features:
    - Rate limiting per user to avoid Telegram API limits
    - Message formatting with alert types
    - Delivery tracking and logging
    - Batch sending support

    Usage:
        service = NotificationService()

        # Send simple message
        result = await service.send(user_id, "Hello!")

        # Send formatted alert
        result = await service.send_alert(
            user_id=123,
            title="Task Completed",
            body="Your export is ready for download",
            alert_type=AlertType.SUCCESS,
        )

        # Send to multiple users
        results = await service.broadcast([123, 456], "System maintenance in 1 hour")
    """

    def __init__(self) -> None:
        """Initialize the notification service."""
        # Rate limiting: {user_id: [timestamps]}
        self._rate_limits: dict[int, list[float]] = defaultdict(list)
        self._rate_limit_per_user = _get_notification_rate_limit()

    def _check_rate_limit(self, user_id: int) -> bool:
        """
        Check if user is within rate limits.

        Args:
            user_id: Telegram user ID

        Returns:
            True if within limits, False if rate limited
        """
        import time

        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW

        # Clean old entries
        self._rate_limits[user_id] = [
            ts for ts in self._rate_limits[user_id] if ts > window_start
        ]

        # Check limit
        if len(self._rate_limits[user_id]) >= self._rate_limit_per_user:
            return False

        # Record this attempt
        self._rate_limits[user_id].append(now)
        return True

    async def send(
        self,
        user_id: int,
        text: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
        reply_markup: Any = None,
    ) -> NotificationResult:
        """
        Send a message to a user.

        Args:
            user_id: Telegram user ID
            text: Message text (HTML supported)
            parse_mode: Parse mode (HTML, Markdown, MarkdownV2)
            disable_notification: Send silently
            reply_markup: Optional keyboard markup

        Returns:
            NotificationResult with success status
        """
        from modules.clients.telegram.bot import get_bot

        # Check rate limit
        if not self._check_rate_limit(user_id):
            log_with_source(
                logger,
                "telegram",
                "warning",
                "Rate limit exceeded for user",
                user_id=user_id,
            )
            return NotificationResult(
                success=False,
                user_id=user_id,
                rate_limited=True,
                error="Rate limit exceeded",
            )

        try:
            bot = get_bot()
            message = await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=parse_mode,
                disable_notification=disable_notification,
                reply_markup=reply_markup,
            )

            log_with_source(
                logger,
                "telegram",
                "info",
                "Notification sent",
                user_id=user_id,
                message_id=message.message_id,
            )

            return NotificationResult(
                success=True,
                user_id=user_id,
                message_id=message.message_id,
            )

        except Exception as e:
            error_msg = str(e)

            log_with_source(
                logger,
                "telegram",
                "error",
                "Failed to send notification",
                user_id=user_id,
                error=error_msg,
            )

            return NotificationResult(
                success=False,
                user_id=user_id,
                error=error_msg,
            )

    async def send_alert(
        self,
        user_id: int,
        title: str,
        body: str,
        alert_type: AlertType = AlertType.INFO,
        data: dict[str, Any] | None = None,
        disable_notification: bool = False,
    ) -> NotificationResult:
        """
        Send a formatted alert message.

        Args:
            user_id: Telegram user ID
            title: Alert title
            body: Alert body text
            alert_type: Type of alert for emoji/formatting
            data: Optional structured data to include
            disable_notification: Send silently

        Returns:
            NotificationResult with success status
        """
        emoji = ALERT_EMOJI.get(alert_type, "📢")

        # Format message
        lines = [
            f"{emoji} <b>{title}</b>",
            "",
            body,
        ]

        # Add data fields if provided
        if data:
            lines.append("")
            for key, value in data.items():
                # Convert snake_case to Title Case
                label = key.replace("_", " ").title()
                lines.append(f"<b>{label}:</b> <code>{value}</code>")

        text = "\n".join(lines)

        return await self.send(
            user_id=user_id,
            text=text,
            disable_notification=disable_notification,
        )

    async def broadcast(
        self,
        user_ids: list[int],
        text: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
        delay_between: float = 0.05,
    ) -> list[NotificationResult]:
        """
        Send a message to multiple users.

        Args:
            user_ids: List of Telegram user IDs
            text: Message text
            parse_mode: Parse mode
            disable_notification: Send silently
            delay_between: Delay between sends (seconds) to avoid rate limits

        Returns:
            List of NotificationResult for each user
        """
        results = []

        for user_id in user_ids:
            result = await self.send(
                user_id=user_id,
                text=text,
                parse_mode=parse_mode,
                disable_notification=disable_notification,
            )
            results.append(result)

            # Small delay to avoid hitting Telegram rate limits
            if delay_between > 0:
                await asyncio.sleep(delay_between)

        # Log summary
        success_count = sum(1 for r in results if r.success)
        log_with_source(
            logger,
            "telegram",
            "info",
            "Broadcast completed",
            total=len(user_ids),
            success=success_count,
            failed=len(user_ids) - success_count,
        )

        return results

    # ==========================================================================
    # Convenience Methods for Common Alert Types
    # ==========================================================================

    async def send_success(
        self,
        user_id: int,
        title: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> NotificationResult:
        """Send success notification."""
        return await self.send_alert(
            user_id=user_id,
            title=title,
            body=message,
            alert_type=AlertType.SUCCESS,
            data=data,
        )

    async def send_warning(
        self,
        user_id: int,
        title: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> NotificationResult:
        """Send warning notification."""
        return await self.send_alert(
            user_id=user_id,
            title=title,
            body=message,
            alert_type=AlertType.WARNING,
            data=data,
        )

    async def send_error(
        self,
        user_id: int,
        title: str,
        error_message: str,
        context: dict[str, Any] | None = None,
    ) -> NotificationResult:
        """Send error notification."""
        return await self.send_alert(
            user_id=user_id,
            title=title,
            body=error_message,
            alert_type=AlertType.ERROR,
            data=context,
        )

    async def send_system(
        self,
        user_id: int,
        title: str,
        message: str,
    ) -> NotificationResult:
        """Send system notification."""
        return await self.send_alert(
            user_id=user_id,
            title=title,
            body=message,
            alert_type=AlertType.SYSTEM,
        )


# Module-level singleton
_notification_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    """Get or create the notification service singleton."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


# =============================================================================
# Convenience Functions
# =============================================================================


async def send_alert(
    user_id: int,
    message: str,
    alert_type: AlertType = AlertType.INFO,
    disable_notification: bool = False,
) -> NotificationResult:
    """
    Send a simple alert message.

    Args:
        user_id: Telegram user ID
        message: Alert message
        alert_type: Type of alert
        disable_notification: Send silently

    Returns:
        NotificationResult

    Example:
        await send_alert(123456789, "Task completed!", AlertType.SUCCESS)
    """
    service = get_notification_service()
    emoji = ALERT_EMOJI.get(alert_type, "📢")
    text = f"{emoji} {message}"

    return await service.send(
        user_id=user_id,
        text=text,
        disable_notification=disable_notification,
    )


async def send_notification(
    user_id: int,
    title: str,
    body: str,
    alert_type: AlertType = AlertType.INFO,
    data: dict[str, Any] | None = None,
) -> NotificationResult:
    """
    Send a formatted notification.

    Args:
        user_id: Telegram user ID
        title: Notification title
        body: Notification body
        alert_type: Type of alert
        data: Optional structured data

    Returns:
        NotificationResult

    Example:
        await send_notification(
            user_id=123456789,
            title="Export Ready",
            body="Your data export has completed",
            alert_type=AlertType.SUCCESS,
            data={"file_size": "2.5 MB", "records": "1,234"},
        )
    """
    service = get_notification_service()
    return await service.send_alert(
        user_id=user_id,
        title=title,
        body=body,
        alert_type=alert_type,
        data=data,
    )
