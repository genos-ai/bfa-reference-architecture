"""
Shared compliance tool implementations.

Thin async wrappers over ComplianceScannerService methods. Each function
accepts project_root, scope, and config — and delegates to the service.
No PydanticAI dependency.
"""

from pathlib import Path
from typing import Any

from modules.backend.agents.deps.base import FileScope
from modules.backend.services.compliance import ComplianceScannerService


def _get_scanner(project_root: Path, config: dict[str, Any]) -> ComplianceScannerService:
    return ComplianceScannerService(project_root, config)


async def scan_imports(
    project_root: Path, scope: FileScope, config: dict[str, Any],
) -> list[dict]:
    """Scan for import violations (relative imports, direct logging, os.getenv fallbacks)."""
    scope.check_read("modules/")
    return _get_scanner(project_root, config).scan_import_violations()


async def scan_datetime(
    project_root: Path, scope: FileScope, config: dict[str, Any],
) -> list[dict]:
    """Scan for datetime.now() and datetime.utcnow() usage."""
    scope.check_read("modules/")
    return _get_scanner(project_root, config).scan_datetime_violations()


async def scan_hardcoded(
    project_root: Path, scope: FileScope, config: dict[str, Any],
) -> list[dict]:
    """Scan for module-level UPPER_CASE constants with literal values."""
    scope.check_read("modules/")
    return _get_scanner(project_root, config).scan_hardcoded_values()


async def scan_file_sizes(
    project_root: Path, scope: FileScope, config: dict[str, Any],
) -> list[dict]:
    """Scan for Python files exceeding the configured line limit."""
    scope.check_read("modules/")
    return _get_scanner(project_root, config).scan_file_sizes()


async def scan_cli_options(
    project_root: Path, scope: FileScope, config: dict[str, Any],
) -> list[dict]:
    """Scan root-level CLI scripts for positional args and missing --verbose/--debug."""
    scope.check_read("*.py")
    return _get_scanner(project_root, config).scan_cli_options()


async def scan_config_files(
    project_root: Path, scope: FileScope, config: dict[str, Any],
) -> list[dict]:
    """Scan YAML config files for missing option header comments."""
    scope.check_read("config/")
    return _get_scanner(project_root, config).scan_config_files()
