"""Check registry for Tier 2 deterministic verification.

Named check functions are registered via @register_check decorator at
import time. The Planning Agent references these names in TaskPlan
tier_2.deterministic_checks. Mission Control's plan validator (rule 6)
rejects unknown names. The verification pipeline looks up and executes
checks by name.

Adding a new check:
  1. Create a function in checks/ submodule
  2. Decorate with @register_check("your_check_name")
  3. It becomes available to TaskPlans immediately
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from modules.backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class CheckResult:
    """Result from a single deterministic check execution."""

    passed: bool
    details: str
    execution_time_ms: float


# Type alias for check function signature
CheckFn = Callable[[dict[str, Any], dict[str, Any]], Awaitable[CheckResult]]

# Module-level registry — populated at import time by @register_check
_REGISTRY: dict[str, CheckFn] = {}


def register_check(name: str) -> Callable[[CheckFn], CheckFn]:
    """Decorator to register a named check function.

    Usage:
        @register_check("validate_json_schema")
        async def validate_json_schema(output: dict, params: dict) -> CheckResult:
            ...

    Args:
        name: Unique check name. Referenced by Planning Agent in TaskPlans.

    Raises:
        ValueError: If name is already registered (duplicate check names
                    are a programming error, not a runtime condition).
    """
    def decorator(fn: CheckFn) -> CheckFn:
        if name in _REGISTRY:
            raise ValueError(
                f"Duplicate check name '{name}'. "
                f"Already registered by {_REGISTRY[name].__module__}.{_REGISTRY[name].__qualname__}"
            )
        _REGISTRY[name] = fn
        logger.debug("Check registered", extra={"check_name": name})
        return fn
    return decorator


def get_check(name: str) -> CheckFn | None:
    """Look up a registered check by name. Returns None if not found."""
    return _REGISTRY.get(name)


def check_exists(name: str) -> bool:
    """Check if a named check function is registered."""
    return name in _REGISTRY


def list_checks() -> list[str]:
    """Return all registered check names (sorted for deterministic output)."""
    return sorted(_REGISTRY.keys())


def get_registry_snapshot() -> dict[str, CheckFn]:
    """Return a shallow copy of the registry. For testing and introspection."""
    return dict(_REGISTRY)
