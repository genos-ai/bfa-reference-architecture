"""
Common Callback Data Factories.

Reusable callback data definitions for common patterns.
"""

from aiogram.filters.callback_data import CallbackData


class ActionCallback(CallbackData, prefix="action"):
    """
    Generic action callback for confirm/cancel patterns.

    Fields:
        action: The action type (confirm, cancel, etc.)
        action_id: Identifier for the action being confirmed

    Usage:
        # Creating buttons
        confirm_btn = InlineKeyboardButton(
            text="✅ Confirm",
            callback_data=ActionCallback(action="confirm", action_id="order_123").pack()
        )

        # Handling
        @router.callback_query(ActionCallback.filter(F.action == "confirm"))
        async def handle_confirm(callback: CallbackQuery, callback_data: ActionCallback):
            action_id = callback_data.action_id
    """

    action: str
    action_id: str


class MenuCallback(CallbackData, prefix="menu"):
    """
    Menu navigation callback.

    Fields:
        menu: Target menu identifier
        item_id: Optional item ID for context

    Usage:
        # Creating menu buttons
        settings_btn = InlineKeyboardButton(
            text="⚙️ Settings",
            callback_data=MenuCallback(menu="settings").pack()
        )

        # Handling
        @router.callback_query(MenuCallback.filter(F.menu == "settings"))
        async def show_settings(callback: CallbackQuery):
            await callback.message.edit_text("Settings menu...")
    """

    menu: str
    item_id: str | None = None


class PaginationCallback(CallbackData, prefix="page"):
    """
    Pagination callback for list navigation.

    Fields:
        list_type: Type of list being paginated
        page: Page number (0-indexed)
        per_page: Items per page

    Usage:
        # Creating pagination buttons
        next_btn = InlineKeyboardButton(
            text="Next ➡️",
            callback_data=PaginationCallback(
                list_type="orders",
                page=2,
                per_page=10
            ).pack()
        )

        # Handling
        @router.callback_query(PaginationCallback.filter())
        async def handle_pagination(callback: CallbackQuery, callback_data: PaginationCallback):
            page = callback_data.page
            items = await get_items(page=page, per_page=callback_data.per_page)
    """

    list_type: str
    page: int = 0
    per_page: int = 10


class ItemCallback(CallbackData, prefix="item"):
    """
    Item selection callback.

    Fields:
        action: Action to perform (view, edit, delete)
        item_type: Type of item
        item_id: Item identifier

    Usage:
        # Creating item buttons
        view_btn = InlineKeyboardButton(
            text="View",
            callback_data=ItemCallback(
                action="view",
                item_type="order",
                item_id="123"
            ).pack()
        )
    """

    action: str
    item_type: str
    item_id: str
