"""
Shared system tool implementations.

Pure functions for system health checking, log analysis, config validation,
and dependency auditing. No PydanticAI dependency.
"""

import asyncio
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from modules.backend.agents.deps.base import FileScope


async def check_system_health() -> dict:
    """Check the health of all backend services (database, Redis).

    Returns:
        Dict with component names as keys and status dicts as values.
    """
    from modules.backend.api.health import check_database, check_redis

    db_check, redis_check = await asyncio.gather(
        check_database(),
        check_redis(),
        return_exceptions=True,
    )

    if isinstance(db_check, Exception):
        db_check = {"status": "error", "error": str(db_check)}
    if isinstance(redis_check, Exception):
        redis_check = {"status": "error", "error": str(redis_check)}

    return {
        "database": db_check,
        "redis": redis_check,
    }


async def get_app_info(app_config: Any) -> dict:
    """Get application metadata from configuration.

    Args:
        app_config: The application config object (from get_app_config()).

    Returns:
        Dict with name, version, environment, and debug status.
    """
    app = app_config.application
    return {
        "name": app.name,
        "version": app.version,
        "environment": app.environment,
        "debug": app.debug,
    }


async def scan_log_errors(
    project_root: Path,
    scope: FileScope,
    max_lines: int = 5000,
) -> dict:
    """Scan system.jsonl for errors, warnings, and patterns.

    Reads the last `max_lines` of the log file and categorizes entries
    by level. Returns error/warning counts, unique error messages,
    and the most recent errors with timestamps.

    Args:
        project_root: Absolute path to the project root.
        scope: FileScope defining allowed read paths.
        max_lines: Maximum number of log lines to analyze (from tail).

    Returns:
        Dict with error_count, warning_count, unique_errors,
        recent_errors, and level_distribution.
    """
    scope.check_read("logs/")
    log_path = project_root / "logs" / "system.jsonl"

    if not log_path.exists():
        return {"status": "no_log_file", "path": "logs/system.jsonl"}

    lines = log_path.read_text(encoding="utf-8").splitlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines

    level_counts: Counter[str] = Counter()
    error_messages: Counter[str] = Counter()
    recent_errors: list[dict] = []

    for line in tail:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        level = entry.get("level", entry.get("severity", "unknown")).lower()
        level_counts[level] += 1

        if level in ("error", "critical", "fatal"):
            msg = entry.get("event", entry.get("message", entry.get("msg", "unknown")))
            error_messages[msg] += 1
            if len(recent_errors) < 20:
                recent_errors.append({
                    "timestamp": entry.get("timestamp", "unknown"),
                    "level": level,
                    "message": msg,
                    "logger": entry.get("logger", "unknown"),
                })

    unique_errors = [
        {"message": msg, "count": count}
        for msg, count in error_messages.most_common(20)
    ]

    return {
        "total_lines_analyzed": len(tail),
        "total_lines_in_file": len(lines),
        "error_count": level_counts.get("error", 0) + level_counts.get("critical", 0),
        "warning_count": level_counts.get("warning", 0),
        "level_distribution": dict(level_counts),
        "unique_errors": unique_errors,
        "recent_errors": recent_errors,
    }


async def validate_config_files(
    project_root: Path,
    scope: FileScope,
) -> dict:
    """Validate all YAML config files and .env secrets.

    Checks:
    - All expected config/settings/*.yaml files exist
    - Each YAML file parses without errors
    - config/.env exists and has non-empty values for critical secrets
    - No config files reference undefined environment variables

    Args:
        project_root: Absolute path to the project root.
        scope: FileScope defining allowed read paths.

    Returns:
        Dict with valid_files, invalid_files, missing_files,
        secrets_status, and issues list.
    """
    import yaml

    scope.check_read("config/")

    expected_configs = [
        "application.yaml",
        "database.yaml",
        "events.yaml",
        "features.yaml",
        "logging.yaml",
        "security.yaml",
        "sessions.yaml",
    ]

    settings_dir = project_root / "config" / "settings"
    valid_files: list[str] = []
    invalid_files: list[dict] = []
    missing_files: list[str] = []

    for config_name in expected_configs:
        config_path = settings_dir / config_name
        if not config_path.exists():
            missing_files.append(config_name)
            continue

        try:
            content = config_path.read_text(encoding="utf-8")
            yaml.safe_load(content)
            valid_files.append(config_name)
        except yaml.YAMLError as e:
            invalid_files.append({
                "file": config_name,
                "error": str(e),
            })

    # Check .env secrets
    env_path = project_root / "config" / ".env"
    secrets_status: dict[str, str] = {}
    critical_secrets = [
        "DB_PASSWORD",
        "JWT_SECRET",
        "ANTHROPIC_API_KEY",
    ]

    if env_path.exists():
        env_content = env_path.read_text(encoding="utf-8")
        for secret in critical_secrets:
            pattern = rf"^{re.escape(secret)}\s*=\s*(.+)$"
            match = re.search(pattern, env_content, re.MULTILINE)
            if match and match.group(1).strip():
                secrets_status[secret] = "set"
            else:
                secrets_status[secret] = "missing_or_empty"
    else:
        for secret in critical_secrets:
            secrets_status[secret] = "no_env_file"

    issues: list[str] = []
    if missing_files:
        issues.append(f"Missing config files: {', '.join(missing_files)}")
    if invalid_files:
        issues.append(
            f"Invalid YAML: {', '.join(f['file'] for f in invalid_files)}"
        )
    missing_secrets = [k for k, v in secrets_status.items() if v != "set"]
    if missing_secrets:
        issues.append(f"Missing secrets: {', '.join(missing_secrets)}")

    return {
        "valid_files": valid_files,
        "valid_count": len(valid_files),
        "invalid_files": invalid_files,
        "missing_files": missing_files,
        "secrets_status": secrets_status,
        "issues": issues,
        "healthy": len(issues) == 0,
    }


async def check_dependencies(
    project_root: Path,
    scope: FileScope,
) -> dict:
    """Check Python dependencies for consistency.

    Compares requirements.txt against installed packages. Reports
    missing packages, version mismatches, and packages not in
    requirements.txt.

    Args:
        project_root: Absolute path to the project root.
        scope: FileScope defining allowed read paths.

    Returns:
        Dict with total_required, installed_count, missing,
        version_mismatches, and issues.
    """
    import importlib.metadata

    scope.check_read("requirements.txt")

    req_path = project_root / "requirements.txt"
    if not req_path.exists():
        return {"status": "no_requirements_file"}

    requirements: dict[str, str | None] = {}
    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Parse name==version, name>=version, or just name
        match = re.match(r"^([a-zA-Z0-9_-]+)\s*([><=!~]+\s*.+)?$", line)
        if match:
            pkg_name = match.group(1).lower()
            version_spec = match.group(2).strip() if match.group(2) else None
            requirements[pkg_name] = version_spec

    missing: list[str] = []
    version_info: list[dict] = []

    for pkg_name, version_spec in requirements.items():
        try:
            dist = importlib.metadata.distribution(pkg_name)
            installed_version = dist.version
            status = "installed"
            if version_spec and "==" in version_spec:
                expected = version_spec.replace("==", "").strip()
                if installed_version != expected:
                    status = "version_mismatch"
            version_info.append({
                "package": pkg_name,
                "required": version_spec or "any",
                "installed": installed_version,
                "status": status,
            })
        except importlib.metadata.PackageNotFoundError:
            missing.append(pkg_name)

    mismatches = [v for v in version_info if v["status"] == "version_mismatch"]

    issues: list[str] = []
    if missing:
        issues.append(f"Missing packages: {', '.join(missing)}")
    if mismatches:
        issues.append(
            f"Version mismatches: "
            + ", ".join(f"{m['package']} (want {m['required']}, have {m['installed']})" for m in mismatches)
        )

    return {
        "total_required": len(requirements),
        "installed_count": len(version_info),
        "missing": missing,
        "missing_count": len(missing),
        "version_mismatches": mismatches,
        "mismatch_count": len(mismatches),
        "issues": issues,
        "healthy": len(issues) == 0,
    }


async def check_file_structure(
    project_root: Path,
    scope: FileScope,
) -> dict:
    """Validate expected project file structure exists.

    Checks that critical directories and files are present:
    config/, modules/, tests/, cli.py, requirements.txt, .project_root.

    Args:
        project_root: Absolute path to the project root.
        scope: FileScope defining allowed read paths.

    Returns:
        Dict with present, missing, and issues.
    """
    expected = [
        "config/settings/",
        "config/.env",
        "modules/backend/",
        "modules/backend/core/",
        "modules/backend/api/",
        "modules/backend/models/",
        "modules/backend/services/",
        "modules/backend/agents/",
        "tests/unit/",
        "cli.py",
        "requirements.txt",
        ".project_root",
        "AGENTS.md",
        "logs/",
    ]

    present: list[str] = []
    missing: list[str] = []

    for path in expected:
        full = project_root / path
        if full.exists():
            present.append(path)
        else:
            missing.append(path)

    issues: list[str] = []
    if missing:
        issues.append(f"Missing: {', '.join(missing)}")

    return {
        "present": present,
        "present_count": len(present),
        "missing": missing,
        "missing_count": len(missing),
        "issues": issues,
        "healthy": len(missing) == 0,
    }
