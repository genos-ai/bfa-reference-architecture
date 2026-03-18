"""
Unit tests for Telegram FSM states.

Tests state definitions and state groups.
"""

import pytest
from aiogram.fsm.state import State, StatesGroup


class TestFeedbackForm:
    """Tests for FeedbackForm states."""

    def test_is_states_group(self):
        """Test that FeedbackForm is a StatesGroup."""
        from modules.clients.telegram.states.example import FeedbackForm

        assert issubclass(FeedbackForm, StatesGroup)

    def test_has_required_states(self):
        """Test that FeedbackForm has all required states."""
        from modules.clients.telegram.states.example import FeedbackForm

        assert hasattr(FeedbackForm, "waiting_for_category")
        assert hasattr(FeedbackForm, "waiting_for_message")

    def test_states_are_state_instances(self):
        """Test that states are State instances."""
        from modules.clients.telegram.states.example import FeedbackForm

        assert isinstance(FeedbackForm.waiting_for_category, State)
        assert isinstance(FeedbackForm.waiting_for_message, State)


class TestSettingsForm:
    """Tests for SettingsForm states."""

    def test_is_states_group(self):
        """Test that SettingsForm is a StatesGroup."""
        from modules.clients.telegram.states.example import SettingsForm

        assert issubclass(SettingsForm, StatesGroup)

    def test_has_required_states(self):
        """Test that SettingsForm has all required states."""
        from modules.clients.telegram.states.example import SettingsForm

        assert hasattr(SettingsForm, "selecting_setting")
        assert hasattr(SettingsForm, "entering_value")
        assert hasattr(SettingsForm, "confirming")


class TestRegistrationForm:
    """Tests for RegistrationForm states."""

    def test_is_states_group(self):
        """Test that RegistrationForm is a StatesGroup."""
        from modules.clients.telegram.states.example import RegistrationForm

        assert issubclass(RegistrationForm, StatesGroup)

    def test_has_required_states(self):
        """Test that RegistrationForm has all required states."""
        from modules.clients.telegram.states.example import RegistrationForm

        assert hasattr(RegistrationForm, "entering_name")
        assert hasattr(RegistrationForm, "entering_email")
        assert hasattr(RegistrationForm, "confirming")

    def test_states_have_unique_names(self):
        """Test that all states have unique state names."""
        from modules.clients.telegram.states.example import RegistrationForm

        state_names = [
            RegistrationForm.entering_name.state,
            RegistrationForm.entering_email.state,
            RegistrationForm.confirming.state,
        ]

        assert len(state_names) == len(set(state_names))
