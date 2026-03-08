"""Built-in deterministic checks for Tier 2 verification.

These checks are generic and reusable across any agent output. They are
registered in the check registry at import time. The Planning Agent
references them by name in TaskPlan tier_2.deterministic_checks.

Adding domain-specific checks: create a new module in checks/ and
import it from checks/__init__.py.
"""

from __future__ import annotations

import time
from typing import Any

from modules.backend.agents.mission_control.check_registry import (
    CheckResult,
    register_check,
)
from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@register_check("validate_json_schema")
async def validate_json_schema(output: dict[str, Any], params: dict[str, Any]) -> CheckResult:
    """Validate output against a JSON Schema.

    Params:
        schema (dict): JSON Schema to validate against.

    Uses jsonschema for validation. Collects all errors, not just the first.
    """
    start = time.perf_counter()
    try:
        import jsonschema

        schema = params.get("schema")
        if not schema:
            return CheckResult(
                passed=False,
                details="No 'schema' provided in check params",
                execution_time_ms=_elapsed_ms(start),
            )

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(output))

        if errors:
            error_details = "; ".join(
                f"{'.'.join(str(p) for p in e.absolute_path)}: {e.message}"
                if e.absolute_path else e.message
                for e in errors[:10]  # Cap at 10 errors to avoid log bloat
            )
            return CheckResult(
                passed=False,
                details=f"{len(errors)} validation error(s): {error_details}",
                execution_time_ms=_elapsed_ms(start),
            )

        return CheckResult(
            passed=True,
            details="Output conforms to schema",
            execution_time_ms=_elapsed_ms(start),
        )
    except ImportError:
        return CheckResult(
            passed=False,
            details="jsonschema package not installed",
            execution_time_ms=_elapsed_ms(start),
        )


@register_check("validate_field_exists")
async def validate_field_exists(output: dict[str, Any], params: dict[str, Any]) -> CheckResult:
    """Validate that specified fields exist in the output.

    Params:
        fields (list[str]): Field names that must be present as top-level keys.
    """
    start = time.perf_counter()

    fields = params.get("fields", [])
    if not fields:
        return CheckResult(
            passed=False,
            details="No 'fields' provided in check params",
            execution_time_ms=_elapsed_ms(start),
        )

    missing = [f for f in fields if f not in output]

    if missing:
        return CheckResult(
            passed=False,
            details=f"Missing fields: {', '.join(missing)}",
            execution_time_ms=_elapsed_ms(start),
        )

    return CheckResult(
        passed=True,
        details=f"All {len(fields)} required fields present",
        execution_time_ms=_elapsed_ms(start),
    )


@register_check("validate_field_type")
async def validate_field_type(output: dict[str, Any], params: dict[str, Any]) -> CheckResult:
    """Validate that specified fields have the expected types.

    Params:
        field_types (dict[str, str]): Mapping of field name to expected type name.
            Supported type names: "str", "int", "float", "bool", "list", "dict", "null".
    """
    start = time.perf_counter()

    TYPE_MAP: dict[str, type | None] = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "null": type(None),
    }

    field_types = params.get("field_types", {})
    if not field_types:
        return CheckResult(
            passed=False,
            details="No 'field_types' provided in check params",
            execution_time_ms=_elapsed_ms(start),
        )

    type_errors = []
    for field_name, expected_type_name in field_types.items():
        if field_name not in output:
            type_errors.append(f"'{field_name}' not found in output")
            continue

        expected_type = TYPE_MAP.get(expected_type_name)
        if expected_type is None and expected_type_name != "null":
            type_errors.append(f"Unknown type name '{expected_type_name}' for field '{field_name}'")
            continue

        actual_value = output[field_name]
        if expected_type_name == "null":
            if actual_value is not None:
                type_errors.append(
                    f"'{field_name}': expected null, got {type(actual_value).__name__}"
                )
        elif not isinstance(actual_value, expected_type):
            type_errors.append(
                f"'{field_name}': expected {expected_type_name}, got {type(actual_value).__name__}"
            )

    if type_errors:
        return CheckResult(
            passed=False,
            details=f"{len(type_errors)} type error(s): {'; '.join(type_errors)}",
            execution_time_ms=_elapsed_ms(start),
        )

    return CheckResult(
        passed=True,
        details=f"All {len(field_types)} field types valid",
        execution_time_ms=_elapsed_ms(start),
    )


@register_check("validate_field_range")
async def validate_field_range(output: dict[str, Any], params: dict[str, Any]) -> CheckResult:
    """Validate that numeric fields fall within specified ranges.

    Params:
        ranges (dict[str, dict]): Mapping of field name to range spec.
            Each range spec can have: "min" (float), "max" (float), or both.
    """
    start = time.perf_counter()

    ranges = params.get("ranges", {})
    if not ranges:
        return CheckResult(
            passed=False,
            details="No 'ranges' provided in check params",
            execution_time_ms=_elapsed_ms(start),
        )

    range_errors = []
    for field_name, range_spec in ranges.items():
        if field_name not in output:
            range_errors.append(f"'{field_name}' not found in output")
            continue

        value = output[field_name]
        if not isinstance(value, (int, float)):
            range_errors.append(
                f"'{field_name}': expected numeric, got {type(value).__name__}"
            )
            continue

        min_val = range_spec.get("min")
        max_val = range_spec.get("max")

        if min_val is not None and value < min_val:
            range_errors.append(f"'{field_name}': {value} < min {min_val}")
        if max_val is not None and value > max_val:
            range_errors.append(f"'{field_name}': {value} > max {max_val}")

    if range_errors:
        return CheckResult(
            passed=False,
            details=f"{len(range_errors)} range error(s): {'; '.join(range_errors)}",
            execution_time_ms=_elapsed_ms(start),
        )

    return CheckResult(
        passed=True,
        details=f"All {len(ranges)} field ranges valid",
        execution_time_ms=_elapsed_ms(start),
    )


def _elapsed_ms(start: float) -> float:
    """Calculate elapsed time in milliseconds since start."""
    return round((time.perf_counter() - start) * 1000, 3)
