"""
Example Handlers.

Demonstrates various aiogram v3 patterns:
- Simple commands
- FSM (Finite State Machine)
- Inline keyboards with callbacks
- Integration with backend services
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from modules.backend.core.config import get_app_config
from modules.backend.core.logging import get_logger
from modules.clients.telegram.callbacks.common import ActionCallback
from modules.clients.telegram.keyboards.common import (
    get_confirmation_keyboard,
    get_main_menu_keyboard,
)
from modules.clients.telegram.states.example import FeedbackForm

logger = get_logger(__name__)

router = Router(name="example")


# =============================================================================
# Simple Command Handlers
# =============================================================================


@router.message(Command("echo"))
async def cmd_echo(message: Message) -> None:
    """
    Echo command - demonstrates simple command with arguments.

    Usage: /echo <text>
    """
    # Extract text after the command
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Usage: /echo <text>")
        return

    text = args[1]
    await message.answer(f"🔊 {text}")


@router.message(Command("info"))
async def cmd_info(message: Message, user_role: str) -> None:
    """
    Info command - demonstrates accessing middleware data.

    Shows information about the bot and user.
    """
    user = message.from_user
    info_text = f"""
<b>ℹ️ Bot Information</b>

<b>Your Details:</b>
• User ID: <code>{user.id}</code>
• Username: @{user.username or 'N/A'}
• Role: <code>{user_role}</code>

<b>Chat Details:</b>
• Chat ID: <code>{message.chat.id}</code>
• Chat Type: {message.chat.type}

<b>Bot Version:</b> {get_app_config().application.version}
"""

    await message.answer(info_text)


# =============================================================================
# FSM (Finite State Machine) Example
# =============================================================================


@router.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext) -> None:
    """
    Start feedback form - demonstrates FSM pattern.

    Collects multi-step input from user.
    """
    await state.set_state(FeedbackForm.waiting_for_category)
    await message.answer(
        "📝 <b>Feedback Form</b>\n\n"
        "Please select a category:\n"
        "• bug - Report a bug\n"
        "• feature - Request a feature\n"
        "• other - Other feedback\n\n"
        "Type your choice or /cancel to abort."
    )


@router.message(FeedbackForm.waiting_for_category, F.text.in_({"bug", "feature", "other"}))
async def process_category(message: Message, state: FSMContext) -> None:
    """Process feedback category selection."""
    await state.update_data(category=message.text)
    await state.set_state(FeedbackForm.waiting_for_message)
    await message.answer(
        f"Category: <b>{message.text}</b>\n\n"
        "Now please describe your feedback:"
    )


@router.message(FeedbackForm.waiting_for_category)
async def process_invalid_category(message: Message) -> None:
    """Handle invalid category input."""
    await message.answer(
        "❌ Invalid category. Please type one of:\n"
        "• bug\n"
        "• feature\n"
        "• other"
    )


@router.message(FeedbackForm.waiting_for_message)
async def process_feedback_message(message: Message, state: FSMContext) -> None:
    """Process feedback message and complete the form."""
    data = await state.get_data()
    category = data.get("category", "unknown")

    # In a real app, save to database via backend service
    logger.info(
        "Feedback received",
        extra={
            "user_id": message.from_user.id if message.from_user else None,
            "category": category,
            "message": message.text[:200],  # Truncate for logging
        },
    )

    await state.clear()
    await message.answer(
        "✅ <b>Thank you for your feedback!</b>\n\n"
        f"Category: {category}\n"
        f"Message: {message.text[:100]}{'...' if len(message.text or '') > 100 else ''}\n\n"
        "Your feedback has been recorded.",
        reply_markup=get_main_menu_keyboard(),
    )


# =============================================================================
# Inline Keyboard & Callback Example
# =============================================================================


@router.message(Command("confirm"))
async def cmd_confirm(message: Message) -> None:
    """
    Confirmation example - demonstrates inline keyboards with callbacks.

    Shows a confirmation dialog with Yes/No buttons.
    """
    await message.answer(
        "⚠️ <b>Confirmation Required</b>\n\n"
        "Do you want to proceed with this action?",
        reply_markup=get_confirmation_keyboard("example_action"),
    )


@router.callback_query(ActionCallback.filter(F.action == "confirm"))
async def callback_confirm(callback: CallbackQuery, callback_data: ActionCallback) -> None:
    """Handle confirmation callback."""
    action_id = callback_data.action_id

    # In a real app, perform the confirmed action
    logger.info(
        "Action confirmed",
        extra={
            "user_id": callback.from_user.id,
            "action_id": action_id,
        },
    )

    await callback.message.edit_text(
        f"✅ Action <code>{action_id}</code> confirmed and executed!"
    )
    await callback.answer("Action confirmed!")


@router.callback_query(ActionCallback.filter(F.action == "cancel"))
async def callback_cancel(callback: CallbackQuery, callback_data: ActionCallback) -> None:
    """Handle cancellation callback."""
    action_id = callback_data.action_id

    logger.info(
        "Action cancelled",
        extra={
            "user_id": callback.from_user.id,
            "action_id": action_id,
        },
    )

    await callback.message.edit_text(
        f"❌ Action <code>{action_id}</code> cancelled."
    )
    await callback.answer("Action cancelled!")


# =============================================================================
# Backend Integration Example
# =============================================================================


@router.message(Command("api_example"))
async def cmd_api_example(message: Message) -> None:
    """
    API integration example - demonstrates calling backend services.

    In a real application, this would call the FastAPI backend.
    """
    # Example: Call backend health endpoint
    # In production, use httpx or aiohttp to call the backend
    #
    # async with httpx.AsyncClient() as client:
    #     response = await client.get("http://localhost:8000/health")
    #     data = response.json()

    # For demonstration, simulate the response
    simulated_response = {
        "status": "healthy",
        "database": "connected",
        "redis": "connected",
    }

    response_text = (
        "🔌 <b>Backend API Response</b>\n\n"
        f"Status: {simulated_response['status']}\n"
        f"Database: {simulated_response['database']}\n"
        f"Redis: {simulated_response['redis']}\n\n"
        "<i>This is a simulated response. "
        "In production, this calls the actual backend.</i>"
    )

    await message.answer(response_text)
