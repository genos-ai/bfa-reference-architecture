"""
Callback Data Factories.

Type-safe callback data using aiogram's CallbackData factory.

aiogram v3 CallbackData:
- Define callback data as classes inheriting from CallbackData
- Specify prefix for routing
- Add typed fields for data
- Use .filter() in handlers for type-safe filtering

Example:
    class MyCallback(CallbackData, prefix="my"):
        action: str
        item_id: int

    # Creating callback data
    button = InlineKeyboardButton(
        text="Click",
        callback_data=MyCallback(action="view", item_id=123).pack()
    )

    # Handling callback
    @router.callback_query(MyCallback.filter(F.action == "view"))
    async def handle_view(callback: CallbackQuery, callback_data: MyCallback):
        item_id = callback_data.item_id
"""

from modules.clients.telegram.callbacks.common import ActionCallback, MenuCallback, PaginationCallback

__all__ = [
    "ActionCallback",
    "MenuCallback",
    "PaginationCallback",
]
