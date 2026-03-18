"""
Common Handlers.

Universal commands available to all users: /start, /help, /cancel, /status.
"""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, User

from modules.backend.core.logging import get_logger
from modules.clients.telegram.keyboards.common import get_main_menu_keyboard

logger = get_logger(__name__)

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message, telegram_user: User, user_role: str) -> None:
    """
    Handle /start command.

    Sends welcome message with main menu keyboard.
    """
    welcome_text = (
        f"👋 Welcome, <b>{telegram_user.first_name}</b>!\n\n"
        f"I'm your assistant bot. Here's what I can do:\n\n"
        f"• /help - Show available commands\n"
        f"• /status - Check system status\n"
        f"• /cancel - Cancel current operation\n\n"
        f"Your role: <code>{user_role}</code>"
    )

    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(user_role),
    )

    logger.info(
        "User started bot",
        extra={
            "user_id": telegram_user.id,
            "username": telegram_user.username,
            "role": user_role,
        },
    )


@router.message(Command("help"))
async def cmd_help(message: Message, user_role: str) -> None:
    """
    Handle /help command.

    Shows available commands based on user role.
    """
    base_commands = """
<b>📚 Available Commands</b>

<b>General:</b>
/start - Start the bot
/help - Show this help message
/status - Check system status
/cancel - Cancel current operation

<b>Examples:</b>
/echo &lt;text&gt; - Echo back your message
/info - Show bot information
"""

    trader_commands = """
<b>Trader Commands:</b>
/balance - Check account balance
/history - View transaction history
"""

    admin_commands = """
<b>Admin Commands:</b>
/users - List authorized users
/broadcast - Send message to all users
/logs - View recent logs
"""

    help_text = base_commands

    if user_role in ("trader", "admin"):
        help_text += trader_commands

    if user_role == "admin":
        help_text += admin_commands

    await message.answer(help_text)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """
    Handle /cancel command.

    Cancels any ongoing FSM state and returns to main menu.
    """
    current_state = await state.get_state()

    if current_state is None:
        await message.answer("❌ Nothing to cancel.")
        return

    await state.clear()
    await message.answer(
        "✅ Operation cancelled. You're back to the main menu.",
        reply_markup=get_main_menu_keyboard(),
    )

    logger.info(
        "User cancelled operation",
        extra={
            "user_id": message.from_user.id if message.from_user else None,
            "cancelled_state": current_state,
        },
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """
    Handle /status command.

    Pings the backend /health/ready endpoint and reports real status.
    """
    import httpx

    from modules.backend.core.config import get_server_base_url

    try:
        base_url, timeout = get_server_base_url()

        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"X-Frontend-ID": "telegram"},
        ) as client:
            response = await client.get("/health/ready")

        if response.status_code == 200:
            data = response.json()
            checks = data.get("checks", {})
            lines = ["<b>📊 System Status</b>\n", "🟢 <b>Bot:</b> Online"]

            for component, check in checks.items():
                status = check.get("status", "unknown")
                icon = "🟢" if status == "healthy" else "🔴" if status == "unhealthy" else "🟡"
                latency = check.get("latency_ms")
                detail = f" ({latency}ms)" if latency else ""
                lines.append(f"{icon} <b>{component.title()}:</b> {status}{detail}")

            await message.answer("\n".join(lines))

        elif response.status_code == 503:
            data = response.json()
            detail = data.get("detail", {})
            checks = detail.get("checks", {})
            lines = ["<b>📊 System Status</b>\n", "🟢 <b>Bot:</b> Online"]

            for component, check in checks.items():
                status = check.get("status", "unknown")
                icon = "🟢" if status == "healthy" else "🔴" if status == "unhealthy" else "🟡"
                lines.append(f"{icon} <b>{component.title()}:</b> {status}")

            await message.answer("\n".join(lines))
        else:
            await message.answer(f"⚠️ Backend returned status {response.status_code}")

    except httpx.ConnectError:
        await message.answer("🟢 <b>Bot:</b> Online\n🔴 <b>Backend:</b> Unreachable")
    except Exception as e:
        logger.error("Health check failed", extra={"error": str(e)})
        await message.answer(f"🟢 <b>Bot:</b> Online\n🔴 <b>Backend:</b> Error — {e}")


@router.message(F.text == "❌ Cancel")
async def btn_cancel(message: Message, state: FSMContext) -> None:
    """Handle Cancel button press (same as /cancel command)."""
    await cmd_cancel(message, state)
