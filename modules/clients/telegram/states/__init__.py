"""
FSM State Definitions.

Finite State Machine states for multi-step conversations.

aiogram v3 FSM:
- States are defined as classes inheriting from StatesGroup
- Each state is a State() instance
- Use FSMContext to get/set state and data
- States persist in storage (Memory/Redis)

Example:
    class MyForm(StatesGroup):
        step_1 = State()
        step_2 = State()

    @router.message(Command("start_form"))
    async def start_form(message: Message, state: FSMContext):
        await state.set_state(MyForm.step_1)

    @router.message(MyForm.step_1)
    async def process_step_1(message: Message, state: FSMContext):
        await state.update_data(field_1=message.text)
        await state.set_state(MyForm.step_2)
"""

from modules.clients.telegram.states.example import FeedbackForm

__all__ = [
    "FeedbackForm",
]
