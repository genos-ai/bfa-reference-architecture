"""Tests for built-in Tier 2 deterministic checks.

Tests each check function independently with various valid and invalid
inputs. No external dependencies beyond jsonschema.
"""

import pytest

from modules.backend.agents.mission_control.checks.builtin import (
    validate_field_exists,
    validate_field_range,
    validate_field_type,
    validate_json_schema,
)


class TestValidateJsonSchema:
    """Tests for validate_json_schema check."""

    @pytest.mark.asyncio
    async def test_valid_output(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "score": {"type": "number"}},
            "required": ["name", "score"],
        }
        output = {"name": "test", "score": 0.95}
        result = await validate_json_schema(output, {"schema": schema})
        assert result.passed is True
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_invalid_output(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        output = {"name": 123}  # wrong type
        result = await validate_json_schema(output, {"schema": schema})
        assert result.passed is False
        assert "validation error" in result.details

    @pytest.mark.asyncio
    async def test_missing_required_field(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        output = {}
        result = await validate_json_schema(output, {"schema": schema})
        assert result.passed is False
        assert "name" in result.details

    @pytest.mark.asyncio
    async def test_no_schema_in_params(self):
        result = await validate_json_schema({"a": 1}, {})
        assert result.passed is False
        assert "No 'schema' provided" in result.details


class TestValidateFieldExists:
    """Tests for validate_field_exists check."""

    @pytest.mark.asyncio
    async def test_all_fields_present(self):
        result = await validate_field_exists(
            {"a": 1, "b": 2, "c": 3},
            {"fields": ["a", "b"]},
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_missing_field(self):
        result = await validate_field_exists(
            {"a": 1},
            {"fields": ["a", "b"]},
        )
        assert result.passed is False
        assert "b" in result.details

    @pytest.mark.asyncio
    async def test_no_fields_in_params(self):
        result = await validate_field_exists({"a": 1}, {})
        assert result.passed is False
        assert "No 'fields' provided" in result.details


class TestValidateFieldType:
    """Tests for validate_field_type check."""

    @pytest.mark.asyncio
    async def test_correct_types(self):
        result = await validate_field_type(
            {"name": "test", "count": 5, "active": True},
            {"field_types": {"name": "str", "count": "int", "active": "bool"}},
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_wrong_type(self):
        result = await validate_field_type(
            {"name": 123},
            {"field_types": {"name": "str"}},
        )
        assert result.passed is False
        assert "expected str" in result.details

    @pytest.mark.asyncio
    async def test_null_type(self):
        result = await validate_field_type(
            {"value": None},
            {"field_types": {"value": "null"}},
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_field_not_found(self):
        result = await validate_field_type(
            {},
            {"field_types": {"missing": "str"}},
        )
        assert result.passed is False
        assert "not found" in result.details


class TestValidateFieldRange:
    """Tests for validate_field_range check."""

    @pytest.mark.asyncio
    async def test_within_range(self):
        result = await validate_field_range(
            {"score": 0.85},
            {"ranges": {"score": {"min": 0.0, "max": 1.0}}},
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_below_min(self):
        result = await validate_field_range(
            {"score": -0.5},
            {"ranges": {"score": {"min": 0.0, "max": 1.0}}},
        )
        assert result.passed is False
        assert "< min" in result.details

    @pytest.mark.asyncio
    async def test_above_max(self):
        result = await validate_field_range(
            {"score": 1.5},
            {"ranges": {"score": {"min": 0.0, "max": 1.0}}},
        )
        assert result.passed is False
        assert "> max" in result.details

    @pytest.mark.asyncio
    async def test_non_numeric_field(self):
        result = await validate_field_range(
            {"score": "high"},
            {"ranges": {"score": {"min": 0.0}}},
        )
        assert result.passed is False
        assert "expected numeric" in result.details
