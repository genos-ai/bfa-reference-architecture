#!/usr/bin/env python3
"""
Compliance Checker — deterministic rule violation scanner.

Scans the codebase against the rules defined in config/agents/code/qa/agent.yaml
and outputs a table of violations. Uses the same scanner functions as the
code.qa.agent but without the LLM — pure detection, no reasoning or fixing.

Usage:
    python scripts/compliance_checker.py
    python scripts/compliance_checker.py --verbose
    python scripts/compliance_checker.py --debug
    python scripts/compliance_checker.py --rule no_hardcoded_values
    python scripts/compliance_checker.py --severity error
"""

import ast
import re
import sys
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger, setup_logging
from modules.backend.agents.vertical.code.qa.agent import (
    _collect_python_files,
    _get_enabled_rule_ids,
    _get_exclusion_paths,
    _get_rule_severity,
    _load_agent_config,
    _scan_file_lines,
)


def scan_all(config: dict, rule_filter: str | None, severity_filter: str | None) -> list[dict]:
    """Run all enabled scanners and return a flat list of violations."""
    project_root = find_project_root()
    exclusions = _get_exclusion_paths(config)
    enabled = _get_enabled_rule_ids(config)
    findings: list[dict] = []

    if rule_filter:
        enabled = {r for r in enabled if r == rule_filter}

    py_files = _collect_python_files(project_root, exclusions)

    if "no_relative_imports" in enabled or "no_direct_logging" in enabled or "no_os_getenv_fallback" in enabled:
        findings.extend(_scan_imports(project_root, py_files, enabled))

    if "no_datetime_now" in enabled:
        findings.extend(_scan_datetime(project_root, py_files))

    if "no_hardcoded_values" in enabled:
        findings.extend(_scan_hardcoded(project_root, py_files))

    if "file_size_limit" in enabled:
        limit = config.get("file_size_limit", 1000)
        findings.extend(_scan_sizes(project_root, py_files, limit))

    if "cli_options_not_positional" in enabled or "cli_verbose_debug" in enabled:
        findings.extend(_scan_cli(project_root, enabled))

    if "yaml_header_comment" in enabled:
        findings.extend(_scan_yaml_headers(project_root))

    for f in findings:
        f["severity"] = _get_rule_severity(config, f["rule_id"])

    if severity_filter:
        findings = [f for f in findings if f["severity"] == severity_filter]

    findings.sort(key=lambda f: (0 if f["severity"] == "error" else 1, f["file"], f.get("line") or 0))
    return findings


def _scan_imports(project_root: Path, py_files: list[str], enabled: set[str]) -> list[dict]:
    findings: list[dict] = []
    for rel_path in py_files:
        lines = _scan_file_lines(project_root, rel_path)
        in_modules = rel_path.startswith("modules/")
        is_core_logging = rel_path == "modules/backend/core/logging.py"

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            if "no_relative_imports" in enabled and re.match(r"^from\s+\.", stripped):
                findings.append({"rule_id": "no_relative_imports", "file": rel_path, "line": i, "message": stripped})

            if "no_direct_logging" in enabled and in_modules and not is_core_logging and stripped == "import logging":
                findings.append({"rule_id": "no_direct_logging", "file": rel_path, "line": i, "message": stripped})

            if "no_os_getenv_fallback" in enabled:
                if re.search(r"os\.(getenv|environ\.get)\s*\(.+,\s*.+\)", stripped):
                    findings.append({"rule_id": "no_os_getenv_fallback", "file": rel_path, "line": i, "message": stripped})

    return findings


def _scan_datetime(project_root: Path, py_files: list[str]) -> list[dict]:
    findings: list[dict] = []
    pattern = re.compile(r"datetime\.(now|utcnow)\s*\(")
    for rel_path in py_files:
        lines = _scan_file_lines(project_root, rel_path)
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                findings.append({"rule_id": "no_datetime_now", "file": rel_path, "line": i, "message": line.strip()})
    return findings


def _scan_hardcoded(project_root: Path, py_files: list[str]) -> list[dict]:
    findings: list[dict] = []
    skip_names = {"__all__", "__version__", "__tablename__", "__abstract__"}

    for rel_path in py_files:
        full_path = project_root / rel_path
        try:
            source = full_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                if name in skip_names or not re.match(r"^[A-Z][A-Z0-9_]+$", name):
                    continue
                if not isinstance(node.value, ast.Constant):
                    continue
                val = node.value.value
                if isinstance(val, (int, float, str)) and not isinstance(val, bool):
                    findings.append({
                        "rule_id": "no_hardcoded_values",
                        "file": rel_path, "line": node.lineno,
                        "message": f"{name} = {val!r}",
                    })

    return findings


def _scan_sizes(project_root: Path, py_files: list[str], limit: int) -> list[dict]:
    findings: list[dict] = []
    for rel_path in py_files:
        lines = _scan_file_lines(project_root, rel_path)
        count = len(lines)
        if count > limit:
            findings.append({
                "rule_id": "file_size_limit",
                "file": rel_path, "line": None,
                "message": f"{count} lines (limit: {limit})",
            })
    return findings


def _scan_cli(project_root: Path, enabled: set[str]) -> list[dict]:
    findings: list[dict] = []
    for full_path in sorted(project_root.glob("*.py")):
        rel_path = str(full_path.relative_to(project_root))
        try:
            source = full_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        if "cli_options_not_positional" in enabled and "add_argument" in source:
            try:
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "add_argument"
                        and node.args
                    ):
                        first_arg = node.args[0]
                        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                            if not first_arg.value.startswith("-"):
                                findings.append({
                                    "rule_id": "cli_options_not_positional",
                                    "file": rel_path, "line": node.lineno,
                                    "message": f"Positional argument: {first_arg.value!r}",
                                })
            except SyntaxError:
                pass

        if "cli_verbose_debug" in enabled:
            has_verbose = "--verbose" in source
            has_debug = "--debug" in source
            if not has_verbose or not has_debug:
                missing = []
                if not has_verbose:
                    missing.append("--verbose")
                if not has_debug:
                    missing.append("--debug")
                findings.append({
                    "rule_id": "cli_verbose_debug",
                    "file": rel_path, "line": None,
                    "message": f"Missing: {', '.join(missing)}",
                })

    return findings


def _scan_yaml_headers(project_root: Path) -> list[dict]:
    findings: list[dict] = []
    yaml_dirs = [
        project_root / "config" / "settings",
        project_root / "config" / "agents",
    ]
    for yaml_dir in yaml_dirs:
        if not yaml_dir.exists():
            continue
        for yaml_path in sorted(yaml_dir.rglob("*.yaml")):
            rel_path = str(yaml_path.relative_to(project_root))
            try:
                head = yaml_path.read_text(encoding="utf-8")[:500]
            except (OSError, UnicodeDecodeError):
                continue
            if "# =====" not in head:
                findings.append({
                    "rule_id": "yaml_header_comment",
                    "file": rel_path, "line": 1,
                    "message": "Missing commented option header",
                })
    return findings


def format_table(findings: list[dict]) -> str:
    """Format findings as a readable table."""
    if not findings:
        return "No violations found."

    lines = []
    lines.append(f"{'#':>3}  {'Severity':<8}  {'Rule':<25}  {'File:Line':<55}  {'Message'}")
    lines.append("─" * 140)

    for i, f in enumerate(findings, 1):
        sev = f["severity"]
        rule = f["rule_id"]
        loc = f"{f['file']}:{f.get('line') or '-'}"
        msg = f["message"][:60]
        lines.append(f"{i:>3}  {sev:<8}  {rule:<25}  {loc:<55}  {msg}")

    return "\n".join(lines)


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output (INFO level logging).")
@click.option("--debug", "-d", is_flag=True, help="Enable debug output (DEBUG level logging).")
@click.option("--rule", default=None, help="Check only this rule ID (e.g., no_hardcoded_values).")
@click.option("--severity", default=None, type=click.Choice(["error", "warning"]), help="Show only this severity.")
def main(verbose: bool, debug: bool, rule: str | None, severity: str | None) -> None:
    """Scan the codebase for compliance violations and output a table."""
    if debug:
        setup_logging(level="DEBUG", format_type="console")
    elif verbose:
        setup_logging(level="INFO", format_type="console")
    else:
        setup_logging(level="WARNING", format_type="console")

    logger = get_logger(__name__)

    config = _load_agent_config()
    logger.info("Loaded config", extra={"rules": len(config.get("rules", []))})

    findings = scan_all(config, rule, severity)

    click.echo()
    click.echo(format_table(findings))
    click.echo()

    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    click.echo(f"Total: {len(findings)} violations ({errors} errors, {warnings} warnings)")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
