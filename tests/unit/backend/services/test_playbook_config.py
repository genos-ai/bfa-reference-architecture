"""
Tests for PlaybooksSchema configuration.

Pure Pydantic schema tests — no mocks, no infrastructure.
"""

import pytest

from modules.backend.core.config_schema import PlaybooksSchema


class TestPlaybooksSchema:
    def test_defaults(self):
        config = PlaybooksSchema()
        assert config.playbooks_dir == "config/playbooks"
        assert config.max_steps_per_playbook == 20
        assert config.max_context_size_bytes == 1_048_576
        assert config.default_step_timeout_seconds == 600
        assert config.default_budget_usd == 10.00
        assert config.max_budget_usd == 100.00
        assert config.max_concurrent_missions == 10
        assert config.enable_playbook_matching is True

    def test_strict_rejects_unknown_fields(self):
        with pytest.raises(Exception):
            PlaybooksSchema(unknown_field="oops")

    def test_custom_values(self):
        config = PlaybooksSchema(
            playbooks_dir="custom/playbooks",
            max_steps_per_playbook=50,
            max_budget_usd=500.0,
            enable_playbook_matching=False,
        )
        assert config.playbooks_dir == "custom/playbooks"
        assert config.max_steps_per_playbook == 50
        assert config.max_budget_usd == 500.0
        assert config.enable_playbook_matching is False
