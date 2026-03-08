"""Built-in deterministic checks for Tier 2 verification.

Import this package to register all built-in checks in the check registry.
Domain-specific checks are added in separate submodules.
"""

from modules.backend.agents.mission_control.checks import builtin  # noqa: F401
