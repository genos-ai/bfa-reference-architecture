"""Tests for the check registry.

Tests registration, lookup, duplicate detection, and listing.
No external dependencies — pure unit tests.
"""

import pytest

from modules.backend.agents.mission_control.check_registry import (
    CheckResult,
    _REGISTRY,
    check_exists,
    get_check,
    list_checks,
    register_check,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Save and restore registry state around each test."""
    original = dict(_REGISTRY)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(original)


class TestRegisterCheck:
    """Tests for @register_check decorator."""

    def test_registers_function(self):
        @register_check("test_check_alpha")
        async def check_alpha(output, params):
            return CheckResult(passed=True, details="ok", execution_time_ms=0.1)

        assert check_exists("test_check_alpha")
        assert get_check("test_check_alpha") is check_alpha

    def test_duplicate_name_raises(self):
        @register_check("test_check_dup")
        async def check_first(output, params):
            return CheckResult(passed=True, details="", execution_time_ms=0.0)

        with pytest.raises(ValueError, match="Duplicate check name"):
            @register_check("test_check_dup")
            async def check_second(output, params):
                return CheckResult(passed=True, details="", execution_time_ms=0.0)


class TestCheckLookup:
    """Tests for get_check and check_exists."""

    def test_nonexistent_check_returns_none(self):
        assert get_check("nonexistent_check_xyz") is None

    def test_nonexistent_check_exists_false(self):
        assert check_exists("nonexistent_check_xyz") is False

    def test_list_checks_sorted(self):
        @register_check("test_check_zebra")
        async def check_z(output, params):
            return CheckResult(passed=True, details="", execution_time_ms=0.0)

        @register_check("test_check_alpha2")
        async def check_a(output, params):
            return CheckResult(passed=True, details="", execution_time_ms=0.0)

        names = list_checks()
        assert names.index("test_check_alpha2") < names.index("test_check_zebra")
