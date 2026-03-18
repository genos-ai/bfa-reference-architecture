"""
Unit tests for Telegram notification service.

Tests notification sending, rate limiting, and alert formatting.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch target for get_bot (imported inside the send method)
GET_BOT_PATCH = "modules.clients.telegram.bot.get_bot"


class TestNotificationService:
    """Tests for NotificationService."""

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """Test successful message sending."""
        from modules.clients.telegram.services.notifications import NotificationService

        service = NotificationService()

        mock_message = MagicMock()
        mock_message.message_id = 12345

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        with patch(GET_BOT_PATCH, return_value=mock_bot):
            result = await service.send(user_id=123, text="Hello!")

        assert result.success is True
        assert result.user_id == 123
        assert result.message_id == 12345
        mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_failure(self):
        """Test message sending failure."""
        from modules.clients.telegram.services.notifications import NotificationService

        service = NotificationService()

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(side_effect=Exception("Bot blocked"))

        with patch(GET_BOT_PATCH, return_value=mock_bot):
            result = await service.send(user_id=123, text="Hello!")

        assert result.success is False
        assert result.user_id == 123
        assert result.error == "Bot blocked"

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test that rate limiting blocks excessive requests."""
        from modules.clients.telegram.services.notifications import NotificationService

        service = NotificationService()
        rate_limit = service._rate_limit_per_user

        mock_message = MagicMock()
        mock_message.message_id = 12345

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        with patch(GET_BOT_PATCH, return_value=mock_bot):
            # Send up to the limit
            for i in range(rate_limit):
                result = await service.send(user_id=123, text=f"Message {i}")
                assert result.success is True

            # Next one should be rate limited
            result = await service.send(user_id=123, text="Over limit")
            assert result.success is False
            assert result.rate_limited is True

    @pytest.mark.asyncio
    async def test_rate_limit_per_user(self):
        """Test that rate limits are tracked per user."""
        from modules.clients.telegram.services.notifications import NotificationService

        service = NotificationService()
        rate_limit = service._rate_limit_per_user

        mock_message = MagicMock()
        mock_message.message_id = 12345

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        with patch(GET_BOT_PATCH, return_value=mock_bot):
            # Exhaust rate limit for user 123
            for i in range(rate_limit):
                await service.send(user_id=123, text=f"Message {i}")

            # User 456 should still be able to send
            result = await service.send(user_id=456, text="Hello!")
            assert result.success is True


class TestSendAlert:
    """Tests for send_alert convenience function."""

    @pytest.mark.asyncio
    async def test_send_alert_formats_message(self):
        """Test that alerts are formatted with emoji."""
        from modules.clients.telegram.services.notifications import AlertType, send_alert

        mock_message = MagicMock()
        mock_message.message_id = 12345

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        with patch(GET_BOT_PATCH, return_value=mock_bot):
            result = await send_alert(
                user_id=123,
                message="Task completed successfully!",
                alert_type=AlertType.SUCCESS,
            )

        assert result.success is True
        # Check that the message includes the success emoji
        call_args = mock_bot.send_message.call_args
        assert "✅" in call_args.kwargs["text"]
        assert "Task completed successfully!" in call_args.kwargs["text"]


class TestSendNotification:
    """Tests for send_notification convenience function."""

    @pytest.mark.asyncio
    async def test_send_notification_formats_with_data(self):
        """Test that notifications include formatted data."""
        from modules.clients.telegram.services.notifications import AlertType, send_notification

        mock_message = MagicMock()
        mock_message.message_id = 12345

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        with patch(GET_BOT_PATCH, return_value=mock_bot):
            result = await send_notification(
                user_id=123,
                title="Export Ready",
                body="Your data export has completed",
                alert_type=AlertType.SUCCESS,
                data={"file_size": "2.5 MB", "records": "1,234"},
            )

        assert result.success is True
        call_args = mock_bot.send_message.call_args
        text = call_args.kwargs["text"]

        # Check title is bold
        assert "<b>Export Ready</b>" in text
        # Check body is included
        assert "Your data export has completed" in text
        # Check data fields are formatted
        assert "File Size:" in text
        assert "2.5 MB" in text


class TestNotificationServiceConvenienceMethods:
    """Tests for convenience methods on NotificationService."""

    @pytest.mark.asyncio
    async def test_send_success(self):
        """Test success notification."""
        from modules.clients.telegram.services.notifications import NotificationService

        service = NotificationService()

        mock_message = MagicMock()
        mock_message.message_id = 12345

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        with patch(GET_BOT_PATCH, return_value=mock_bot):
            result = await service.send_success(
                user_id=123,
                title="Task Completed",
                message="Your export is ready",
                data={"file_size": "2.5 MB"},
            )

        assert result.success is True
        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Task Completed" in text
        assert "Your export is ready" in text
        assert "✅" in text

    @pytest.mark.asyncio
    async def test_send_warning(self):
        """Test warning notification."""
        from modules.clients.telegram.services.notifications import NotificationService

        service = NotificationService()

        mock_message = MagicMock()
        mock_message.message_id = 12345

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        with patch(GET_BOT_PATCH, return_value=mock_bot):
            result = await service.send_warning(
                user_id=123,
                title="Storage Warning",
                message="You are approaching your storage limit",
            )

        assert result.success is True
        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Storage Warning" in text
        assert "⚠️" in text

    @pytest.mark.asyncio
    async def test_send_error(self):
        """Test error notification."""
        from modules.clients.telegram.services.notifications import NotificationService

        service = NotificationService()

        mock_message = MagicMock()
        mock_message.message_id = 12345

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        with patch(GET_BOT_PATCH, return_value=mock_bot):
            result = await service.send_error(
                user_id=123,
                title="Task Failed",
                error_message="Unable to process your request",
                context={"task_id": "123"},
            )

        assert result.success is True
        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Task Failed" in text
        assert "❌" in text

    @pytest.mark.asyncio
    async def test_send_system(self):
        """Test system notification."""
        from modules.clients.telegram.services.notifications import NotificationService

        service = NotificationService()

        mock_message = MagicMock()
        mock_message.message_id = 12345

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        with patch(GET_BOT_PATCH, return_value=mock_bot):
            result = await service.send_system(
                user_id=123,
                title="Scheduled Maintenance",
                message="System will be down for maintenance at 2:00 AM UTC",
            )

        assert result.success is True
        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Scheduled Maintenance" in text
        assert "🔧" in text


class TestBroadcast:
    """Tests for broadcast functionality."""

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_users(self):
        """Test broadcasting to multiple users."""
        from modules.clients.telegram.services.notifications import NotificationService

        service = NotificationService()

        mock_message = MagicMock()
        mock_message.message_id = 12345

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=mock_message)

        with patch(GET_BOT_PATCH, return_value=mock_bot):
            results = await service.broadcast(
                user_ids=[123, 456, 789],
                text="System maintenance in 1 hour",
                delay_between=0,  # No delay for testing
            )

        assert len(results) == 3
        assert all(r.success for r in results)
        assert mock_bot.send_message.call_count == 3


class TestAlertType:
    """Tests for AlertType enum."""

    def test_alert_types_have_emojis(self):
        """Test that all alert types have emoji mappings."""
        from modules.clients.telegram.services.notifications import ALERT_EMOJI, AlertType

        for alert_type in AlertType:
            assert alert_type in ALERT_EMOJI
            assert len(ALERT_EMOJI[alert_type]) > 0

    def test_alert_type_values(self):
        """Test alert type string values."""
        from modules.clients.telegram.services.notifications import AlertType

        assert AlertType.INFO.value == "info"
        assert AlertType.SUCCESS.value == "success"
        assert AlertType.WARNING.value == "warning"
        assert AlertType.ERROR.value == "error"
        assert AlertType.SYSTEM.value == "system"
