"""
Example FSM States.

Demonstrates FSM state definitions for multi-step conversations.
"""

from aiogram.fsm.state import State, StatesGroup


class FeedbackForm(StatesGroup):
    """
    FSM states for feedback collection form.

    Flow:
    1. waiting_for_category - User selects bug/feature/other
    2. waiting_for_message - User provides feedback text
    """

    waiting_for_category = State()
    waiting_for_message = State()


class SettingsForm(StatesGroup):
    """
    FSM states for user settings configuration.

    Flow:
    1. selecting_setting - User chooses which setting to change
    2. entering_value - User provides new value
    3. confirming - User confirms the change
    """

    selecting_setting = State()
    entering_value = State()
    confirming = State()


class RegistrationForm(StatesGroup):
    """
    FSM states for user registration flow.

    Flow:
    1. entering_name - User provides their name
    2. entering_email - User provides email address
    3. confirming - User confirms registration details
    """

    entering_name = State()
    entering_email = State()
    confirming = State()
