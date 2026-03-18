"""
Telegram Bot Services.

Services for sending notifications and alerts via Telegram.
"""

from modules.clients.telegram.services.notifications import (
    NotificationService,
    get_notification_service,
    send_alert,
    send_notification,
)

__all__ = [
    "NotificationService",
    "get_notification_service",
    "send_alert",
    "send_notification",
]
