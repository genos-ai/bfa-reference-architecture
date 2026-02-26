#!/usr/bin/env python3
"""
Compliance Checker — deterministic rule violation scanner.

Scans the codebase against the rules defined in config/agents/code/qa/agent.yaml
and outputs a table of violations. Uses ComplianceScannerService — the same
business logic that powers code.qa.agent — without any LLM.

Usage:
    python scripts/compliance_checker.py
    python scripts/compliance_checker.py --verbose
    python scripts/compliance_checker.py --debug
    python scripts/compliance_checker.py --rule no_hardcoded_values
    python scripts/compliance_checker.py --severity error
"""

import sys
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.backend.core.config import find_project_root
from modules.backend.core.logging import get_logger, setup_logging
from modules.backend.services.compliance import ComplianceScannerService, load_config


def format_table(findings: list[dict]) -> str:
    """Format findings as a readable table."""
    if not findings:
        return "No violations found."

    lines = []
    lines.append(f"{'#':>3}  {'Severity':<8}  {'Rule':<25}  {'File:Line':<55}  {'Message'}")
    lines.append("\u2500" * 140)

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

    config = load_config()
    logger.info("Loaded config", extra={"rules": len(config.get("rules", []))})

    project_root = find_project_root()
    scanner = ComplianceScannerService(project_root, config)
    findings = scanner.scan_all()

    for f in findings:
        f["severity"] = scanner.get_rule_severity(f["rule_id"])

    if rule:
        findings = [f for f in findings if f["rule_id"] == rule]

    if severity:
        findings = [f for f in findings if f["severity"] == severity]

    findings.sort(key=lambda f: (0 if f["severity"] == "error" else 1, f["file"], f.get("line") or 0))

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
