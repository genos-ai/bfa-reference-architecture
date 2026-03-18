"""
Keyboard Builders.

Reply and inline keyboard builders for Telegram bot.

aiogram v3 Keyboards:
- ReplyKeyboardMarkup: Persistent buttons below input field
- InlineKeyboardMarkup: Buttons attached to messages
- Use builders for cleaner keyboard construction

Example:
    from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

    # Inline keyboard
    builder = InlineKeyboardBuilder()
    builder.button(text="Click", callback_data="action")
    keyboard = builder.as_markup()

    # Reply keyboard
    builder = ReplyKeyboardBuilder()
    builder.button(text="Option 1")
    keyboard = builder.as_markup(resize_keyboard=True)
"""

from modules.clients.telegram.keyboards.common import (
    get_cancel_keyboard,
    get_confirmation_keyboard,
    get_main_menu_keyboard,
    get_pagination_keyboard,
)

__all__ = [
    "get_cancel_keyboard",
    "get_confirmation_keyboard",
    "get_main_menu_keyboard",
    "get_pagination_keyboard",
]
